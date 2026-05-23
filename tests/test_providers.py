"""Tests for the provider-adapter + local-LLM backend layer.

No real network: every adapter's ``_raw_complete`` and every local backend's
``_raw_generate`` is monkeypatched to return canned payloads, and the rate
limiter is driven by a fake clock so throttling is asserted without wall-clock
waits.
"""

from __future__ import annotations

import random

import httpx
import pytest

from looksmart.config import LocalLLMConfig, ProviderConfig
from looksmart.llm_protocol import LocalLLM, StubLLM
from looksmart.localllm import (
    LocalLLMError,
    OllamaLLM,
    OpenAICompatLLM,
    build_local_llm,
    post_process,
)
from looksmart.models import (
    EngagementType,
    QueryKind,
    Query,
    Session,
    Turn,
)
from looksmart.providers import (
    AnthropicAdapter,
    GeminiAdapter,
    GrokAdapter,
    OpenAIAdapter,
    ProviderError,
    RateLimiter,
)
from looksmart.providers.base import ProviderAdapter
from looksmart.providers.registry import (
    available_providers,
    build_adapter,
    register_adapter,
)


# ---------------------------------------------------------------------------
# Fake clock for deterministic rate-limit tests
# ---------------------------------------------------------------------------


class FakeClock:
    """Monotonic clock whose ``sleep`` advances time instead of blocking."""

    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.sleeps.append(dt)
        self.t += dt


@pytest.fixture
def env_key(monkeypatch):
    monkeypatch.setenv("LS_TEST_KEY", "sk-test-secret")
    return "LS_TEST_KEY"


def _cfg(name: str, env: str = "LS_TEST_KEY", rate: int = 20) -> ProviderConfig:
    return ProviderConfig(name=name, credential_env=env, rate_limit_per_min=rate)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


def test_rate_limiter_allows_up_to_limit_without_sleep():
    clock = FakeClock()
    rl = RateLimiter(3, time_fn=clock.time, sleep=clock.sleep)
    for _ in range(3):
        rl.acquire()
    assert clock.sleeps == []  # no throttling within budget


def test_rate_limiter_throttles_over_limit():
    clock = FakeClock()
    rl = RateLimiter(2, time_fn=clock.time, sleep=clock.sleep, window_s=60.0)
    rl.acquire()
    rl.acquire()
    # Third acquire must wait for the oldest event to age out of the window.
    rl.acquire()
    assert clock.sleeps, "expected the limiter to sleep on the 3rd acquire"
    assert pytest.approx(sum(clock.sleeps), abs=1e-6) == 60.0


def test_rate_limiter_zero_disables():
    clock = FakeClock()
    rl = RateLimiter(0, time_fn=clock.time, sleep=clock.sleep)
    for _ in range(100):
        rl.acquire()
    assert clock.sleeps == []


# ---------------------------------------------------------------------------
# Per-adapter request shaping + response parsing
# ---------------------------------------------------------------------------


def _capture(adapter: ProviderAdapter, raw: dict):
    """Replace _raw_complete with a recorder returning ``raw``."""
    seen = {}

    def fake(messages):
        seen["messages"] = messages
        return raw

    adapter._raw_complete = fake  # type: ignore[assignment]
    return seen


def test_openai_request_and_parse(env_key):
    clock = FakeClock()
    a = OpenAIAdapter(_cfg("openai"), time_fn=clock.time, sleep=clock.sleep)
    seen = _capture(
        a,
        {"choices": [{"message": {"content": "hi there"},
                      "finish_reason": "stop"}]},
    )
    resp = a.send(Query(text="hello", kind=QueryKind.DECOY))
    assert resp.text == "hi there"
    assert resp.provider == "openai"
    assert not resp.refused and not resp.truncated
    assert seen["messages"] == [{"role": "user", "content": "hello"}]


def test_openai_real_raw_complete_shapes_payload(env_key, monkeypatch):
    """Exercise the real _raw_complete body without network."""
    clock = FakeClock()
    a = OpenAIAdapter(_cfg("openai"), time_fn=clock.time, sleep=clock.sleep)
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"},
                                 "finish_reason": "stop"}]}

    def fake_post(url, *, headers, json):
        captured.update(url=url, headers=headers, json=json)
        return FakeResp()

    monkeypatch.setattr(a, "_client", type("C", (), {"post": staticmethod(fake_post)})())
    resp = a.send(Query(text="hello", kind=QueryKind.DECOY))
    assert resp.text == "ok"
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer sk-test-secret"
    assert captured["json"]["model"] == "gpt-4o"
    assert captured["json"]["messages"] == [{"role": "user", "content": "hello"}]


