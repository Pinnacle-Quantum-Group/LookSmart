"""Weird Al Mode -- register-chaos generator (README §5.9).

Deliberate cross-register mixing within single turns, with stochastic injection
of (a) semantic placeholder nouns that occupy grammatical slots without
resolvable referents, (b) cross-register fragments, (c) bursty (Poisson)
vulgarity tied to tone shifts, and (d) ambiguity-injection sentences that parse
but underdetermine.

The §5.9 live test case is the target output *density*:

    "Coming in from the squanch, hit you with a donkey punch, give jah the
     thanks and praises, I've been on my own for too long, so you can suck my
     dong, but you don't take too long."

-- six registers, three placeholder/invented terms, song-meter that matches no
specific song. We aim at that density: placeholder markers + at least two
registers when ``register_chaos`` is high.
"""

from __future__ import annotations

import random

from ..models import GenerationMode, Query
from .base import DecoyGenerator

# Semantic placeholder nouns (README §5.9 enumerates these explicitly).
PLACEHOLDER_NOUNS = [
    "squanch",
    "marglar",
    "da kine",
    "thingamajig",
    "whatchamacallit",
    "doohickey",
    "the wahoozit",
    "jawn",
    "the dingus",
    "the hoozit",
]

# Mild, calibrated vulgarity lexicon. Bursty injection, not uniform (§5.9).
# Deliberately kept to the "donkey punch / suck my dong" comedic-vulgar band of
# the live test case -- nothing that trips the curator's hard exclusions.
VULGAR_FRAGMENTS = [
    "you can suck my dong",
    "hit you with a donkey punch",
    "this whole damn thing",
    "ain't no bullshit",
    "give it the old hell-no",
]

# Register fragments keyed by register name. The config's cross_register_pairs
# names which registers may co-occur within a turn.
REGISTER_FRAGMENTS: dict[str, list[str]] = {
    "academic": [
        "the epistemic status of the claim remains underdetermined",
        "per the received literature on the matter",
        "one might adduce a counterexample here",
    ],
    "vulgar": VULGAR_FRAGMENTS,
    "devotional": [
        "give jah the thanks and praises",
        "blessed be, and selah",
        "by grace alone, amen",
    ],
    "conversational": [
        "you know what I mean?",
        "anyway, long story short",
        "so here's the thing",
    ],
    "pidgin": [
        "da kine stay broke, brah",
        "we go holoholo bumbye",
        "no can, too much hassle",
    ],
    "technical": [
        "the buffer flushed before the handshake completed",
        "you have to repoint the DNS first",
        "it segfaults on the second pass",
    ],
    "blues_narrative": [
        "I've been on my own for too long",
        "woke up this morning with the worried mind",
        "the road been hard and the night been cold",
    ],
    "aave": [
        "that joint go hard, no cap",
        "she been had it figured out",
        "we outchea regardless",
    ],
}

DEFAULT_REGISTERS = list(REGISTER_FRAGMENTS)


class WeirdAlGenerator(DecoyGenerator):
    """Register-chaos decoy generator (§5.9)."""

    mode = GenerationMode.WEIRD_AL

    def _draft(self, persona_ctx: dict, rng: random.Random) -> Query:
        cfg = self.config
        chaos = float(getattr(cfg, "register_chaos", 0.0))
        ph_rate = float(getattr(cfg, "placeholder_noun_rate", 0.0))
        vulg_lambda = float(getattr(cfg, "vulgarity_rate", 0.0))
        pairs = getattr(cfg, "cross_register_pairs", None) or []

        # Pick which registers may mix this turn.
        if pairs:
            pair = rng.choice(pairs)
            registers = [r for r in pair if r in REGISTER_FRAGMENTS]
        else:
            registers = []
        if not registers:
            registers = rng.sample(DEFAULT_REGISTERS, k=min(2, len(DEFAULT_REGISTERS)))

        # number of fragments scales with chaos: clean -> 1, full Weird Al -> ~4
        n_frags = 1 + int(round(chaos * 3))
        n_frags = max(1, n_frags)

        fragments: list[str] = []
        used_registers: list[str] = []
        for _ in range(n_frags):
            reg = rng.choice(registers)
            frag = rng.choice(REGISTER_FRAGMENTS[reg])
            fragments.append(frag)
            used_registers.append(reg)

        # Placeholder-noun injection: with prob ph_rate inject a placeholder clause.
        n_placeholders = 0
        markers: list[str] = []
        if rng.random() < ph_rate or (ph_rate > 0 and chaos >= 0.8):
            # ambiguity-injection sentence built around placeholders (§5.9)
            a, b, c = (rng.choice(PLACEHOLDER_NOUNS) for _ in range(3))
            markers = [a, b, c]
            n_placeholders = 3
            fragments.insert(
                rng.randrange(len(fragments) + 1),
                f"the thing about the {a} is you can't really {b} it "
                f"until {c} settles down, you know",
            )

        # Bursty (Poisson) vulgarity: number of extra vulgar fragments ~ Pois(lambda)
        n_vulg_extra = _poisson(rng, vulg_lambda)
        for _ in range(n_vulg_extra):
            frag = rng.choice(VULGAR_FRAGMENTS)
            fragments.insert(rng.randrange(len(fragments) + 1), frag)
            used_registers.append("vulgar")

        text = self._stitch(fragments)

        return self._query(
            text,
            persona_ctx,
            category="weird_al",
            registers=sorted(set(used_registers)),
            register_count=len(set(used_registers)),
            placeholder_count=n_placeholders
            + sum(
                text.count(p) for p in PLACEHOLDER_NOUNS if p not in markers
            ),
            placeholder_markers=[p for p in PLACEHOLDER_NOUNS if p in text],
            chaos=chaos,
        )

    @staticmethod
    def _stitch(fragments: list[str]) -> str:
        # join with comma/tag-like connectors to keep song-lyric / run-on cadence
        text = ", ".join(fragments).strip()
        if not text.endswith((".", "?", "!")):
            text += "."
        return text[0].upper() + text[1:]


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's Poisson sampler (small lambda regime), seeded RNG."""
    if lam <= 0:
        return 0
    import math

    l = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= l:
            return k - 1
