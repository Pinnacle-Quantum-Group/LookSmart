"""Echo Mode SQLite store (README §5.22).

Implements the exact schema documented in §5.22:

  - ``recommender_observations`` (id, timestamp, platform, observation_type,
    content_hash BLOB, topic_tags JSON, raw_content nullable, source)
  - ``correlations`` (id, query_id, rec_id, time_delta, topic_overlap,
    baseline_p, fdr_adjusted_p, notes) with FKs to ``injections(id)`` (§5.17)
    and ``recommender_observations(id)``
  - indexes idx_rec_platform, idx_corr_delta, idx_corr_sig

Hash discipline (§5.6): recommendation content is stored as an HMAC of the
content (``content_hash`` BLOB), never as a deconfusion-friendly plaintext key.
The HMAC is supplied as a *callable* so the caller can reuse the same
salt-with-HMAC construction the audit/CooKoo stores use (so the user can join
stores without any one becoming an oracle).

Hard constraints enforced here (§5.22):
  - all data is local SQLite, no network code anywhere in this module
  - user-controlled retention (default 90 days) with an explicit ``purge``
  - ``raw_content`` is nullable and purged on its own (possibly shorter) window
  - export to CSV/JSON for the user's own audit
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import sqlite3
import time
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

# A hash callable maps recommendation content bytes/str -> digest bytes.
HashFn = Callable[[bytes], bytes]

_SCHEMA = """
-- §5.17 store; Echo Mode foreign-keys query_id into this table. We create a
-- minimal compatible definition if the CooKoo store has not been attached, so
-- the FK target exists and roundtrips stand alone in tests.
CREATE TABLE IF NOT EXISTS injections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       INTEGER NOT NULL,
    real_query_hash BLOB    NOT NULL,
    injection_type  TEXT    NOT NULL,
    injection_category TEXT,
    injection_text  TEXT    NOT NULL,
    position        TEXT    NOT NULL,
    provider        TEXT,
    response_hash   BLOB,
    user_override   INTEGER DEFAULT 0,
    retired_at      INTEGER
);

CREATE TABLE IF NOT EXISTS recommender_observations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        INTEGER NOT NULL,
    platform         TEXT    NOT NULL,
    observation_type TEXT    NOT NULL,
    content_hash     BLOB    NOT NULL,
    topic_tags       TEXT,
    raw_content      TEXT,
    source           TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS correlations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id        INTEGER NOT NULL,
    rec_id          INTEGER NOT NULL,
    time_delta      INTEGER NOT NULL,
    topic_overlap   REAL    NOT NULL,
    baseline_p      REAL    NOT NULL,
    fdr_adjusted_p  REAL    NOT NULL,
    notes           TEXT,
    FOREIGN KEY (query_id) REFERENCES injections(id),
    FOREIGN KEY (rec_id)   REFERENCES recommender_observations(id)
);

