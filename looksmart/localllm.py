"""Local-LLM backends for decoy generation (README §5.8).

Decoy content is synthesized by a *locally hosted* model so the user's real
credentials are never spent on cover-traffic generation and so generation
stays under the user's control. Two concrete backends implement the frozen
:class:`looksmart.llm_protocol.LocalLLM` protocol:

* :class:`OllamaLLM` -- talks to an Ollama server (``/api/chat``); the default.
* :class:`OpenAICompatLLM` -- talks to any OpenAI-compatible
  ``/v1/chat/completions`` endpoint (vLLM, LM Studio, llama.cpp server, ...).

README §5.8 mitigation: local-model output has a detectable distributional
cleanliness. :func:`post_process` roughens it by injecting realistic typos and
mid-stream edit artifacts. It is deterministic given a seeded ``rng`` and is a
no-op unless explicitly enabled (``LocalLLMConfig.post_process_typos``), so it
is off-by-default-safe at the call sites that don't opt in.

The single HTTP round-trip lives in :meth:`_HttpLocalLLM._raw_generate`, which
tests monkeypatch so no network is touched.
"""

from __future__ import annotations

import random
from typing import Callable

import httpx

from .config import LocalLLMConfig
from .llm_protocol import LocalLLM, StubLLM


class LocalLLMError(RuntimeError):
    """Raised when a local-LLM backend request fails."""


# ---------------------------------------------------------------------------
# Post-processing (README §5.8 distributional-cleanliness mitigation)
# ---------------------------------------------------------------------------

# Adjacent-key style swaps so injected typos look like plausible fat-finger
# slips rather than uniform random noise.
_ADJACENT = {
    "a": "s", "s": "a", "e": "r", "r": "e", "t": "y", "y": "t",
    "i": "o", "o": "i", "n": "m", "m": "n", "l": "k", "h": "g",
}


def post_process(
    text: str,
    rng: random.Random,
    *,
    typo_rate: float = 0.03,
    edit_rate: float = 0.04,
) -> str:
    """Roughen clean local-model output (README §5.8).

    Injects three kinds of human-like noise, each gated on ``rng`` so the
    result is fully deterministic for a seeded generator:

    * character transpositions / adjacent-key swaps (typos);
    * dropped characters;
    * mid-stream "edit" artifacts -- a word retyped after a correction marker
      (e.g. ``"teh*the"``), mimicking a user fixing themselves in-line.

    ``typo_rate`` / ``edit_rate`` are tunable. With both at 0 (or empty input)
    the function returns ``text`` unchanged, which keeps it off-by-default-safe.
    """
    if not text or (typo_rate <= 0 and edit_rate <= 0):
        return text

    words = text.split(" ")
    out: list[str] = []
    for word in words:
        if len(word) >= 4 and edit_rate > 0 and rng.random() < edit_rate:
            # Mid-stream edit artifact: mistype then "correct" inline.
            typo = _mangle(word, rng)
            if typo != word:
                out.append(f"{typo}*{word}")
                continue
        if typo_rate > 0 and rng.random() < typo_rate:
            out.append(_mangle(word, rng))
        else:
            out.append(word)
    return " ".join(out)


def _mangle(word: str, rng: random.Random) -> str:
    """Apply one realistic single-character corruption to ``word``."""
    letters = [i for i, c in enumerate(word) if c.isalpha()]
    if not letters:
        return word
    choice = rng.random()
    if choice < 0.34 and len(letters) >= 2:
        # Transpose two adjacent alphabetic characters.
        idx = rng.choice(letters[:-1])
        chars = list(word)
        chars[idx], chars[idx + 1] = chars[idx + 1], chars[idx]
        return "".join(chars)
    if choice < 0.67:
        # Adjacent-key substitution.
        idx = rng.choice(letters)
        chars = list(word)
        repl = _ADJACENT.get(chars[idx].lower())
        if repl is not None:
            chars[idx] = repl if chars[idx].islower() else repl.upper()
        return "".join(chars)
    # Drop a character.
    idx = rng.choice(letters)
    return word[:idx] + word[idx + 1 :]


