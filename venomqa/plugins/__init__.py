"""Plugin system for VenomQA - journey discovery and registration."""

from venomqa.plugins.discovery import (
    action,
    discover_actions,
    discover_all,
    discover_fixtures,
    discover_from_actions_dir,
    discover_from_fixtures_dir,
    discover_from_journeys_dir,
    discover_journeys,
    extension,
    fixture,
    journey,
)
from venomqa.plugins.registry import FixtureInfo, JourneyRegistry, get_registry

__all__ = [
    "journey",
    "action",
    "fixture",
    "extension",
    "JourneyRegistry",
    "FixtureInfo",
    "get_registry",
    "discover_journeys",
    "discover_from_journeys_dir",
    "discover_actions",
    "discover_from_actions_dir",
    "discover_fixtures",
    "discover_from_fixtures_dir",
    "discover_all",
]
