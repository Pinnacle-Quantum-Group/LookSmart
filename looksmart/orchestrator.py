"""Pipeline orchestrator (ties README §5 components together).

Wires: PersonaSampler -> BehavioralScheduler -> {decoy generation (§5.9-5.21)
+ EngagementSimulator (§5.4)} / {CooKoo Filter on real queries (§5.17)} ->
ProviderAdapter (§5.7) -> AuditStore (§5.6).

Dispatch is DRY-RUN by default. Actually transmitting traffic to a live LLM
account is a consequential, ToS-relevant action (README §7), so the caller must
opt in explicitly (`live=True` with a configured, enabled provider). In dry-run
the orchestrator builds and audits the traffic without sending it.
"""

from __future__ import annotations

import random

import numpy as np

from .audit import AuditStore
from .config import LookSmartConfig
from .cookoo.injector import CooKooInjector
from .engagement import EngagementSimulator
from .generation.registry import build_generator
from .llm_protocol import LocalLLM
from .localllm import build_local_llm
from .models import GenerationMode, ProviderResponse, Query, QueryKind, Session
from .persona.library import Persona, PersonaLibrary
from .persona.sampler import PersonaSampler
from .providers.registry import build_adapter
from .scheduler import BehavioralScheduler

# Per-mode config field -> GenerationMode, with the rate attribute to weight by.
_MODE_RATE_FIELDS: dict[GenerationMode, str] = {
    GenerationMode.WEIRD_AL: "weird_al",
    GenerationMode.FENCE: "fence",
    GenerationMode.SPELUNKING: "spelunking",
    GenerationMode.POLITIC_ROULETTE: "politic_roulette",
    GenerationMode.RELIGIOUS: "religious",
    GenerationMode.ASKING_FOR_A_FRIEND: "asking_for_a_friend",
    GenerationMode.IDENTITY_SEARCH: "identity_search",
    GenerationMode.GENDER_ROULETTE: "gender_roulette",
    GenerationMode.ORIENTATION_ROULETTE: "orientation_roulette",
    GenerationMode.IMMIGRATION_ROULETTE: "immigration_roulette",
    GenerationMode.HEALTH_STATUS_ROULETTE: "health_status_roulette",
}


class Orchestrator:
    def __init__(
        self,
        config: LookSmartConfig,
        *,
        llm: LocalLLM | None = None,
        seed: int | None = None,
    ):
        self.config = config
        self.llm = llm or build_local_llm(config.local_llm)
        self.library = PersonaLibrary.from_dir(config.persona_library_dir)
        self.sampler = PersonaSampler(self.library, config.sampler)
        self.scheduler = BehavioralScheduler(config.scheduler)
        self.engagement = EngagementSimulator(self.llm, config.engagement)
        self.cookoo = CooKooInjector(config.cookoo) if config.cookoo.enabled else None
        self.audit = AuditStore(config.audit)
        self._np = np.random.default_rng(seed)
        self._py = random.Random(seed)
        self._generators: dict[GenerationMode, object] = {}
        self._adapters: dict[str, object] = {}

    # -- mode selection ------------------------------------------------------
    def select_mode(self) -> GenerationMode:
        """Sample a decoy mode weighted by each mode's configured rate.

        Spelunking is the default-on productivity mode (§5.11): if no mode has
        a positive rate we fall back to it.
        """
        weights: dict[GenerationMode, float] = {}
        for mode, field in _MODE_RATE_FIELDS.items():
            rate = float(getattr(getattr(self.config, field), "rate", 0.0))
            if rate > 0:
                weights[mode] = rate
        if not weights:
            return GenerationMode.SPELUNKING
        modes = list(weights)
        probs = np.array([weights[m] for m in modes], dtype=float)
        probs /= probs.sum()
        return modes[int(self._np.choice(len(modes), p=probs))]

    def _generator(self, mode: GenerationMode):
        if mode not in self._generators:
            self._generators[mode] = build_generator(mode, self.config, self.llm)
        return self._generators[mode]

    # -- decoy path ----------------------------------------------------------
    def generate_decoy(
        self, persona: Persona | None = None, mode: GenerationMode | None = None
    ) -> Query | Session:
        mode = mode or self.select_mode()
        persona = persona or self.sampler.sample_persona(self._np)
        ctx = {"persona_id": persona.id, "tier": persona.tier}
        return self._generator(mode).generate(ctx, self._py)

    # -- real path -----------------------------------------------------------
    def prepare_real(
        self, text: str, *, user_override_passthrough: bool = False
    ) -> Query:
        """Apply CooKoo (if enabled) to a real query, else pass it through."""
        if self.cookoo is None:
            return Query(text=text, kind=QueryKind.REAL, original_text=text)
        return self.cookoo.inject(
            text, self._py, user_override_passthrough=user_override_passthrough
        )

    # -- dispatch ------------------------------------------------------------
    def _adapter(self, provider: str):
        if provider not in self._adapters:
            cfg = next(
                (p for p in self.config.providers if p.name == provider and p.enabled),
                None,
            )
            if cfg is None:
                raise ValueError(f"provider {provider!r} not configured/enabled")
            self._adapters[provider] = build_adapter(cfg)
        return self._adapters[provider]

    def dispatch(
        self,
        item: Query | Session,
        *,
        provider: str | None = None,
        live: bool = False,
        covers_real: str | None = None,
    ) -> ProviderResponse | None:
        """Audit `item` and, when `live` and a provider is given, transmit it.

        Returns the ProviderResponse when sent, else None (dry-run).
        """
        queries = (
            [Query(text=t.prompt, kind=item.kind, persona_id=item.persona_id,
                   mode=item.mode) for t in item.turns]
            if isinstance(item, Session)
            else [item]
        )
        for q in queries:
            if provider:
                q.metadata["provider"] = provider
            self.audit.log(q, covers_real=covers_real)

        if not live or provider is None:
            return None
        adapter = self._adapter(provider)
        if isinstance(item, Session):
            return adapter.send_session(item)
        return adapter.send(item)

    def close(self) -> None:
        self.audit.close()
        for a in self._adapters.values():
            close = getattr(a, "close", None)
            if close:
                close()
