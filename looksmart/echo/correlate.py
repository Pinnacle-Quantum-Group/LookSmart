"""Echo Mode correlation engine (README §5.22 methodology).

Implements the seven-step methodology from §5.22 verbatim:

1-2. Topic tagging (queries + observations) -- done upstream by
     :mod:`looksmart.echo.tagging`; tags are read off the store here.
3.   Temporal alignment: for each query at T1, find observations in
     ``[T1, T1 + correlation_window_days]`` with topic overlap > threshold.
4.   Per-user, per-platform, per-topic baseline establishment from history
     *prior to T1*. New users get a ``bootstrap_days`` observation-only window
     during which correlations are recorded but NOT significance-tested.
5.   Significance test: chi-square (with a permutation-test fallback for small
     counts) of the post-query rate against the per-user baseline rate.
6.   Benjamini-Hochberg FDR control across the many simultaneous
     topic x platform comparisons.
7.   Cross-platform higher-order pattern detection: one query correlating to
     multiple platforms in similar windows.

It also supports diffing leak rate for queries WITH vs WITHOUT a CooKoo
injection variant (§5.22: the ``query_id`` FK to ``injections`` exists exactly
so this is measurable).

Findings surface discipline (§5.22 hard constraint): a :class:`Finding` carries
only ``topic`` (a Q-ID/label key), ``platform`` and ``p`` -- never a per-
recommendation natural-language index of the user's interests.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats

from .store import EchoStore

_DAY = 86_400


def topic_overlap(a: list[str], b: list[str]) -> float:
    """Jaccard overlap of two topic-key sets (0.0..1.0)."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def benjamini_hochberg(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR-adjusted p-values (monotone, clipped to <=1)."""
    n = len(pvals)
    if n == 0:
        return []
    p = np.asarray(pvals, dtype=float)
    order = np.argsort(p)
    ranked = p[order]
    adj = ranked * n / (np.arange(n) + 1)
    # Enforce monotonicity from the largest p downward.
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    adj = np.clip(adj, 0.0, 1.0)
    out = np.empty(n, dtype=float)
    out[order] = adj
    return out.tolist()


@dataclass
class Finding:
    """A single privacy-preserving correlation finding.

    Intentionally does NOT include raw recommendation text (§5.22 constraint).
    """

    topic: str
    platform: str
    raw_p: float
    fdr_p: float
    significant: bool
    n_post: int  # observations in-window matching the topic
    baseline_rate: float  # observations/day prior to T1
    query_id: int
    rec_ids: list[int] = field(default_factory=list)
    median_delta_s: int = 0
    has_injection: bool = False
    notes: str | None = None


@dataclass
class CrossPlatformPattern:
    """Higher-order finding: one query correlated to multiple platforms (§5.22 step 7)."""

    query_id: int
    topic: str
    platforms: list[str]
    fdr_ps: dict[str, float]
    window_spread_s: int  # spread of median deltas across platforms


