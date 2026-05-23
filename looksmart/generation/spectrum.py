"""Shared cross-spectrum balanced generator (README §5.12/§5.13/§5.18-§5.21).

PoliticRoulette, Religious, and the four cohort modes (Gender/Orientation/
Immigration/HealthStatus Roulette) all share one structural template: a
``SpectrumModeConfig`` with a ``balance`` (a categorical distribution over the
dimension's positions), a ``register_mix``, and per-mode hard constraints. The
mechanism (README §5.12 complication 2, §5.18) requires GENUINELY balanced
coverage -- if the library skews to the user's own position they "sign the
noise" (§4 principle 5, §5.5). So when the config supplies no balance, we
default to the spec's balanced weights, NOT to a curator-flavored subset.

Each concrete mode supplies a SEED BANK: ``{balance_category: [queries...]}``.
Seeds are human-vetted and route through the curator like everything else.
"""

from __future__ import annotations

import random

from ..models import GenerationMode, Query
from .base import DecoyGenerator, weighted_choice


class SpectrumGenerator(DecoyGenerator):
    """Cross-spectrum balanced decoy generator.

    Subclasses set :attr:`mode`, :attr:`SEED_BANK`, :attr:`DEFAULT_BALANCE`,
    and (optionally) :attr:`DEFAULT_REGISTERS` and :attr:`CONTEMPORARY_KEYS`.
    """

    SEED_BANK: dict[str, list[str]] = {}
    DEFAULT_BALANCE: dict[str, float] = {}
    DEFAULT_REGISTERS: list[str] = []
    #: balance keys whose content is contemporary-figure / fence-adjacent and
    #: must be gated behind ``contemporary_rate`` (§5.12 complication 1).
    CONTEMPORARY_KEYS: set[str] = set()

    def _balance_weights(self) -> dict[str, float]:
        """Resolve the active balance. Defaults to spec-balanced, not user taste."""
        bal = getattr(self.config, "balance", None)
        weights = getattr(bal, "weights", None) if bal is not None else None
        if weights:
            # restrict to categories we actually have seeds for
            usable = {k: v for k, v in weights.items() if k in self.SEED_BANK}
            if usable:
                return usable
        return dict(self.DEFAULT_BALANCE)

    def _draft(self, persona_ctx: dict, rng: random.Random) -> Query:
        weights = self._balance_weights()
        contemporary_rate = float(getattr(self.config, "contemporary_rate", 0.0))

        category = weighted_choice(rng, weights)
        # §5.12 complication 1: gate contemporary/fence-adjacent categories.
        if category in self.CONTEMPORARY_KEYS and rng.random() >= contemporary_rate:
            historical = {
                k: v for k, v in weights.items() if k not in self.CONTEMPORARY_KEYS
            }
            if historical:
                category = weighted_choice(rng, historical)

        text = rng.choice(self.SEED_BANK[category])

        registers = list(
            getattr(self.config, "register_mix", None) or self.DEFAULT_REGISTERS
        )
        register = rng.choice(registers) if registers else None

        return self._query(
            text,
            persona_ctx,
            category=category,
            register=register,
            contemporary=category in self.CONTEMPORARY_KEYS,
        )
