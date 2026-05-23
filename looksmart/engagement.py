"""Engagement simulator (README §5.4).

Decoys that terminate at the first response are trivially classifier-separable
on engagement features alone. This module turns a persona + a decoy seed prompt
into a multi-turn :class:`Session` (2-8 turns, bounds from
:class:`EngagementConfig`) generated with a local LLM, and stochastically emits
:class:`EngagementEvent` s (copy / regenerate / follow-up / thumbs) calibrated
to the persona's engagement priors.

Persona coherence (README §5.4 / §5.3). Every follow-up turn is derived from the
*same* persona and the running conversation; we never inject an unrelated topic
mid-session (cross-topic mixing within one conversation is a documented tell).

This is explicitly the v0.1 "hardest unsolved problem" approach from §5.4: a
heuristic, persona-conditioned multi-turn generator with calibrated engagement
emission, not a learned engagement model.
"""

from __future__ import annotations

import numpy as np

from .config import EngagementConfig
from .llm_protocol import LocalLLM
from .models import (
    EngagementEvent,
    EngagementType,
    GenerationMode,
    QueryKind,
    Session,
    Turn,
)
from .persona.library import Persona

# Persona-coherent follow-up scaffolds. These are content-free conversational
# moves (clarify / go deeper / ask for an example) so the *topic* always stays
# bound to the persona's own prior turn, never a fresh unrelated subject.
_FOLLOW_UP_TEMPLATES = (
    "Can you go into more detail on that?",
    "That helps -- can you give a concrete example?",
    "What would you change if I'm a beginner at this?",
    "Got it. What's the most common mistake people make here?",
    "Could you break that down into steps?",
    "How does that apply to my situation specifically?",
)

_CLARIFICATION_TEMPLATES = (
    "Wait, can you clarify what you meant by that?",
    "Sorry, which option are you recommending?",
    "I'm not sure I follow the last part -- can you rephrase?",
)


class EngagementSimulator:
    """Generate persona-coherent multi-turn decoy sessions with engagement."""

    def __init__(self, llm: LocalLLM, config: EngagementConfig | None = None):
        self.llm = llm
        self.config = config or EngagementConfig()

    # ------------------------------------------------------------------ API
    def simulate(
        self,
        persona: Persona,
        seed: str,
        rng: np.random.Generator,
        *,
        mode: GenerationMode | None = None,
    ) -> Session:
        """Build a multi-turn decoy :class:`Session` for ``persona`` from ``seed``.

        The session has between ``min_turns`` and ``max_turns`` user turns, each
        with a generated assistant response, plus stochastically emitted
        engagement events calibrated to the persona's priors.
        """
        n_turns = self._draw_turn_count(rng)
        system = self._system_prompt(persona)

        session = Session(
            persona_id=persona.id,
            kind=QueryKind.DECOY,
            mode=mode,
            metadata={"tier": persona.tier},
        )

        prompt = seed.strip() or self._seed_from_persona(persona, rng)
        for index in range(n_turns):
            response = self.llm.generate(prompt, system=system, temperature=0.9)
            turn = Turn(prompt=prompt, index=index, response=response)
            session.turns.append(turn)

            self._emit_turn_events(session, persona, index, rng)

            # Build the next user turn from the SAME persona/topic (coherence).
            if index < n_turns - 1:
                prompt = self._next_user_turn(persona, response, index, rng)

        return session

    # -------------------------------------------------------- turn building
    def _draw_turn_count(self, rng: np.random.Generator) -> int:
        lo = max(1, int(self.config.min_turns))
        hi = max(lo, int(self.config.max_turns))
        return int(rng.integers(lo, hi + 1))  # inclusive upper bound

    def _system_prompt(self, persona: Persona) -> str:
        bits = [f"You are assisting {persona.display_name}."]
        if persona.coherence_constraints:
            bits.append(f"Stay in scope: {persona.coherence_constraints}")
        topics = ", ".join(list(persona.topic_priors)[:5])
        if topics:
            bits.append(f"Typical topics: {topics}.")
        register = max(persona.register_priors, key=persona.register_priors.get) \
            if persona.register_priors else None
        if register:
            bits.append(f"Register: {register}.")
        return " ".join(bits)

    def _seed_from_persona(self, persona: Persona, rng: np.random.Generator) -> str:
        if persona.seed_prompts:
            return str(rng.choice(persona.seed_prompts))
        topic = persona.sample_topic(rng) or persona.display_name
        return f"I have a question about {topic}."

    def _next_user_turn(
        self, persona: Persona, last_response: str, index: int, rng: np.random.Generator
    ) -> str:
        # Occasionally ask a clarification rather than a forward follow-up, but
        # always anchored to the persona's running conversation (no new topic).
        if rng.random() < 0.25:
            return str(rng.choice(_CLARIFICATION_TEMPLATES))
        return str(rng.choice(_FOLLOW_UP_TEMPLATES))

    # ---------------------------------------------------------- engagement
    def _emit_turn_events(
        self,
        session: Session,
        persona: Persona,
        index: int,
        rng: np.random.Generator,
    ) -> None:
        """Stochastically emit engagement events for the turn at ``index``.

        Probabilities come from the persona's priors (which themselves default
        from EngagementConfig at load time). A turn may emit several signals or
        none.
        """
        # COPY: user copied the answer out.
        if rng.random() < persona.copy_rate:
            session.engagement.append(
                EngagementEvent(kind=EngagementType.COPY, turn_index=index)
            )
        # REGENERATE: user asked for a different answer.
        if rng.random() < persona.regeneration_rate:
            session.engagement.append(
                EngagementEvent(kind=EngagementType.REGENERATE, turn_index=index)
            )
        # FOLLOW_UP: only meaningful when another turn follows.
        has_next = index < len(session.turns) or True  # follow handled by caller loop
        if rng.random() < persona.follow_up_rate and has_next:
            session.engagement.append(
                EngagementEvent(kind=EngagementType.FOLLOW_UP, turn_index=index)
            )
        # THUMBS: split up/down weighted toward up.
        if rng.random() < persona.thumbs_rate:
            kind = (
                EngagementType.THUMBS_UP
                if rng.random() < 0.8
                else EngagementType.THUMBS_DOWN
            )
            session.engagement.append(EngagementEvent(kind=kind, turn_index=index))
