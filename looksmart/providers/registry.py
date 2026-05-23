"""Adapter factory keyed on provider name (README §5.7).

``build_adapter`` maps a :class:`~looksmart.config.ProviderConfig` to a
concrete :class:`~looksmart.providers.base.ProviderAdapter`. New providers
register themselves through :func:`register_adapter` so the dispatch table is
open for extension without editing this module.
"""

from __future__ import annotations

from typing import Callable

from ..config import ProviderConfig
from .anthropic import AnthropicAdapter
from .base import ProviderAdapter, ProviderError
from .gemini import GeminiAdapter
from .grok import GrokAdapter
from .openai import OpenAIAdapter

#: name -> adapter class. Names match ProviderConfig.name (README §5.7).
_REGISTRY: dict[str, type[ProviderAdapter]] = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "gemini": GeminiAdapter,
    "grok": GrokAdapter,
}


def register_adapter(name: str, cls: type[ProviderAdapter]) -> None:
    """Register (or override) the adapter class for a provider name."""
    if not issubclass(cls, ProviderAdapter):
        raise TypeError(f"{cls!r} is not a ProviderAdapter subclass")
    _REGISTRY[name.lower()] = cls


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def build_adapter(cfg: ProviderConfig, **kwargs) -> ProviderAdapter:
    """Construct the adapter for ``cfg.name``.

    Extra keyword arguments (e.g. ``client``, ``time_fn``, ``sleep``, ``rng``,
    ``model``, ``base_url``) are forwarded to the adapter constructor, which is
    how tests inject fakes and how callers override defaults.
    """
    key = (cfg.name or "").lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        raise ProviderError(
            f"unknown provider '{cfg.name}'; known: {available_providers()}"
        )
    return cls(cfg, **kwargs)


# Convenience alias for callers that prefer an explicit factory type.
AdapterFactory = Callable[[ProviderConfig], ProviderAdapter]
