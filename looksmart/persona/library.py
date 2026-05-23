"""Persona library: dataclass + YAML loader (README §5.5).

A persona encodes *who is speaking* in a decoy session. Per §5.5 each persona
carries:

  - topic_priors:        Dirichlet weights over a topic taxonomy (dict[str,float])
  - language_weights:    power-law weights over languages (dict[str,float])
  - register/formality:  register and formality priors
  - engagement priors:   typical follow_up_rate / regeneration_rate / copy_rate
  - seed_prompts:        sample seed prompts for generation
  - coherence_constraints: free-form, e.g. "doesn't query in Albanian about
                          Tagalog poetry"
  - tier:                "median" | "polymath" | "rare"
  - distinctiveness_warning: opt-in distinctive presets are flagged so the UI
                          can warn (anti-signature discipline, §5.5).

The loader reads all ``*.yaml`` in the configured library dir, validates each,
and returns a ``dict[id, Persona]``. ``PersonaLibrary`` wraps that mapping with
``get`` / ``all`` / ``sample_weighted`` helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

VALID_TIERS = ("median", "polymath", "rare")


@dataclass
class Persona:
    """One curated decoy persona (README §5.5)."""

    id: str
    display_name: str
    topic_priors: dict[str, float] = field(default_factory=dict)
    language_weights: dict[str, float] = field(default_factory=dict)
    register_priors: dict[str, float] = field(default_factory=dict)
    formality: float = 0.5
    follow_up_rate: float = 0.5
    regeneration_rate: float = 0.1
    copy_rate: float = 0.2
    thumbs_rate: float = 0.1
    seed_prompts: list[str] = field(default_factory=list)
    coherence_constraints: str = ""
    tier: str = "median"
    distinctiveness_warning: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("persona.id must be non-empty")
        if self.tier not in VALID_TIERS:
            raise ValueError(
                f"persona {self.id!r}: tier must be one of {VALID_TIERS}, "
                f"got {self.tier!r}"
            )
        # Polymath / rare presets are aesthetically distinctive; per §5.5 they
        # carry a distinctiveness warning by default unless explicitly cleared.
        if self.tier in ("polymath", "rare") and not self.distinctiveness_warning:
            self.distinctiveness_warning = True
        self.topic_priors = _normalize(self.topic_priors)
        self.language_weights = _normalize(self.language_weights)
        self.register_priors = _normalize(self.register_priors)
        for name, val in (
            ("formality", self.formality),
            ("follow_up_rate", self.follow_up_rate),
            ("regeneration_rate", self.regeneration_rate),
            ("copy_rate", self.copy_rate),
            ("thumbs_rate", self.thumbs_rate),
        ):
            if not 0.0 <= float(val) <= 1.0:
                raise ValueError(
                    f"persona {self.id!r}: {name} must be in [0,1], got {val}"
                )

    def sample_topic(self, rng: np.random.Generator) -> str | None:
        """Draw a topic from this persona's Dirichlet topic priors."""
        return _sample_from(self.topic_priors, rng)

    def sample_language(self, rng: np.random.Generator) -> str | None:
        """Draw a language from this persona's power-law language weights."""
        return _sample_from(self.language_weights, rng)


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    if not weights:
        return {}
    total = sum(weights.values())
    if total <= 0:
        return dict(weights)
    return {k: float(v) / total for k, v in weights.items()}


def _sample_from(weights: dict[str, float], rng: np.random.Generator) -> str | None:
    if not weights:
        return None
    keys = list(weights.keys())
    probs = np.asarray([weights[k] for k in keys], dtype=float)
    probs = probs / probs.sum()
    return str(rng.choice(keys, p=probs))


def _coerce_persona(pid_default: str, data: dict) -> Persona:
    """Build a Persona from a parsed YAML mapping, tolerating field aliases."""
    if not isinstance(data, dict):
        raise ValueError(f"persona file {pid_default!r}: top-level must be a mapping")

    eng = data.get("engagement_priors") or {}
    pid = str(data.get("id") or pid_default)
    return Persona(
        id=pid,
        display_name=str(data.get("display_name") or pid),
        topic_priors=dict(data.get("topic_priors") or {}),
        language_weights=dict(data.get("language_weights") or {}),
        register_priors=dict(
            data.get("register_priors") or data.get("register") or {}
        ),
        formality=float(data.get("formality", 0.5)),
        follow_up_rate=float(eng.get("follow_up_rate", data.get("follow_up_rate", 0.5))),
        regeneration_rate=float(
            eng.get("regeneration_rate", data.get("regeneration_rate", 0.1))
        ),
        copy_rate=float(eng.get("copy_rate", data.get("copy_rate", 0.2))),
        thumbs_rate=float(eng.get("thumbs_rate", data.get("thumbs_rate", 0.1))),
        seed_prompts=list(data.get("seed_prompts") or []),
        coherence_constraints=str(data.get("coherence_constraints") or ""),
        tier=str(data.get("tier") or "median"),
        distinctiveness_warning=bool(data.get("distinctiveness_warning", False)),
    )


def load_personas(library_dir: str | Path) -> dict[str, Persona]:
    """Read every ``*.yaml`` under ``library_dir`` and validate each persona.

    Raises ``FileNotFoundError`` if the directory does not exist and
    ``ValueError`` on a duplicate persona id.
    """
    path = Path(library_dir).expanduser()
    if not path.is_dir():
        raise FileNotFoundError(f"persona library dir not found: {path}")

    out: dict[str, Persona] = {}
    for yaml_path in sorted(path.glob("*.yaml")):
        raw = yaml.safe_load(yaml_path.read_text()) or {}
        persona = _coerce_persona(yaml_path.stem, raw)
        if persona.id in out:
            raise ValueError(
                f"duplicate persona id {persona.id!r} (file {yaml_path.name})"
            )
        out[persona.id] = persona
    return out


class PersonaLibrary:
    """A validated collection of personas with sampling helpers."""

    def __init__(self, personas: dict[str, Persona]):
        self._personas = dict(personas)

    @classmethod
    def from_dir(cls, library_dir: str | Path) -> "PersonaLibrary":
        return cls(load_personas(library_dir))

    def get(self, persona_id: str) -> Persona:
        try:
            return self._personas[persona_id]
        except KeyError as exc:
            raise KeyError(f"unknown persona id: {persona_id!r}") from exc

    def all(self) -> list[Persona]:
        return list(self._personas.values())

    def ids(self) -> list[str]:
        return list(self._personas.keys())

    def by_tier(self, tier: str) -> list[Persona]:
        return [p for p in self._personas.values() if p.tier == tier]

    def __len__(self) -> int:
        return len(self._personas)

    def __contains__(self, persona_id: object) -> bool:
        return persona_id in self._personas

    def sample_weighted(
        self, weights: dict[str, float], rng: np.random.Generator
    ) -> Persona:
        """Sample a persona using ``weights`` (id -> weight).

        Personas absent from ``weights`` get weight 0. If ``weights`` is empty
        the choice is uniform over the whole library. Unknown ids in ``weights``
        are ignored.
        """
        if not self._personas:
            raise ValueError("cannot sample from an empty persona library")

        ids = self.ids()
        if not weights:
            probs = np.full(len(ids), 1.0 / len(ids))
        else:
            raw = np.asarray([max(0.0, float(weights.get(i, 0.0))) for i in ids])
            if raw.sum() <= 0:
                probs = np.full(len(ids), 1.0 / len(ids))
            else:
                probs = raw / raw.sum()
        chosen = str(rng.choice(ids, p=probs))
        return self._personas[chosen]
