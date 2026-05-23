"""DecoyGenerator ABC and shared sampling helpers (README §5.9-§5.21).

Every mode subclasses :class:`DecoyGenerator` and implements
:meth:`_draft`, which produces a *candidate* Query or Session from a
persona context dict and a seeded ``random.Random``. The base class wires
in the curator: it calls :meth:`_draft`, runs every emitted string through
:class:`~looksmart.generation.curation.LibraryCurator`, and resamples on
exclusion (README §4 principle 11: a misfiring decoy is invisible to the
user, so resampling is the right failure mode -- never patch and ship).
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from ..llm_protocol import LocalLLM
from ..models import GenerationMode, Query, QueryKind, Session, Turn
from .curation import LibraryCurator


class MaxResampleError(RuntimeError):
    """Raised when a generator cannot produce curation-clean content.

    This is a guardrail-of-the-guardrail: if the candidate space keeps
    tripping the curator, we refuse to emit rather than degrade.
    """


def weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    """Sample a key from a (possibly unnormalized) weight dict."""
    if not weights:
        raise ValueError("cannot sample from empty weight dict")
    keys = list(weights)
    vals = [max(0.0, float(weights[k])) for k in keys]
    total = sum(vals)
    if total <= 0:
        return rng.choice(keys)
    r = rng.random() * total
    upto = 0.0
    for k, v in zip(keys, vals):
        upto += v
        if r <= upto:
            return k
    return keys[-1]


class DecoyGenerator(ABC):
    """Abstract base for all decoy content generators.

    Subclasses implement :meth:`_draft`. The public :meth:`generate` enforces
    the curation contract on every candidate before returning it.
    """

    mode: GenerationMode

    #: how many curation-failed candidates to tolerate before giving up
    max_resamples: int = 16

    def __init__(self, config, llm: LocalLLM, curator: LibraryCurator | None = None):
        self.config = config
        self.llm = llm
        self.curator = curator or LibraryCurator()

    # -- subclass hook -------------------------------------------------------
    @abstractmethod
    def _draft(self, persona_ctx: dict, rng: random.Random) -> Query | Session:
        """Produce a candidate Query or Session. May be re-invoked on resample."""

    # -- curation-enforced emit ---------------------------------------------
    def generate(
        self, persona_ctx: dict | None = None, rng: random.Random | None = None
    ) -> Query | Session:
        persona_ctx = persona_ctx or {}
        rng = rng or random.Random()
        last_reason = ""
        for _ in range(self.max_resamples):
            candidate = self._draft(persona_ctx, rng)
            ok, reason = self._curate(candidate)
            if ok:
                return candidate
            last_reason = reason
        raise MaxResampleError(
            f"{type(self).__name__} could not produce clean content in "
            f"{self.max_resamples} tries (last: {last_reason})"
        )

    def _curate(self, candidate: Query | Session) -> tuple[bool, str]:
        """Return (clean, reason). Checks every emitted string."""
        for text, cat in self._texts(candidate):
            res = self.curator.check(text, cat)
            if res.excluded:
                return False, f"{res.category}: {res.reason}"
        return True, ""

    @staticmethod
    def _texts(candidate: Query | Session):
        """Yield (text, category_label) for every string the candidate emits."""
        if isinstance(candidate, Query):
            cat = (candidate.metadata or {}).get("category")
            yield candidate.text, cat
        elif isinstance(candidate, Session):
            cat = (candidate.metadata or {}).get("category")
            for turn in candidate.turns:
                yield turn.prompt, cat
        else:  # pragma: no cover - defensive
            raise TypeError(f"unexpected candidate type {type(candidate)!r}")

    # -- convenience builders used by subclasses -----------------------------
    def _query(self, text: str, persona_ctx: dict, **metadata) -> Query:
        return Query(
            text=text,
            kind=QueryKind.DECOY,
            persona_id=persona_ctx.get("persona_id"),
            mode=self.mode,
            metadata=metadata,
        )

    def _session(self, persona_ctx: dict, prompts: list[str], **metadata) -> Session:
        sess = Session(
            persona_id=persona_ctx.get("persona_id", "decoy"),
            kind=QueryKind.DECOY,
            mode=self.mode,
            metadata=metadata,
        )
        for i, p in enumerate(prompts):
            sess.turns.append(Turn(prompt=p, index=i))
        return sess
