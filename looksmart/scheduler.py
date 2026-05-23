"""Behavioral scheduler (README §5.3).

Replaces a naive fixed-interval daemon with a stochastic point process fitted
to the user's *real* interarrival times over a rolling window, then samples
decoy interarrival times from a **perturbed** version of that fit (the
perturbation knob favors small KL divergence from the real distribution).

Two processes are supported (selected via ``SchedulerConfig.process``):

``poisson`` / ``nhpp``
    A (locally) homogeneous Poisson process. We estimate the base rate
    ``mu`` = 1 / mean(interarrival) and sample exponential delays. (A full
    non-homogeneous Poisson process would modulate ``mu`` by time-of-day; for
    v0.1 we keep a single rolling-window rate, which is the NHPP restricted to
    the current window.)

``hawkes``
    A self-exciting Hawkes process with an exponential kernel:

        lambda*(t) = mu + sum_{t_i < t} alpha * beta * exp(-beta * (t - t_i))

    where ``mu`` is the background rate, ``alpha`` the branching ratio
    (expected number of children per event, must be < 1 for stability), and
    ``beta`` the decay rate of excitation. Bursty human activity is well
    described by this family (standard in queueing / network-traffic modeling,
    README §5.3). We fit (mu, alpha, beta) by maximum likelihood and sample the
    next delay with Ogata's thinning algorithm.

Perturbation. ``sample_next_delay_ms`` draws from a perturbed copy of the fit.
The perturbation scales the *rate* by a factor drawn near 1.0 with spread set
by ``SchedulerConfig.perturbation`` (0 => exact fit, 1 => up to ~2x slower /
faster). Small perturbations keep the sampled distribution close (small KL) to
the real one, which is the documented default.

Session-level interleaving. ``interleave_sessions`` merges real and decoy
session start-times so that *whole sessions* alternate on the timeline rather
than individual turns (mixing protein-folding and risotto turns inside one
conversation is a tell, README §5.3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

from .config import SchedulerConfig
from .models import QueryKind, Session

_MIN_DELAY_MS = 1  # never emit a non-positive delay
_DEFAULT_DELAY_MS = 5 * 60 * 1000  # fallback rate when we have no data: 5 min


@dataclass
class HawkesParams:
    """Fitted exponential-kernel Hawkes parameters (rates in events / ms)."""

    mu: float
    alpha: float  # branching ratio (0 <= alpha < 1)
    beta: float  # excitation decay (1/ms)


@dataclass
class _Fit:
    process: str
    mu: float  # base rate, events per ms
    hawkes: HawkesParams | None = field(default=None)
    history_ms: list[float] = field(default_factory=list)  # event times within window


class BehavioralScheduler:
    """Fit a point process to real interarrivals; sample perturbed decoy delays."""

    def __init__(self, config: SchedulerConfig | None = None):
        self.config = config or SchedulerConfig()
        self._fit: _Fit | None = None

    # ------------------------------------------------------------------ fit
    def fit(self, timestamps_ms: list[int]) -> None:
        """Fit the configured process to absolute event timestamps (ms).

        Only events inside the rolling window (``rolling_window_days`` ending at
        the last timestamp) are used. With < 2 events we fall back to a default
        background rate so sampling still produces plausible delays.
        """
        process = self.config.process
        ts = sorted(float(t) for t in timestamps_ms)

        if len(ts) >= 2:
            window_ms = self.config.rolling_window_days * 86_400_000
            cutoff = ts[-1] - window_ms
            ts = [t for t in ts if t >= cutoff]

        if len(ts) < 2:
            # Not enough data: homogeneous Poisson at the default rate.
            self._fit = _Fit(process=process, mu=1.0 / _DEFAULT_DELAY_MS)
            return

        # shift so the window starts at 0 (numerically friendlier)
        t0 = ts[0]
        shifted = [t - t0 for t in ts]
        interarrivals = np.diff(shifted)
        interarrivals = interarrivals[interarrivals > 0]
        mean_ia = float(interarrivals.mean()) if interarrivals.size else _DEFAULT_DELAY_MS
        base_mu = 1.0 / max(mean_ia, 1.0)

        if process == "hawkes":
            self._fit = _Fit(
                process=process,
                mu=base_mu,
                hawkes=self._fit_hawkes(np.asarray(shifted, dtype=float), base_mu),
                history_ms=shifted,
            )
        else:  # poisson / nhpp
            self._fit = _Fit(process=process, mu=base_mu, history_ms=shifted)

    # --------------------------------------------------------- hawkes MLE
    @staticmethod
    def _hawkes_neg_loglik(
        params: np.ndarray, events: np.ndarray, t_end: float
    ) -> float:
        """Negative log-likelihood of an exp-kernel Hawkes process.

        log L = sum_i log(lambda*(t_i)) - integral_0^T lambda*(t) dt

        Using the standard recursive form for the excitation sum to keep the
        likelihood O(n) rather than O(n^2).
        """
        mu, alpha, beta = params
        if mu <= 0 or alpha < 0 or alpha >= 1 or beta <= 0:
            return 1e12

        # recursive excitation term A_i = sum_{j<i} exp(-beta (t_i - t_j))
        loglik = 0.0
        a = 0.0
        prev = events[0]
        loglik += math.log(mu)  # first event has no predecessors
        for i in range(1, len(events)):
            dt = events[i] - prev
            a = math.exp(-beta * dt) * (1.0 + a)
            intensity = mu + alpha * beta * a
            if intensity <= 0:
                return 1e12
            loglik += math.log(intensity)
            prev = events[i]

        # compensator: integral of lambda over [0, t_end]
        compensator = mu * t_end
        for ti in events:
            compensator += alpha * (1.0 - math.exp(-beta * (t_end - ti)))

        return -(loglik - compensator)

    def _fit_hawkes(self, events: np.ndarray, base_mu: float) -> HawkesParams:
        t_end = float(events[-1])
        # reasonable inits: half the mass to background, modest branching, decay
        # over ~one mean-interarrival.
        mean_ia = float(np.diff(events).mean()) or 1.0
        x0 = np.array([base_mu * 0.7, 0.4, 1.0 / mean_ia])
        bounds = [
            (1e-12, None),  # mu > 0
            (0.0, 0.95),  # alpha in [0, 0.95) for stability
            (1e-12, None),  # beta > 0
        ]
        try:
            res = minimize(
                self._hawkes_neg_loglik,
                x0,
                args=(events, t_end),
                method="L-BFGS-B",
                bounds=bounds,
            )
            mu, alpha, beta = res.x
            if not (np.isfinite(mu) and np.isfinite(alpha) and np.isfinite(beta)):
                raise ValueError("non-finite fit")
        except Exception:
            mu, alpha, beta = base_mu * 0.7, 0.4, 1.0 / mean_ia
        return HawkesParams(mu=float(mu), alpha=float(alpha), beta=float(beta))

    # ------------------------------------------------------------- sampling
    def _perturb_factor(self, rng: np.random.Generator) -> float:
        """Multiplicative rate perturbation centered at 1.0.

        Spread grows with ``config.perturbation``. perturbation=0 => factor 1
        (exact fit, zero KL); larger values draw a lognormal factor with sigma
        proportional to the knob, keeping KL small for small knob values.
        """
        p = float(self.config.perturbation)
        if p <= 0:
            return 1.0
        sigma = 0.5 * p  # modest spread; small p => near-1 factor => small KL
        return float(math.exp(rng.normal(0.0, sigma)))

    def sample_next_delay_ms(self, rng: np.random.Generator) -> int:
        """Sample the delay (ms) until the next decoy event.

        Draws from a *perturbed* copy of the fitted process. Always returns a
        strictly positive integer.
        """
        if self._fit is None:
            # Unfitted: degrade to a perturbed default-rate exponential.
            rate = (1.0 / _DEFAULT_DELAY_MS) * self._perturb_factor(rng)
            return max(_MIN_DELAY_MS, int(rng.exponential(1.0 / rate)))

        factor = self._perturb_factor(rng)

        if self._fit.process == "hawkes" and self._fit.hawkes is not None:
            delay = self._sample_hawkes_delay(rng, factor)
        else:
            rate = max(self._fit.mu * factor, 1e-15)
            delay = rng.exponential(1.0 / rate)

        return max(_MIN_DELAY_MS, int(round(delay)))

    def _sample_hawkes_delay(
        self, rng: np.random.Generator, factor: float
    ) -> float:
        """Ogata thinning: sample the next event time given fitted history.

        Perturbation scales mu and alpha by ``factor`` (slows/speeds the whole
        process while keeping the kernel shape, i.e. small KL for small knob).
        """
        h = self._fit.hawkes
        assert h is not None
        mu = h.mu * factor
        alpha = min(h.alpha * factor, 0.999)
        beta = h.beta

        hist = np.asarray(self._fit.history_ms, dtype=float)
        t_last = float(hist[-1]) if hist.size else 0.0

        # current excitation contribution from history, evaluated at t_last
        def excitation(t: float) -> float:
            if hist.size == 0:
                return 0.0
            return float(
                np.sum(alpha * beta * np.exp(-beta * (t - hist[hist <= t])))
            )

        t = t_last
        # safety cap on iterations to avoid pathological loops
        for _ in range(100_000):
            lam_bar = mu + excitation(t)  # upper bound at current t (decreasing)
            lam_bar = max(lam_bar, 1e-15)
            t += rng.exponential(1.0 / lam_bar)
            lam_t = mu + excitation(t)
            if rng.random() <= lam_t / lam_bar:
                return t - t_last
        # fell through: return an exponential at background rate
        return rng.exponential(1.0 / max(mu, 1e-15))

    # -------------------------------------------------- session interleaving
    def interleave_sessions(
        self,
        real_sessions: list[Session],
        decoy_sessions: list[Session],
    ) -> list[Session]:
        """Order real and decoy sessions on a single timeline (README §5.3).

        Interleaving is at the **session** level: each session keeps all of its
        turns contiguous, and we merge whole sessions by their ``started_ms`` so
        decoy and real conversations alternate without ever mixing topics inside
        one conversation.
        """
        if not self.config.interleave_at_session_level:
            return list(real_sessions) + list(decoy_sessions)
        merged = list(real_sessions) + list(decoy_sessions)
        merged.sort(key=lambda s: s.started_ms)
        return merged

    def schedule_decoy_sessions(
        self,
        decoy_sessions: list[Session],
        rng: np.random.Generator,
        start_ms: int,
    ) -> list[Session]:
        """Assign perturbed start times to decoy sessions from ``start_ms``.

        Mutates each session's ``started_ms`` so successive decoy *sessions* are
        spaced by sampled interarrival delays (turn timing within a session is
        the engagement simulator's concern, §5.4).
        """
        t = int(start_ms)
        for session in decoy_sessions:
            t += self.sample_next_delay_ms(rng)
            session.started_ms = t
            session.kind = QueryKind.DECOY
        return decoy_sessions
