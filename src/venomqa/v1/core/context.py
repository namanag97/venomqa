"""Context for sharing data between actions.

The Context is a mutable store that flows through exploration.
It enables actions to share data (e.g., user_id from login used in create_order).

Key features:
- Checkpoint/rollback support (context is restored with state)
- Type-safe getters with defaults
- Scoped namespaces for organization
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, TypeVar, overload

T = TypeVar("T")


@dataclass
class Context:
    """Mutable context for sharing data between actions.

    Usage in actions:
        def login(api, context):
            response = api.post("/login", json={...})
            user = response.json()
            context.set("user_id", user["id"])
            context.set("auth_token", user["token"])
            return ActionResult.from_response(...)

        def create_order(api, context):
            user_id = context.get("user_id")
            response = api.post("/orders", json={"user_id": user_id})
            context.set("order_id", response.json()["id"])
            return ActionResult.from_response(...)

    Context is automatically checkpointed/restored during exploration,
    so rolling back to a previous state also restores the context.

    Named clients (registered via World(clients={...})) are stored separately
    in _clients and are NOT checkpointed — they survive rollbacks intact.
    Access them with context.get_client("viewer").
    """

    _data: dict[str, Any] = field(default_factory=dict)
    _clients: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """Set a value in the context."""
        self._data[key] = value

    @overload
    def get(self, key: str) -> Any | None: ...

    @overload
    def get(self, key: str, default: T) -> T: ...

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the context."""
        return self._data.get(key, default)

    def get_typed(self, key: str, type_: type[T], default: T | None = None) -> T | None:
        """Get a value with type hint (for IDE support)."""
        value = self._data.get(key, default)
        return value if isinstance(value, type_) else default

    def get_required(self, key: str) -> Any:
        """Get a value that MUST exist, or raise ValueError.

        Use in actions that have a precondition requiring this key — the action
        will only run if the key is present, so this is a fast-fail assertion:

            @requires_context("customer_id")
            def create_payment_intent(api, context):
                customer_id = context.get_required("customer_id")
                ...
        """
        if key not in self._data:
            raise ValueError(
                f"Required context key '{key}' is missing. "
                f"Available: {list(self._data.keys())}"
            )
        return self._data[key]

    def get_client(self, name: str) -> Any:
        """Get a named HTTP client registered via World(clients={...}).

        Clients are NOT affected by rollback — they survive checkpoint/restore.

        Example::

            world = World(api=admin_api, clients={"viewer": viewer_api})

            def check_as_viewer(api, context):
                viewer = context.get_client("viewer")
                return viewer.get("/resource/1")

        Raises:
            KeyError: If no client is registered under that name.
        """
        if name not in self._clients:
            available = list(self._clients.keys())
            raise KeyError(
                f"No client registered as '{name}'. "
                f"Available clients: {available}. "
                f"Register via World(clients={{'{name}': HttpClient(...)}})"
            )
        return self._clients[name]

    def _register_client(self, name: str, client: Any) -> None:
        """Register a named client. Called by World during setup."""
        self._clients[name] = client

    def has(self, key: str) -> bool:
        """Check if a key exists in the context."""
        return key in self._data

    def delete(self, key: str) -> None:
        """Delete a key from the context."""
        self._data.pop(key, None)

    def clear(self) -> None:
        """Clear all context data."""
        self._data.clear()

    def keys(self) -> list[str]:
        """Get all keys in the context."""
        return list(self._data.keys())

    def to_dict(self) -> dict[str, Any]:
        """Get a copy of all context data."""
        return dict(self._data)

    def update(self, data: dict[str, Any]) -> None:
        """Update context with multiple values."""
        self._data.update(data)

    # Scoped access
    def scope(self, namespace: str) -> ScopedContext:
        """Get a scoped view of the context.

        Example:
            user = context.scope("user")
            user.set("id", 123)  # Sets "user.id"
            user.get("id")       # Gets "user.id"
        """
        return ScopedContext(self, namespace)

    # Checkpoint support
    def checkpoint(self) -> dict[str, Any]:
        """Create a checkpoint of current context state.

        Only _data is checkpointed. Named clients (_clients) are excluded —
        they are test infrastructure, not application state, and should not
        be rolled back.
        """
        return copy.deepcopy(self._data)

    def restore(self, checkpoint: dict[str, Any]) -> None:
        """Restore context from a checkpoint.

        Restores _data only. Named clients registered via _register_client
        are preserved across rollbacks.
        """
        self._data = copy.deepcopy(checkpoint)
        # _clients is intentionally left untouched

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:
        return f"Context({self._data})"


@dataclass
class ScopedContext:
    """A namespaced view into a Context."""

    _parent: Context
    _namespace: str

    def _key(self, key: str) -> str:
        return f"{self._namespace}.{key}"

    def set(self, key: str, value: Any) -> None:
        self._parent.set(self._key(key), value)

    def get(self, key: str, default: Any = None) -> Any:
        return self._parent.get(self._key(key), default)

    def has(self, key: str) -> bool:
        return self._parent.has(self._key(key))

    def delete(self, key: str) -> None:
        self._parent.delete(self._key(key))
