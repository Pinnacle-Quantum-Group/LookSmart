"""Generator factory (README §5.9-§5.21).

``build_generator(mode, config, llm)`` returns the :class:`DecoyGenerator` for a
mode. ``config`` is the *per-mode* config object (e.g. ``WeirdAlConfig``,
``SpectrumModeConfig``, ``FenceConfig``) -- the same object that lives on the
corresponding field of :class:`~looksmart.config.LookSmartConfig`. A
:class:`~looksmart.config.LookSmartConfig` may also be passed and the right
field is selected automatically.
"""

from __future__ import annotations

from ..config import LookSmartConfig
from ..llm_protocol import LocalLLM
from ..models import GenerationMode
from .base import DecoyGenerator
from .cohort import (
    GenderRouletteGenerator,
    HealthStatusRouletteGenerator,
    ImmigrationRouletteGenerator,
    OrientationRouletteGenerator,
)
from .curation import LibraryCurator
from .fence import FenceGenerator
from .health import HealthGenerator
from .identity import IdentityGenerator
from .plain import PlainGenerator
from .politic import PoliticGenerator
from .religious import ReligiousGenerator
from .spelunking import SpelunkingGenerator
from .weird_al import WeirdAlGenerator

# mode -> (generator class, LookSmartConfig field name for that mode's config)
_REGISTRY: dict[GenerationMode, tuple[type[DecoyGenerator], str]] = {
    GenerationMode.WEIRD_AL: (WeirdAlGenerator, "weird_al"),
    GenerationMode.FENCE: (FenceGenerator, "fence"),
    GenerationMode.SPELUNKING: (SpelunkingGenerator, "spelunking"),
    GenerationMode.POLITIC_ROULETTE: (PoliticGenerator, "politic_roulette"),
    GenerationMode.RELIGIOUS: (ReligiousGenerator, "religious"),
    GenerationMode.ASKING_FOR_A_FRIEND: (HealthGenerator, "asking_for_a_friend"),
    GenerationMode.IDENTITY_SEARCH: (IdentityGenerator, "identity_search"),
    GenerationMode.GENDER_ROULETTE: (GenderRouletteGenerator, "gender_roulette"),
    GenerationMode.ORIENTATION_ROULETTE: (
        OrientationRouletteGenerator,
        "orientation_roulette",
    ),
    GenerationMode.IMMIGRATION_ROULETTE: (
        ImmigrationRouletteGenerator,
        "immigration_roulette",
    ),
    GenerationMode.HEALTH_STATUS_ROULETTE: (
        HealthStatusRouletteGenerator,
        "health_status_roulette",
    ),
    GenerationMode.PLAIN: (PlainGenerator, "plain"),
}


def build_generator(
    mode: GenerationMode,
    config,
    llm: LocalLLM,
    curator: LibraryCurator | None = None,
) -> DecoyGenerator:
    """Construct the generator for ``mode``.

    ``config`` may be the per-mode config object or a full
    :class:`LookSmartConfig` (in which case the per-mode field is selected).
    """
    if mode not in _REGISTRY:
        raise ValueError(f"no generator registered for mode {mode!r}")
    gen_cls, field = _REGISTRY[mode]

    mode_config = config
    if isinstance(config, LookSmartConfig):
        mode_config = getattr(config, field, None)
        if mode_config is None and mode is GenerationMode.PLAIN:
            mode_config = object()  # PLAIN reads nothing off config

    if mode_config is None:
        mode_config = object()

    return gen_cls(mode_config, llm, curator=curator)
