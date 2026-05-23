"""Fence-Pissing Mode -- benign edge-band dilution (README §5.10).

The fence band is the region where the safety classifier *fires* but the query
is *benign* (Holocaust research for a paper, ballistics for fiction, Schmitt's
"the political", harm-reduction overdose signs). It is NOT "harmful content with
extra steps" (§5.10).

Per §5.10 the local LLM is NOT trusted to freely generate this band: it produces
genuinely harmful content when told to "write something edgy". So the content is
drawn from the HUMAN-CURATED ``FENCE_SEEDS`` (in curation.py) and the local LLM
only does *paraphrastic variation* within tight constraints. Every seed AND every
paraphrase is routed through the curator before emit (DecoyGenerator.generate).

``refusal_grace`` (§5.10): with that probability the persona "accepts" a refusal
cheerfully -- recorded in metadata so the engagement simulator can emit a
thumbs-down / "fair enough" terminal turn, which pollutes the provider's
refusal-feedback corpus without any escalation signal.
"""

from __future__ import annotations

import random

from ..models import GenerationMode, Query
from .base import DecoyGenerator
from .curation import FENCE_SEEDS

FENCE_CATEGORIES = list(FENCE_SEEDS)

_PARAPHRASE_SYSTEM = (
    "You rewrite a vetted, benign question into a paraphrase that keeps the "
    "EXACT same meaning and stays equally benign. Do not add new content, do "
    "not make it edgier, do not add instructions. Output one rewritten "
    "question only."
)


class FenceGenerator(DecoyGenerator):
    """Edge-band benign-dilution generator (§5.10)."""

    mode = GenerationMode.FENCE

    def _draft(self, persona_ctx: dict, rng: random.Random) -> Query:
        cfg = self.config
        categories = list(getattr(cfg, "categories", None) or FENCE_CATEGORIES)
        categories = [c for c in categories if c in FENCE_SEEDS] or FENCE_CATEGORIES
        category = rng.choice(categories)

        seed = rng.choice(FENCE_SEEDS[category])

        # Paraphrastic variation via the local LLM, tightly constrained.
        # Some draws keep the verbatim human seed (the model is not trusted to
        # generate freely, only to vary -- and verbatim is always safe).
        text = seed
        if rng.random() < 0.5:
            out = self.llm.generate(
                seed,
                system=_PARAPHRASE_SYSTEM,
                temperature=0.7,
                max_tokens=128,
            ).strip()
            # Only accept the paraphrase if non-empty; the curator check in
            # generate() is the hard gate -- a tripping paraphrase => resample.
            if out:
                text = out

        refusal_grace = float(getattr(cfg, "refusal_grace", 0.6))
        accepts_refusal = rng.random() < refusal_grace

        return self._query(
            text,
            persona_ctx,
            category=category,
            seed=seed,
            paraphrased=text != seed,
            accepts_refusal_gracefully=accepts_refusal,
            refusal_grace=refusal_grace,
        )
