"""Frozen local-LLM interface (README §5.8).

Decoy generators (§5.9-5.21) depend on this protocol; provider/local-LLM
backends implement it. Kept in its own module so generation and backend code
can be developed in parallel against a stable contract.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LocalLLM(Protocol):
    """A locally-hosted generation model used to synthesize decoy content."""

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.9,
        max_tokens: int = 512,
        stop: list[str] | None = None,
    ) -> str:
        """Return a single completion string for `prompt`."""
        ...


class StubLLM:
    """Deterministic stand-in for tests and offline development.

    Echoes a transformed prompt so generators can be exercised without a real
    model. Real backends live in `looksmart.localllm`.
    """

    def __init__(self, canned: str | None = None):
        self.canned = canned

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.9,
        max_tokens: int = 512,
        stop: list[str] | None = None,
    ) -> str:
        if self.canned is not None:
            return self.canned
        return f"[stub:{(system or 'none')[:16]}] {prompt[:max_tokens]}"
