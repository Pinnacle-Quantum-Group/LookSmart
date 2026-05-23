"""Persona sampler: two-stage decoy sampling (README §5.2).

Stage 1 (``decide_kind``): with probability ``p_real`` pass through to the
user's real query stream; otherwise generate a decoy.

Stage 2 (``sample_persona``): for decoys, draw a persona from the library using
power-law weights. The default distribution mirrors realistic multi-persona
usage rather than a uniform one -- *uniform decoy distribution produces a
profile no human matches*, the same OOD failure mode that made classifier-
separable TrackMeNot decoys detectable (README §5.2 rationale).

Persona selection is **sticky within a session**: once a session id has been
assigned a persona, every subsequent draw for that session returns the same
persona, preserving conversational coherence (README §5.3).
"""

from __future__ import annotations

import numpy as np

from ..config import SamplerConfig
from ..models import QueryKind
from .library import Persona, PersonaLibrary


def default_power_law_weights(persona_ids: list[str]) -> dict[str, float]:
    """Construct the §5.2 default decoy persona distribution.

    "one dominant decoy persona ~50%, two secondary ~20% each, long tail ~10%".
    With <= 3 personas we collapse gracefully onto the available ids and
    renormalize.
    """
    n = len(persona_ids)
    if n == 0:
        return {}
    if n == 1:
        return {persona_ids[0]: 1.0}
    if n == 2:
        return {persona_ids[0]: 0.7, persona_ids[1]: 0.3}
    if n == 3:
        return {persona_ids[0]: 0.5, persona_ids[1]: 0.25, persona_ids[2]: 0.25}

    weights: dict[str, float] = {
        persona_ids[0]: 0.50,
        persona_ids[1]: 0.20,
        persona_ids[2]: 0.20,
    }
    tail = persona_ids[3:]
    # remaining ~10% spread over the long tail
    share = 0.10 / len(tail)
    for pid in tail:
        weights[pid] = share
    return weights


class PersonaSampler:
    """Two-stage decoy sampler with sticky-within-session persona binding."""

    def __init__(self, library: PersonaLibrary, config: SamplerConfig | None = None):
        if len(library) == 0:
            raise ValueError("PersonaSampler requires a non-empty persona library")
        self.library = library
        self.config = config or SamplerConfig()
        # session id -> persona id (sticky binding, README §5.3)
        self._session_personas: dict[str, str] = {}

    # -- stage 1 -----------------------------------------------------------
    def decide_kind(self, rng: np.random.Generator) -> QueryKind:
        """Return REAL with probability ``p_real``, else DECOY (§5.2)."""
        return QueryKind.REAL if rng.random() < self.config.p_real else QueryKind.DECOY

    # -- stage 2 -----------------------------------------------------------
    def _effective_weights(self) -> dict[str, float]:
        """Weights to sample personas with, applying the §5.2 default when the
        config supplies none (so we never silently fall back to uniform)."""
        configured = self.config.persona_weights
        # Keep only ids that actually exist in the library.
        configured = {
            k: v for k, v in configured.items() if k in self.library and v > 0
        }
        if configured:
            return configured
        return default_power_law_weights(self.library.ids())

    def sample_persona(self, rng: np.random.Generator) -> Persona:
        """Draw a decoy persona using power-law weights (non-uniform, §5.2)."""
        return self.library.sample_weighted(self._effective_weights(), rng)

    # -- sticky-within-session ---------------------------------------------
    def persona_for_session(
        self, session_id: str, rng: np.random.Generator
    ) -> Persona:
        """Return the persona bound to ``session_id``, sampling and caching one
        on first use. When ``sticky_within_session`` is disabled this samples
        fresh each call (no caching)."""
        if not self.config.sticky_within_session:
            return self.sample_persona(rng)
        bound = self._session_personas.get(session_id)
        if bound is not None:
            return self.library.get(bound)
        persona = self.sample_persona(rng)
        self._session_personas[session_id] = persona.id
        return persona

    def release_session(self, session_id: str) -> None:
        """Forget the sticky binding for a finished session."""
        self._session_personas.pop(session_id, None)

    def clear_sessions(self) -> None:
        self._session_personas.clear()
