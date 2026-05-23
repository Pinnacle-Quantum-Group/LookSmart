"""Tests for §8 success-criteria metrics."""

from __future__ import annotations

import math

from looksmart import metrics
from looksmart.models import (
    EngagementEvent,
    EngagementType,
    GenerationMode,
    Query,
    QueryKind,
    Session,
)


def _decoy(text, mode=GenerationMode.SPELUNKING):
    return Query(text=text, kind=QueryKind.DECOY, mode=mode)


def _real(text):
    return Query(text=text, kind=QueryKind.REAL, original_text=text)


def test_kl_divergence_zero_for_identical():
    p = {"a": 0.5, "b": 0.5}
    assert metrics.kl_divergence(p, p) == 0.0


def test_kl_divergence_positive_and_directional():
    p = {"a": 0.9, "b": 0.1}
    q = {"a": 0.5, "b": 0.5}
    assert metrics.kl_divergence(p, q) > 0
    assert not math.isclose(
        metrics.kl_divergence(p, q), metrics.kl_divergence(q, p)
    )


def test_profile_dilution_kl_grows_as_decoys_diverge():
    real = [_real("garden tomatoes")]

    def topic(q):
        return "garden" if "garden" in q.text else "other"

    # advertised == real -> low divergence
    low = metrics.profile_dilution_kl(real, real, topic)
    # advertised heavily shifted toward 'other'
    advertised = real + [_decoy("other thing")] * 10
    high = metrics.profile_dilution_kl(advertised, real, topic)
    assert high > low


def test_token_ratio_whitespace_fallback():
    qs = [_real("one two"), _decoy("a b c d e f")]  # 2 real, 6 decoy tokens
    assert metrics.token_ratio(qs) == 3.0


def test_token_ratio_with_custom_tokenizer():
    qs = [_real("x"), _decoy("y")]
    assert metrics.token_ratio(qs, tokenizer=lambda t: 5) == 1.0


def test_engagement_ratio():
    def sess(n):
        s = Session(persona_id="p", kind=QueryKind.DECOY)
        s.engagement = [
            EngagementEvent(kind=EngagementType.COPY, turn_index=0) for _ in range(n)
        ]
        return s

    assert metrics.engagement_ratio([sess(2)], [sess(4)]) == 2.0


def test_tokenizer_fertility():
    # "a b" = 2 words; tokenizer says 4 tokens -> tpw 2.0; baseline 1.0 -> 2.0x
    f = metrics.tokenizer_fertility("a b", lambda t: 4, english_baseline_tpw=1.0)
    assert f == 2.0


def test_cost_metrics_targets():
    qs = [_real("one two")] + [_decoy("a b c d e f")]  # 3:1 token ratio

    def sess(n, kind=QueryKind.DECOY):
        s = Session(persona_id="p", kind=kind)
        s.engagement = [
            EngagementEvent(kind=EngagementType.COPY, turn_index=0) for _ in range(n)
        ]
        return s

    cm = metrics.cost_metrics(
        qs,
        real_sessions=[sess(1, QueryKind.REAL)],
        decoy_sessions=[sess(2)],
        fertilities=[1.6, 1.6],
    )
    assert cm.meets_token_target  # 3.0 >= 3.0
    assert cm.meets_engagement_target  # 2.0 >= 2.0
    assert cm.meets_fertility_target  # 1.6 >= 1.5


def test_cost_vector_breakdown_attributes_modes():
    qs = [
        _decoy("q1", GenerationMode.FENCE),
        _decoy("q2", GenerationMode.SPELUNKING),
        _decoy("q3", GenerationMode.GENDER_ROULETTE),
        _real("real"),  # ignored
    ]
    bd = metrics.cost_vector_breakdown(qs)
    assert bd["safety_classifier"] == 1
    assert bd["retrieval"] == 1
    assert bd["demographic_inference"] == 1


def test_mid_stream_replacement_rate():
    class R:
        def __init__(self, truncated):
            self.truncated = truncated

    assert metrics.mid_stream_replacement_rate([]) == 0.0
    assert metrics.mid_stream_replacement_rate([R(True), R(False), R(False), R(False)]) == 0.25
