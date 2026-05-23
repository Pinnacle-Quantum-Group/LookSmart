"""AskingForAFriend Mode -- harm-reduction health queries (README §5.14).

Decoy health queries in the registers the harm-reduction community actually
uses: "asking for a friend", the "SWIM" (Someone Who Isn't Me) framing,
"hypothetically if", "I have this friend", "asking because curious".

Per §5.14 the local LLM is NOT trusted to generate these unsupervised (it will
sometimes emit lethal-dose / suicide-method / eating-disorder-coaching content).
So content is drawn from the HUMAN-CURATED ``HEALTH_SEEDS`` (curation.py), the
LLM does only paraphrastic variation, and every string is routed through the
curator. The §5.14 hard exclusions (no lethal-dose, no suicide methods, no
eating-disorder coaching, no prescription-substitution, no named non-public
individuals) are belt-and-suspenders enforced by an additional health-specific
deny-list layered onto the shared curator instance.
"""

from __future__ import annotations

import random
import re

from ..models import GenerationMode, Query
from .base import DecoyGenerator
from .curation import HEALTH_SEEDS

HEALTH_TOPICS = list(HEALTH_SEEDS)

# §5.14-specific register prefixes the SWIM/asking-for-a-friend family uses.
REGISTER_PREFIXES: dict[str, str] = {
    "asking_for_a_friend": "Asking for a friend -- ",
    "swim_was_wondering": "SWIM was wondering, ",
    "hypothetically_if": "Hypothetically, ",
    "i_have_this_friend": "I have this friend who's curious -- ",
    "asking_because_curious": "Asking because I'm curious, ",
}

# §5.14 health-specific hard exclusions, layered on top of the shared curator.
# These fire on lethal-dose / suicide-method / eating-disorder-coaching /
# prescription-substitution phrasing, which are NOT in the global §12.5 list but
# are §5.14 hard constraints.
HEALTH_DENY = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(lethal|fatal|deadly)\b.{0,15}\b(dose|dosage|amount|quantity)\b",
        r"\bhow (much|many)\b.{0,30}\b(to (die|overdose|kill)|would kill|is fatal|is lethal)",
        r"\b(kill myself|end my life|commit suicide|how to (die|suicide)|"
        r"painless way to die|suicide method)\b",
        r"\b(purge|purging|restrict(ing)? calories|lose weight by (not eating|starv)|"
        r"thinspo|pro[- ]?ana|pro[- ]?mia|how to (starve|throw up after eating))\b",
        # prescription-substitution
        r"\b(stronger|better) alternative to .{0,30}\bwithout (a )?prescription\b",
        r"\bget .{0,20}\b(without a prescription|over the counter instead of)\b",
        # named non-public "friend"
        r"\bmy friend [A-Z][a-z]+ [A-Z][a-z]+\b",
    )
]

_PARAPHRASE_SYSTEM = (
    "Rewrite this benign health question as a paraphrase with identical "
    "meaning, keeping it equally benign. Do not add dosage numbers, do not "
    "make it about self-harm, do not name any person. Output one question only."
)


class HealthGenerator(DecoyGenerator):
    """AskingForAFriend harm-reduction-register generator (§5.14)."""

    mode = GenerationMode.ASKING_FOR_A_FRIEND

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # layer the §5.14 health deny-list onto our curator instance
        self.curator = self._with_health_layer(self.curator)

    @staticmethod
    def _with_health_layer(curator):
        from .curation import LibraryCurator

        layered = LibraryCurator()
        # copy base deny rules then add health-specific
        layered._deny = {k: list(v) for k, v in curator._deny.items()}
        layered._deny.setdefault("health_harm_vector", []).extend(HEALTH_DENY)
        return layered

    def _draft(self, persona_ctx: dict, rng: random.Random) -> Query:
        cfg = self.config
        topics = self._balance_keys(getattr(cfg, "topic_balance", None), HEALTH_TOPICS)
        topics = [t for t in topics if t in HEALTH_SEEDS] or HEALTH_TOPICS
        topic = rng.choice(topics)

        registers = self._balance_keys(
            getattr(cfg, "register_mix", None), list(REGISTER_PREFIXES)
        )
        register = rng.choice([r for r in registers if r in REGISTER_PREFIXES]
                              or list(REGISTER_PREFIXES))

        seed = rng.choice(HEALTH_SEEDS[topic])

        text = seed
        if rng.random() < 0.4:
            out = self.llm.generate(
                seed, system=_PARAPHRASE_SYSTEM, temperature=0.7, max_tokens=96
            ).strip()
            if out:
                text = out

        # Ensure the chosen register prefix is present (re-register if the seed
        # already carries a different framing word, just prepend the marker).
        prefix = REGISTER_PREFIXES[register]
        marker_words = ("asking for a friend", "swim", "hypothetically",
                        "i have this friend", "asking because")
        if not any(m in text.lower() for m in marker_words):
            text = prefix + text[0].lower() + text[1:]

        return self._query(
            text,
            persona_ctx,
            category=topic,
            register=register,
            seed=seed,
            paraphrased=text != seed,
        )

    @staticmethod
    def _balance_keys(balance, default: list[str]) -> list[str]:
        if balance is None:
            return list(default)
        items = getattr(balance, "weights", None)
        if items:
            return list(items)
        return list(default)
