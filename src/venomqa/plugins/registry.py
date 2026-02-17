"""Registry for journeys, actions, fixtures, and extensions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from venomqa.core.models import ActionCallable, Journey


@dataclass
class FixtureInfo:
    """Information about a registered fixture."""

    name: str
    factory: Callable[..., Any]
    depends: list[str] = field(default_factory=list)
    scope: str = "function"


class JourneyRegistry:
    """Thread-safe registry for storing and retrieving journeys, actions, fixtures."""

    _instance: JourneyRegistry | None = None

    def __new__(cls) -> JourneyRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._journeys: dict[str, Journey] = {}
            cls._instance._actions: dict[str, ActionCallable] = {}
            cls._instance._fixtures: dict[str, FixtureInfo] = {}
            cls._instance._extensions: dict[str, Any] = {}
            cls._instance._fixture_cache: dict[str, Any] = {}
        return cls._instance

    def register_journey(self, journey: Journey) -> None:
        if journey.name in self._journeys:
            raise ValueError(f"Journey '{journey.name}' is already registered")
        self._journeys[journey.name] = journey

    def get_journey(self, name: str) -> Journey | None:
        return self._journeys.get(name)

    def get_all_journeys(self) -> dict[str, Journey]:
        return dict(self._journeys)

    def clear_journeys(self) -> None:
        self._journeys.clear()

    def register_action(self, name: str, action: ActionCallable) -> None:
        if name in self._actions:
            raise ValueError(f"Action '{name}' is already registered")
        self._actions[name] = action

    def get_action(self, name: str) -> ActionCallable | None:
        return self._actions.get(name)

    def resolve_action(self, name: str) -> ActionCallable:
        """Resolve action by name, supporting dotted notation like 'cart.add_to_cart'."""
        action = self._actions.get(name)
        if action is not None:
            return action
        raise KeyError(f"Action '{name}' not found in registry")

    def get_all_actions(self) -> dict[str, ActionCallable]:
        return dict(self._actions)

    def clear_actions(self) -> None:
        self._actions.clear()

    def register_fixture(
        self,
        name: str,
        factory: Callable[..., Any],
        depends: list[str] | None = None,
        scope: str = "function",
    ) -> None:
        if name in self._fixtures:
            raise ValueError(f"Fixture '{name}' is already registered")
        self._fixtures[name] = FixtureInfo(
            name=name,
            factory=factory,
            depends=depends or [],
            scope=scope,
        )

    def get_fixture(self, name: str) -> FixtureInfo | None:
        return self._fixtures.get(name)

    def get_all_fixtures(self) -> dict[str, FixtureInfo]:
        return dict(self._fixtures)

    def resolve_fixture(self, name: str, resolved: dict[str, Any] | None = None) -> Any:
        """Resolve fixture with dependency injection."""
        if resolved is None:
            resolved = {}

        if name in resolved:
            return resolved[name]

        if name in self._fixture_cache:
            return self._fixture_cache[name]

        fixture_info = self._fixtures.get(name)
        if fixture_info is None:
            raise KeyError(f"Fixture '{name}' not found in registry")

        deps = {}
        for dep_name in fixture_info.depends:
            deps[dep_name] = self.resolve_fixture(dep_name, resolved)

        result = fixture_info.factory(**deps)
        resolved[name] = result

        if fixture_info.scope in ("journey", "session"):
            self._fixture_cache[name] = result

        return result

    def resolve_fixtures(self, names: list[str]) -> dict[str, Any]:
        """Resolve multiple fixtures with dependency ordering."""
        resolved: dict[str, Any] = {}
        for name in names:
            self.resolve_fixture(name, resolved)
        return resolved

    def clear_fixtures(self) -> None:
        self._fixtures.clear()
        self._fixture_cache.clear()

    def clear_fixture_cache(self) -> None:
        self._fixture_cache.clear()

    def register_extension(self, name: str, extension: Any) -> None:
        if name in self._extensions:
            raise ValueError(f"Extension '{name}' is already registered")
        self._extensions[name] = extension

    def get_extension(self, name: str) -> Any | None:
        return self._extensions.get(name)

    def get_all_extensions(self) -> dict[str, Any]:
        return dict(self._extensions)

    def clear_extensions(self) -> None:
        self._extensions.clear()

    def clear_all(self) -> None:
        self.clear_journeys()
        self.clear_actions()
        self.clear_fixtures()
        self.clear_extensions()

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None


def get_registry() -> JourneyRegistry:
    return JourneyRegistry()