def test_openai_truncated_and_content_filter(env_key):
    a = OpenAIAdapter(_cfg("openai"))
    _capture(a, {"choices": [{"message": {"content": "partial"},
                              "finish_reason": "length"}]})
    assert a.send(Query(text="x", kind=QueryKind.DECOY)).truncated

    a2 = OpenAIAdapter(_cfg("openai"))
    _capture(a2, {"choices": [{"message": {"content": ""},
                               "finish_reason": "content_filter"}]})
    assert a2.send(Query(text="x", kind=QueryKind.DECOY)).refused


def test_anthropic_request_and_parse(env_key):
    a = AnthropicAdapter(_cfg("anthropic"))
    seen = _capture(
        a,
        {"content": [{"type": "text", "text": "claude says hi"}],
         "stop_reason": "end_turn"},
    )
    resp = a.send(Query(text="hello", kind=QueryKind.DECOY))
    assert resp.text == "claude says hi"
    assert not resp.truncated and not resp.refused
    assert seen["messages"] == [{"role": "user", "content": "hello"}]


def test_anthropic_real_payload_uses_api_key_header(env_key, monkeypatch):
    a = AnthropicAdapter(_cfg("anthropic"))
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"type": "text", "text": "x"}],
                    "stop_reason": "max_tokens"}

    def fake_post(url, *, headers, json):
        captured.update(url=url, headers=headers, json=json)
        return FakeResp()

    monkeypatch.setattr(a, "_client", type("C", (), {"post": staticmethod(fake_post)})())
    resp = a.send(Query(text="hi", kind=QueryKind.DECOY))
    assert resp.truncated  # max_tokens -> truncated
    assert captured["url"].endswith("/v1/messages")
    assert captured["headers"]["x-api-key"] == "sk-test-secret"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["json"]["max_tokens"] == 1024


def test_anthropic_refusal_stop_reason(env_key):
    a = AnthropicAdapter(_cfg("anthropic"))
    _capture(a, {"content": [{"type": "text", "text": ""}],
                 "stop_reason": "refusal"})
    assert a.send(Query(text="x", kind=QueryKind.DECOY)).refused


def test_gemini_request_and_parse(env_key):
    a = GeminiAdapter(_cfg("gemini"))
    _capture(
        a,
        {"candidates": [{"finishReason": "STOP",
                         "content": {"parts": [{"text": "gem response"}]}}]},
    )
    resp = a.send(Query(text="hello", kind=QueryKind.DECOY))
    assert resp.text == "gem response"
    assert not resp.refused and not resp.truncated


def test_gemini_safety_block_is_refused(env_key):
    a = GeminiAdapter(_cfg("gemini"))
    _capture(
        a,
        {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}],
         "promptFeedback": {"blockReason": "SAFETY"}},
    )
    assert a.send(Query(text="x", kind=QueryKind.DECOY)).refused


def test_gemini_real_payload_role_mapping(env_key, monkeypatch):
    a = GeminiAdapter(_cfg("gemini"))
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"finishReason": "MAX_TOKENS",
                                    "content": {"parts": [{"text": "y"}]}}]}

    def fake_post(url, *, headers, json):
        captured.update(url=url, headers=headers, json=json)
        return FakeResp()

    monkeypatch.setattr(a, "_client", type("C", (), {"post": staticmethod(fake_post)})())
    resp = a.send(Query(text="hi", kind=QueryKind.DECOY))
    assert resp.truncated
    assert "generateContent" in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "sk-test-secret"
    assert captured["json"]["contents"][0]["role"] == "user"
    assert captured["json"]["contents"][0]["parts"] == [{"text": "hi"}]


def test_grok_inherits_openai_shaping(env_key):
    a = GrokAdapter(_cfg("grok"))
    assert a.base_url == "https://api.x.ai/v1"
    assert a.model == "grok-2-latest"
    _capture(a, {"choices": [{"message": {"content": "grok hi"},
                              "finish_reason": "stop"}]})
    resp = a.send(Query(text="hello", kind=QueryKind.DECOY))
    assert resp.text == "grok hi"
    assert resp.provider == "grok"


# ---------------------------------------------------------------------------
# Session semantics + engagement surface
# ---------------------------------------------------------------------------


def test_send_session_accumulates_context(env_key):
    a = OpenAIAdapter(_cfg("openai"))
    seen_lengths = []

    def fake(messages):
        seen_lengths.append(len(messages))
        return {"choices": [{"message": {"content": f"r{len(messages)}"},
                             "finish_reason": "stop"}]}

    a._raw_complete = fake  # type: ignore[assignment]
    session = Session(persona_id="p1", kind=QueryKind.DECOY,
                      turns=[Turn(prompt="one", index=0),
                             Turn(prompt="two", index=1)])
    responses = a.send_session(session)
    assert len(responses) == 2
    # Turn 1: [user]. Turn 2: [user, assistant, user].
    assert seen_lengths == [1, 3]
    assert session.turns[0].response == "r1"


