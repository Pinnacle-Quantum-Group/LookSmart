"""Provider adapter base class (README §5.7).

A `ProviderAdapter` is the pluggable seam between LookSmart's traffic
scheduler and a concrete LLM provider's HTTP API. Each adapter:

* authenticates with the *user's own* credentials, read from the env var
  named in :class:`looksmart.config.ProviderConfig.credential_env`;
* enforces a client-side rate limit calibrated to the provider's stated
  per-minute limit (README §7 mitigation) using a token-bucket limiter;
* retries transient/429 failures with exponential backoff + jitter, honoring
  a ``Retry-After`` header when the provider supplies one;
* maps a provider response to the frozen :class:`ProviderResponse`, including
  refusal and truncation detection;
* exposes an optional engagement-signal surface (thumbs / regenerate) that
  no-ops on providers that do not offer one.

The single network call is isolated in :meth:`_raw_complete` so tests can
monkeypatch it and never touch the network.
"""

from __future__ import annotations

import os
import threading
import time
from abc import ABC, abstractmethod
from collections import deque

import httpx

from ..config import ProviderConfig
from ..models import (
    EngagementType,
    ProviderResponse,
    Query,
    Session,
)


class ProviderError(RuntimeError):
    """Raised when a provider request fails non-recoverably."""


class RateLimiter:
    """Sliding-window rate limiter (README §5.7 "rate-limit awareness").

    Allows at most ``max_per_min`` acquisitions in any rolling 60-second
    window. ``acquire`` blocks (via the injected ``sleep``) until a slot frees
    up. ``time_fn``/``sleep`` are injectable so tests can drive a fake clock
    and assert that throttling actually happened without real wall-clock waits.
    """

    def __init__(
        self,
        max_per_min: int,
        *,
        time_fn=time.monotonic,
        sleep=time.sleep,
        window_s: float = 60.0,
    ) -> None:
        self.max_per_min = max(0, int(max_per_min))
        self.window_s = window_s
        self._time = time_fn
        self._sleep = sleep
        self._events: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self.max_per_min <= 0:
            return
        while True:
            with self._lock:
                now = self._time()
                self._evict(now)
                if len(self._events) < self.max_per_min:
                    self._events.append(now)
                    return
                # Oldest event must age out of the window before a slot frees.
                wait = self.window_s - (now - self._events[0])
            if wait > 0:
                self._sleep(wait)
            else:
                # Clock advanced under us; loop to re-evict.
                continue

    def _evict(self, now: float) -> None:
        horizon = now - self.window_s
        while self._events and self._events[0] <= horizon:
            self._events.popleft()


# Substrings that strongly indicate a policy refusal in plain-text output.
_REFUSAL_MARKERS = (
    "i can't help with that",
    "i can't assist with that",
    "i cannot help with that",
    "i cannot assist with that",
    "i'm unable to help",
    "i am unable to help",
    "i won't be able to help",
    "i can't provide",
    "i cannot provide",
    "i'm not able to provide",
    "as an ai",  # weak, but combined with refusal phrasing below
    "i'm sorry, but i can't",
    "i'm sorry, but i cannot",
)


