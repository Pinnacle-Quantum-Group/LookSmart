"""CooKoo Filter subsystem (README §5.17).

Two-layer name:
  - cuckoo bird (brood parasitism): inject cohort/topic/register context into
    the "nest" of the user's real query so the provider's per-query inference
    about the user shifts. The user's prose passes through verbatim.
  - cuckoo filter (data structure): probabilistic set-membership with deletion,
    used to dedup/rotate injections so the injection stream develops no
    signature. Deletion is load-bearing for sliding-window aging.

This subsystem modifies the user's OWN real queries before they reach the
provider. It does NOT rewrite the user's words and does NOT do stylometric
obfuscation (§2.2).
"""

from .filter import CuckooFilter
from .injector import CooKooInjector
from .store import CooKooStore

__all__ = ["CuckooFilter", "CooKooInjector", "CooKooStore"]
