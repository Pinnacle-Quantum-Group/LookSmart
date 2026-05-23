"""CooKoo injector (README §5.17).

Wraps the user's OWN real query with cohort/topic/register context to shift the
provider's per-query inference about the user. It does NOT rewrite the user's
words (§2.2): the verbatim prose passes through inside the wrapper, and the
output is asserted to contain the original substring.

Two-layer name in action:
  - brood parasitism: a context "egg" is laid in the nest of the real query.
  - cuckoo filter: each candidate injection is deduped against a CuckooFilter so
    the injection stream rotates and develops no signature (resample on hit).

Hard constraints enforced in code (§5.17, non-negotiable):
  - user prose passes through verbatim (asserted);
  - high-personal-stakes queries get a conservative wrapper or passthrough;
  - probe injections are flagged distinctly and never silently mixed with
    substantive queries;
  - injections that would be evidentiary false statements in real legal
    proceedings are denied (a small deny check). Cohort framings against the
    profiler ("As a doctor asking about", inverted-cohort, etc.) are explicitly
    allowed and NOT treated as credential fraud.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from random import Random

from ..config import CooKooConfig
from ..models import (
    AppliedInjection,
    InjectionPosition,
    InjectionType,
    Query,
    QueryKind,
)
from .filter import CuckooFilter

# --- §5.17 default libraries (used when config supplies none) ----------------
_DEFAULT_COHORT = [
    "I'm helping a friend who works in this area",
    "From the perspective of someone researching this",
    "For a research project on this topic",
    "A colleague asked me about this",
    "Quick question on behalf of someone",
    "As a doctor looking into this",
    "As an attorney reviewing this",
    "From a journalist's angle",
    "Writing this for a professional audience",
    "As someone in a different field entirely, asking about",
]

_DEFAULT_DISTRACTOR = [
    "Also, unrelated, but I've been thinking about medieval cartography",
    "While I'm here - quick aside on tide tables",
    "Separately, do you know much about freight logistics",
    "On another note, I've been curious about glassblowing",
]

_DEFAULT_REGISTER = {
    "academic": "Could you formally analyze the following question:",
    "journalistic": "I'm writing an article and need to know:",
    "conversational": "okay so like, basically i'm wondering",
    "technical": "Question, specification-style:",
    "pedagogical": "Explain to someone who's just learning this:",
}

_DEFAULT_PROBE = [
    "[probe: baseline framing]",
    "[probe: neutral context]",
]

# Deny patterns: injections that would be evidentiary FALSE statements in real
# legal proceedings (claiming to have witnessed events, sworn testimony, etc.).
# This is intentionally narrow per §5.17 constraint 2 -- cohort framings against
# a profiler are allowed; only courtroom-evidentiary fabrications are denied.
_LEGAL_EVIDENTIARY_DENY = re.compile(
    r"\b("
    r"i (?:personally )?witnessed|i saw (?:the|him|her|them) "
    r"(?:commit|do|kill|steal|attack)|"
    r"i was an eyewitness|under (?:oath|penalty of perjury)|"
    r"i (?:hereby )?(?:swear|testify|attest) that|"
    r"i can confirm under oath|my sworn (?:statement|testimony)|"
    r"i was present when .* (?:died|was killed|was murdered)"
    r")\b",
    re.IGNORECASE,
)

# High-personal-stakes detectors (§5.17). Conservative: false positive (skip
# injection on a routine query) is cheap; false negative (inject on a high-stakes
# query) can give the user worse advice on something that matters.
_CODE_FENCE = re.compile(r"```|\bdef \w+\s*\(|\bclass \w+|;\s*$|\{\s*$|#include\b")
_INLINE_CODE = re.compile(r"`[^`]+`")
_NUMERIC_SPEC = re.compile(
    r"\d+\s*(mg|ml|kg|mph|kph|hz|ghz|mhz|gb|mb|tb|px|°[cf]|%|mm|cm|km|"
    r"volts?|amps?|watts?|psi|bar|rpm|bpm)\b",
    re.IGNORECASE,
)
_MULTI_NUMBER = re.compile(r"(\d[\d.,]*\s+){3,}")

_MEDICAL = re.compile(
    r"\b(symptom|diagnos\w*|prescrib\w*|dosage|dose|medication|mg of|side effect|"
    r"my doctor|chest pain|blood pressure|tumou?r|cancer|chemo\w*|antibiotic|"
    r"surgery|prognosis|biopsy|insulin|blood sugar|seizure|allerg\w*)\b",
    re.IGNORECASE,
)
_LEGAL = re.compile(
    r"\b(lawsuit|sue|sued|plaintiff|defendant|subpoena|deposition|custody|"
    r"divorce|my lawyer|attorney|court date|indict\w*|felony|misdemeanor|"
    r"liabilit\w*|breach of contract|restraining order|statute of limitations)\b",
    re.IGNORECASE,
)
_MENTAL_HEALTH = re.compile(
    r"\b(suicid\w*|self[- ]harm|kill myself|want to die|depress\w*|"
    r"anxiety attack|panic attack|bipolar|ptsd|eating disorder|"
    r"hopeless|hurting myself)\b",
    re.IGNORECASE,
)
_IMMIGRATION = re.compile(
    r"\b(visa|green card|asylum|deport\w*|uscis|immigration|undocumented|"
    r"naturali[sz]ation|work permit|i-?\d{2,3}\b|h1b|h-1b|removal proceedings)\b",
    re.IGNORECASE,
)
_FINANCIAL = re.compile(
    r"\b(should i invest|invest my|my mortgage|my 401k|retirement savings|"
    r"my taxes|tax return|bankruptcy|my debt|my credit score|"
    r"life savings|net worth|my portfolio|refinanc\w*)\b",
    re.IGNORECASE,
)


def has_code_block(query: str) -> bool:
    if _CODE_FENCE.search(query):
        return True
    # several inline-code spans suggests a code-heavy question
    return len(_INLINE_CODE.findall(query)) >= 2


def has_numerical_specification(query: str) -> bool:
    return bool(_NUMERIC_SPEC.search(query) or _MULTI_NUMBER.search(query))


def looks_like_medical_question(query: str) -> bool:
    return bool(_MEDICAL.search(query))


def looks_like_legal_question(query: str) -> bool:
    return bool(_LEGAL.search(query))


def looks_like_mental_health(query: str) -> bool:
    return bool(_MENTAL_HEALTH.search(query))


def looks_like_immigration(query: str) -> bool:
    return bool(_IMMIGRATION.search(query))


def looks_like_financial_advice(query: str) -> bool:
    return bool(_FINANCIAL.search(query))


class InjectionDenied(ValueError):
    """Raised when a candidate injection would be a courtroom-evidentiary lie."""


def is_evidentiary_false_statement(text: str) -> bool:
    """Deny check (§5.17 constraint 2, narrow version).

    True only for framings that would be directly evidentiary false statements
    in real legal proceedings. Cohort/professional/inverted framings against the
    profiler are allowed and return False.
    """
    return bool(_LEGAL_EVIDENTIARY_DENY.search(text))


# Conservative low-claim wrapper used for high-stakes queries that are still
# injected rather than passed through (§5.17 constraint 3).
_CONSERVATIVE_PREFIX = "Asking on behalf of someone"


class CooKooInjector:
    """Applies §5.17 per-query injections to the user's real queries."""

    def __init__(
        self,
        cfg: CooKooConfig | None = None,
        cuckoo: CuckooFilter | None = None,
    ):
        self.cfg = cfg or CooKooConfig()
        self.cuckoo = cuckoo or CuckooFilter.from_config(self.cfg)
        self.cohort_library: Sequence[str] = (
            self.cfg.cohort_library or _DEFAULT_COHORT
        )
        self.distractor_library: Sequence[str] = (
            self.cfg.distractor_library or _DEFAULT_DISTRACTOR
        )
        self.register_modifiers: dict[str, str] = (
            self.cfg.register_modifiers or _DEFAULT_REGISTER
        )

    # --- high-stakes detector ----------------------------------------------
    def should_passthrough(self, query: str) -> bool:
        """§5.17 high-personal-stakes detector (conservative, default-on)."""
        return any(
            [
                has_code_block(query),
                has_numerical_specification(query),
                looks_like_medical_question(query),
                looks_like_legal_question(query),
                looks_like_mental_health(query),
                looks_like_immigration(query),
                looks_like_financial_advice(query),
                len(query) > self.cfg.passthrough_max_length,
            ]
        )

    # --- distribution helpers ----------------------------------------------
    @staticmethod
    def _weighted_choice(
        rng: Random, balance: dict[str, float], fallback: list[str]
    ) -> str:
        items = [(k, v) for k, v in balance.items() if v > 0]
        if not items:
            return rng.choice(fallback)
        keys = [k for k, _ in items]
        weights = [v for _, v in items]
        return rng.choices(keys, weights=weights, k=1)[0]

    def _pick_type(self, rng: Random) -> InjectionType:
        balance = dict(self.cfg.type_balance.weights)
        if not balance:
            balance = {
                "cohort": 0.30,
                "topic": 0.25,
                "register": 0.25,
                "probe": 0.10,
                "passthrough": 0.10,
            }
        key = self._weighted_choice(rng, balance, ["cohort"])
        return InjectionType(key)

    def _pick_position(self, rng: Random, itype: InjectionType) -> InjectionPosition:
        if itype == InjectionType.PASSTHROUGH:
            return InjectionPosition.NONE
        balance = dict(self.cfg.position_distribution.weights)
        # The position balance config includes a "passthrough" weight that maps
        # to NONE; drop it here since type already decided passthrough.
        balance.pop("passthrough", None)
        if not balance:
            balance = {"prefix": 0.45, "suffix": 0.30, "wrap": 0.25}
        key = self._weighted_choice(rng, balance, ["prefix"])
        return InjectionPosition(key)

    def _pick_text(
        self, rng: Random, itype: InjectionType
    ) -> tuple[str, str | None]:
        """Return (injection_text, category)."""
        if itype == InjectionType.COHORT_CONTEXT:
            return rng.choice(list(self.cohort_library)), "cohort"
        if itype == InjectionType.TOPIC_DISTRACTOR:
            return rng.choice(list(self.distractor_library)), "topic"
        if itype == InjectionType.REGISTER_MODIFIER:
            reg = rng.choice(list(self.register_modifiers.keys()))
            return self.register_modifiers[reg], reg
        if itype == InjectionType.PROBE:
            return rng.choice(_DEFAULT_PROBE), "probe"
        return "", None  # passthrough

    # --- assembly -----------------------------------------------------------
    @staticmethod
    def _assemble(query: str, inj_text: str, position: InjectionPosition) -> str:
        if position == InjectionPosition.NONE or not inj_text:
            return query
        if position == InjectionPosition.PREFIX:
            return f"{inj_text} {query}"
        if position == InjectionPosition.SUFFIX:
            return f"{query} {inj_text}"
        if position == InjectionPosition.WRAP:
            return f"{inj_text} {query} (end of question)"
        return query

    def _resample_dedup(
        self, rng: Random, itype: InjectionType, now_ms: int | None
    ) -> tuple[str, str | None]:
        """Pick injection text, resampling on cuckoo-filter hit; deny check.

        Up to a bounded number of attempts; on exhaustion the last candidate is
        accepted (a repeat is harmless correctness-wise, dedup is best-effort).
        """
        attempts = 0
        last: tuple[str, str | None] = ("", None)
        while attempts < 12:
            attempts += 1
            text, category = self._pick_text(rng, itype)
            if is_evidentiary_false_statement(text):
                continue  # never emit a courtroom-evidentiary lie
            last = (text, category)
            if not text:  # passthrough has no text to dedup
                return last
            if not self.cuckoo.contains(text):
                self.cuckoo.insert(text, now_ms=now_ms)
                return last
        # exhausted: accept the last non-denied candidate, record it
        if last[0]:
            self.cuckoo.insert(last[0], now_ms=now_ms)
        return last

    # --- public entry point -------------------------------------------------
    def inject(
        self,
        query: str,
        rng: Random,
        *,
        user_override_passthrough: bool = False,
        probe: bool = False,
        now_ms: int | None = None,
    ) -> Query:
        """Apply a §5.17 injection to a real query and return a REAL Query.

        Args:
            query: the user's verbatim prose.
            rng: a `random.Random` for reproducibility.
            user_override_passthrough: user explicitly demanded no injection.
            probe: this is a measurement probe pass (flagged distinctly).
            now_ms: insertion time for cuckoo aging (defaults to wall clock).
        """
        high_stakes = self.should_passthrough(query)

        # Probe queries are a separate measurement workflow and are flagged
        # distinctly; they are NEVER silently mixed with substantive injections.
        if probe:
            if high_stakes or user_override_passthrough:
                # Never probe a high-stakes / overridden query: pass it through.
                return self._build(
                    query,
                    InjectionType.PASSTHROUGH,
                    InjectionPosition.NONE,
                    "",
                    None,
                    user_override=user_override_passthrough,
                    probe=True,
                )
            text, category = self._resample_dedup(rng, InjectionType.PROBE, now_ms)
            position = self._pick_position(rng, InjectionType.PROBE)
            return self._build(
                query,
                InjectionType.PROBE,
                position,
                text,
                category,
                probe=True,
            )

        # User override or high-stakes -> passthrough (verbatim, no injection).
        if user_override_passthrough or high_stakes:
            return self._build(
                query,
                InjectionType.PASSTHROUGH,
                InjectionPosition.NONE,
                "",
                None,
                user_override=user_override_passthrough,
                high_stakes=high_stakes,
            )

        itype = self._pick_type(rng)
        if itype == InjectionType.PROBE:
            # type_balance can roll "probe", but probes must not silently mix
            # with substantive queries -> downgrade to passthrough control.
            itype = InjectionType.PASSTHROUGH
        if itype == InjectionType.PASSTHROUGH:
            return self._build(
                query, InjectionType.PASSTHROUGH, InjectionPosition.NONE, "", None
            )

        text, category = self._resample_dedup(rng, itype, now_ms)
        position = self._pick_position(rng, itype)
        return self._build(query, itype, position, text, category)

    def _build(
        self,
        query: str,
        itype: InjectionType,
        position: InjectionPosition,
        inj_text: str,
        category: str | None,
        *,
        user_override: bool = False,
        probe: bool = False,
        high_stakes: bool = False,
    ) -> Query:
        wrapped = self._assemble(query, inj_text, position)

        # HARD CONSTRAINT: verbatim prose must survive untouched.
        assert query in wrapped, "CooKoo must never rewrite the user's prose"

        applied = AppliedInjection(
            injection_type=itype,
            position=position,
            text=inj_text,
            category=category,
            user_override=user_override,
        )
        meta = {}
        if probe:
            meta["probe"] = True
        if high_stakes:
            meta["high_stakes"] = True
        return Query(
            text=wrapped,
            kind=QueryKind.REAL,
            original_text=query,
            injection=applied,
            metadata=meta,
        )
