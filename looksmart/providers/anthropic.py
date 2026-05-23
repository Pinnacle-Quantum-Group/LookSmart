"""Anthropic / Claude adapter (README §5.7).

Targets the Messages API: ``POST /v1/messages`` with ``x-api-key`` and
``anthropic-version`` headers. Anthropic requires ``max_tokens`` and uses a
content-block list for output; system prompts ride a top-level ``system``
field rather than a message with role=system.
"""

from __future__ import annotations

from ..models import ProviderResponse
from .base import ProviderAdapter

_DEFAULT_BASE = "https://api.anthropic.com/v1"
_DEFAULT_MODEL = "claude-3-5-sonnet-latest"
_API_VERSION = "2023-06-01"


class AnthropicAdapter(ProviderAdapter):
    # The Messages API has no thumbs/regenerate engagement endpoint.
    HAS_ENGAGEMENT = False

    class_ts_notes = (
        "Anthropic: Usage Policy + Commercial Terms prohibit using the service "
        "to develop competing models and restrict abusive/automated patterns. "
        "Rate limits are tier-based and surfaced via response headers; honor "
        "Retry-After. Decoy cover traffic is unsettled ground; engagement "
        "simulation carries the most ToS risk (README §7). User's own key "
        "only. Not legal advice; counsel review required."
    )

    def __init__(self, cfg, *, base_url: str = _DEFAULT_BASE,
                 model: str = _DEFAULT_MODEL, max_tokens: int = 1024,
                 api_version: str = _API_VERSION, **kw):
        super().__init__(cfg, **kw)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.api_version = api_version

    def _split_system(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        system = None
        convo = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content")
            else:
                convo.append({"role": m["role"], "content": m["content"]})
        return system, convo

    def _raw_complete(self, messages: list[dict]) -> dict:
        system, convo = self._split_system(messages)
        payload: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": convo,
            "temperature": 0.9,
        }
        if system:
            payload["system"] = system
        resp = self.client.post(
            f"{self.base_url}/messages",
            headers={
                "x-api-key": self.credential,
                "anthropic-version": self.api_version,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse(self, raw: dict) -> ProviderResponse:
        blocks = raw.get("content") or []
        text = "".join(
            b.get("text", "") for b in blocks if b.get("type") == "text"
        )
        stop = raw.get("stop_reason")
        truncated = stop == "max_tokens"
        refused = stop == "refusal" or self._looks_refused(text)
        return ProviderResponse(
            text=text,
            provider=self.name,
            refused=refused,
            truncated=truncated,
            raw=raw,
        )
