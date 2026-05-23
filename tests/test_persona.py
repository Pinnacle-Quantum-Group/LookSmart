"""Tests for the persona library and two-stage sampler (README §5.2, §5.5)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from looksmart.config import SamplerConfig
from looksmart.models import QueryKind
from looksmart.persona.library import PersonaLibrary, load_personas
from looksmart.persona.sampler import PersonaSampler, default_power_law_weights

LIB_DIR = Path(__file__).resolve().parents[1] / "looksmart" / "persona" / "library"


@pytest.fixture
def library() -> PersonaLibrary:
    return PersonaLibrary.from_dir(LIB_DIR)


def test_default_library_loads_and_has_expected_presets(library: PersonaLibrary):
    ids = set(library.ids())
    medians = {
        "office_it_generalist",
        "small_business_operator",
        "hobbyist_gardener_cook",
        "parent_school_age",
        "college_social_sciences",
    }
    assert medians.issubset(ids)
    # at least one polymath and one rare, both flagged distinctive
    assert library.by_tier("polymath")
    assert library.by_tier("rare")
    for p in library.by_tier("polymath") + library.by_tier("rare"):
        assert p.distinctiveness_warning is True


def test_persona_priors_normalized(library: PersonaLibrary):
    p = library.get("office_it_generalist")
    assert pytest.approx(sum(p.topic_priors.values()), abs=1e-9) == 1.0
    assert pytest.approx(sum(p.language_weights.values()), abs=1e-9) == 1.0


def test_p_real_respected_over_many_draws(library: PersonaLibrary):
    cfg = SamplerConfig(p_real=0.3)
    sampler = PersonaSampler(library, cfg)
    rng = np.random.default_rng(42)
    n = 20_000
    reals = sum(
        1 for _ in range(n) if sampler.decide_kind(rng) is QueryKind.REAL
    )
    assert abs(reals / n - 0.3) < 0.02


def test_weighted_sampling_is_non_uniform(library: PersonaLibrary):
    """Default power-law weights must NOT produce a uniform distribution."""
    sampler = PersonaSampler(library)
    rng = np.random.default_rng(7)
    counts: dict[str, int] = {pid: 0 for pid in library.ids()}
    n = 30_000
    for _ in range(n):
        counts[sampler.sample_persona(rng).id] += 1

    freqs = np.array([counts[pid] / n for pid in library.ids()])
    uniform = 1.0 / len(library)
    # dominant persona should be far above uniform
    assert freqs.max() > uniform * 1.8
    # there must be meaningful spread (non-uniform)
    assert freqs.std() > 0.05


def test_default_power_law_shape():
    w = default_power_law_weights([f"p{i}" for i in range(6)])
    vals = sorted(w.values(), reverse=True)
    assert vals[0] == pytest.approx(0.50)
    assert vals[1] == pytest.approx(0.20)
    assert vals[2] == pytest.approx(0.20)
    assert sum(w.values()) == pytest.approx(1.0)


def test_sticky_within_session(library: PersonaLibrary):
    sampler = PersonaSampler(library, SamplerConfig(sticky_within_session=True))
    rng = np.random.default_rng(1)
    first = sampler.persona_for_session("sess-A", rng)
    for _ in range(50):
        assert sampler.persona_for_session("sess-A", rng).id == first.id
    sampler.release_session("sess-A")
    # a fresh binding may differ; just ensure it does not raise
    sampler.persona_for_session("sess-A", rng)


def test_explicit_weights_override(library: PersonaLibrary):
    cfg = SamplerConfig(persona_weights={"office_it_generalist": 1.0})
    sampler = PersonaSampler(library, cfg)
    rng = np.random.default_rng(3)
    for _ in range(100):
        assert sampler.sample_persona(rng).id == "office_it_generalist"


def test_load_personas_missing_dir():
    with pytest.raises(FileNotFoundError):
        load_personas("/nonexistent/persona/dir")
