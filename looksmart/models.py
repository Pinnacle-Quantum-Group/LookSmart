"""Core runtime data contracts shared across all LookSmart subsystems.

These are frozen interfaces. Subsystem modules import from here and must not
redefine these types. Config-file schemas live in `looksmart.config`; this
module holds the in-memory objects that flow between components at runtime.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class ThreatObjective(str, Enum):
    """The two primary objectives from README §2.3."""

    PROFILE_DILUTION = "profile_dilution"  # objective (3): move profile centroid
    COST_IMPOSITION = "cost_imposition"  # objective (4): raise cost-per-useful-bit


class QueryKind(str, Enum):
    REAL = "real"  # user's actual query (may be CooKoo-wrapped)
    DECOY = "decoy"  # synthetic cover traffic
    PROBE = "probe"  # CooKoo provider-behavior probe (§5.17)


class GenerationMode(str, Enum):
    """Decoy generation modes (README §5.9-5.21)."""

    WEIRD_AL = "weird_al"
    FENCE = "fence"  # benign edge-band dilution only; no safety-stack-load objective
    SPELUNKING = "spelunking"
    POLITIC_ROULETTE = "politic_roulette"
    RELIGIOUS = "religious"
    ASKING_FOR_A_FRIEND = "asking_for_a_friend"
    IDENTITY_SEARCH = "identity_search"
    GENDER_ROULETTE = "gender_roulette"
    ORIENTATION_ROULETTE = "orientation_roulette"
    IMMIGRATION_ROULETTE = "immigration_roulette"
    HEALTH_STATUS_ROULETTE = "health_status_roulette"
    PLAIN = "plain"  # persona-coherent content with no special register treatment


class InjectionType(str, Enum):
    """CooKoo Filter injection categories (README §5.17)."""

    COHORT_CONTEXT = "cohort"
    TOPIC_DISTRACTOR = "topic"
    REGISTER_MODIFIER = "register"
    PROBE = "probe"
    PASSTHROUGH = "passthrough"


class InjectionPosition(str, Enum):
    PREFIX = "prefix"
    SUFFIX = "suffix"
    WRAP = "wrap"
    NONE = "none"


class EngagementType(str, Enum):
    """Engagement signals a real user emits (README §5.4)."""

    FOLLOW_UP = "follow_up"
    CLARIFICATION = "clarification"
    COPY = "copy"
    REGENERATE = "regenerate"
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    CONTINUE = "continue"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class EngagementEvent:
    kind: EngagementType
    turn_index: int
    timestamp_ms: int = field(default_factory=_now_ms)
    detail: str | None = None


@dataclass
class Turn:
    """One user->assistant exchange within a session."""

    prompt: str
    role: str = "user"
    index: int = 0
    response: str | None = None
    timestamp_ms: int = field(default_factory=_now_ms)


@dataclass
class Query:
    """A single dispatchable unit of traffic.

    For DECOY queries `persona_id` identifies the source persona. For REAL
    queries that passed through CooKoo, `injection` records what was applied
    and `original_text` preserves the user's verbatim prose.
    """

    text: str
    kind: QueryKind
    id: str = field(default_factory=_new_id)
    persona_id: str | None = None
    mode: GenerationMode | None = None
    original_text: str | None = None  # set when CooKoo wrapped a REAL query
    injection: "AppliedInjection | None" = None
    objective: ThreatObjective | None = None
    timestamp_ms: int = field(default_factory=_now_ms)
    metadata: dict = field(default_factory=dict)


@dataclass
class Session:
    """A multi-turn conversation bound to one persona (README §5.3 sticky)."""

    persona_id: str
    kind: QueryKind
    id: str = field(default_factory=_new_id)
    mode: GenerationMode | None = None
    turns: list[Turn] = field(default_factory=list)
    engagement: list[EngagementEvent] = field(default_factory=list)
    started_ms: int = field(default_factory=_now_ms)
    metadata: dict = field(default_factory=dict)


@dataclass
class AppliedInjection:
    """Record of a CooKoo injection applied to a real query (README §5.17)."""

    injection_type: InjectionType
    position: InjectionPosition
    text: str
    category: str | None = None
    user_override: bool = False


@dataclass
class ProviderResponse:
    text: str
    provider: str
    refused: bool = False
    truncated: bool = False  # output replaced/cut mid-stream
    raw: dict = field(default_factory=dict)
    latency_ms: int | None = None


@dataclass
class TopicTag:
    """Normalized topic identifier (WikiData Q-ID where available, README §5.22)."""

    qid: str | None
    label: str
    confidence: float = 1.0
