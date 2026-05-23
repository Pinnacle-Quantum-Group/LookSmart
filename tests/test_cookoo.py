"""Tests for the CooKoo Filter subsystem (README §5.17)."""

from __future__ import annotations

import hashlib
import hmac
import random
import tempfile
from pathlib import Path

import pytest

from looksmart.audit import AuditStore, SaltProvider, normalize_query
from looksmart.config import AuditConfig, Balance, CooKooConfig
from looksmart.cookoo.filter import CuckooFilter
from looksmart.cookoo.injector import CooKooInjector, is_evidentiary_false_statement
from looksmart.cookoo.store import CooKooStore
from looksmart.models import (
    AppliedInjection,
    InjectionPosition,
    InjectionType,
    ProviderResponse,
    Query,
    QueryKind,
)

DAY_MS = 86_400_000


# --- cuckoo filter ----------------------------------------------------------
def test_insert_contains_delete():
    cf = CuckooFilter(capacity=1024, fingerprint_bits=12, bucket_size=4, seed=1)
    assert not cf.contains("alpha")
    assert cf.insert("alpha")
    assert cf.contains("alpha")
    assert cf.delete("alpha")
    assert not cf.contains("alpha")
    # deleting again returns False (nothing to remove)
    assert not cf.delete("alpha")


def test_insert_many_and_membership():
    cf = CuckooFilter(capacity=4096, fingerprint_bits=12, bucket_size=4, seed=7)
    items = [f"injection-{i}" for i in range(500)]
    for it in items:
        assert cf.insert(it)
    for it in items:
        assert cf.contains(it), f"{it} should be present"


def test_false_positive_rate_roughly_in_target():
    # FP bound for a cuckoo filter is ~ 2*bucket_size / 2^fingerprint_bits.
    fp_bits = 12
    bucket = 4
    cf = CuckooFilter(capacity=8192, fingerprint_bits=fp_bits, bucket_size=bucket, seed=3)
    inserted = {f"in-{i}" for i in range(2000)}
    for it in inserted:
        cf.insert(it)
    trials = 20000
    fp = 0
    for i in range(trials):
        probe = f"absent-{i}"
        if probe in inserted:
            continue
        if cf.contains(probe):
            fp += 1
    rate = fp / trials
    bound = 2.0 * bucket / (2 ** fp_bits)  # ~0.00195
    # Should be comfortably under a loose multiple of the theoretical bound.
    assert rate < bound * 4 + 0.001, f"FP rate {rate} too high (bound ~{bound})"


def test_aging_deletes_old_entries():
    cf = CuckooFilter(
        capacity=1024, fingerprint_bits=12, bucket_size=4, aging_window_days=30, seed=2
    )
    base = 1_000_000_000_000
    cf.insert("old", now_ms=base)
    cf.insert("recent", now_ms=base + 29 * DAY_MS)
    # age relative to a "now" that is 31 days after base
    removed = cf.age(now_ms=base + 31 * DAY_MS)
    assert removed == 1
    assert not cf.contains("old")
    assert cf.contains("recent")


def test_from_config():
    cfg = CooKooConfig(filter_capacity=2048, fingerprint_bits=10, bucket_size=4)
    cf = CuckooFilter.from_config(cfg, seed=5)
    assert cf.fingerprint_bits == 10
    assert cf.capacity >= 2048


# --- injector: verbatim prose preservation ----------------------------------
def _injector(**overrides) -> CooKooInjector:
    cfg = CooKooConfig(**overrides)
    return CooKooInjector(cfg)


def test_verbatim_prose_preserved_across_all_types():
    rng = random.Random(0)
    inj = _injector()
    query = "How do tides interact with coastal sediment transport over decades?"
    for _ in range(200):
        q = inj.inject(query, rng)
        assert q.kind == QueryKind.REAL
        assert q.original_text == query
        assert query in q.text  # HARD CONSTRAINT: verbatim survives


def test_passthrough_yields_unmodified_text():
    rng = random.Random(1)
    inj = _injector()
    query = "What is the capital of Australia?"
    q = inj.inject(query, rng, user_override_passthrough=True)
    assert q.text == query
    assert q.injection.injection_type == InjectionType.PASSTHROUGH
    assert q.injection.position == InjectionPosition.NONE
    assert q.injection.user_override is True


