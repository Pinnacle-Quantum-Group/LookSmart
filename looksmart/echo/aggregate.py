"""Echo Mode community-aggregation tier (README §5.22 + §12).

SEPARATELY opt-in, default OFF (§5.22 hard constraint): "Enabling Echo Mode
locally does not opt the user into the community dataset." This module refuses
to produce anything unless ``community_aggregation_optin`` is True.

What is contributed (§5.22): only *topic-platform pairs with significance
levels* -- never raw queries or raw recommendation content. Privacy is then
further protected by ONE of:

* Differential privacy: Laplace noise on the per-cell counts (epsilon-DP), or
* k-anonymity: suppression of any cell with k < 5 contributors/observations.

Public-safety exclusion (§12.0 / §5.22): "The community-aggregation tier of
§5.22 explicitly excludes correlations on public-safety-classified topics from
the aggregated dataset." A simple, reusable exclusion list is applied before
anything leaves the local store.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

from .correlate import Finding

# §12.5 public-safety-classified topic categories. Reusable exclusion list:
# matched against a finding's topic key OR label substring (case-insensitive).
PUBLIC_SAFETY_EXCLUSIONS: frozenset[str] = frozenset(
    {
        "csam",
        "child_exploitation",
        "child exploitation",
        "grooming",
        "terrorism",
        "terrorist_financing",
        "material_support",
        "wmd",
        "bioweapon",
        "nuclear_weapon",
        "chemical_weapon",
        "weapons_trafficking",
        "drug_trafficking",
        "drug-chemistry",
        "erowid",
        "lycaeum",
        "pubchem",
        "fraud_operations",
    }
)

K_ANON_MIN = 5  # §5.22: suppress cells with k < 5


class PrivacyMechanism(str, Enum):
    DIFFERENTIAL_PRIVACY = "differential_privacy"
    K_ANONYMITY = "k_anonymity"


class AggregationRefused(RuntimeError):
    """Raised when aggregation is attempted without the separate opt-in."""


def is_public_safety_topic(topic_key: str, label: str | None = None) -> bool:
    """Reusable §12 exclusion check (also used by tests)."""
    hay = (topic_key or "").lower()
    lab = (label or "").lower()
    for term in PUBLIC_SAFETY_EXCLUSIONS:
        if term in hay or (lab and term in lab):
            return True
    return False


@dataclass
class CommunityAggregator:
    """Build a privacy-preserving aggregate contribution from local findings.

    Args:
        community_aggregation_optin: the §5.22 separate opt-in gate. MUST be
            True or every public method raises :class:`AggregationRefused`.
        mechanism: differential privacy (Laplace) or k-anonymity suppression.
        epsilon: DP privacy budget (smaller => more noise). Used for DP only.
        rng: numpy Generator (tests pass ``np.random.default_rng(seed)``).
    """

    community_aggregation_optin: bool
    mechanism: PrivacyMechanism = PrivacyMechanism.K_ANONYMITY
    epsilon: float = 1.0
    k: int = K_ANON_MIN
    rng: np.random.Generator | None = None

    def __post_init__(self) -> None:
        if self.rng is None:
            self.rng = np.random.default_rng(0)

    def _require_optin(self) -> None:
        if not self.community_aggregation_optin:
            raise AggregationRefused(
                "community aggregation requires the separate opt-in "
                "(EchoConfig.community_aggregation_optin); refusing to export."
            )

    def contribute(self, findings: list[Finding]) -> list[dict[str, Any]]:
        """Return the aggregated, privacy-protected topic-platform contribution.

        Each output cell is ``{topic, platform, count, significant_count,
        mechanism, ...}`` -- topic-platform pairs with significance levels, no
        raw query/recommendation content. Refuses without the opt-in.
        """
        self._require_optin()

        # 1) restrict to tested, significant findings; drop public-safety topics
        cells: dict[tuple[str, str], dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "significant_count": 0, "min_fdr_p": 1.0}
        )
        for f in findings:
            if f.notes is not None:  # bootstrap / untested -> not contributable
                continue
            if is_public_safety_topic(f.topic, f.topic):
                continue  # §12 hard exclusion
            cell = cells[(f.topic, f.platform)]
            cell["count"] += 1
            if f.significant:
                cell["significant_count"] += 1
                cell["min_fdr_p"] = min(cell["min_fdr_p"], f.fdr_p)

        out: list[dict[str, Any]] = []
        for (topic, platform), c in cells.items():
            count = c["count"]
            sig = c["significant_count"]
            if self.mechanism is PrivacyMechanism.K_ANONYMITY:
                if count < self.k:
                    continue  # suppress small cell
                rec = {
                    "topic": topic,
                    "platform": platform,
                    "count": count,
                    "significant_count": sig,
                    "min_fdr_p": round(c["min_fdr_p"], 6),
                    "mechanism": self.mechanism.value,
                }
            else:  # differential privacy: Laplace noise on counts
                scale = 1.0 / max(self.epsilon, 1e-9)
                noisy_count = count + float(self.rng.laplace(0.0, scale))
                noisy_sig = sig + float(self.rng.laplace(0.0, scale))
                rec = {
                    "topic": topic,
                    "platform": platform,
                    "count": max(0.0, round(noisy_count, 3)),
                    "significant_count": max(0.0, round(noisy_sig, 3)),
                    "mechanism": self.mechanism.value,
                    "epsilon": self.epsilon,
                }
            out.append(rec)
        out.sort(key=lambda r: (r["topic"], r["platform"]))
        return out
