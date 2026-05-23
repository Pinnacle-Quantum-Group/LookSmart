"""SQLite tracking store for CooKoo injections (README §5.17).

Schema matches the §5.17 proposal exactly: an `injections` table keyed on a
salted-HMAC `real_query_hash` plus the three named indexes. The HMAC
construction is shared with the §5.6 audit subsystem (same salt, same
`normalize_query`), so the user can join CooKoo records against the audit log
without either store becoming a deconfusion oracle on its own. Salt rotation
rotates both stores together.

The store does not own the salt: it takes a hash callable (typically
`AuditStore.hash_query`) so that audit and cookoo hash identically.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

from ..audit import normalize_query  # noqa: F401  (shared canonicalization)
from ..config import CooKooConfig
from ..models import AppliedInjection, ProviderResponse, Query

_SCHEMA = """
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
CREATE INDEX IF NOT EXISTS idx_inj_query     ON injections(real_query_hash);
CREATE INDEX IF NOT EXISTS idx_inj_type      ON injections(injection_type, injection_category);
CREATE INDEX IF NOT EXISTS idx_inj_timestamp ON injections(timestamp);
CREATE INDEX IF NOT EXISTS idx_inj_provider  ON injections(provider, timestamp);
"""

_COLS = [
    "id",
    "timestamp",
    "real_query_hash",
    "injection_type",
    "injection_category",
    "injection_text",
    "position",
    "provider",
    "response_hash",
    "user_override",
    "retired_at",
]


class CooKooStore:
    """SQLite-backed injection log with retire/aging and an audit-join helper."""

    def __init__(
        self,
        db_path: str,
        hash_query: Callable[[str], bytes],
        cfg: CooKooConfig | None = None,
    ):
        """
        Args:
            db_path: SQLite path (":memory:" supported for tests).
            hash_query: the shared salted-HMAC callable. Pass
                `AuditStore.hash_query` so cookoo and audit hash identically.
            cfg: optional CooKooConfig; supplies default aging window.
        """
        self._hash_query = hash_query
        self.cfg = cfg or CooKooConfig()
        if db_path != ":memory:":
            p = Path(db_path).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            db_path = str(p)
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # --- write path ---------------------------------------------------------
    def record(
        self,
        query: Query,
        provider: str | None = None,
        response: ProviderResponse | str | None = None,
        now_ms: int | None = None,
    ) -> int:
        """Record one CooKoo-modified real query. Returns the row id.

        `query.original_text` (the verbatim user prose) is what gets hashed, so
        the row joins to the audit log's real-query hash. `query.injection`
        carries the applied wrapper metadata.
        """
        if query.injection is None:
            raise ValueError("record() requires query.injection to be set")
        inj: AppliedInjection = query.injection
        source = query.original_text if query.original_text is not None else query.text
        ts = now_ms if now_ms is not None else query.timestamp_ms

        response_hash = None
        if response is not None:
            text = response.text if isinstance(response, ProviderResponse) else response
            response_hash = self._hash_query(text)

        cur = self.conn.execute(
            "INSERT INTO injections"
            "(timestamp, real_query_hash, injection_type, injection_category,"
            " injection_text, position, provider, response_hash, user_override,"
            " retired_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                ts,
                self._hash_query(source),
                inj.injection_type.value,
                inj.category,
                inj.text,
                inj.position.value,
                provider,
                response_hash,
                1 if inj.user_override else 0,
                None,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def attach_response(
        self, row_id: int, response: ProviderResponse | str
    ) -> None:
        """Late-bind a response hash (probe workflow: send, then diff)."""
        text = response.text if isinstance(response, ProviderResponse) else response
        self.conn.execute(
            "UPDATE injections SET response_hash = ? WHERE id = ?",
            (self._hash_query(text), row_id),
        )
        self.conn.commit()

    # --- aging / retention --------------------------------------------------
    def retire_aged(self, now_ms: int | None = None) -> int:
        """Mark rows older than the aging window as retired (sets retired_at).

        Mirrors the cuckoo filter's sliding-window deletion: the SQLite record
        persists (for audit/measurement) but is flagged retired. Returns the
        number of rows newly retired.
        """
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        cutoff = now - self.cfg.aging_window_days * 86_400_000
        cur = self.conn.execute(
            "UPDATE injections SET retired_at = ? "
            "WHERE timestamp < ? AND retired_at IS NULL",
            (now, cutoff),
        )
        self.conn.commit()
        return cur.rowcount

    # --- read / join --------------------------------------------------------
    def for_real_query(
        self, real_query: str, include_retired: bool = True
    ) -> list[dict]:
        """Join helper keyed on real_query_hash.

        Re-hashes the candidate verbatim query with the shared HMAC and returns
        every injection row recorded for it — the cookoo side of the audit join.
        """
        h = self._hash_query(real_query)
        sql = "SELECT * FROM injections WHERE real_query_hash = ?"
        params: tuple = (h,)
        if not include_retired:
            sql += " AND retired_at IS NULL"
        sql += " ORDER BY timestamp"
        cur = self.conn.execute(sql, params)
        return [dict(zip(_COLS, row)) for row in cur.fetchall()]

    def all_rows(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM injections ORDER BY id")
        return [dict(zip(_COLS, row)) for row in cur.fetchall()]

    def close(self) -> None:
        self.conn.close()
