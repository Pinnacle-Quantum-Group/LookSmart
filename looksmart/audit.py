"""Audit subsystem (README §5.6).

Threat: a complete local log of "real query A, decoys B/C/D" is a perfect
deconfusion oracle if leaked or subpoenaed. Design response:

  - decoys logged in plaintext (user must audit what was sent on their behalf)
  - real queries logged as salted HMAC only (never plaintext)
  - salt held by the user (keychain / file / env); panic-delete supported (§9)
  - verification mode re-hashes a candidate real query to find its decoy cluster
  - retention defaults to 30 days; configurable to 0
  - never synced to the cloud

The HMAC construction is shared with the CooKoo store (§5.17) so the two
stores can be joined by the user without either becoming an oracle alone.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import unicodedata
from pathlib import Path

from .config import AuditConfig
from .models import Query, QueryKind

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decoys (
    id           TEXT PRIMARY KEY,
    timestamp_ms INTEGER NOT NULL,
    persona_id   TEXT,
    mode         TEXT,
    text         TEXT NOT NULL,           -- plaintext: user audits decoys
    cluster_hash BLOB,                     -- HMAC of the real query it covers
    provider     TEXT
);
CREATE TABLE IF NOT EXISTS real_queries (
    id           TEXT PRIMARY KEY,
    timestamp_ms INTEGER NOT NULL,
    query_hash   BLOB NOT NULL,            -- HMAC only; never plaintext
    provider     TEXT
);
CREATE INDEX IF NOT EXISTS idx_decoy_cluster ON decoys(cluster_hash);
CREATE INDEX IF NOT EXISTS idx_decoy_ts ON decoys(timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_real_hash ON real_queries(query_hash);
CREATE INDEX IF NOT EXISTS idx_real_ts ON real_queries(timestamp_ms);
"""


def normalize_query(text: str) -> bytes:
    """Canonicalize so equivalent queries hash identically (NFC + casefold + ws)."""
    norm = unicodedata.normalize("NFC", text).casefold()
    return " ".join(norm.split()).encode("utf-8")


class SaltProvider:
    """Holds the per-user HMAC salt. Supports panic-delete (§9 open problem)."""

    def __init__(self, cfg: AuditConfig):
        self.cfg = cfg
        self._salt: bytes | None = None

    def _file_path(self) -> Path:
        return Path(self.cfg.db_path).expanduser().parent / "salt.bin"

    def get(self) -> bytes:
        if self._salt is not None:
            return self._salt
        if self.cfg.salt_source == "env":
            env = os.environ.get("LOOKSMART_SALT")
            if not env:
                raise RuntimeError("LOOKSMART_SALT not set")
            self._salt = bytes.fromhex(env)
        else:
            # 'keychain' falls back to file storage when no OS keychain is wired;
            # both keep the salt off the cloud, which is the operative property.
            p = self._file_path()
            if p.exists():
                self._salt = p.read_bytes()
            else:
                self._salt = secrets.token_bytes(32)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(self._salt)
                os.chmod(p, 0o600)
        return self._salt

    def panic_delete(self) -> None:
        """Destroy the salt, permanently severing real-query hashes from queries."""
        self._salt = None
        if self.cfg.salt_source != "env":
            p = self._file_path()
            if p.exists():
                # overwrite before unlink
                p.write_bytes(secrets.token_bytes(len(p.read_bytes()) or 32))
                p.unlink()


class AuditStore:
    def __init__(self, cfg: AuditConfig, salt_provider: SaltProvider | None = None):
        self.cfg = cfg
        self.salt = salt_provider or SaltProvider(cfg)
        db = Path(cfg.db_path).expanduser()
        db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db))
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def hash_query(self, text: str) -> bytes:
        return hmac.new(self.salt.get(), normalize_query(text), hashlib.sha256).digest()

    def log_real(self, query: Query) -> None:
        # never store plaintext for real queries; use original_text if CooKoo-wrapped
        source = query.original_text or query.text
        self.conn.execute(
            "INSERT OR REPLACE INTO real_queries(id, timestamp_ms, query_hash, provider)"
            " VALUES (?,?,?,?)",
            (query.id, query.timestamp_ms, self.hash_query(source),
             query.metadata.get("provider")),
        )
        self.conn.commit()

    def log_decoy(self, query: Query, covers_real: str | None = None) -> None:
        cluster = self.hash_query(covers_real) if covers_real else None
        self.conn.execute(
            "INSERT OR REPLACE INTO decoys"
            "(id, timestamp_ms, persona_id, mode, text, cluster_hash, provider)"
            " VALUES (?,?,?,?,?,?,?)",
            (query.id, query.timestamp_ms, query.persona_id,
             query.mode.value if query.mode else None, query.text, cluster,
             query.metadata.get("provider")),
        )
        self.conn.commit()

    def log(self, query: Query, covers_real: str | None = None) -> None:
        if query.kind == QueryKind.REAL:
            self.log_real(query)
        else:
            self.log_decoy(query, covers_real=covers_real)

    def verify(self, candidate_real_query: str) -> list[dict]:
        """Verification mode (§5.6): which decoys were injected to cover this query?"""
        h = self.hash_query(candidate_real_query)
        cur = self.conn.execute(
            "SELECT id, timestamp_ms, persona_id, mode, text, provider"
            " FROM decoys WHERE cluster_hash = ? ORDER BY timestamp_ms",
            (h,),
        )
        cols = ["id", "timestamp_ms", "persona_id", "mode", "text", "provider"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def enforce_retention(self, now_ms: int | None = None) -> int:
        if self.cfg.retention_days <= 0 and self.cfg.retention_days != 0:
            return 0
        now_ms = now_ms or int(time.time() * 1000)
        cutoff = now_ms - self.cfg.retention_days * 86_400_000
        c1 = self.conn.execute("DELETE FROM decoys WHERE timestamp_ms < ?", (cutoff,))
        c2 = self.conn.execute(
            "DELETE FROM real_queries WHERE timestamp_ms < ?", (cutoff,)
        )
        self.conn.commit()
        return c1.rowcount + c2.rowcount

    def close(self) -> None:
        self.conn.close()