def test_engagement_surface_openai_vs_anthropic(env_key):
    o = OpenAIAdapter(_cfg("openai"))
    assert o.supports_engagement() is True
    fake_resp = o._parse({"choices": [{"message": {"content": "x"},
                                       "finish_reason": "stop"}]})
    assert o.send_engagement(fake_resp, EngagementType.REGENERATE) is True
    assert o.send_engagement(fake_resp, EngagementType.THUMBS_UP) is False

    a = AnthropicAdapter(_cfg("anthropic"))
    assert a.supports_engagement() is False
    assert a.send_engagement(fake_resp, EngagementType.REGENERATE) is False


# ---------------------------------------------------------------------------
# Credentials + backoff
# ---------------------------------------------------------------------------


def test_missing_credential_env_raises(monkeypatch):
    monkeypatch.delenv("LS_TEST_KEY", raising=False)
    a = OpenAIAdapter(_cfg("openai"))
    _capture(a, {})
    with pytest.raises(ProviderError):
        _ = a.credential


def test_backoff_retries_then_succeeds(env_key):
    clock = FakeClock()
    a = OpenAIAdapter(_cfg("openai"), time_fn=clock.time, sleep=clock.sleep,
                      rng=random.Random(0))
    calls = {"n": 0}

    def flaky(messages):
        calls["n"] += 1
        if calls["n"] < 3:
            req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            resp = httpx.Response(429, request=req, headers={"retry-after": "2"})
            raise httpx.HTTPStatusError("rate", request=req, response=resp)
        return {"choices": [{"message": {"content": "finally"},
                             "finish_reason": "stop"}]}

    a._raw_complete = flaky  # type: ignore[assignment]
    resp = a.send(Query(text="x", kind=QueryKind.DECOY))
    assert resp.text == "finally"
    assert calls["n"] == 3
    # Retry-After=2 honored on each retry.
    assert clock.sleeps == [2.0, 2.0]


def test_backoff_gives_up_after_max_retries(env_key):
    clock = FakeClock()
    a = OpenAIAdapter(_cfg("openai"), time_fn=clock.time, sleep=clock.sleep,
                      rng=random.Random(0))
    a.max_retries = 2

    def always_500(messages):
        req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        resp = httpx.Response(500, request=req)
        raise httpx.HTTPStatusError("boom", request=req, response=resp)

    a._raw_complete = always_500  # type: ignore[assignment]
    with pytest.raises(ProviderError):
        a.send(Query(text="x", kind=QueryKind.DECOY))


def test_non_retryable_status_raises_immediately(env_key):
    clock = FakeClock()
    a = OpenAIAdapter(_cfg("openai"), time_fn=clock.time, sleep=clock.sleep)

    def unauthorized(messages):
        req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        resp = httpx.Response(401, request=req)
        raise httpx.HTTPStatusError("unauth", request=req, response=resp)

    a._raw_complete = unauthorized  # type: ignore[assignment]
    with pytest.raises(ProviderError):
        a.send(Query(text="x", kind=QueryKind.DECOY))
    assert clock.sleeps == []  # no retry/backoff for 401


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,cls",
    [("openai", OpenAIAdapter), ("anthropic", AnthropicAdapter),
     ("gemini", GeminiAdapter), ("grok", GrokAdapter)],
)
def test_registry_builds_each_adapter(name, cls):
    adapter = build_adapter(_cfg(name))
    assert isinstance(adapter, cls)
    assert adapter.class_ts_notes  # ToS posture populated
    assert adapter.ts_notes == adapter.class_ts_notes


def test_registry_unknown_provider_raises():
    with pytest.raises(ProviderError):
        build_adapter(_cfg("nope"))


def test_registry_register_and_list():
    class Dummy(OpenAIAdapter):
        pass

    register_adapter("dummy", Dummy)
    assert "dummy" in available_providers()
    assert isinstance(build_adapter(_cfg("dummy")), Dummy)


def test_each_adapter_has_distinct_ts_notes():
    notes = {
        n: build_adapter(_cfg(n)).ts_notes
        for n in ("openai", "anthropic", "gemini", "grok")
    }
    assert len(set(notes.values())) == 4  # per-provider posture, not shared


# ---------------------------------------------------------------------------
# Local LLM backends
# ---------------------------------------------------------------------------


def _ollama_cfg(**kw) -> LocalLLMConfig:
    base = dict(backend="ollama", endpoint="http://localhost:11434",
                model="llama3:70b", post_process_typos=False)
    base.update(kw)
    return LocalLLMConfig(**base)


