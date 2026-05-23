"""OpenAI / ChatGPT adapter (README §5.7).

Targets the Chat Completions API: ``POST /v1/chat/completions`` with a
Bearer token. Exposes an engagement surface (the ChatGPT product exposes
thumbs/regenerate; the public API does not have a feedback endpoint, so the
signal is recorded locally and treated as best-effort).
"""

from __future__ import annotations


from ..models import EngagementType, ProviderResponse
from .base import ProviderAdapter

_DEFAULT_BASE = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o"


class OpenAIAdapter(ProviderAdapter):
    HAS_ENGAGEMENT = True

    class_ts_notes = (
        "OpenAI: Usage Policies + Service Terms restrict automated/programmatic "
        "use that circumvents intended use and prohibit interfering with the "
        "service. Per-account rate limits are published; calibrate "
        "rate_limit_per_min to your tier. Decoy submission is a gray area; "
        "multi-turn engagement simulation is the highest-risk action (README "
        "§7). Use the user's own API key only. Not legal advice."
    )

    def __init__(self, cfg, *, base_url: str = _DEFAULT_BASE,
                 model: str = _DEFAULT_MODEL, **kw):
        super().__init__(cfg, **kw)
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _raw_complete(self, messages: list[dict]) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.9,
        }
        resp = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.credential}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse(self, raw: dict) -> ProviderResponse:
        choices = raw.get("choices") or []
        text = ""
        finish = None
        if choices:
            text = (choices[0].get("message") or {}).get("content") or ""
            finish = choices[0].get("finish_reason")
        truncated = finish == "length"
        refused = finish == "content_filter" or self._looks_refused(text)
        return ProviderResponse(
            text=text,
            provider=self.name,
            refused=refused,
            truncated=truncated,
            raw=raw,
        )

    def _send_engagement(self, response: ProviderResponse,
                         signal: EngagementType) -> bool:
        # The OpenAI API has no public feedback endpoint; regenerate is the
        # only signal expressible as another API call. Thumbs are recorded
        # locally by the caller. Report regenerate as deliverable.
        return signal == EngagementType.REGENERATE