# --- injector: high-stakes detector -----------------------------------------
def test_passthrough_detector_flags_code():
    inj = _injector()
    assert inj.should_passthrough("```python\nprint(1)\n```")
    assert inj.should_passthrough("Why does def foo(x): return x+1 raise here?")


def test_passthrough_detector_flags_medical():
    inj = _injector()
    assert inj.should_passthrough("I have chest pain and my doctor prescribed a new medication")
    assert inj.should_passthrough("what are the side effects of this antibiotic")


def test_passthrough_detector_flags_legal_mental_immigration_financial():
    inj = _injector()
    assert inj.should_passthrough("My lawyer says the plaintiff filed a lawsuit")
    assert inj.should_passthrough("I feel hopeless and keep thinking about self-harm")
    assert inj.should_passthrough("How do I apply for asylum after my visa expired?")
    assert inj.should_passthrough("Should I invest my retirement savings in this fund?")


def test_passthrough_detector_flags_numerical_and_long():
    inj = _injector(passthrough_max_length=50)
    assert inj.should_passthrough("dose it at 500 mg twice daily")
    assert inj.should_passthrough("x" * 51)


def test_passthrough_detector_passes_routine_query():
    inj = _injector()
    assert not inj.should_passthrough("what's a good recipe for risotto")


def test_high_stakes_query_is_passed_through_by_inject():
    rng = random.Random(2)
    inj = _injector()
    q = inj.inject("I have chest pain, what could cause it", rng)
    assert q.text == "I have chest pain, what could cause it"
    assert q.injection.injection_type == InjectionType.PASSTHROUGH
    assert q.metadata.get("high_stakes") is True


# --- injector: probe flagging ------------------------------------------------
def test_probe_queries_are_flagged_distinctly():
    rng = random.Random(3)
    inj = _injector()
    q = inj.inject("who painted the Mona Lisa", rng, probe=True)
    assert q.metadata.get("probe") is True
    assert q.injection.injection_type == InjectionType.PROBE
    assert "who painted the Mona Lisa" in q.text


def test_probe_never_applied_to_high_stakes():
    rng = random.Random(4)
    inj = _injector()
    q = inj.inject("my doctor prescribed insulin, correct dosage?", rng, probe=True)
    # high-stakes probe downgrades to passthrough (verbatim), still flagged probe
    assert q.injection.injection_type == InjectionType.PASSTHROUGH
    assert q.text == "my doctor prescribed insulin, correct dosage?"


def test_substantive_inject_never_emits_probe_type():
    rng = random.Random(5)
    # type_balance rolls probe 100% of the time; substantive path must downgrade
    inj = CooKooInjector(CooKooConfig(type_balance=Balance(weights={"probe": 1.0})))
    for _ in range(50):
        q = inj.inject("explain photosynthesis", rng)
        assert q.injection.injection_type != InjectionType.PROBE


# --- injector: deny check for evidentiary false statements -------------------
def test_evidentiary_false_statement_deny():
    assert is_evidentiary_false_statement("I personally witnessed the crash, asking about")
    assert is_evidentiary_false_statement("Under penalty of perjury, I swear that")
    # cohort/professional framings are NOT denied
    assert not is_evidentiary_false_statement("As a doctor looking into this")
    assert not is_evidentiary_false_statement("From a journalist's angle")
    assert not is_evidentiary_false_statement("As an attorney reviewing this")


def test_cohort_framings_allowed():
    rng = random.Random(6)
    inj = CooKooInjector(CooKooConfig(type_balance=Balance(weights={"cohort": 1.0})))
    seen = set()
    for _ in range(100):
        q = inj.inject("what are the rules of evidence", rng)
        if q.injection.text:
            seen.add(q.injection.text)
    # professional cohort framings appear and are never blocked
    assert any("doctor" in t or "attorney" in t or "journalist" in t for t in seen)


# --- injector: dedup against cuckoo filter -----------------------------------
def test_dedup_inserts_into_filter():
    rng = random.Random(8)
    inj = CooKooInjector(CooKooConfig(type_balance=Balance(weights={"register": 1.0})))
    q = inj.inject("explain entropy", rng)
    assert inj.cuckoo.contains(q.injection.text)