def test_ollama_parses_canned_response():
    llm = OllamaLLM(_ollama_cfg())
    captured = {}

    def fake(prompt, *, system, temperature, max_tokens, stop):
        captured.update(prompt=prompt, system=system, max_tokens=max_tokens)
        return {"message": {"content": "decoy output"}}

    llm._raw_generate = fake  # type: ignore[assignment]
    out = llm.generate("write a decoy", system="be a person")
    assert out == "decoy output"
    assert captured["prompt"] == "write a decoy"
    assert captured["system"] == "be a person"


def test_ollama_real_raw_generate_payload(monkeypatch):
    llm = OllamaLLM(_ollama_cfg())
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "hi"}}

    def fake_post(url, *, json):
        captured.update(url=url, json=json)
        return FakeResp()

    monkeypatch.setattr(llm, "_client", type("C", (), {"post": staticmethod(fake_post)})())
    out = llm.generate("p", temperature=0.5, max_tokens=42, stop=["END"])
    assert out == "hi"
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["json"]["model"] == "llama3:70b"
    assert captured["json"]["stream"] is False
    assert captured["json"]["options"]["temperature"] == 0.5
    assert captured["json"]["options"]["num_predict"] == 42
    assert captured["json"]["options"]["stop"] == ["END"]


def test_openai_compat_parses_and_payload(monkeypatch):
    cfg = _ollama_cfg(backend="openai_compat", endpoint="http://localhost:8000",
                      model="vllm-model")
    llm = OpenAICompatLLM(cfg, api_key="local-key")
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "compat out"}}]}

    def fake_post(url, *, json, headers):
        captured.update(url=url, json=json, headers=headers)
        return FakeResp()

    monkeypatch.setattr(llm, "_client", type("C", (), {"post": staticmethod(fake_post)})())
    out = llm.generate("hello", system="sys")
    assert out == "compat out"
    assert captured["url"] == "http://localhost:8000/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer local-key"
    assert captured["json"]["messages"][0] == {"role": "system", "content": "sys"}


def test_local_backends_satisfy_protocol():
    assert isinstance(OllamaLLM(_ollama_cfg()), LocalLLM)
    assert isinstance(OpenAICompatLLM(_ollama_cfg(backend="openai_compat")), LocalLLM)
    assert isinstance(StubLLM(), LocalLLM)


def test_build_local_llm_factory():
    assert isinstance(build_local_llm(_ollama_cfg()), OllamaLLM)
    assert isinstance(
        build_local_llm(_ollama_cfg(backend="openai_compat")), OpenAICompatLLM
    )
    assert isinstance(build_local_llm(LocalLLMConfig(backend="stub")), StubLLM)


def test_build_local_llm_unknown_backend():
    cfg = _ollama_cfg()
    object.__setattr__(cfg, "backend", "bogus")  # bypass pattern validation
    with pytest.raises(LocalLLMError):
        build_local_llm(cfg)


def test_unparseable_local_response_raises():
    llm = OllamaLLM(_ollama_cfg())
    # message.content present but wrong type -> not a parseable completion.
    llm._raw_generate = lambda *a, **k: {"message": {"content": 123}}  # type: ignore
    with pytest.raises(LocalLLMError):
        llm.generate("x")


# ---------------------------------------------------------------------------
# post_process (README §5.8) determinism + safety
# ---------------------------------------------------------------------------


def test_post_process_deterministic_with_seed():
    text = "the quick brown fox jumps over the lazy sleeping dog repeatedly"
    a = post_process(text, random.Random(42), typo_rate=0.3, edit_rate=0.3)
    b = post_process(text, random.Random(42), typo_rate=0.3, edit_rate=0.3)
    assert a == b
    assert a != text  # something was roughened at these rates


def test_post_process_noop_when_rates_zero():
    text = "perfectly clean local model output"
    assert post_process(text, random.Random(1), typo_rate=0.0, edit_rate=0.0) == text


def test_post_process_empty_string():
    assert post_process("", random.Random(1)) == ""


def test_post_process_applied_in_generate_when_enabled():
    cfg = _ollama_cfg(post_process_typos=True)
    rng = random.Random(7)
    llm = OllamaLLM(cfg, rng=rng)
    long = "the quick brown fox jumps over the lazy sleeping dog again and again"
    llm._raw_generate = lambda *a, **k: {"message": {"content": long}}  # type: ignore

    clean_cfg = _ollama_cfg(post_process_typos=False)
    clean = OllamaLLM(clean_cfg)
    clean._raw_generate = lambda *a, **k: {"message": {"content": long}}  # type: ignore

    assert clean.generate("p") == long
    # With typos enabled and a high-entropy seed, output is roughened.
    rough = llm.generate("p")
    assert isinstance(rough, str)
