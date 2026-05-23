"""xAI Grok adapter (README §5.7).

xAI ships an OpenAI-compatible Chat Completions API at
``https://api.x.ai/v1`` with Bearer auth, so request/response shaping mirrors
the OpenAI adapter while keeping a distinct ToS posture and default model.
"""

from __future__ import annotations

from .base import ProviderAdapter
from .openai import OpenAIAdapter

_DEFAULT_BASE = "https://api.x.ai/v1"
_DEFAULT_MODEL = "grok-2-latest"


class GrokAdapter(OpenAIAdapter):
    # xAI's API has no public feedback/regenerate endpoint distinct from
    # re-issuing a completion.
    HAS_ENGAGEMENT = False

    class_ts_notes = (
        "xAI Grok: Terms of Service prohibit abuse and automated use that "
        "circumvents the service; the API is OpenAI-compatible but governed by "
        "xAI's own usage policy and rate tiers. Decoy traffic is unsettled; "
        "engagement simulation is the highest-risk action (README §7). User's "
        "own API key only. Not legal advice."
    )

    def __init__(self, cfg, *, base_url: str = _DEFAULT_BASE,
                 model: str = _DEFAULT_MODEL, **kw):
        # Bypass OpenAIAdapter.__init__ defaults by passing explicit values.
        ProviderAdapter.__init__(self, cfg, **kw)
        self.base_url = base_url.rstrip("/")
        self.model = model
