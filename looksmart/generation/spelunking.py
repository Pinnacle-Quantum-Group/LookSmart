"""Spelunking Mode -- vague-description identification queries (README §5.11).

"Who was that guy who...", "what was that movie where...", "what's the word for
when you...". A real productivity workflow AND profile-dilution-friendly cover
(the query is about third parties, not the user). Default-on mode.

Generates a multi-turn :class:`Session`: an initial vague-description query plus
``follow_up_rate``-gated "no, the OTHER one" negotiation turns, which produce
engagement-signal density (§5.4) organically.
"""

from __future__ import annotations

import random

from ..models import GenerationMode, Session
from .base import DecoyGenerator

SPELUNKING_CATEGORIES = [
    "public_figures",
    "musicians_and_bands",
    "films_and_tv",
    "books_and_authors",
    "historical_events",
    "products_and_brands",
    "technical_terms",
    "art_and_artists",
    "obscure_factoids",
]

# Stylized opener templates by category (the recognizable "workflow" phrasings).
_OPENERS: dict[str, list[str]] = {
    "public_figures": [
        "Who was that guy on stage who had mutton chops and told everyone with "
        "a smartphone they're an intel officer?",
        "Who was that British prime minister who resigned over a scandal in the "
        "70s, the one with the pipe?",
    ],
    "musicians_and_bands": [
        "What was that band from the 90s with the one-word name and the song "
        "about a river?",
        "Who sang that song that goes kind of doo-doo-doo, it was in a car ad?",
    ],
    "films_and_tv": [
        "What was that movie where the guy wakes up and the whole town is fake?",
        "What's that show with the chemistry teacher who goes bad, but the "
        "older British one, not the American one?",
    ],
    "books_and_authors": [
        "Who wrote that book about a lighthouse where nothing really happens but "
        "it's supposed to be a masterpiece?",
        "What was that sci-fi novel where the desert planet has giant worms?",
    ],
    "historical_events": [
        "What was that battle where a small force held a mountain pass against a "
        "huge army, the ancient one?",
        "What was the name of that financial panic in the 1800s with the railroads?",
    ],
    "products_and_brands": [
        "What was that soda from the 90s that was clear, like a clear cola?",
        "What's that gadget that everyone had clipped to their belt before phones?",
    ],
    "technical_terms": [
        "What's the word for when a program keeps a file open and won't let go?",
        "What do you call it when a website remembers you between visits, the "
        "little file thing?",
    ],
    "art_and_artists": [
        "Bosh older artist if memnory serves me slightly aniumated bizarre "
        "tortured images demons and such",
        "Who was that painter who did the melting clocks, was he the mustache guy?",
    ],
    "obscure_factoids": [
        "What's that thing where you feel like you've already lived a moment "
        "before?",
        "What's the word for that smell after it rains?",
    ],
}

_FOLLOWUPS = [
    "No, the OTHER one -- earlier than that, like the 80s.",
    "Hmm, not quite. It had more of a beard, I think.",
    "Closer, but it was definitely European, not American.",
    "That rings a bell actually -- can you say more about that one?",
    "Maybe? The cover was green if that helps.",
    "No, older. Like decades older.",
]


class SpelunkingGenerator(DecoyGenerator):
    """Vague-description identification-query generator (§5.11)."""

    mode = GenerationMode.SPELUNKING

    def _draft(self, persona_ctx: dict, rng: random.Random) -> Session:
        cfg = self.config
        cats = list(getattr(cfg, "categories", None) or SPELUNKING_CATEGORIES)
        cats = [c for c in cats if c in _OPENERS] or SPELUNKING_CATEGORIES
        category = rng.choice(cats)
        vagueness = float(getattr(cfg, "vagueness", 0.5))
        follow_up_rate = float(getattr(cfg, "follow_up_rate", 0.7))

        opener = rng.choice(_OPENERS[category])
        prompts = [opener]

        # follow-up negotiation turns -- the §5.11 "no, the OTHER one" pattern
        max_follow = 3
        for _ in range(max_follow):
            if rng.random() < follow_up_rate:
                prompts.append(rng.choice(_FOLLOWUPS))
            else:
                break

        return self._session(
            persona_ctx,
            prompts,
            category=category,
            vagueness=vagueness,
            follow_up_turns=len(prompts) - 1,
        )
