"""Provider-adapter plugin layer (README §5.7).

Each adapter sends the user's traffic (real + decoy) to a concrete LLM
provider's HTTP API using the *user's own* credentials, surfacing a
per-provider Terms-of-Service posture (README §7).
"""

from __future__ import annotations

from .anthropic import AnthropicAdapter
from .base import ProviderAdapter, ProviderError, RateLimiter
from .gemini import GeminiAdapter
from .grok import GrokAdapter
from .openai import OpenAIAdapter
from .registry import build_adapter, register_adapter

__all__ = [
    "ProviderAdapter",
    "ProviderError",
    "RateLimiter",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "GeminiAdapter",
    "GrokAdapter",
    "build_adapter",
    "register_adapter",
]
