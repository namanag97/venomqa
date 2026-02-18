"""Bridge module for gradual migration from old API."""

from venomqa.v1.bridge.journey import (
    LegacyCheckpoint,
    LegacyInvariant,
    LegacyJourney,
    LegacyStep,
    adapt_journey,
)
from venomqa.v1.bridge.state_manager import adapt_state_manager

__all__ = [
    "adapt_journey",
    "adapt_state_manager",
    "LegacyCheckpoint",
    "LegacyInvariant",
    "LegacyJourney",
    "LegacyStep",
]
