"""Echo Mode (README §5.22): local recommender-system correlation tracking.

Echo Mode is a *measurement* mode. It does not touch any LLM provider and
generates no cover traffic. It correlates the user's own query log against the
user's own recommender-system data exhaust (Google/YouTube/Spotify/Amazon
takeout exports plus optional browser-extension capture) to surface statistical
evidence of cross-platform data leakage of the form:

    "topic X correlated to platform Y recommendation, p = Z"

All data stays local; community aggregation is separately opt-in (§5.22 hard
constraints).
"""

from __future__ import annotations

from .aggregate import AggregationRefused, CommunityAggregator
from .correlate import CorrelationEngine, Finding
from .store import EchoStore
from .tagging import KeywordFallbackTagger, LLMTagger, TopicTagger

__all__ = [
    "EchoStore",
    "CorrelationEngine",
    "Finding",
    "CommunityAggregator",
    "AggregationRefused",
    "TopicTagger",
    "LLMTagger",
    "KeywordFallbackTagger",
]
