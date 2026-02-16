"""Action resolution protocol for journey execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from venomqa.core.models import ActionCallable


class ActionResolver(ABC):
    """Protocol for resolving action names to callables.

    This abstraction allows different implementations for action resolution,
    enabling dependency injection instead of relying on a global singleton.
    """

    @abstractmethod
    def resolve(self, name: str) -> ActionCallable:
        """Resolve an action name to a callable.

        Args:
            name: The action name to resolve (e.g., 'auth.login').

        Returns:
            The resolved callable.

        Raises:
            KeyError: If the action cannot be resolved.
        """
        ...


class RegistryActionResolver(ActionResolver):
    """Action resolver backed by the JourneyRegistry.

    This is the default implementation that uses the existing global
    registry for backward compatibility.
    """

    def resolve(self, name: str) -> ActionCallable:
        """Resolve action using the global registry."""
        from venomqa.plugins.registry import get_registry

        registry = get_registry()
        return registry.resolve_action(name)


class DictActionResolver(ActionResolver):
    """Action resolver backed by a simple dictionary.

    Useful for testing or when actions are defined locally.
    """

    def __init__(self, actions: dict[str, ActionCallable] | None = None) -> None:
        """Initialize with optional action dictionary.

        Args:
            actions: Dictionary mapping names to callables.
        """
        self._actions: dict[str, ActionCallable] = actions or {}

    def register(self, name: str, action: ActionCallable) -> None:
        """Register an action.

        Args:
            name: Action name.
            action: Action callable.
        """
        self._actions[name] = action

    def resolve(self, name: str) -> ActionCallable:
        """Resolve action from the dictionary."""
        if name not in self._actions:
            raise KeyError(f"Action '{name}' not found")
        return self._actions[name]
