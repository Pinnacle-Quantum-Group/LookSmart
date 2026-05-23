"""Cuckoo filter data structure for CooKoo injection dedup/rotation (README §5.17).

A cuckoo filter is a probabilistic set-membership structure that, unlike a Bloom
filter, supports *deletion*. Deletion is load-bearing here: it enables a clean
sliding-window rotation (aging-out) of recently-used injections so the injection
stream stays non-stationary and develops no classifier signature (§5.17).

Design (Fan et al., "Cuckoo Filter: Practically Better Than Bloom", CoNEXT 2014):
  - Each item gets a short fingerprint (`fingerprint_bits` wide, never zero).
  - Two candidate buckets:  i1 = hash(item) % num_buckets
                            i2 = i1 XOR (hash(fingerprint) % num_buckets)
    The XOR-with-hash(fingerprint) construction makes i1 and i2 derivable from
    each other given only the fingerprint, which is what enables eviction
    (cuckoo "kicking") without storing the original item.
  - Each bucket holds up to `bucket_size` fingerprints.
  - On a full insert, evict a random resident fingerprint and relocate it to its
    alternate bucket, repeating up to `max_kicks` times.

Aging: each stored fingerprint carries an insertion timestamp. `age()` deletes
every entry older than `aging_window_days`, implementing the §5.17 sliding
window. The SQLite record persists with `retired_at`; only the in-filter entry
is dropped.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass

from ..config import CooKooConfig


def _stable_hash(data: bytes) -> int:
    """Deterministic 64-bit hash (blake2b). Not security-sensitive on its own."""
    return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")


@dataclass
class _Entry:
    fingerprint: int
    inserted_ms: int


class CuckooFilter:
    """Fingerprint cuckoo filter with deletion and time-based aging."""

    def __init__(
        self,
        capacity: int = 10_000,
        fingerprint_bits: int = 12,
        bucket_size: int = 4,
        max_kicks: int = 500,
        aging_window_days: int = 30,
        seed: int | None = None,
    ):
        if fingerprint_bits < 1 or fingerprint_bits > 32:
            raise ValueError("fingerprint_bits must be in [1, 32]")
        if bucket_size < 1:
            raise ValueError("bucket_size must be >= 1")
        self.fingerprint_bits = fingerprint_bits
        self.bucket_size = bucket_size
        self.max_kicks = max_kicks
        self.aging_window_days = aging_window_days
        self._fp_mask = (1 << fingerprint_bits) - 1

        # Round bucket count up to a power of two so the XOR alternate-bucket
        # trick stays in range without a modulo that breaks the involution.
        wanted = max(1, capacity // bucket_size)
        num_buckets = 1
        while num_buckets < wanted:
            num_buckets <<= 1
        self.num_buckets = num_buckets
        self.capacity = num_buckets * bucket_size

        self.buckets: list[list[_Entry]] = [[] for _ in range(num_buckets)]
        self.count = 0
        # Deterministic per-instance randomness for eviction choice.
        self._rng_state = (
            seed
            if seed is not None
            else int.from_bytes(os.urandom(8), "big")
        )

    # --- internal helpers ---------------------------------------------------
    @classmethod
    def from_config(cls, cfg: CooKooConfig, seed: int | None = None) -> "CuckooFilter":
        return cls(
            capacity=cfg.filter_capacity,
            fingerprint_bits=cfg.fingerprint_bits,
            bucket_size=cfg.bucket_size,
            max_kicks=cfg.max_kicks,
            aging_window_days=cfg.aging_window_days,
            seed=seed,
        )

    def _next_rand(self) -> int:
        # xorshift64* — small, deterministic, dependency-free.
        x = self._rng_state & 0xFFFFFFFFFFFFFFFF
        x ^= (x >> 12)
        x ^= (x << 25) & 0xFFFFFFFFFFFFFFFF
        x ^= (x >> 27)
        self._rng_state = x
        return (x * 0x2545F4914F6CDD1D) & 0xFFFFFFFFFFFFFFFF

    def _fingerprint(self, item: bytes) -> int:
        # Fingerprint derived from a different hash slice than the index hash so
        # they are independent. Never zero (zero == "empty slot" sentinel use).
        h = _stable_hash(b"fp:" + item)
        fp = h & self._fp_mask
        if fp == 0:
            fp = 1
        return fp

    def _index1(self, item: bytes) -> int:
        return _stable_hash(b"idx:" + item) % self.num_buckets

    def _alt_index(self, index: int, fp: int) -> int:
        # i2 = i1 XOR hash(fingerprint). num_buckets is a power of two so the
        # masked XOR is its own inverse: _alt_index(_alt_index(i)) == i.
        fp_hash = _stable_hash(b"alt:" + fp.to_bytes(4, "big"))
        return (index ^ (fp_hash % self.num_buckets)) % self.num_buckets

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    # --- public API ---------------------------------------------------------
    def contains(self, item: str | bytes) -> bool:
        data = item.encode("utf-8") if isinstance(item, str) else item
        fp = self._fingerprint(data)
        i1 = self._index1(data)
        i2 = self._alt_index(i1, fp)
        return self._bucket_has(i1, fp) or self._bucket_has(i2, fp)

    def _bucket_has(self, index: int, fp: int) -> bool:
        return any(e.fingerprint == fp for e in self.buckets[index])

    def insert(self, item: str | bytes, now_ms: int | None = None) -> bool:
        """Insert an item. Returns False if the filter is too full to place it.

        Note: cuckoo filters can hold duplicate fingerprints; we treat insert as
        idempotent at the membership level by short-circuiting if already present
        (callers use this purely for dedup, not multiset counting).
        """
        data = item.encode("utf-8") if isinstance(item, str) else item
        now = now_ms if now_ms is not None else self._now_ms()
        fp = self._fingerprint(data)
        i1 = self._index1(data)
        i2 = self._alt_index(i1, fp)

        if self._bucket_has(i1, fp) or self._bucket_has(i2, fp):
            return True  # already a member; nothing to do

        for idx in (i1, i2):
            if len(self.buckets[idx]) < self.bucket_size:
                self.buckets[idx].append(_Entry(fp, now))
                self.count += 1
                return True

        # Both candidate buckets full: relocate existing entries (cuckoo kick).
        index = i1 if (self._next_rand() & 1) == 0 else i2
        carry_fp = fp
        for _ in range(self.max_kicks):
            slot = self._next_rand() % self.bucket_size
            victim = self.buckets[index][slot]
            self.buckets[index][slot] = _Entry(carry_fp, now)
            carry_fp = victim.fingerprint
            now = victim.inserted_ms  # preserve the evicted entry's age
            index = self._alt_index(index, carry_fp)
            if len(self.buckets[index]) < self.bucket_size:
                self.buckets[index].append(_Entry(carry_fp, now))
                self.count += 1
                return True
        # Failed to place the last carried fingerprint; filter is effectively full.
        return False

    def delete(self, item: str | bytes) -> bool:
        """Remove one matching fingerprint. Returns True if something was removed."""
        data = item.encode("utf-8") if isinstance(item, str) else item
        fp = self._fingerprint(data)
        i1 = self._index1(data)
        i2 = self._alt_index(i1, fp)
        for idx in (i1, i2):
            for pos, e in enumerate(self.buckets[idx]):
                if e.fingerprint == fp:
                    del self.buckets[idx][pos]
                    self.count -= 1
                    return True
        return False

    def age(self, now_ms: int | None = None) -> int:
        """Delete entries older than aging_window_days (§5.17 sliding window).

        Returns the number of entries removed. This is the load-bearing deletion
        path that keeps the injection stream non-stationary.
        """
        now = now_ms if now_ms is not None else self._now_ms()
        cutoff = now - self.aging_window_days * 86_400_000
        removed = 0
        for bucket in self.buckets:
            kept = [e for e in bucket if e.inserted_ms >= cutoff]
            removed += len(bucket) - len(kept)
            bucket[:] = kept
        self.count -= removed
        return removed

    @property
    def load_factor(self) -> float:
        return self.count / self.capacity if self.capacity else 0.0

    def __len__(self) -> int:
        return self.count
