"""Pydantic schemas for LookSmart configuration (loaded from YAML/JSON).

Mirrors the per-mode config blocks in README §5. Subsystems consume these
models; they do not parse raw YAML themselves. Use `LookSmartConfig.load(path)`.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


def _normalize(balance: dict[str, float]) -> dict[str, float]:
    total = sum(balance.values())
    if total <= 0:
        return balance
    return {k: v / total for k, v in balance.items()}


class Balance(BaseModel):
    """A categorical distribution that auto-normalizes its weights."""

    weights: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _norm(self) -> "Balance":
        self.weights = _normalize(self.weights)
        return self

    def items(self):
        return self.weights.items()


# --- §5.2 Persona Sampler ---------------------------------------------------
class SamplerConfig(BaseModel):
    p_real: float = Field(0.30, ge=0.0, le=1.0)  # passthrough probability
    # power-law weights over persona ids; empty => uniform over library
    persona_weights: dict[str, float] = Field(default_factory=dict)
    sticky_within_session: bool = True


# --- §5.3 Behavioral Scheduler ----------------------------------------------
class SchedulerConfig(BaseModel):
    process: str = Field("hawkes", pattern="^(hawkes|nhpp|poisson)$")
    rolling_window_days: int = 30
    perturbation: float = Field(0.1, ge=0.0, le=1.0)  # KL-divergence knob
    interleave_at_session_level: bool = True


# --- §5.4 Engagement Simulator ----------------------------------------------
class EngagementConfig(BaseModel):
    min_turns: int = 2
    max_turns: int = 8
    copy_rate: float = 0.2
    regenerate_rate: float = 0.1
    follow_up_rate: float = 0.5
    thumbs_rate: float = 0.1


# --- §5.9 Weird Al ----------------------------------------------------------
class WeirdAlConfig(BaseModel):
    register_chaos: float = Field(0.0, ge=0.0, le=1.0)
    placeholder_noun_rate: float = Field(0.0, ge=0.0, le=1.0)
    vulgarity_rate: float = 0.0  # Poisson lambda
    cross_register_pairs: list[list[str]] = Field(default_factory=list)


# --- §5.10 Fence band (benign dilution category only) -----------------------
class FenceConfig(BaseModel):
    rate: float = Field(0.0, ge=0.0, le=1.0)
    categories: list[str] = Field(default_factory=list)
    refusal_grace: float = Field(0.6, ge=0.0, le=1.0)


# --- §5.11 Spelunking -------------------------------------------------------
class SpelunkingConfig(BaseModel):
    rate: float = Field(0.0, ge=0.0, le=1.0)
    categories: list[str] = Field(default_factory=list)
    vagueness: float = Field(0.5, ge=0.0, le=1.0)
    follow_up_rate: float = Field(0.7, ge=0.0, le=1.0)


# --- §5.12 / §5.13 / §5.18-21 spectrum modes --------------------------------
class SpectrumModeConfig(BaseModel):
    """Shared template for cross-spectrum balanced modes."""

    rate: float = Field(0.0, ge=0.0, le=1.0)
    balance: Balance = Field(default_factory=Balance)
    register_mix: list[str] = Field(default_factory=list)
    contemporary_rate: float = Field(0.0, ge=0.0, le=1.0)  # politic only
    no_real_person_targeting: bool = True


# --- §5.14 AskingForAFriend -------------------------------------------------
class AskingForAFriendConfig(BaseModel):
    rate: float = Field(0.0, ge=0.0, le=1.0)
    register_mix: Balance = Field(default_factory=Balance)
    topic_balance: Balance = Field(default_factory=Balance)


# --- §5.16 IdentitySearch ---------------------------------------------------
class IdentitySearchConfig(BaseModel):
    rate: float = Field(0.0, ge=0.0, le=1.0)
    topic_balance: Balance = Field(default_factory=Balance)
    engagement_density: str = Field("high", pattern="^(low|medium|high)$")
    no_excluded_dimensions: bool = True  # hard constraint per §5.15


# --- §5.17 CooKoo Filter ----------------------------------------------------
class CooKooConfig(BaseModel):
    enabled: bool = False  # default OFF in v0.1 per §5.17 recommendation
    rate: float = Field(1.0, ge=0.0, le=1.0)
    position_distribution: Balance = Field(default_factory=Balance)
    type_balance: Balance = Field(default_factory=Balance)
    cohort_library: list[str] = Field(default_factory=list)
    distractor_library: list[str] = Field(default_factory=list)
    register_modifiers: dict[str, str] = Field(default_factory=dict)
    # cuckoo filter params (§5.17 table)
    filter_capacity: int = 10_000
    filter_fp_rate: float = 0.01
    fingerprint_bits: int = 12
    bucket_size: int = 4
    max_kicks: int = 500
    aging_window_days: int = 30
    # high-personal-stakes detector (§5.17)
    passthrough_max_length: int = 2000


# --- §5.6 Audit -------------------------------------------------------------
class AuditConfig(BaseModel):
    db_path: str = "~/.looksmart/audit.db"
    retention_days: int = 30  # user-configurable to 0
    salt_source: str = Field("keychain", pattern="^(keychain|file|env)$")
    log_decoys_plaintext: bool = True


# --- §5.7 Provider adapters -------------------------------------------------
class ProviderConfig(BaseModel):
    name: str  # openai|anthropic|gemini|grok
    enabled: bool = True
    credential_env: str | None = None
    rate_limit_per_min: int = 20


# --- §5.8 Local LLM ---------------------------------------------------------
class LocalLLMConfig(BaseModel):
    backend: str = Field("ollama", pattern="^(ollama|openai_compat|stub)$")
    endpoint: str = "http://localhost:11434"
    model: str = "llama3:70b"
    post_process_typos: bool = True


# --- §5.22 Echo Mode --------------------------------------------------------
class EchoConfig(BaseModel):
    enabled: bool = False
    db_path: str = "~/.looksmart/echo.db"
    retention_days: int = 90
    topic_overlap_threshold: float = 0.3
    correlation_window_days: int = 30
    bootstrap_days: int = 30
    community_aggregation_optin: bool = False


# --- Top-level --------------------------------------------------------------
class LookSmartConfig(BaseModel):
    sampler: SamplerConfig = Field(default_factory=SamplerConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    engagement: EngagementConfig = Field(default_factory=EngagementConfig)
    weird_al: WeirdAlConfig = Field(default_factory=WeirdAlConfig)
    fence: FenceConfig = Field(default_factory=FenceConfig)
    spelunking: SpelunkingConfig = Field(default_factory=SpelunkingConfig)
    politic_roulette: SpectrumModeConfig = Field(default_factory=SpectrumModeConfig)
    religious: SpectrumModeConfig = Field(default_factory=SpectrumModeConfig)
    asking_for_a_friend: AskingForAFriendConfig = Field(
        default_factory=AskingForAFriendConfig
    )
    identity_search: IdentitySearchConfig = Field(default_factory=IdentitySearchConfig)
    gender_roulette: SpectrumModeConfig = Field(default_factory=SpectrumModeConfig)
    orientation_roulette: SpectrumModeConfig = Field(default_factory=SpectrumModeConfig)
    immigration_roulette: SpectrumModeConfig = Field(default_factory=SpectrumModeConfig)
    health_status_roulette: SpectrumModeConfig = Field(
        default_factory=SpectrumModeConfig
    )
    cookoo: CooKooConfig = Field(default_factory=CooKooConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    local_llm: LocalLLMConfig = Field(default_factory=LocalLLMConfig)
    echo: EchoConfig = Field(default_factory=EchoConfig)
    providers: list[ProviderConfig] = Field(default_factory=list)
    persona_library_dir: str = "looksmart/persona/library"

    @classmethod
    def load(cls, path: str | Path) -> "LookSmartConfig":
        data = yaml.safe_load(Path(path).expanduser().read_text()) or {}
        return cls.model_validate(data)

    def dump(self, path: str | Path) -> None:
        Path(path).expanduser().write_text(
            yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)
        )
