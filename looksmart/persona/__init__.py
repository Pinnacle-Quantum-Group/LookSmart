"""Persona subsystem (README §5.2, §5.5).

Two-stage sampling: first roll picks *who is speaking* (persona), the second
roll (handled by generation modes) picks language and content conditional on
that persona's plausible distribution. Internally-coherent sessions, no random
cross-topic products. See README §5.5.
"""

from __future__ import annotations

from .library import Persona, PersonaLibrary, load_personas
from .sampler import PersonaSampler

__all__ = [
    "Persona",
    "PersonaLibrary",
    "load_personas",
    "PersonaSampler",
]
