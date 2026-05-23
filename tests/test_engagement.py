"""Tests for the engagement simulator (README §5.4)."""

from __future__ import annotations

import numpy as np
import pytest

from looksmart.config import EngagementConfig
from looksmart.engagement import EngagementSimulator
from looksmart.llm_protocol import StubLLM
from looksmart.models import EngagementType, QueryKind
from looksmart.persona.library import Persona


@pytest.fixture
def persona() -> Persona:
    return Persona(
        id="test_gardener",
        display_name="Test gardener",
        topic_priors={"tomatoes": 3.0, "compost": 1.0},
        register_priors={"casual": 1.0},
        follow_up_rate=0.6,
        regeneration_rate=0.2,
        copy_rate=0.5,
        thumbs_rate=0.3,
        seed_prompts=["My tomatoes are wilting, help?"],
        coherence_constraints="gardening only",
        tier="median",
    )


def test_produces_2_to_8_turns(persona: Persona):
    sim = EngagementSimulator(StubLLM(), EngagementConfig(min_turns=2, max_turns=8))
    rng = np.random.default_rng(0)
    for _ in range(50):
        session = sim.simulate(persona, persona.seed_prompts[0], rng)
        assert 2 <= len(session.turns) <= 8
        assert session.kind is QueryKind.DECOY
        assert session.persona_id == "test_gardener"


def test_turns_have_indices_and_responses(persona: Persona):
    sim = EngagementSimulator(StubLLM("canned answer"))
    rng = np.random.default_rng(1)
    session = sim.simulate(persona, "seed", rng)
    for i, turn in enumerate(session.turns):
        assert turn.index == i
        assert turn.response == "canned answer"
        assert turn.prompt


def test_emits_engagement_events(persona: Persona):
    sim = EngagementSimulator(StubLLM())
    rng = np.random.default_rng(2)
    total_events = 0
    seen_kinds: set[EngagementType] = set()
    for _ in range(40):
        s = sim.simulate(persona, "seed", rng)
        total_events += len(s.engagement)
        seen_kinds.update(e.kind for e in s.engagement)
        for ev in s.engagement:
            assert 0 <= ev.turn_index < len(s.turns)
    assert total_events > 0
    # with high persona rates we should see several distinct signal types
    assert len(seen_kinds) >= 3


def test_engagement_rates_calibrated_to_persona():
    """A persona with copy_rate=0 should never emit copy events."""
    p = Persona(
        id="no_copy",
        display_name="No copier",
        copy_rate=0.0,
        follow_up_rate=0.0,
        regeneration_rate=0.0,
        thumbs_rate=0.0,
    )
    sim = EngagementSimulator(StubLLM())
    rng = np.random.default_rng(3)
    for _ in range(100):
        s = sim.simulate(p, "seed", rng)
        assert s.engagement == []


def test_single_turn_config_clamps_min():
    p = Persona(id="x", display_name="X")
    sim = EngagementSimulator(StubLLM(), EngagementConfig(min_turns=3, max_turns=3))
    rng = np.random.default_rng(4)
    s = sim.simulate(p, "seed", rng)
    assert len(s.turns) == 3


def test_session_is_topic_coherent(persona: Persona):
    """Follow-up prompts are content-free moves, never a new injected topic."""
    sim = EngagementSimulator(StubLLM())
    rng = np.random.default_rng(5)
    s = sim.simulate(persona, "My tomatoes are wilting, help?", rng)
    # first prompt is the seed; later prompts come from the coherent template set
    assert s.turns[0].prompt == "My tomatoes are wilting, help?"
    from looksmart.engagement import _CLARIFICATION_TEMPLATES, _FOLLOW_UP_TEMPLATES

    allowed = set(_FOLLOW_UP_TEMPLATES) | set(_CLARIFICATION_TEMPLATES)
    for turn in s.turns[1:]:
        assert turn.prompt in allowed
