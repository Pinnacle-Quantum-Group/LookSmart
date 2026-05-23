"""Tests for Echo Mode (README §5.22).

Covers: store schema roundtrip + purge; importers parsing synthetic
Takeout/Spotify/Amazon fixtures; correlation engine finding a planted
correlation with significance, respecting the bootstrap period, and applying
Benjamini-Hochberg correction; aggregation refusing without opt-in and applying
DP / k-anonymity when opted in; deterministic tagging fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import numpy as np
import pytest

from looksmart.echo.aggregate import (
    AggregationRefused,
    CommunityAggregator,
    PrivacyMechanism,
    is_public_safety_topic,
)
from looksmart.echo.correlate import (
    CorrelationEngine,
    benjamini_hochberg,
    topic_overlap,
)
from looksmart.echo.importers import (
    BrowserCaptureImporter,
    ListBrowserCapture,
    import_amazon_orders,
    import_generic,
    import_google_takeout,
    import_spotify_export,
    import_youtube_takeout,
)
from looksmart.echo.store import EchoStore, default_hash_fn
from looksmart.echo.tagging import (
    KeywordFallbackTagger,
    LLMTagger,
    is_low_confidence,
    tag_keys,
)
from looksmart.llm_protocol import StubLLM
from looksmart.models import TopicTag

_DAY = 86_400
SALT = b"unit-test-salt"


def _store(tmp_path, retention_days=90, raw_retention_days=None):
    return EchoStore(
        tmp_path / "echo.db",
        hash_fn=default_hash_fn(SALT),
        retention_days=retention_days,
        raw_retention_days=raw_retention_days,
    )


# --- store -------------------------------------------------------------------
def test_store_schema_and_indexes(tmp_path):
    s = _store(tmp_path)
    tables = {
        r[0]
        for r in s.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"recommender_observations", "correlations", "injections"} <= tables
    idx = {
        r[0]
        for r in s.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert {"idx_rec_platform", "idx_corr_delta", "idx_corr_sig"} <= idx
    s.close()


def test_store_observation_roundtrip_and_hmac(tmp_path):
    s = _store(tmp_path)
    rid = s.add_observation(
        timestamp=1000,
        platform="youtube",
        observation_type="recommendation",
        content="quantum computing",
        topic_tags=["Q42"],
        raw_content="quantum computing",
        source="takeout",
    )
    rows = s.observations(platform="youtube")
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == rid
    assert row["platform"] == "youtube"
    assert row["topic_tags"] == ["Q42"]
    # content_hash is the HMAC of the content, not plaintext
    expected = hmac.new(SALT, b"quantum computing", hashlib.sha256).digest()
    assert row["content_hash"] == expected
    assert b"quantum computing" not in row["content_hash"]
    s.close()


def test_store_correlation_roundtrip_and_fk(tmp_path):
    s = _store(tmp_path)
    qid = s.add_injection(
        timestamp=100,
        real_query_hash=s.hash_content("real query"),
        injection_type="passthrough",
    )
    rid = s.add_observation(
        timestamp=200, platform="google", observation_type="search_suggest",
        content="c", topic_tags=["Q1"],
    )
    cid = s.add_correlation(
        query_id=qid, rec_id=rid, time_delta=100, topic_overlap=0.5,
        baseline_p=0.01, fdr_adjusted_p=0.04, notes="topic=Q1",
    )
    corr = s.correlations()
    assert corr and corr[0]["id"] == cid
    assert corr[0]["fdr_adjusted_p"] == 0.04
    # FK enforcement: bad rec_id should fail
    with pytest.raises(Exception):
        s.add_correlation(
            query_id=qid, rec_id=99999, time_delta=1, topic_overlap=0.1,
            baseline_p=0.5, fdr_adjusted_p=0.5,
        )
    s.close()


def test_store_purge_retention(tmp_path):
    s = _store(tmp_path, retention_days=30, raw_retention_days=7)
    now = 100 * _DAY
    old = s.add_observation(
        timestamp=now - 40 * _DAY, platform="youtube",
        observation_type="recommendation", content="old", raw_content="old",
    )
    midraw = s.add_observation(
        timestamp=now - 10 * _DAY, platform="youtube",
        observation_type="recommendation", content="mid", raw_content="mid",
    )
    recent = s.add_observation(
        timestamp=now - 1 * _DAY, platform="youtube",
        observation_type="recommendation", content="new", raw_content="new",
    )
    res = s.purge(now=now)
    assert res["observations_deleted"] == 1  # the 40-day-old row
    ids = {o["id"] for o in s.observations()}
    assert old not in ids
    assert {midraw, recent} <= ids
    by_id = {o["id"]: o for o in s.observations()}
    # mid (10d) is past raw window (7d) -> raw nulled; recent (1d) keeps raw
    assert by_id[midraw]["raw_content"] is None
    assert by_id[recent]["raw_content"] == "new"
    s.close()


def test_store_export_no_plaintext_hash(tmp_path):
    s = _store(tmp_path)
    s.add_observation(
        timestamp=1, platform="spotify", observation_type="recommendation",
        content="secret artist", topic_tags=["Q7"], raw_content="secret artist",
    )
    j = json.loads(s.export_json())
    assert "secret artist" in j["recommender_observations"][0]["raw_content"]
    # content_hash exported as hex, not raw bytes; not the plaintext
    ch = j["recommender_observations"][0]["content_hash"]
    assert isinstance(ch, str) and len(ch) == 64
    csv_text = s.export_csv("recommender_observations")
    assert "spotify" in csv_text and "Q7" in csv_text
    s.close()


# --- importers ---------------------------------------------------------------
def test_import_youtube_takeout(tmp_path):
    fx = tmp_path / "yt.json"
    fx.write_text(json.dumps([
        {"header": "YouTube", "title": "Watched Intro to Quantum Computing",
         "time": "2026-01-02T10:00:00Z"},
        {"header": "YouTube Search", "title": "Searched for risotto recipe",
         "time": "2026-01-02T11:00:00Z"},
        {"header": "YouTube", "title": "no time field"},  # dropped
    ]))
    rows = import_youtube_takeout(fx)
    assert len(rows) == 2
    assert rows[0]["platform"] == "youtube"
    assert rows[0]["observation_type"] == "recommendation"
    assert rows[0]["content"] == "Intro to Quantum Computing"
    assert rows[1]["observation_type"] == "search_suggest"
    assert rows[1]["content"] == "risotto recipe"


def test_import_google_takeout(tmp_path):
    fx = tmp_path / "g.json"
    fx.write_text(json.dumps([
        {"title": "Searched for tax deadline 2026", "time": "2026-03-01T09:00:00Z"},
    ]))
    rows = import_google_takeout(fx)
    assert rows[0]["platform"] == "google"
    assert rows[0]["content"] == "tax deadline 2026"


def test_import_spotify_export(tmp_path):
    fx = tmp_path / "sp.json"
    fx.write_text(json.dumps([
        {"endTime": "2026-02-01 20:30", "artistName": "Boards of Canada",
         "trackName": "Roygbiv", "msPlayed": 200000},
        {"ts": "2026-02-02T21:00:00Z",
         "master_metadata_album_artist_name": "Aphex Twin",
         "master_metadata_track_name": "Xtal"},
    ]))
    rows = import_spotify_export(fx)
    assert len(rows) == 2
    assert rows[0]["platform"] == "spotify"
    assert "Boards of Canada" in rows[0]["content"]
    assert "Aphex Twin" in rows[1]["content"]


def test_import_amazon_orders(tmp_path):
    fx = tmp_path / "amz.csv"
    fx.write_text(
        "Order Date,Title,Quantity\n"
        "01/15/2026,USB-C Cable 2m,1\n"
        '"Feb 03, 2026",Mechanical Keyboard,1\n'
    )
    rows = import_amazon_orders(fx)
    assert len(rows) == 2
    assert rows[0]["platform"] == "amazon"
    assert rows[0]["content"] == "USB-C Cable 2m"
    assert rows[1]["content"] == "Mechanical Keyboard"


def test_import_generic_and_browser_capture(tmp_path):
    fx = tmp_path / "feed.json"
    fx.write_text(json.dumps([
        {"timestamp": 1700000000, "content": "some rec"},
        {"timestamp": "bad", "content": "dropped"},
    ]))
    rows = import_generic(fx, platform="reddit")
    assert len(rows) == 1
    assert rows[0]["platform"] == "reddit"

    cap = ListBrowserCapture([
        {"platform": "amazon", "type": "recommendation",
         "text": "Recommended for you: widget", "time": 1700000100},
        {"platform": "amazon", "text": "", "time": 1700000200},  # dropped
    ])
    bc = BrowserCaptureImporter(cap)
    erows = bc.import_events()
    assert len(erows) == 1
    assert erows[0]["source"] == "browser_ext"
    assert erows[0]["platform"] == "amazon"


# --- tagging -----------------------------------------------------------------
def test_keyword_fallback_deterministic():
    t = KeywordFallbackTagger()
    a = t.tag("Intro to Quantum Computing and entanglement")
    b = t.tag("Intro to Quantum Computing and entanglement")
    assert [(x.qid, x.label, x.confidence) for x in a] == [
        (x.qid, x.label, x.confidence) for x in b
    ]
    # same keyword across different texts -> same QID (enables overlap)
    q = t.tag("quantum mechanics lecture")
    qids_a = {x.label: x.qid for x in a}
    qids_q = {x.label: x.qid for x in q}
    assert qids_a["quantum"] == qids_q["quantum"]
    # stopwords removed
    assert "and" not in {x.label for x in a}


def test_tag_keys_and_low_confidence():
    high = TopicTag(qid="Q42", label="quantum", confidence=0.9)
    low = TopicTag(qid=None, label="thing", confidence=0.2)
    assert not is_low_confidence(high)
    assert is_low_confidence(low)
    keys_all = tag_keys([high, low])
    assert "Q42" in keys_all and "label:thing" in keys_all
    keys_filtered = tag_keys([high, low], include_low_confidence=False)
    assert keys_filtered == ["Q42"]


def test_llm_tagger_parses_json_and_falls_back():
    payload = json.dumps([{"qid": "Q42", "label": "Douglas Adams", "confidence": 0.95}])
    tagger = LLMTagger(StubLLM(canned=payload))
    tags = tagger.tag("who wrote hitchhiker's guide")
    assert tags[0].qid == "Q42" and tags[0].label == "Douglas Adams"
    # StubLLM default echo is not JSON -> deterministic keyword fallback used
    fb = LLMTagger(StubLLM())
    out = fb.tag("risotto recipe milanese")
    assert out and all(isinstance(x, TopicTag) for x in out)


# --- correlation engine ------------------------------------------------------
def test_benjamini_hochberg_monotone():
    p = [0.001, 0.01, 0.02, 0.5, 0.8]
    adj = benjamini_hochberg(p)
    assert all(0.0 <= a <= 1.0 for a in adj)
    assert adj == sorted(adj)  # ascending input -> ascending adjusted
    assert benjamini_hochberg([]) == []


def test_topic_overlap():
    assert topic_overlap(["Q1", "Q2"], ["Q2", "Q3"]) == pytest.approx(1 / 3)
    assert topic_overlap([], ["Q1"]) == 0.0
    assert topic_overlap(["Q1"], ["Q1"]) == 1.0


def _seed_history(s, platform, topic, *, start, n, gap_days, off_topic_each=1):
    """Insert background history so a baseline can be established."""
    ts = start
    for _ in range(n):
        s.add_observation(
            timestamp=ts, platform=platform, observation_type="recommendation",
            content=f"bg-{ts}", topic_tags=[topic] if False else ["Qbg"],
        )
        ts += gap_days * _DAY


def test_correlation_finds_planted_signal_and_bootstrap(tmp_path):
    s = _store(tmp_path)
    rng = np.random.default_rng(7)
    topic = "Qquantum"
    plat = "youtube"
    base = 0

    # 90 days of background history on an unrelated topic -> baseline rate ~0
    # for the planted topic (so a post-query burst is significant).
    for d in range(90):
        s.add_observation(
            timestamp=base + d * _DAY, platform=plat,
            observation_type="recommendation", content=f"bg{d}",
            topic_tags=["Qbackground"],
        )

    # Query about the topic on day 95 (well past 30-day bootstrap window).
    t1 = base + 95 * _DAY
    qid = s.add_injection(
        timestamp=t1, real_query_hash=s.hash_content("about quantum"),
        injection_type="passthrough",
    )
    s.set_query_tags(qid, [topic])
    # Planted burst: many topic-matching recs in the days right after the query.
    for h in range(6):
        s.add_observation(
            timestamp=t1 + (h + 1) * 3600, platform=plat,
            observation_type="recommendation", content=f"q{h}",
            topic_tags=[topic],
        )

    # A second, *bootstrap-period* query on day 5 with its own burst: must NOT
    # be significance-tested.
    t_boot = base + 5 * _DAY
    qid_b = s.add_injection(
        timestamp=t_boot, real_query_hash=s.hash_content("early"),
        injection_type="passthrough",
    )
    s.set_query_tags(qid_b, ["Qearly"])
    for h in range(4):
        s.add_observation(
            timestamp=t_boot + (h + 1) * 3600, platform=plat,
            observation_type="recommendation", content=f"e{h}",
            topic_tags=["Qearly"],
        )

    eng = CorrelationEngine(
        s, window_days=30, overlap_threshold=0.3, bootstrap_days=30, rng=rng
    )
    findings = eng.run()

    planted = [f for f in findings if f.query_id == qid and f.topic == topic]
    assert planted, "planted correlation not found"
    f = planted[0]
    assert f.n_post == 6
    assert f.notes is None  # was significance-tested
    assert f.significant and f.fdr_p <= 0.05

    # bootstrap query recorded but never tested
    boot = [f for f in findings if f.query_id == qid_b]
    assert boot and all(b.notes and "bootstrap" in b.notes for b in boot)
    assert all(not b.significant for b in boot)

    # persisted to correlations table
    assert s.correlations(max_fdr_p=0.05)
    s.close()


def test_correlation_bh_applied_across_findings(tmp_path):
    s = _store(tmp_path)
    rng = np.random.default_rng(3)
    # Establish long baselines across two topics on two platforms.
    for d in range(90):
        for plat in ("youtube", "spotify"):
            s.add_observation(
                timestamp=d * _DAY, platform=plat,
                observation_type="recommendation", content=f"{plat}{d}",
                topic_tags=["Qbg"],
            )
    t1 = 95 * _DAY
    for topic in ("Qa", "Qb"):
        qid = s.add_injection(
            timestamp=t1, real_query_hash=s.hash_content(topic),
            injection_type="passthrough",
        )
        s.set_query_tags(qid, [topic])
        for plat in ("youtube", "spotify"):
            for h in range(5):
                s.add_observation(
                    timestamp=t1 + (h + 1) * 3600, platform=plat,
                    observation_type="recommendation", content=f"{topic}{plat}{h}",
                    topic_tags=[topic],
                )
    eng = CorrelationEngine(s, bootstrap_days=30, rng=rng)
    findings = eng.run()
    tested = [f for f in findings if f.notes is None]
    assert len(tested) >= 4
    # FDR-adjusted p must be >= raw p for every tested finding (BH inflates).
    for f in tested:
        assert f.fdr_p >= f.raw_p - 1e-9
        assert 0.0 <= f.fdr_p <= 1.0

    # cross-platform higher-order detection (same query+topic on 2 platforms)
    patterns = eng.cross_platform_patterns(findings)
    assert any(len(p.platforms) >= 2 for p in patterns)
    s.close()


def test_injection_leak_diff(tmp_path):
    s = _store(tmp_path)
    rng = np.random.default_rng(11)
    plat = "youtube"
    for d in range(90):
        s.add_observation(
            timestamp=d * _DAY, platform=plat,
            observation_type="recommendation", content=f"bg{d}",
            topic_tags=["Qbg"],
        )
    t1 = 95 * _DAY
    # passthrough (no injection) query -> strong burst
    q_plain = s.add_injection(
        timestamp=t1, real_query_hash=s.hash_content("plain"),
        injection_type="passthrough",
    )
    s.set_query_tags(q_plain, ["Qx"])
    for h in range(6):
        s.add_observation(
            timestamp=t1 + (h + 1) * 3600, platform=plat,
            observation_type="recommendation", content=f"x{h}",
            topic_tags=["Qx"],
        )
    # injected (cohort) query -> weak/no burst
    q_inj = s.add_injection(
        timestamp=t1 + _DAY, real_query_hash=s.hash_content("inj"),
        injection_type="cohort", injection_category="research_framing",
    )
    s.set_query_tags(q_inj, ["Qy"])
    s.add_observation(
        timestamp=t1 + _DAY + 3600, platform=plat,
        observation_type="recommendation", content="y0", topic_tags=["Qy"],
    )
    eng = CorrelationEngine(s, bootstrap_days=30, rng=rng)
    findings = eng.run()
    diff = eng.injection_leak_diff(findings)
    assert diff["n_with_injection"] >= 1 and diff["n_without_injection"] >= 1
    # passthrough query leaked (significant) more than the injected one
    assert diff["leak_rate_without_injection"] >= diff["leak_rate_with_injection"]
    s.close()


# --- aggregation -------------------------------------------------------------
def _findings():
    fs = []
    # 6 contributors for a topic/platform cell (>= k=5), all significant
    for _ in range(6):
        fs.append(_F("Qmusic", "spotify", 0.001, 0.01, True))
    # 2 contributors -> suppressed under k-anon
    fs.append(_F("Qrare", "youtube", 0.02, 0.04, True))
    fs.append(_F("Qrare", "youtube", 0.03, 0.05, True))
    # public-safety topic -> always excluded
    fs.append(_F("terrorism", "google", 0.001, 0.001, True))
    for _ in range(6):
        fs.append(_F("terrorism", "google", 0.001, 0.001, True))
    # bootstrap/untested -> not contributable
    b = _F("Qmusic", "spotify", 1.0, 1.0, False)
    b.notes = "bootstrap: observation-only, not tested"
    fs.append(b)
    return fs


def _F(topic, platform, raw_p, fdr_p, sig):
    from looksmart.echo.correlate import Finding
    return Finding(
        topic=topic, platform=platform, raw_p=raw_p, fdr_p=fdr_p,
        significant=sig, n_post=3, baseline_rate=0.0, query_id=1,
    )


def test_aggregation_refused_without_optin():
    agg = CommunityAggregator(community_aggregation_optin=False)
    with pytest.raises(AggregationRefused):
        agg.contribute(_findings())


def test_aggregation_k_anonymity_and_public_safety_exclusion():
    agg = CommunityAggregator(
        community_aggregation_optin=True, mechanism=PrivacyMechanism.K_ANONYMITY,
    )
    out = agg.contribute(_findings())
    topics = {(r["topic"], r["platform"]) for r in out}
    assert ("Qmusic", "spotify") in topics  # 6 >= k
    assert ("Qrare", "youtube") not in topics  # 2 < k suppressed
    assert not any(r["topic"] == "terrorism" for r in out)  # §12 exclusion
    cell = next(r for r in out if r["topic"] == "Qmusic")
    assert cell["count"] == 6 and cell["significant_count"] == 6
    assert cell["mechanism"] == "k_anonymity"


def test_aggregation_differential_privacy_noises_counts():
    rng = np.random.default_rng(99)
    agg = CommunityAggregator(
        community_aggregation_optin=True,
        mechanism=PrivacyMechanism.DIFFERENTIAL_PRIVACY,
        epsilon=0.5, rng=rng,
    )
    out = agg.contribute(_findings())
    cell = next(r for r in out if r["topic"] == "Qmusic")
    # DP does not k-suppress; small Qrare cell survives but noised
    assert any(r["topic"] == "Qrare" for r in out)
    assert cell["mechanism"] == "differential_privacy"
    # noise applied -> count generally not the exact integer 6
    assert cell["count"] != 6 or cell["significant_count"] != 6
    # public-safety still excluded regardless of mechanism
    assert not any(r["topic"] == "terrorism" for r in out)


def test_public_safety_helper():
    assert is_public_safety_topic("terrorism")
    assert is_public_safety_topic("Qx", "CSAM material")
    assert not is_public_safety_topic("Qmusic", "jazz")
