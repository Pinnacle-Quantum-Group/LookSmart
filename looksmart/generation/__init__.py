"""Decoy content generation subsystem (README §5.9-§5.21).

Each :class:`DecoyGenerator` subclass implements one generation mode. All
generated content is routed through :mod:`looksmart.generation.curation` (the
§12.4-§12.5 hard-exclusion guardrail) before it is emitted as a Query/Session.

Use :func:`build_generator` to construct a generator for a mode + config + LLM.
"""

from __future__ import annotations

from .base import DecoyGenerator, MaxResampleError
from .curation import (
    ALL_CATEGORIES,
    CurationError,
    CurationResult,
    FENCE_SEEDS,
    HEALTH_SEEDS,
    LibraryCurator,
    is_excluded,
    validate_seed_libraries,
)
from .registry import build_generator

__all__ = [
    "DecoyGenerator",
    "MaxResampleError",
    "LibraryCurator",
    "CurationResult",
    "CurationError",
    "is_excluded",
    "validate_seed_libraries",
    "FENCE_SEEDS",
    "HEALTH_SEEDS",
    "ALL_CATEGORIES",
    "build_generator",
]