class CorrelationEngine:
    """Run §5.22 correlation analysis over an :class:`EchoStore`."""

    def __init__(
        self,
        store: EchoStore,
        *,
        window_days: int = 30,
        overlap_threshold: float = 0.3,
        bootstrap_days: int = 30,
        alpha: float = 0.05,
        rng: np.random.Generator | None = None,
    ):
        self.store = store
        self.window_s = window_days * _DAY
        self.overlap_threshold = overlap_threshold
        self.bootstrap_s = bootstrap_days * _DAY
        self.alpha = alpha
        self.rng = rng if rng is not None else np.random.default_rng(0)

    # -- baseline ------------------------------------------------------------
    def _baseline_rate(
        self, observations: list[dict[str, Any]], topic: str, t1: int
    ) -> tuple[float, int]:
        """Per-user/platform/topic baseline rate (matches/day) strictly before T1.

        Returns (rate_per_day, span_days). Observations are already filtered to
        a single platform by the caller.
        """
        pre = [o for o in observations if o["timestamp"] < t1]
        if not pre:
            return 0.0, 0
        first = min(o["timestamp"] for o in pre)
        span_s = max(t1 - first, _DAY)
        matches = sum(1 for o in pre if topic in o["topic_tags"])
        return matches / (span_s / _DAY), int(span_s / _DAY)

    def _in_bootstrap(self, observations: list[dict[str, Any]], t1: int) -> bool:
        """True if there isn't yet ``bootstrap_days`` of history before T1.

        Per §5.22: "first 30 days run in observation-only mode, no significance
        testing reported." We measure history depth from the earliest
        observation overall.
        """
        if not observations:
            return True
        first = min(o["timestamp"] for o in observations)
        return (t1 - first) < self.bootstrap_s

    # -- significance --------------------------------------------------------
    def _significance(
        self, n_post: int, post_span_days: float, baseline_rate: float
    ) -> float:
        """Test post-query rate against baseline. Chi-square; permutation fallback.

        Compares observed in-window matches against the count expected under
        the per-user baseline rate. For very small expected counts chi-square is
        unreliable, so we use a Poisson-based permutation test instead.
        """
        post_span_days = max(post_span_days, 1.0 / 24.0)  # >= 1 hour
        expected = max(baseline_rate * post_span_days, 1e-9)
        if expected >= 5 and n_post + expected >= 10:
            # 1-df goodness-of-fit: observed vs expected (and complement).
            other_obs = max(post_span_days - n_post, 0.0)
            other_exp = max(post_span_days - expected, 1e-9)
            chi2 = (n_post - expected) ** 2 / expected + (
                other_obs - other_exp
            ) ** 2 / other_exp
            p = float(stats.chi2.sf(chi2, df=1))
            # one-sided interest in excess; halve when excess, else ~1.
            return p / 2 if n_post > expected else 1.0 - p / 2
        # Permutation / Monte-Carlo: how often does Poisson(expected) >= n_post?
        draws = self.rng.poisson(expected, size=20_000)
        p = float((draws >= n_post).sum() + 1) / (len(draws) + 1)
        return p

    # -- main ----------------------------------------------------------------
    def run(self, *, persist: bool = True) -> list[Finding]:
        """Run the full pipeline, return findings (and optionally persist rows)."""
        queries = self.store.queries()
        all_obs = self.store.observations()
        by_platform: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for o in all_obs:
            by_platform[o["platform"]].append(o)

        raw: list[Finding] = []
        for q in queries:
            t1 = q["timestamp"]
            q_topics = set(q["topic_tags"])
            if not q_topics:
                continue
            for platform, obs in by_platform.items():
                bootstrap = self._in_bootstrap(obs, t1)
                # in-window observations with topic overlap > threshold
                window = [
                    o
                    for o in obs
                    if t1 <= o["timestamp"] <= t1 + self.window_s
                    and topic_overlap(q["topic_tags"], o["topic_tags"])
                    > self.overlap_threshold
                ]
                if not window:
                    continue
                # group the matched observations by the specific shared topic
                shared_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for o in window:
                    for t in set(o["topic_tags"]) & q_topics:
                        shared_by_topic[t].append(o)
                for topic, matched in shared_by_topic.items():
                    n_post = len(matched)
                    deltas = sorted(o["timestamp"] - t1 for o in matched)
                    median_delta = int(np.median(deltas)) if deltas else 0
                    baseline_rate, _ = self._baseline_rate(obs, topic, t1)
                    if bootstrap:
                        # observation-only: record, never significance-test
                        raw.append(
                            Finding(
                                topic=topic,
                                platform=platform,
                                raw_p=1.0,
                                fdr_p=1.0,
                                significant=False,
                                n_post=n_post,
                                baseline_rate=baseline_rate,
                                query_id=q["id"],
                                rec_ids=[o["id"] for o in matched],
                                median_delta_s=median_delta,
                                has_injection=q["has_injection"],
                                notes="bootstrap: observation-only, not tested",
                            )
                        )
                        continue
                    post_span_days = max(self.window_s / _DAY, 1.0 / 24.0)
                    p = self._significance(n_post, post_span_days, baseline_rate)
                    raw.append(
                        Finding(
                            topic=topic,
                            platform=platform,
                            raw_p=p,
                            fdr_p=1.0,  # filled after BH
                            significant=False,
                            n_post=n_post,
                            baseline_rate=baseline_rate,
                            query_id=q["id"],
                            rec_ids=[o["id"] for o in matched],
                            median_delta_s=median_delta,
                            has_injection=q["has_injection"],
                        )
                    )

        # BH across the tested (non-bootstrap) findings only.
        tested = [f for f in raw if f.notes is None]
        if tested:
            adj = benjamini_hochberg([f.raw_p for f in tested])
            for f, a in zip(tested, adj):
                f.fdr_p = a
                f.significant = a <= self.alpha

        if persist:
            self.store.clear_correlations()
            for f in raw:
                for rid in f.rec_ids:
                    self.store.add_correlation(
                        query_id=f.query_id,
                        rec_id=rid,
                        time_delta=f.median_delta_s,
                        topic_overlap=self.overlap_threshold,
                        baseline_p=f.raw_p,
                        fdr_adjusted_p=f.fdr_p,
                        notes=(f.notes or (f"topic={f.topic}")),
                    )
        return raw

    # -- step 7: cross-platform higher-order patterns ------------------------
    def cross_platform_patterns(
        self, findings: list[Finding], *, max_window_spread_days: int = 7
    ) -> list[CrossPlatformPattern]:
        """Flag queries whose same topic correlated significantly on >=2 platforms.

        Similar time windows (median deltas within ``max_window_spread_days``)
        suggest centralized sharing / fingerprint linkage rather than per-
        platform leakage (§5.22 step 7).
        """
        by_qt: dict[tuple[int, str], list[Finding]] = defaultdict(list)
        for f in findings:
            if f.significant:
                by_qt[(f.query_id, f.topic)].append(f)
        out: list[CrossPlatformPattern] = []
        spread_limit = max_window_spread_days * _DAY
        for (qid, topic), group in by_qt.items():
            platforms = sorted({f.platform for f in group})
            if len(platforms) < 2:
                continue
            deltas = [f.median_delta_s for f in group]
            spread = max(deltas) - min(deltas)
            if spread <= spread_limit:
                out.append(
                    CrossPlatformPattern(
                        query_id=qid,
                        topic=topic,
                        platforms=platforms,
                        fdr_ps={f.platform: f.fdr_p for f in group},
                        window_spread_s=spread,
                    )
                )
        return out

    # -- CooKoo injection differential leak rate -----------------------------
    def injection_leak_diff(self, findings: list[Finding]) -> dict[str, Any]:
        """Diff leak rate for queries WITH vs WITHOUT a CooKoo injection (§5.22).

        Computes the share of tested findings that are significant, split by
        whether the originating query carried an injection variant. A lower
        significant-leak rate for injected queries is evidence the injection
        partially obscures the cross-platform channel.
        """
        tested = [f for f in findings if f.notes is None]
        with_inj = [f for f in tested if f.has_injection]
        without_inj = [f for f in tested if not f.has_injection]

        def rate(fs: list[Finding]) -> float:
            return (sum(f.significant for f in fs) / len(fs)) if fs else 0.0

        return {
            "n_with_injection": len(with_inj),
            "n_without_injection": len(without_inj),
            "leak_rate_with_injection": rate(with_inj),
            "leak_rate_without_injection": rate(without_inj),
            "leak_rate_delta": rate(without_inj) - rate(with_inj),
        }