CREATE INDEX IF NOT EXISTS idx_rec_platform ON recommender_observations(platform, timestamp);
CREATE INDEX IF NOT EXISTS idx_corr_delta   ON correlations(time_delta, topic_overlap);
CREATE INDEX IF NOT EXISTS idx_corr_sig     ON correlations(fdr_adjusted_p);
"""

_REC_COLS = (
    "id",
    "timestamp",
    "platform",
    "observation_type",
    "content_hash",
    "topic_tags",
    "raw_content",
    "source",
)
_CORR_COLS = (
    "id",
    "query_id",
    "rec_id",
    "time_delta",
    "topic_overlap",
    "baseline_p",
    "fdr_adjusted_p",
    "notes",
)


def default_hash_fn(salt: bytes) -> HashFn:
    """Build the §5.6/§5.17-style HMAC-SHA256 content-hash callable from a salt."""

    def _h(content: bytes) -> bytes:
        return hmac.new(salt, content, hashlib.sha256).digest()

    return _h


def _to_bytes(content: str | bytes) -> bytes:
    return content if isinstance(content, bytes) else content.encode("utf-8")


class EchoStore:
    """SQLite-backed store for Echo Mode observations and correlations."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        hash_fn: HashFn,
        retention_days: int = 90,
        raw_retention_days: int | None = None,
    ):
        """Open/create the store.

        Args:
            db_path: SQLite path (``:memory:`` supported for tests).
            hash_fn: callable hashing recommendation-content bytes -> digest.
                Pass ``default_hash_fn(salt)`` to reuse the shared HMAC salt.
            retention_days: user-controlled retention for rows. 0 keeps nothing
                older than "now"; negative means retain forever.
            raw_retention_days: optional shorter window after which only the
                ``raw_content`` column is nulled out (the row/hash survives).
                Defaults to ``retention_days``.
        """
        self.hash_fn = hash_fn
        self.retention_days = retention_days
        self.raw_retention_days = (
            raw_retention_days if raw_retention_days is not None else retention_days
        )
        if str(db_path) == ":memory:":
            self.conn = sqlite3.connect(":memory:")
        else:
            p = Path(db_path).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(p))
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # -- observations --------------------------------------------------------
    def hash_content(self, content: str | bytes) -> bytes:
        return self.hash_fn(_to_bytes(content))

    def add_observation(
        self,
        *,
        timestamp: int,
        platform: str,
        observation_type: str,
        content: str | bytes,
        topic_tags: Sequence[str] | None = None,
        raw_content: str | None = None,
        source: str = "manual_import",
        content_hash: bytes | None = None,
    ) -> int:
        """Insert one recommender observation, returning its rowid.

        ``content`` is hashed via the configured HMAC; pass ``content_hash``
        directly to override (e.g. when re-importing already-hashed rows).
        """
        ch = content_hash if content_hash is not None else self.hash_content(content)
        tags_json = json.dumps(list(topic_tags)) if topic_tags is not None else None
        cur = self.conn.execute(
            "INSERT INTO recommender_observations"
            "(timestamp, platform, observation_type, content_hash, topic_tags,"
            " raw_content, source) VALUES (?,?,?,?,?,?,?)",
            (timestamp, platform, observation_type, ch, tags_json, raw_content, source),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_observations(self, rows: Iterable[dict[str, Any]]) -> list[int]:
        """Bulk-insert observation dicts (as produced by importers)."""
        return [
            self.add_observation(
                timestamp=int(r["timestamp"]),
                platform=r["platform"],
                observation_type=r["observation_type"],
                content=r.get("content", r.get("raw_content", "")),
                topic_tags=r.get("topic_tags"),
                raw_content=r.get("raw_content"),
                source=r.get("source", "manual_import"),
                content_hash=r.get("content_hash"),
            )
            for r in rows
        ]

    def set_observation_tags(self, rec_id: int, topic_tags: Sequence[str]) -> None:
        self.conn.execute(
            "UPDATE recommender_observations SET topic_tags = ? WHERE id = ?",
            (json.dumps(list(topic_tags)), rec_id),
        )
        self.conn.commit()

    def observations(
        self,
        *,
        platform: str | None = None,
        since: int | None = None,
        until: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT %s FROM recommender_observations" % ", ".join(_REC_COLS)
        clauses, args = [], []
        if platform is not None:
            clauses.append("platform = ?")
            args.append(platform)
        if since is not None:
            clauses.append("timestamp >= ?")
            args.append(since)
        if until is not None:
            clauses.append("timestamp <= ?")
            args.append(until)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp"
        rows = self.conn.execute(sql, args).fetchall()
        return [self._rec_row(r) for r in rows]

    @staticmethod
    def _rec_row(row: Sequence[Any]) -> dict[str, Any]:
        d = dict(zip(_REC_COLS, row))
        d["topic_tags"] = json.loads(d["topic_tags"]) if d["topic_tags"] else []
        return d

    # -- injections (query log; FK target) -----------------------------------
    def add_injection(
        self,
        *,
        timestamp: int,
        real_query_hash: bytes,
        injection_type: str = "passthrough",
        injection_category: str | None = None,
        injection_text: str = "",
        position: str = "none",
        provider: str | None = None,
        user_override: int = 0,
    ) -> int:
        """Insert an injections row (the query-log side of a correlation).

        Echo Mode reads this table (populated by the §5.17 CooKoo store) but we
        provide an inserter so the engine + tests can populate a query log when
        the CooKoo store is not co-resident. ``injection_type == 'passthrough'``
        denotes a query that carried no CooKoo injection variant.
        """
        cur = self.conn.execute(
            "INSERT INTO injections(timestamp, real_query_hash, injection_type,"
            " injection_category, injection_text, position, provider, user_override)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                timestamp,
                real_query_hash,
                injection_type,
                injection_category,
                injection_text,
                position,
                provider,
                user_override,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def queries(self) -> list[dict[str, Any]]:
        """Return the query log (injections rows) for correlation."""
        rows = self.conn.execute(
            "SELECT id, timestamp, injection_type, injection_category,"
            " topic_tags_for(id) FROM injections ORDER BY timestamp"
            if False
            else "SELECT id, timestamp, injection_type, injection_category,"
            " injection_text FROM injections ORDER BY timestamp"
        ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r[0],
                    "timestamp": r[1],
                    "injection_type": r[2],
                    "injection_category": r[3],
                    "injection_text": r[4],
                    # topic tags for queries are tracked on a side table:
                    "topic_tags": self._query_tags(r[0]),
                    # a query "has injection" if it is not passthrough/none:
                    "has_injection": r[2] not in (None, "passthrough", "none"),
                }
            )
        return out

    # Query topic tags are not part of the frozen §5.22 schema (which only
    # tags observations); we keep them in a lightweight side table so the
    # correlation engine can match query topics to observation topics.
    def _ensure_query_tags(self) -> None:
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS query_topic_tags ("
            " query_id INTEGER PRIMARY KEY, topic_tags TEXT,"
            " FOREIGN KEY (query_id) REFERENCES injections(id))"
        )

    def set_query_tags(self, query_id: int, topic_tags: Sequence[str]) -> None:
        self._ensure_query_tags()
        self.conn.execute(
            "INSERT OR REPLACE INTO query_topic_tags(query_id, topic_tags)"
            " VALUES (?, ?)",
            (query_id, json.dumps(list(topic_tags))),
        )
        self.conn.commit()

    def _query_tags(self, query_id: int) -> list[str]:
        self._ensure_query_tags()
        row = self.conn.execute(
            "SELECT topic_tags FROM query_topic_tags WHERE query_id = ?",
            (query_id,),
        ).fetchone()
        return json.loads(row[0]) if row and row[0] else []

    # -- correlations --------------------------------------------------------
    def add_correlation(
        self,
        *,
        query_id: int,
        rec_id: int,
        time_delta: int,
        topic_overlap: float,
        baseline_p: float,
        fdr_adjusted_p: float,
        notes: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO correlations(query_id, rec_id, time_delta, topic_overlap,"
            " baseline_p, fdr_adjusted_p, notes) VALUES (?,?,?,?,?,?,?)",
            (
                query_id,
                rec_id,
                time_delta,
                topic_overlap,
                baseline_p,
                fdr_adjusted_p,
                notes,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def clear_correlations(self) -> None:
        self.conn.execute("DELETE FROM correlations")
        self.conn.commit()

    def correlations(
        self, *, max_fdr_p: float | None = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT %s FROM correlations" % ", ".join(_CORR_COLS)
        args: list[Any] = []
        if max_fdr_p is not None:
            sql += " WHERE fdr_adjusted_p <= ?"
            args.append(max_fdr_p)
        sql += " ORDER BY fdr_adjusted_p, time_delta"
        rows = self.conn.execute(sql, args).fetchall()
        return [dict(zip(_CORR_COLS, r)) for r in rows]

    # -- retention -----------------------------------------------------------
    def purge(self, now: int | None = None) -> dict[str, int]:
        """Apply user-controlled retention (§5.22).

        Drops observations and correlations older than ``retention_days``; for
        rows that survive but are older than ``raw_retention_days``, nulls out
        ``raw_content`` so the (potentially sensitive) plaintext does not
        linger past its shorter window. ``retention_days`` < 0 retains forever.

        Returns a dict of how many rows/values were affected.
        """
        now = now if now is not None else int(time.time())
        result = {"observations_deleted": 0, "correlations_deleted": 0, "raw_nulled": 0}
        if self.retention_days >= 0:
            cutoff = now - self.retention_days * 86_400
            old_ids = [
                r[0]
                for r in self.conn.execute(
                    "SELECT id FROM recommender_observations WHERE timestamp < ?",
                    (cutoff,),
                ).fetchall()
            ]
            if old_ids:
                qmarks = ",".join("?" * len(old_ids))
                c2 = self.conn.execute(
                    f"DELETE FROM correlations WHERE rec_id IN ({qmarks})", old_ids
                )
                result["correlations_deleted"] += c2.rowcount
            c1 = self.conn.execute(
                "DELETE FROM recommender_observations WHERE timestamp < ?", (cutoff,)
            )
            result["observations_deleted"] = c1.rowcount
        if self.raw_retention_days >= 0:
            raw_cutoff = now - self.raw_retention_days * 86_400
            cr = self.conn.execute(
                "UPDATE recommender_observations SET raw_content = NULL"
                " WHERE raw_content IS NOT NULL AND timestamp < ?",
                (raw_cutoff,),
            )
            result["raw_nulled"] = cr.rowcount
        self.conn.commit()
        return result

    # -- export --------------------------------------------------------------
    def export_json(self, path: str | Path | None = None) -> str:
        """Export observations + correlations as JSON (content_hash hex-encoded).

        Returns the JSON string; also writes to ``path`` when supplied.
        """
        obs = []
        for o in self.observations():
            o = dict(o)
            o["content_hash"] = o["content_hash"].hex()
            obs.append(o)
        payload = {"recommender_observations": obs, "correlations": self.correlations()}
        text = json.dumps(payload, indent=2, sort_keys=True)
        if path is not None:
            Path(path).expanduser().write_text(text)
        return text

    def export_csv(self, table: str, path: str | Path | None = None) -> str:
        """Export one table (``recommender_observations`` or ``correlations``)."""
        if table == "recommender_observations":
            cols, rows = list(_REC_COLS), self.observations()
            for r in rows:
                r["content_hash"] = r["content_hash"].hex()
                r["topic_tags"] = json.dumps(r["topic_tags"])
        elif table == "correlations":
            cols, rows = list(_CORR_COLS), self.correlations()
        else:
            raise ValueError(f"unknown table {table!r}")
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})
        text = buf.getvalue()
        if path is not None:
            Path(path).expanduser().write_text(text)
        return text

    def close(self) -> None:
        self.conn.close()
