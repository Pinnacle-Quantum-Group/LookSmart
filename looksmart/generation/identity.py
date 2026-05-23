"""IdentitySearch Mode -- cohort cover for identity-search-state queries (§5.16).

Generates decoys across the BROADER identity-search topic space (career,
relocation, education, relationships, meaning, parenting, etc.) so any user's
real identity-search engagement reads as one query among many. High engagement
density (multi-turn, emotional register, return visits -- §5.16).

HARD CONSTRAINT ``no_excluded_dimensions`` (§5.15/§5.16): the mode must NOT drift
into the §5.15 excluded dimensions (gender identity, sexual orientation, specific
health-status). If a candidate session drifts there, the session is reset (we
detect drift with a dimension deny-list and resample, per §5.16: "the session
terminates and the persona resets").
"""

from __future__ import annotations

import random
import re

from ..models import GenerationMode, Session
from .base import DecoyGenerator
from .curation import LibraryCurator

IDENTITY_TOPICS = [
    "career_transitions",
    "geographic_relocation",
    "educational_decisions",
    "relationship_transitions",
    "religious_philosophical",
    "skill_acquisition",
    "existential_meaning",
    "parenting_transitions",
    "body_non_identity",
    "friendship_community",
]

_DEFAULT_BALANCE = {
    "career_transitions": 0.15,
    "geographic_relocation": 0.10,
    "educational_decisions": 0.10,
    "relationship_transitions": 0.15,
    "religious_philosophical": 0.10,
    "skill_acquisition": 0.10,
    "existential_meaning": 0.10,
    "parenting_transitions": 0.10,
    "body_non_identity": 0.05,
    "friendship_community": 0.05,
}

# §5.15 EXCLUDED DIMENSIONS -- identity mode must never emit these. This is the
# no_excluded_dimensions hard constraint. Detected here so a drifting LLM
# paraphrase (or a bad seed) triggers a session reset / resample.
_EXCLUDED_DIMENSIONS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(trans(gender)?|nonbinary|non[- ]binary|gender[- ]?(identity|questioning|"
        r"affirming|dysphoria)|transition(ing)?|coming out as (trans|a (man|woman)))\b",
        r"\b(gay|lesbian|bisexual|bi[- ]?curious|pansexual|asexual|queer|"
        r"sexual orientation|same[- ]sex|attracted to (men|women|the same))\b",
        r"\b(hiv|aids|bipolar|schizophreni|my (depression|anxiety) diagnosis|"
        r"newly diagnosed with|my diagnosis of)\b",
        r"\b(immigration status|undocumented|asylum|deportation|my visa status)\b",
    )
]

_SEED_BANK: dict[str, list[str]] = {
    "career_transitions": [
        "I keep thinking about leaving software to teach high school -- how do "
        "people know when it's time to change careers?",
        "I don't know if I should go back for a graduate degree at 40 or just "
        "stay where I am. How do people think this through?",
    ],
    "geographic_relocation": [
        "I keep wondering whether I'd be happier if I moved abroad. How do people "
        "decide whether relocation is running away or moving toward something?",
        "How do people weigh cost of living against community when deciding where "
        "to settle down?",
    ],
    "educational_decisions": [
        "I keep going back and forth on whether a humanities degree was worth it "
        "and what to do with it now.",
        "How do adults decide between trade school and a four-year college later "
        "in life?",
    ],
    "relationship_transitions": [
        "How do people know when a long marriage is actually over versus just a "
        "rough patch?",
        "I keep thinking about whether I want children -- how do people work "
        "through that decision honestly?",
    ],
    "religious_philosophical": [
        "I've been losing my faith slowly and I don't know how to think about "
        "meaning after that. How do people navigate deconversion?",
        "How do people find a sense of purpose when the framework they grew up "
        "with stops fitting?",
    ],
    "skill_acquisition": [
        "Is it too late to seriously learn an instrument as an adult, and how do "
        "people stay motivated?",
        "I keep wanting to become a writer in midlife -- how do people actually "
        "start?",
    ],
    "existential_meaning": [
        "I keep thinking about what to do with my one wild and precious life. How "
        "do people approach that without it being paralyzing?",
        "How do people make peace with mortality and think about legacy?",
    ],
    "parenting_transitions": [
        "Now that the kids have moved out the house feels empty -- how do people "
        "rebuild a sense of purpose after the nest empties?",
        "How do people adjust to parenting their own aging parents?",
    ],
    "body_non_identity": [
        "I want to become a runner in my 40s but I'm worried about my knees -- how "
        "do people start safely?",
        "How do people make peace with changing physical capacity as they age?",
    ],
    "friendship_community": [
        "How do people actually make new friends as adults after a move?",
        "How do people end a friendship that's become toxic without drama?",
    ],
}

_FOLLOWUPS = [
    "I keep coming back to this, honestly. Can you say more?",
    "That helps. But how do you tell the difference between fear and intuition?",
    "I don't know if I'm overthinking it. What questions should I be asking myself?",
    "Yeah. I've been sitting with this for a while.",
]


class IdentityGenerator(DecoyGenerator):
    """Identity-search-state cohort-cover generator (§5.16)."""

    mode = GenerationMode.IDENTITY_SEARCH

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # layer the §5.15 excluded-dimension deny-list onto our curator so
        # generate()'s resample loop treats drift as a reason to reset.
        self.curator = self._with_dimension_layer(self.curator)

    @staticmethod
    def _with_dimension_layer(curator) -> LibraryCurator:
        layered = LibraryCurator()
        layered._deny = {k: list(v) for k, v in curator._deny.items()}
        layered._deny.setdefault("excluded_dimension", []).extend(_EXCLUDED_DIMENSIONS)
        return layered

    def _balance(self) -> dict[str, float]:
        bal = getattr(self.config, "topic_balance", None)
        weights = getattr(bal, "weights", None) if bal is not None else None
        if weights:
            usable = {k: v for k, v in weights.items() if k in _SEED_BANK}
            if usable:
                return usable
        return dict(_DEFAULT_BALANCE)

    def _draft(self, persona_ctx: dict, rng: random.Random) -> Session:
        from .base import weighted_choice

        weights = self._balance()
        category = weighted_choice(rng, weights)
        density = getattr(self.config, "engagement_density", "high")

        opener = rng.choice(_SEED_BANK[category])
        prompts = [opener]

        # high engagement density => more follow-ups (§5.16: multi-turn).
        n_follow = {"low": 0, "medium": 1, "high": 3}.get(density, 3)
        for _ in range(n_follow):
            # stay within the SAME transition (no random pivot, §5.16 note)
            prompts.append(rng.choice(_FOLLOWUPS))

        return self._session(
            persona_ctx,
            prompts,
            category=category,
            engagement_density=density,
            follow_up_turns=len(prompts) - 1,
        )
