"""Google Gemini adapter (README §5.7).

Targets the Generative Language API:
``POST /v1beta/models/{model}:generateContent`` with the API key passed as a
``x-goog-api-key`` header. Gemini uses ``contents`` with ``role`` ("user" /
"model") and ``parts: [{text}]``; system prompts ride ``systemInstruction``.
"""

from __future__ import annotations

from ..models import ProviderResponse
from .base import ProviderAdapter

_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "gemini-1.5-pro"


class GeminiAdapter(ProviderAdapter):
    HAS_ENGAGEMENT = False

    class_ts_notes = (
        "Google Gemini: Generative AI Prohibited Use Policy + API Terms "
        "restrict abuse, automated scraping, and circumvention of usage "
        "limits. Free-tier and paid quotas differ; calibrate "
        "rate_limit_per_min accordingly. Decoy traffic is unsettled; multi-turn "
        "engagement simulation is the highest-risk action (README §7). User's "
        "own API key only. Not legal advice."
    )

    def __init__(self, cfg, *, base_url: str = _DEFAULT_BASE,
                 model: str = _DEFAULT_MODEL, **kw):
        super().__init__(cfg, **kw)
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _to_contents(self, messages: list[dict]) -> tuple[dict | None, list[dict]]:
        system = None
        contents = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                system = {"parts": [{"text": m["content"]}]}
                continue
            g_role = "model" if role == "assistant" else "user"
            contents.append({"role": g_role, "parts": [{"text": m["content"]}]})
        return system, contents

    def _raw_complete(self, messages: list[dict]) -> dict:
        system, contents = self._to_contents(messages)
        payload: dict = {
            "contents": contents,
            "generationConfig": {"temperature": 0.9},
        }
        if system:
            payload["systemInstruction"] = system
        resp = self.client.post(
            f"{self.base_url}/models/{self.model}:generateContent",
            headers={
                "x-goog-api-key": self.credential,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse(self, raw: dict) -> ProviderResponse:
        candidates = raw.get("candidates") or []
        text = ""
        finish = None
        if candidates:
            finish = candidates[0].get("finishReason")
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts)
        truncated = finish == "MAX_TOKENS"
        # Gemini blocks via promptFeedback.blockReason or SAFETY finish reason.
        block = (raw.get("promptFeedback") or {}).get("blockReason")
        refused = (
            finish in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT")
            or bool(block)
            or self._looks_refused(text)
        )
        return ProviderResponse(
            text=text,
            provider=self.name,
            refused=refused,
            truncated=truncated,
            raw=raw,
        )
