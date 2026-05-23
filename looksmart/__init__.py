"""LookSmart: knowledge-work infrastructure with incidental privacy properties.

Implements the architecture in README §5. Public re-exports below are the
stable surface; subsystem internals live in their respective modules.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .config import LookSmartConfig
from .models import (
    AppliedInjection,
    EngagementEvent,
    EngagementType,
    GenerationMode,
    InjectionPosition,
    InjectionType,
    ProviderResponse,
    Query,
    QueryKind,
    Session,
    ThreatObjective,
    TopicTag,
    Turn,
)

__all__ = [
    "__version__",
    "LookSmartConfig",
    "Query",
    "QueryKind",
    "Session",
    "Turn",
    "EngagementEvent",
    "EngagementType",
    "GenerationMode",
    "InjectionType",
    "InjectionPosition",
    "AppliedInjection",
    "ProviderResponse",
    "ThreatObjective",
    "TopicTag",
]
