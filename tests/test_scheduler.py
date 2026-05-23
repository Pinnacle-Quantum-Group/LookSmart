"""Tests for the behavioral scheduler (README §5.3)."""

from __future__ import annotations

import numpy as np
import pytest

from looksmart.config import SchedulerConfig
from looksmart.models import QueryKind, Session
from looksmart.scheduler import BehavioralScheduler


def _poisson_timestamps(rng: np.random.Generator, n: int, mean_ms: float) -> list[int]:
    t = 0.0
    out = []
    for _ in range(n):
        t += rng.exponential(mean_ms)
        out.append(int(t))
    return out


@pytest.mark.parametrize("process", ["poisson", "nhpp", "hawkes"])
def test_fit_sample_roundtrip_positive_plausible(process: str):
    rng = np.random.default_rng(11)
    ts = _poisson_timestamps(rng, 300, mean_ms=600_000)  # ~10 min mean
    sched = BehavioralScheduler(SchedulerConfig(process=process, perturbation=0.1))
    sched.fit(ts)

    delays = [sched.sample_next_delay_ms(rng) for _ in range(500)]
    assert all(d >= 1 for d in delays)
    # plausibility: mean delay within an order of magnitude of the real mean
    mean_delay = float(np.mean(delays))
    assert 60_000 < mean_delay < 6_000_000


def test_unfitted_scheduler_still_samples():
    rng = np.random.default_rng(0)
    sched = BehavioralScheduler()
    d = sched.sample_next_delay_ms(rng)
    assert d >= 1


def test_too_few_events_falls_back():
    rng = np.random.default_rng(2)
    sched = BehavioralScheduler(SchedulerConfig(process="hawkes"))
    sched.fit([1000])  # single event
    d = sched.sample_next_delay_ms(rng)
    assert d >= 1


def test_zero_perturbation_is_deterministic_rate():
    """perturbation=0 => exact fit (factor 1.0), zero-KL by construction."""
    rng = np.random.default_rng(5)
    ts = _poisson_timestamps(rng, 200, mean_ms=300_000)
    sched = BehavioralScheduler(SchedulerConfig(process="poisson", perturbation=0.0))
    sched.fit(ts)
    # the perturbation factor must be exactly 1.0
    assert sched._perturb_factor(rng) == 1.0


def test_higher_perturbation_widens_spread():
    rng = np.random.default_rng(9)
    factors_low = [
        BehavioralScheduler(SchedulerConfig(perturbation=0.05))._perturb_factor(rng)
        for _ in range(2000)
    ]
    factors_high = [
        BehavioralScheduler(SchedulerConfig(perturbation=0.8))._perturb_factor(rng)
        for _ in range(2000)
    ]
    assert np.std(factors_high) > np.std(factors_low)


def test_session_level_interleaving_keeps_turns_contiguous():
    real = [Session(persona_id="r", kind=QueryKind.REAL, started_ms=t)
            for t in (1000, 3000, 5000)]
    decoy = [Session(persona_id="d", kind=QueryKind.DECOY, started_ms=t)
             for t in (2000, 4000)]
    sched = BehavioralScheduler(SchedulerConfig(interleave_at_session_level=True))
    merged = sched.interleave_sessions(real, decoy)
    times = [s.started_ms for s in merged]
    assert times == sorted(times)
    # whole sessions preserved (no turn-level mixing): every Session object intact
    assert len(merged) == 5
    assert {s.kind for s in merged} == {QueryKind.REAL, QueryKind.DECOY}


def test_schedule_decoy_sessions_assigns_increasing_starts():
    rng = np.random.default_rng(13)
    ts = _poisson_timestamps(rng, 100, mean_ms=600_000)
    sched = BehavioralScheduler(SchedulerConfig(process="poisson"))
    sched.fit(ts)
    decoys = [Session(persona_id=f"d{i}", kind=QueryKind.DECOY) for i in range(6)]
    out = sched.schedule_decoy_sessions(decoys, rng, start_ms=1_000_000)
    starts = [s.started_ms for s in out]
    assert starts == sorted(starts)
    assert all(b > a for a, b in zip(starts, starts[1:]))


def test_hawkes_fit_recovers_stable_branching():
    rng = np.random.default_rng(21)
    ts = _poisson_timestamps(rng, 400, mean_ms=400_000)
    sched = BehavioralScheduler(SchedulerConfig(process="hawkes"))
    sched.fit(ts)
    assert sched._fit is not None
    assert sched._fit.hawkes is not None
    assert 0.0 <= sched._fit.hawkes.alpha < 1.0
    assert sched._fit.hawkes.mu > 0
    assert sched._fit.hawkes.beta > 0