class ProviderAdapter(ABC):
    """Abstract base for all provider plugins (README §5.7)."""

    #: Per-provider Terms-of-Service posture string (README §7). Subclasses set
    #: a class-level value; instances expose it via :attr:`ts_notes`.
    class_ts_notes: str = (
        "Generic posture: most LLM provider ToS prohibit 'automated use' or "
        "'circumvention of intended use'. Decoy/cover traffic sits in a gray "
        "area; engagement simulation is the largest ToS-risk vector (README "
        "§7). Not legal advice; counsel review required."
    )

    #: Whether this provider exposes an engagement-signal API (thumbs/regen).
    HAS_ENGAGEMENT: bool = False

    # Backoff tuning (overridable per adapter / per test).
    max_retries: int = 4
    backoff_base_s: float = 0.5
    backoff_cap_s: float = 30.0

    def __init__(
        self,
        cfg: ProviderConfig,
        *,
        client: httpx.Client | None = None,
        time_fn=time.monotonic,
        sleep=time.sleep,
        rng=None,
    ) -> None:
        self.cfg = cfg
        self.name = cfg.name
        self._sleep = sleep
        self._time = time_fn
        self._client = client
        self._owns_client = client is None
        self.rate_limiter = RateLimiter(
            cfg.rate_limit_per_min, time_fn=time_fn, sleep=sleep
        )
        # Jitter source; deterministic in tests when a seeded Random is passed.
        if rng is None:
            import random

            rng = random.Random()
        self._rng = rng

    # -- credential handling (user's own keys; never hardcoded) ------------
    @property
    def credential(self) -> str:
        env = self.cfg.credential_env
        if not env:
            raise ProviderError(
                f"provider '{self.name}' has no credential_env configured"
            )
        val = os.environ.get(env)
        if not val:
            raise ProviderError(
                f"credential env var '{env}' is unset for provider '{self.name}'"
            )
        return val

    @property
    def ts_notes(self) -> str:
        return self.class_ts_notes

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
            self._owns_client = True
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "ProviderAdapter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- engagement surface (README §5.7) ----------------------------------
    def supports_engagement(self) -> bool:
        return self.HAS_ENGAGEMENT

    def send_engagement(
        self, response: ProviderResponse, signal: EngagementType
    ) -> bool:
        """Emit an engagement signal (thumbs/regenerate/etc.).

        Returns True if the signal was delivered. The base implementation
        no-ops and returns False for providers without an engagement API so
        callers can treat the surface uniformly.
        """
        if not self.supports_engagement():
            return False
        return self._send_engagement(response, signal)

    def _send_engagement(
        self, response: ProviderResponse, signal: EngagementType
    ) -> bool:  # pragma: no cover - overridden by engagement-capable adapters
        return False

    # -- core send path ----------------------------------------------------
    def send(self, query: Query) -> ProviderResponse:
        """Send a single query, returning a parsed :class:`ProviderResponse`."""
        return self.send_session_messages(
            [{"role": "user", "content": query.text}]
        )

    def send_session(self, session: Session) -> list[ProviderResponse]:
        """Drive a multi-turn :class:`Session`.

        Conversation context accumulates across turns (provider session
        semantics, README §5.7). Returns one response per user turn.
        """
        responses: list[ProviderResponse] = []
        messages: list[dict] = []
        for turn in sorted(session.turns, key=lambda t: t.index):
            messages.append({"role": "user", "content": turn.prompt})
            resp = self.send_session_messages(messages)
            responses.append(resp)
            turn.response = resp.text
            messages.append({"role": "assistant", "content": resp.text})
        return responses

    def send_session_messages(self, messages: list[dict]) -> ProviderResponse:
        """Rate-limit, retry-with-backoff, then parse one completion."""
        self.rate_limiter.acquire()
        started = self._time()
        raw = self._with_backoff(messages)
        latency_ms = int((self._time() - started) * 1000)
        resp = self._parse(raw)
        if resp.latency_ms is None:
            resp.latency_ms = latency_ms
        return resp

    def _with_backoff(self, messages: list[dict]) -> dict:
        attempt = 0
        while True:
            try:
                return self._raw_complete(messages)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                retryable = status == 429 or 500 <= status < 600
                if not retryable or attempt >= self.max_retries:
                    raise ProviderError(
                        f"{self.name} request failed: HTTP {status}"
                    ) from exc
                self._sleep(self._backoff_delay(attempt, exc.response))
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise ProviderError(
                        f"{self.name} transport error: {exc}"
                    ) from exc
                self._sleep(self._backoff_delay(attempt, None))
            attempt += 1

    def _backoff_delay(self, attempt: int, response: httpx.Response | None) -> float:
        # Honor Retry-After when present (seconds form).
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(float(retry_after), self.backoff_cap_s)
                except ValueError:
                    pass
        exp = self.backoff_base_s * (2 ** attempt)
        exp = min(exp, self.backoff_cap_s)
        # Full jitter (AWS architecture blog): uniform in [0, exp].
        return self._rng.uniform(0, exp)

    # -- provider-specific seams (subclasses implement) --------------------
    @abstractmethod
    def _raw_complete(self, messages: list[dict]) -> dict:
        """Perform the single HTTP round-trip and return the parsed JSON body.

        Must raise ``httpx.HTTPStatusError`` on non-2xx so the backoff layer
        can react. Tests monkeypatch this method to return canned payloads.
        """

    @abstractmethod
    def _parse(self, raw: dict) -> ProviderResponse:
        """Map a raw JSON body to a :class:`ProviderResponse`."""

    # -- shared helpers ----------------------------------------------------
    @staticmethod
    def _looks_refused(text: str) -> bool:
        low = text.strip().lower()
        if not low:
            return False
        return any(marker in low for marker in _REFUSAL_MARKERS)
