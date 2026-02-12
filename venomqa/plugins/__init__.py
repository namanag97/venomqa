"""Plugin system for VenomQA - journey discovery and registration."""

from venomqa.plugins.discovery import (
    action,
    discover_from_journeys_dir,
    discover_journeys,
    extension,
    journey,
)
from venomqa.plugins.registry import JourneyRegistry, get_registry

__all__ = [
    "journey",
    "action",
    "extension",
    "JourneyRegistry",
    "get_registry",
    "discover_journeys",
    "discover_from_journeys_dir",
]