# --- store: roundtrip + retire ----------------------------------------------
def _audit_store(tmp: Path) -> AuditStore:
    cfg = AuditConfig(db_path=str(tmp / "audit.db"), salt_source="file")
    return AuditStore(cfg, SaltProvider(cfg))


def test_store_roundtrip_and_join():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        audit = _audit_store(tmp)
        store = CooKooStore(str(tmp / "cookoo.db"), audit.hash_query, CooKooConfig())
        query = "what is the boiling point of water at altitude"
        q = Query(
            text="For a research project on this topic " + query,
            kind=QueryKind.REAL,
            original_text=query,
            injection=AppliedInjection(
                injection_type=InjectionType.COHORT_CONTEXT,
                position=InjectionPosition.PREFIX,
                text="For a research project on this topic",
                category="cohort",
            ),
        )
        row_id = store.record(q, provider="openai", response="around 100C lower")
        assert row_id > 0
        rows = store.for_real_query(query)
        assert len(rows) == 1
        assert rows[0]["injection_type"] == "cohort"
        assert rows[0]["provider"] == "openai"
        assert rows[0]["response_hash"] is not None
        audit.close()
        store.close()


def test_store_retire_aged():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        audit = _audit_store(tmp)
        store = CooKooStore(
            str(tmp / "c.db"), audit.hash_query, CooKooConfig(aging_window_days=30)
        )
        base = 1_000_000_000_000
        q = Query(
            text="x prefix",
            kind=QueryKind.REAL,
            original_text="x",
            injection=AppliedInjection(
                injection_type=InjectionType.TOPIC_DISTRACTOR,
                position=InjectionPosition.SUFFIX,
                text="prefix",
                category="topic",
            ),
        )
        store.record(q, now_ms=base)
        retired = store.retire_aged(now_ms=base + 31 * DAY_MS)
        assert retired == 1
        rows = store.for_real_query("x")
        assert rows[0]["retired_at"] is not None
        # idempotent: nothing new to retire
        assert store.retire_aged(now_ms=base + 31 * DAY_MS) == 0
        audit.close()
        store.close()


# --- shared HMAC alignment with audit ----------------------------------------
def test_same_query_hashes_identically_across_audit_and_cookoo():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        audit = _audit_store(tmp)
        store = CooKooStore(str(tmp / "c.db"), audit.hash_query, CooKooConfig())
        query = "When did the Roman Republic become an Empire?"

        q = Query(
            text="As a doctor looking into this " + query,
            kind=QueryKind.REAL,
            original_text=query,
            injection=AppliedInjection(
                injection_type=InjectionType.COHORT_CONTEXT,
                position=InjectionPosition.PREFIX,
                text="As a doctor looking into this",
                category="cohort",
            ),
        )
        store.record(q, provider="anthropic")
        # The audit log stores the same source hash for the real query.
        audit.log_real(q)

        cookoo_hash = store.for_real_query(query)[0]["real_query_hash"]
        audit_hash = audit.hash_query(query)
        assert bytes(cookoo_hash) == audit_hash

        # And it equals a manually-reconstructed HMAC over the shared normalize.
        manual = hmac.new(
            audit.salt.get(), normalize_query(query), hashlib.sha256
        ).digest()
        assert audit_hash == manual
        audit.close()
        store.close()


def test_response_hash_uses_shared_hmac():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        audit = _audit_store(tmp)
        store = CooKooStore(str(tmp / "c.db"), audit.hash_query, CooKooConfig())
        q = Query(
            text="q prefix",
            kind=QueryKind.REAL,
            original_text="q",
            injection=AppliedInjection(
                injection_type=InjectionType.REGISTER_MODIFIER,
                position=InjectionPosition.PREFIX,
                text="prefix",
                category="academic",
            ),
        )
        resp = ProviderResponse(text="the answer", provider="gemini")
        rid = store.record(q, provider="gemini", response=resp)
        rows = store.all_rows()
        assert bytes(rows[0]["response_hash"]) == audit.hash_query("the answer")
        # attach_response late-binds the same way
        store.attach_response(rid, "revised answer")
        assert bytes(store.all_rows()[0]["response_hash"]) == audit.hash_query(
            "revised answer"
        )
        audit.close()
        store.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
