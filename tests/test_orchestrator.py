"""Integration tests for the orchestrator + CLI (dry-run, no network)."""

from __future__ import annotations


import pytest

from looksmart.cli import main
from looksmart.config import LookSmartConfig
from looksmart.models import GenerationMode, Query, QueryKind, Session
from looksmart.orchestrator import Orchestrator


@pytest.fixture
def cfg(tmp_path):
    c = LookSmartConfig()
    c.local_llm.backend = "stub"
    c.audit.db_path = str(tmp_path / "audit.db")
    c.audit.salt_source = "file"
    return c


def test_orchestrator_builds_with_stub(cfg):
    orch = Orchestrator(cfg, seed=1)
    assert orch.llm is not None
    assert len(orch.library) > 0
    orch.close()


def test_generate_decoy_is_audited(cfg):
    orch = Orchestrator(cfg, seed=7)
    item = orch.generate_decoy(mode=GenerationMode.SPELUNKING)
    assert isinstance(item, (Query, Session))
    orch.dispatch(item)  # dry-run, audits only
    # decoys are logged plaintext; count rows
    n = orch.audit.conn.execute("SELECT COUNT(*) FROM decoys").fetchone()[0]
    assert n >= 1
    orch.close()


def test_prepare_real_passthrough_when_cookoo_disabled(cfg):
    assert cfg.cookoo.enabled is False
    orch = Orchestrator(cfg, seed=3)
    q = orch.prepare_real("what is the capital of France")
    assert q.kind == QueryKind.REAL
    assert q.text == "what is the capital of France"
    orch.close()


def test_prepare_real_cookoo_preserves_verbatim(cfg):
    cfg.cookoo.enabled = True
    orch = Orchestrator(cfg, seed=3)
    text = "explain how photosynthesis works"
    q = orch.prepare_real(text)
    assert q.original_text == text
    assert text in q.text  # verbatim prose survives (§5.17 hard constraint)
    orch.close()


def test_real_query_logged_as_hash_not_plaintext(cfg):
    orch = Orchestrator(cfg, seed=3)
    secret = "my very identifying real question about xyz"
    q = orch.prepare_real(secret)
    orch.dispatch(q)
    # the plaintext must NOT appear in the real_queries table
    rows = orch.audit.conn.execute(
        "SELECT query_hash FROM real_queries"
    ).fetchall()
    assert rows
    assert all(secret.encode() not in bytes(r[0]) for r in rows)
    # verification roundtrip works
    orch.audit.log_decoy(
        Query(text="decoy cover", kind=QueryKind.DECOY, persona_id="p"),
        covers_real=secret,
    )
    assert any(r["text"] == "decoy cover" for r in orch.audit.verify(secret))
    orch.close()


def test_select_mode_respects_rates(cfg):
    cfg.spelunking.rate = 0.0
    cfg.religious.rate = 1.0
    orch = Orchestrator(cfg, seed=11)
    modes = {orch.select_mode() for _ in range(20)}
    assert modes == {GenerationMode.RELIGIOUS}
    orch.close()


def test_select_mode_defaults_to_spelunking(cfg):
    orch = Orchestrator(cfg, seed=11)  # all rates 0 by default
    assert orch.select_mode() == GenerationMode.SPELUNKING
    orch.close()


def test_dispatch_dry_run_does_not_send(cfg):
    orch = Orchestrator(cfg, seed=5)
    item = orch.generate_decoy(mode=GenerationMode.PLAIN)
    assert orch.dispatch(item, provider=None, live=False) is None
    orch.close()


def test_cli_init_and_decoy_dry_run(tmp_path, capsys):
    cfgfile = tmp_path / "c.yaml"
    assert main(["init-config", str(cfgfile)]) == 0
    assert cfgfile.exists()
    # point audit db into tmp via an edited config
    c = LookSmartConfig.load(cfgfile)
    c.local_llm.backend = "stub"
    c.audit.db_path = str(tmp_path / "a.db")
    c.audit.salt_source = "file"
    c.dump(cfgfile)
    rc = main(["--config", str(cfgfile), "--seed", "2", "decoy", "-n", "2",
               "--mode", "spelunking"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "decoy" in out.lower()


def test_cli_real_dry_run(tmp_path, capsys):
    cfgfile = tmp_path / "c.yaml"
    c = LookSmartConfig()
    c.local_llm.backend = "stub"
    c.audit.db_path = str(tmp_path / "a.db")
    c.audit.salt_source = "file"
    c.dump(cfgfile)
    rc = main(["--config", str(cfgfile), "real", "what time is it in Tokyo"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out.lower()
