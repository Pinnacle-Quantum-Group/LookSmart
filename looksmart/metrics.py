"""Success-criteria metrics (README §8).

Objective (3) profile dilution is measured as KL divergence between the
*advertised* profile (real + decoy traffic, as the provider sees it) and the
*actual* operational profile (real queries only). Objective (4) cost imposition
uses proxies: decoy:real token ratio, tokenizer fertility, engagement ratio.

Targets from §8 are design proposals, not validated thresholds:
  token-count ratio decoy:real >= 3:1
  mean tokenizer fertility across persona languages >= 1.5x English
  engagement-signal volume ratio decoy:real >= 2:1

Per-vector cost breakout (§8): different modes hit different provider stacks;
`cost_vector_breakdown` attributes traffic to the stack each mode loads.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from .models import GenerationMode, Query, QueryKind, Session

# §8 design-proposal targets (not empirically validated)
TARGET_TOKEN_RATIO = 3.0
TARGET_FERTILITY = 1.5
TARGET_ENGAGEMENT_RATIO = 2.0

# Which provider stack each mode primarily loads (README §8 breakout).
MODE_COST_VECTOR: dict[GenerationMode, str] = {
    GenerationMode.WEIRD_AL: "content_classifier",
    GenerationMode.FENCE: "safety_classifier",
    GenerationMode.SPELUNKING: "retrieval",
    GenerationMode.POLITIC_ROULETTE: "retrieval",
    GenerationMode.RELIGIOUS: "retrieval",
    GenerationMode.ASKING_FOR_A_FRIEND: "safety_classifier",
    GenerationMode.IDENTITY_SEARCH: "content_stack_engagement",
    GenerationMode.GENDER_ROULETTE: "demographic_inference",
    GenerationMode.ORIENTATION_ROULETTE: "demographic_inference",
    GenerationMode.IMMIGRATION_ROULETTE: "demographic_inference",
    GenerationMode.HEALTH_STATUS_ROULETTE: "safety_classifier",
    GenerationMode.PLAIN: "content_stack",
}


def _smoothed_distribution(
    labels: Iterable[str], vocabulary: set[str], alpha: float = 1.0
) -> dict[str, float]:
    """Laplace-smoothed categorical distribution over `vocabulary`."""
    counts = Counter(labels)
    total = sum(counts.values()) + alpha * len(vocabulary)
    return {v: (counts.get(v, 0) + alpha) / total for v in vocabulary}


def kl_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """KL(P || Q) in nats over the shared support; assumes smoothed inputs."""
    keys = set(p) | set(q)
    out = 0.0
    for k in keys:
        pk = p.get(k, 0.0)
        qk = q.get(k, 0.0)
        if pk > 0 and qk > 0:
            out += pk * math.log(pk / qk)
    return out


def profile_dilution_kl(
    advertised: Sequence[Query],
    actual_real: Sequence[Query],
    topic_of: Callable[[Query], str],
) -> float:
    """KL divergence between advertised (real+decoy) and actual (real-only) topic
    profiles. Higher = profile centroid moved further from the user's truth.

    `topic_of` maps a query to a topic label (e.g. dominant TopicTag label).
    """
    vocab = {topic_of(q) for q in advertised} | {topic_of(q) for q in actual_real}
    p_actual = _smoothed_distribution((topic_of(q) for q in actual_real), vocab)
    p_advert = _smoothed_distribution((topic_of(q) for q in advertised), vocab)
    return kl_divergence(p_actual, p_advert)


@dataclass
class CostMetrics:
    token_ratio: float
    engagement_ratio: float
    mean_fertility: float
    meets_token_target: bool
    meets_engagement_target: bool
    meets_fertility_target: bool


def _count_tokens(text: str, tokenizer: Callable[[str], int] | None) -> int:
    return tokenizer(text) if tokenizer else max(1, len(text.split()))


def token_ratio(
    queries: Sequence[Query], tokenizer: Callable[[str], int] | None = None
) -> float:
    """decoy:real token-count ratio (§8 target >= 3:1). Whitespace fallback."""
    real = sum(
        _count_tokens(q.original_text or q.text, tokenizer)
        for q in queries
        if q.kind == QueryKind.REAL
    )
    decoy = sum(
        _count_tokens(q.text, tokenizer) for q in queries if q.kind == QueryKind.DECOY
    )
    return decoy / real if real else float("inf") if decoy else 0.0


def engagement_ratio(real: Sequence[Session], decoy: Sequence[Session]) -> float:
    """decoy:real engagement-event volume ratio (§8 target >= 2:1)."""
    r = sum(len(s.engagement) for s in real)
    d = sum(len(s.engagement) for s in decoy)
    return d / r if r else float("inf") if d else 0.0


def tokenizer_fertility(
    text: str, tokenizer: Callable[[str], int], english_baseline_tpw: float = 1.3
) -> float:
    """Tokens-per-word relative to an English baseline (§5.8 / §8).

    High-fertility languages impose more provider compute per word.
    """
    words = max(1, len(text.split()))
    tpw = tokenizer(text) / words
    return tpw / english_baseline_tpw


def cost_metrics(
    queries: Sequence[Query],
    real_sessions: Sequence[Session],
    decoy_sessions: Sequence[Session],
    tokenizer: Callable[[str], int] | None = None,
    fertilities: Sequence[float] = (),
) -> CostMetrics:
    tr = token_ratio(queries, tokenizer)
    er = engagement_ratio(real_sessions, decoy_sessions)
    mf = sum(fertilities) / len(fertilities) if fertilities else 1.0
    return CostMetrics(
        token_ratio=tr,
        engagement_ratio=er,
        mean_fertility=mf,
        meets_token_target=tr >= TARGET_TOKEN_RATIO,
        meets_engagement_target=er >= TARGET_ENGAGEMENT_RATIO,
        meets_fertility_target=mf >= TARGET_FERTILITY,
    )


def cost_vector_breakdown(queries: Sequence[Query]) -> dict[str, int]:
    """Attribute decoy traffic to the provider stack each mode loads (§8)."""
    out: Counter[str] = Counter()
    for q in queries:
        if q.kind == QueryKind.DECOY and q.mode is not None:
            out[MODE_COST_VECTOR.get(q.mode, "unknown")] += 1
    return dict(out)


def mid_stream_replacement_rate(responses: Iterable) -> float:
    """Fraction of responses the provider truncated/replaced mid-stream (§8).

    An observable proxy for safety-stack work; measuring provider behavior is
    passive observation, not interference.
    """
    responses = list(responses)
    if not responses:
        return 0.0
    truncated = sum(1 for r in responses if getattr(r, "truncated", False))
    return truncated / len(responses)