# ---------------------------------------------------------------------------
# HTTP backends
# ---------------------------------------------------------------------------


class _HttpLocalLLM:
    """Shared plumbing for HTTP-backed local LLMs.

    Concrete subclasses build the request body / parse the response; the single
    network round-trip is isolated in :meth:`_raw_generate` for testability.
    """

    def __init__(
        self,
        cfg: LocalLLMConfig,
        *,
        client: httpx.Client | None = None,
        rng: random.Random | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.cfg = cfg
        self.endpoint = cfg.endpoint.rstrip("/")
        self.model = cfg.model
        self.post_process_typos = cfg.post_process_typos
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout
        self._rng = rng if rng is not None else random.Random()

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
            self._owns_client = True
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    # -- protocol surface --------------------------------------------------
    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.9,
        max_tokens: int = 512,
        stop: list[str] | None = None,
    ) -> str:
        raw = self._raw_generate(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
        )
        text = self._parse(raw)
        if self.post_process_typos:
            text = post_process(text, self._rng)
        return text

    # -- seams (overridden / monkeypatched) --------------------------------
    def _raw_generate(self, prompt, *, system, temperature, max_tokens, stop) -> dict:
        raise NotImplementedError

    def _parse(self, raw: dict) -> str:
        raise NotImplementedError


class OllamaLLM(_HttpLocalLLM):
    """Ollama backend (README §5.8 default). Uses ``POST /api/chat``."""

    def _raw_generate(self, prompt, *, system, temperature, max_tokens, stop) -> dict:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        options: dict = {"temperature": temperature, "num_predict": max_tokens}
        if stop:
            options["stop"] = stop
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        resp = self.client.post(f"{self.endpoint}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()

    def _parse(self, raw: dict) -> str:
        # Non-streaming Ollama chat returns {"message": {"content": ...}}.
        msg = raw.get("message") or {}
        text = msg.get("content")
        if text is None:
            text = raw.get("response", "")  # /api/generate fallback shape
        if not isinstance(text, str):
            raise LocalLLMError(f"unexpected Ollama response shape: {raw!r}")
        return text


class OpenAICompatLLM(_HttpLocalLLM):
    """OpenAI-compatible local server (vLLM, LM Studio, llama.cpp, ...).

    Uses ``POST /v1/chat/completions``. A local API key is optional; if the
    server requires one, set it via ``api_key``.
    """

    def __init__(self, cfg: LocalLLMConfig, *, api_key: str | None = None, **kw):
        super().__init__(cfg, **kw)
        self.api_key = api_key

    def _raw_generate(self, prompt, *, system, temperature, max_tokens, stop) -> dict:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop:
            payload["stop"] = stop
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = self.client.post(
            f"{self.endpoint}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse(self, raw: dict) -> str:
        choices = raw.get("choices") or []
        if not choices:
            raise LocalLLMError(f"no choices in response: {raw!r}")
        text = (choices[0].get("message") or {}).get("content")
        if not isinstance(text, str):
            raise LocalLLMError(f"unexpected completion shape: {raw!r}")
        return text


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_BACKENDS: dict[str, Callable[..., LocalLLM]] = {
    "ollama": OllamaLLM,
    "openai_compat": OpenAICompatLLM,
}


def build_local_llm(cfg: LocalLLMConfig, **kwargs) -> LocalLLM:
    """Build the configured local-LLM backend (README §5.8).

    ``backend="stub"`` returns the frozen :class:`StubLLM` for offline tests
    and development. Extra kwargs (``client``, ``rng``, ``api_key``) are
    forwarded to HTTP backends.
    """
    backend = (cfg.backend or "").lower()
    if backend == "stub":
        return StubLLM()
    ctor = _BACKENDS.get(backend)
    if ctor is None:
        raise LocalLLMError(
            f"unknown local LLM backend '{cfg.backend}'; "
            f"known: {sorted(_BACKENDS) + ['stub']}"
        )
    return ctor(cfg, **kwargs)
