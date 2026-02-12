"""Registry for journeys, actions, and extensions."""

from __future__ import annotations

from typing import Any

from venomqa.core.models import ActionCallable, Journey


class JourneyRegistry:
    """Thread-safe registry for storing and retrieving journeys."""

    _instance: JourneyRegistry | None = None

    def __new__(cls) -> JourneyRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._journeys: dict[str, Journey] = {}
            cls._instance._actions: dict[str, ActionCallable] = {}
            cls._instance._extensions: dict[str, Any] = {}
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

    def get_all_actions(self) -> dict[str, ActionCallable]:
        return dict(self._actions)

    def clear_actions(self) -> None:
        self._actions.clear()

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
        self.clear_extensions()

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None


def get_registry() -> JourneyRegistry:
    return JourneyRegistry()
