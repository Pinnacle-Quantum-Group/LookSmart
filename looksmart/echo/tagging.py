"""Echo Mode topic tagging (README §5.22, methodology steps 1-2).

Both LookSmart queries and imported recommender observations are tagged to
WikiData-Q-ID-style :class:`~looksmart.models.TopicTag` objects so the
correlation engine can match query topics to observation topics on a single
canonical cross-platform identifier.

Two taggers are provided:

* :class:`LLMTagger` -- uses a :class:`~looksmart.llm_protocol.LocalLLM` to do
  NER + topic classification + entity extraction and map the result to
  WikiData Q-IDs with confidence scores. Low-confidence mappings are flagged
  (per §5.22 open question on taxonomy: "WikiData with confidence scores,
  flagging low-confidence mappings as such").
* :class:`KeywordFallbackTagger` -- a *deterministic* offline tagger
  (keyword -> fake-QID) so tests and offline development do not need a real
  model. Same hash of the same text always yields the same tags.

WikiData lossiness is real (§5.22): the mapping to WikiData is lossy and
platforms use different internal taxonomies, so confidence is first-class and
``low_confidence`` is surfaced rather than silently dropped.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..llm_protocol import LocalLLM
from ..models import TopicTag

# Mappings below the threshold are kept but flagged ``low_confidence``.
LOW_CONFIDENCE_THRESHOLD = 0.5

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'_-]+")
_STOPWORDS = frozenset(
    """
    the a an and or but of to in on at for with about from into over after
    is are was were be been being do does did this that these those it its
    i you he she we they me my your his her our their what who when where why
    how which whom whose as by if so than then there here not no yes can will
    just like get got was were has have had me mine ours yours theirs
    """.split()
)


class TopicTagger(Protocol):
    """Tag arbitrary text into normalized :class:`TopicTag` objects."""

    def tag(self, text: str) -> list[TopicTag]: ...


def _keywords(text: str, *, max_terms: int = 6) -> list[str]:
    """Extract candidate content words, deterministically ordered.

    Ordering is by (first-occurrence index) so the same text always yields the
    same keyword sequence -- the determinism the fallback tagger relies on.
    """
    seen: dict[str, int] = {}
    for i, m in enumerate(_WORD_RE.finditer(text.lower())):
        w = m.group(0)
        if w in _STOPWORDS or len(w) < 3:
            continue
        if w not in seen:
            seen[w] = i
    ordered = sorted(seen, key=lambda w: seen[w])
    return ordered[:max_terms]


def _fake_qid(keyword: str) -> str:
    """Deterministic fake WikiData Q-ID for a keyword (offline fallback).

    Real WikiData Q-IDs look like ``Q42``. We synthesize a stable pseudo-QID
    from a hash of the lemma so equal keywords across queries and observations
    map to the *same* tag (which is what makes topic overlap computable).
    """
    h = hashlib.sha1(keyword.encode("utf-8")).hexdigest()
    return "Q" + str(int(h[:8], 16))


@dataclass
class KeywordFallbackTagger:
    """Deterministic offline tagger: keyword -> fake-QID.

    No model required. Confidence is a deterministic function of the keyword's
    salience (earlier, longer keywords score higher) so that ``low_confidence``
    flagging is still exercised in tests without randomness.
    """

    max_terms: int = 6

    def tag(self, text: str) -> list[TopicTag]:
        kws = _keywords(text, max_terms=self.max_terms)
        tags: list[TopicTag] = []
        for rank, kw in enumerate(kws):
            # Deterministic confidence: decays with rank, boosted by length.
            conf = max(0.2, min(1.0, 0.9 - 0.12 * rank + 0.01 * (len(kw) - 3)))
            tags.append(TopicTag(qid=_fake_qid(kw), label=kw, confidence=round(conf, 4)))
        return tags


@dataclass
class LLMTagger:
    """LocalLLM-backed NER + topic classifier mapping to WikiData Q-IDs.

    The model is prompted to return JSON ``[{"qid","label","confidence"}, ...]``.
    Parsing is tolerant; if the model returns nothing usable we fall back to the
    deterministic keyword tagger so a query is never left untagged.
    """

    llm: LocalLLM
    fallback: KeywordFallbackTagger | None = None

    _SYSTEM = (
        "You are a topic tagger. Extract named entities and topics from the "
        "user text. Return ONLY a JSON array of objects with keys 'qid' "
        "(WikiData Q-ID like Q42, or null if unknown), 'label' (short string), "
        "and 'confidence' (0..1). No prose."
    )

    def __post_init__(self) -> None:
        if self.fallback is None:
            self.fallback = KeywordFallbackTagger()

    def tag(self, text: str) -> list[TopicTag]:
        raw = self.llm.generate(text, system=self._SYSTEM, temperature=0.0)
        tags = self._parse(raw)
        if not tags:
            return self.fallback.tag(text)  # type: ignore[union-attr]
        return tags

    @staticmethod
    def _parse(raw: str) -> list[TopicTag]:
        # Find the first JSON array in the output and parse leniently.
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            data = json.loads(raw[start : end + 1])
        except (ValueError, json.JSONDecodeError):
            return []
        out: list[TopicTag] = []
        if not isinstance(data, list):
            return []
        for item in data:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            qid = item.get("qid")
            qid = str(qid) if qid not in (None, "", "null") else None
            try:
                conf = float(item.get("confidence", 1.0))
            except (TypeError, ValueError):
                conf = 1.0
            out.append(TopicTag(qid=qid, label=label, confidence=max(0.0, min(1.0, conf))))
        return out


def is_low_confidence(tag: TopicTag, threshold: float = LOW_CONFIDENCE_THRESHOLD) -> bool:
    """Flag a mapping as low-confidence (§5.22 taxonomy open question)."""
    return tag.qid is None or tag.confidence < threshold


def tag_keys(tags: Sequence[TopicTag], *, include_low_confidence: bool = True) -> list[str]:
    """Reduce tags to canonical match keys (Q-ID where present, else label).

    These keys are what the store persists (JSON array) and what the
    correlation engine compares for topic overlap.
    """
    keys: list[str] = []
    for t in tags:
        if not include_low_confidence and is_low_confidence(t):
            continue
        keys.append(t.qid if t.qid else f"label:{t.label.lower()}")
    # de-dup, stable order
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out
