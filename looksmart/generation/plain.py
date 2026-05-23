"""PLAIN Mode -- persona-coherent content, no special register treatment (§5.5).

The baseline decoy: a single persona-conditioned query with no register chaos,
no fence-band edginess, no spectrum balancing. Content comes from the persona
context's seed prompts when provided, otherwise from the local LLM under a
persona system prompt. Routed through the curator like every other mode.
"""

from __future__ import annotations

import random

from ..models import GenerationMode, Query
from .base import DecoyGenerator

_GENERIC_SEEDS = [
    "What's a good way to organize a weekly meal plan for a family of four?",
    "How do I fix a leaky faucet without calling a plumber?",
    "What are some beginner tips for starting a vegetable garden?",
    "How do small businesses usually handle their first hire?",
    "What's the best way to back up photos from my phone?",
]


class PlainGenerator(DecoyGenerator):
    """Persona-coherent baseline decoy generator."""

    mode = GenerationMode.PLAIN

    def _draft(self, persona_ctx: dict, rng: random.Random) -> Query:
        seeds = persona_ctx.get("seed_prompts") or _GENERIC_SEEDS
        topic = persona_ctx.get("topic")
        if persona_ctx.get("use_llm"):
            system = persona_ctx.get(
                "system",
                "You are a persona generating a single ordinary, benign question.",
            )
            base = rng.choice(seeds)
            text = self.llm.generate(base, system=system, temperature=0.8).strip() or base
        else:
            text = rng.choice(seeds)
        return self._query(text, persona_ctx, category="plain", topic=topic)
