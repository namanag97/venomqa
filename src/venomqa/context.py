"""Enhanced test context with ports support.

This module provides TestContext with dependency injection through ports,
enabling clean separation of concerns and testable components.

Example:
    >>> from venomqa.context import TestContext, ContextBuilder
    >>> from venomqa.ports import ClientPort, StatePort
    >>>
    >>> # Using builder pattern
    >>> ctx = (
    ...     ContextBuilder()
    ...     .with_client_port(my_client)
    ...     .with_state_port(my_state)
    ...     .with_data("user_id", 123)
    ...     .build()
    ... )
    >>>
    >>> # Direct creation
    >>> ctx = TestContext(_ports={"client": my_client})
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from venomqa.ports import (
        CachePort,
        ClientPort,
        ConcurrencyPort,
        DatabasePort,
        FilePort,
        MailPort,
        MockPort,
        NotificationPort,
        QueuePort,
        SearchPort,
        StatePort,
        StoragePort,
        TimePort,
        WebhookPort,
        WebSocketPort,
    )

T = TypeVar("T")


@dataclass
class TestContext:
    """Enhanced context that holds ports for dependency injection.

    Provides typed access to ports and maintains execution state. Combines
    the functionality of ExecutionContext with port-based dependency injection.

    Attributes:
        _data: General-purpose key-value storage.
        _step_results: Results indexed by step name.
        _ports: Port instances indexed by name.
        _created_at: Timestamp when context was created.

    Example:
        >>> ctx = TestContext()
        >>> ctx.set_port("client", http_client)
        >>> ctx.set("base_url", "https://api.example.com")
        >>>
        >>> # Access port
        >>> client = ctx.client_port
        >>> response = client.get(ctx.get("base_url") + "/users")
    """

    _data: dict[str, Any] = field(default_factory=dict)
    _step_results: dict[str, Any] = field(default_factory=dict)
    _ports: dict[str, Any] = field(default_factory=dict)
    _created_at: datetime = field(default_factory=datetime.now)

    def set(self, key: str, value: Any) -> None:
        """Store a value in context.

        Args:
            key: The key to store the value under.
            value: The value to store.
        """
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from context.

        Args:
            key: The key to retrieve.
            default: Value to return if key not found.

        Returns:
            The stored value or default if not found.
        """
        return self._data.get(key, default)

    def get_required(self, key: str) -> Any:
        """Retrieve a value, raising KeyError if not found.

        Args:
            key: The key to retrieve.

        Returns:
            The stored value.

        Raises:
            KeyError: If the key does not exist.
        """
        if key not in self._data:
            raise KeyError(f"Required context key not found: {key}")
        return self._data[key]

    def get_typed(self, key: str, expected_type: type[T], default: T | None = None) -> T:
        """Retrieve a value with type validation.

        Args:
            key: The key to retrieve.
            expected_type: The expected type of the value.
            default: Default value if key not found.

        Returns:
            The stored value (validated type).

        Raises:
            TypeError: If value is not of expected type.
        """
        value = self._data.get(key, default)
        if value is not None and not isinstance(value, expected_type):
            raise TypeError(
                f"Context key '{key}' has type {type(value).__name__}, "
                f"expected {expected_type.__name__}"
            )
        return value  # type: ignore[return-value]

    def store_step_result(self, step_name: str, result: Any) -> None:
        """Store result of a step for later access.

        Args:
            step_name: Name of the step.
            result: The result to store.
        """
        self._step_results[step_name] = result
        self._data[step_name] = result

    def get_step_result(self, step_name: str) -> Any:
        """Get result from a previous step.

        Args:
            step_name: Name of the step.

        Returns:
            The stored result or None if not found.
        """
        return self._step_results.get(step_name)

    def get_step_result_required(self, step_name: str) -> Any:
        """Get result from a previous step, raising if not found.

        Args:
            step_name: Name of the step.

        Returns:
            The stored result.

        Raises:
            KeyError: If no result exists for the step.
        """
        if step_name not in self._step_results:
            raise KeyError(f"No result stored for step: {step_name}")
        return self._step_results[step_name]

    def has_step_result(self, step_name: str) -> bool:
        """Check if a step result exists."""
        return step_name in self._step_results

    def clear(self) -> None:
        """Clear all context data (but not ports)."""
        self._data.clear()
        self._step_results.clear()

    def clear_all(self) -> None:
        """Clear all context data including ports."""
        self._data.clear()
        self._step_results.clear()
        self._ports.clear()

    def snapshot(self) -> dict[str, Any]:
        """Create a snapshot of current context.

        Returns:
            Dictionary containing complete context state.
        """
        return {
            "data": deepcopy(self._data),
            "step_results": deepcopy(self._step_results),
            "ports": deepcopy(self._ports),
            "created_at": self._created_at.isoformat(),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore context from a snapshot.

        Args:
            snapshot: A snapshot created by snapshot().
        """
        self._data = deepcopy(snapshot.get("data", {}))
        self._step_results = deepcopy(snapshot.get("step_results", {}))
        self._ports = deepcopy(snapshot.get("ports", {}))

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in context."""
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        """Dictionary-style get access."""
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Dictionary-style set access."""
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        """Dictionary-style delete access."""
        del self._data[key]

    def __len__(self) -> int:
        """Number of items in context."""
        return len(self._data)

    def __bool__(self) -> bool:
        """Context is truthy if it has data or ports."""
        return bool(self._data or self._step_results or self._ports)

    def to_dict(self) -> dict[str, Any]:
        """Export context as dictionary for serialization."""
        return self.snapshot()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TestContext:
        """Create context from a dictionary.

        Args:
            data: Dictionary with 'data', 'step_results', and 'ports' keys.

        Returns:
            New TestContext instance.
        """
        return cls(
            _data=deepcopy(data.get("data", {})),
            _step_results=deepcopy(data.get("step_results", {})),
            _ports=deepcopy(data.get("ports", {})),
        )

    def copy(self) -> TestContext:
        """Create a deep copy of this context."""
        return TestContext(
            _data=deepcopy(self._data),
            _step_results=deepcopy(self._step_results),
            _ports=deepcopy(self._ports),
        )

    def set_port(self, name: str, port: Any) -> None:
        """Register a port instance.

        Args:
            name: Port identifier (e.g., "client", "database").
            port: The port instance.

        Example:
            >>> ctx.set_port("client", http_client)
            >>> ctx.set_port("database", postgres_adapter)
        """
        self._ports[name] = port

    def get_port(self, name: str, default: Any = None) -> Any:
        """Get a port instance by name.

        Args:
            name: Port identifier.
            default: Default value if port not found.

        Returns:
            The port instance or default.
        """
        return self._ports.get(name, default)

    def get_required_port(self, name: str) -> Any:
        """Get a port instance, raising if not found.

        Args:
            name: Port identifier.

        Returns:
            The port instance.

        Raises:
            KeyError: If port not found.
        """
        if name not in self._ports:
            raise KeyError(f"Port not found: {name}")
        return self._ports[name]

    def get_typed_port(self, name: str, port_type: type[T]) -> T:
        """Get a port with type validation.

        Args:
            name: Port identifier.
            port_type: Expected port type.

        Returns:
            The port instance (validated type).

        Raises:
            KeyError: If port not found.
            TypeError: If port is not of expected type.

        Example:
            >>> client = ctx.get_typed_port("client", ClientPort)
        """
        port = self._ports.get(name)
        if port is None:
            raise KeyError(f"Port not found: {name}")
        if not isinstance(port, port_type):
            raise TypeError(
                f"Port '{name}' has type {type(port).__name__}, expected {port_type.__name__}"
            )
        return port  # type: ignore[return-value]

    def has_port(self, name: str) -> bool:
        """Check if a port is registered."""
        return name in self._ports

    def remove_port(self, name: str) -> Any:
        """Remove and return a port.

        Args:
            name: Port identifier.

        Returns:
            The removed port instance.

        Raises:
            KeyError: If port not found.
        """
        if name not in self._ports:
            raise KeyError(f"Port not found: {name}")
        return self._ports.pop(name)

    @property
    def client_port(self) -> ClientPort | None:
        """HTTP client port for making requests."""
        return self._ports.get("client")

    @property
    def state_port(self) -> StatePort | None:
        """State management port for checkpoints/rollback."""
        return self._ports.get("state")

    @property
    def database_port(self) -> DatabasePort | None:
        """Database port for direct DB operations."""
        return self._ports.get("database")

    @property
    def time_port(self) -> TimePort | None:
        """Time manipulation port for testing."""
        return self._ports.get("time")

    @property
    def file_port(self) -> FilePort | None:
        """File system operations port."""
        return self._ports.get("file")

    @property
    def storage_port(self) -> StoragePort | None:
        """Cloud storage port (S3, GCS, etc.)."""
        return self._ports.get("storage")

    @property
    def websocket_port(self) -> WebSocketPort | None:
        """WebSocket client port."""
        return self._ports.get("websocket")

    @property
    def queue_port(self) -> QueuePort | None:
        """Message queue port (RabbitMQ, SQS, etc.)."""
        return self._ports.get("queue")

    @property
    def mail_port(self) -> MailPort | None:
        """Email port for testing mail delivery."""
        return self._ports.get("mail")

    @property
    def concurrency_port(self) -> ConcurrencyPort | None:
        """Concurrency testing port."""
        return self._ports.get("concurrency")

    @property
    def cache_port(self) -> CachePort | None:
        """Cache port (Redis, Memcached, etc.)."""
        return self._ports.get("cache")

    @property
    def search_port(self) -> SearchPort | None:
        """Search engine port (Elasticsearch, etc.)."""
        return self._ports.get("search")

    @property
    def notification_port(self) -> NotificationPort | None:
        """Push notification port."""
        return self._ports.get("notification")

    @property
    def webhook_port(self) -> WebhookPort | None:
        """Webhook testing port."""
        return self._ports.get("webhook")

    @property
    def mock_port(self) -> MockPort | None:
        """Mock server port."""
        return self._ports.get("mock")

    @property
    def ports(self) -> dict[str, Any]:
        """Get a copy of all registered ports."""
        return self._ports.copy()

    @property
    def port_names(self) -> list[str]:
        """Get list of registered port names."""
        return list(self._ports.keys())


@dataclass
class PortConfig:
    """Configuration for a single port.

    Attributes:
        name: Unique identifier for this port.
        adapter_type: Type identifier for the adapter.
        config: Adapter-specific configuration.
        enabled: Whether this port is active.
    """

    name: str
    adapter_type: str
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Port name cannot be empty")
        if not self.adapter_type.strip():
            raise ValueError("Adapter type cannot be empty")


@dataclass
class PortsConfiguration:
    """Complete ports configuration.

    Manages a collection of port configurations for initialization.

    Attributes:
        ports: Dictionary of port name to PortConfig.
    """

    ports: dict[str, PortConfig] = field(default_factory=dict)

    def add_port(self, config: PortConfig) -> None:
        """Add a port configuration.

        Args:
            config: PortConfig to add.

        Raises:
            ValueError: If port name already exists.
        """
        if config.name in self.ports:
            raise ValueError(f"Port '{config.name}' already configured")
        self.ports[config.name] = config

    def get_port(self, name: str) -> PortConfig | None:
        """Get a port configuration by name."""
        return self.ports.get(name)

    def get_required_port(self, name: str) -> PortConfig:
        """Get a port configuration, raising if not found.

        Raises:
            KeyError: If port not found.
        """
        if name not in self.ports:
            raise KeyError(f"Port configuration not found: {name}")
        return self.ports[name]

    def get_enabled_ports(self) -> list[PortConfig]:
        """Get list of enabled port configurations."""
        return [p for p in self.ports.values() if p.enabled]

    def remove_port(self, name: str) -> PortConfig:
        """Remove and return a port configuration.

        Raises:
            KeyError: If port not found.
        """
        if name not in self.ports:
            raise KeyError(f"Port configuration not found: {name}")
        return self.ports.pop(name)

    def has_port(self, name: str) -> bool:
        """Check if a port is configured."""
        return name in self.ports


class ContextBuilder:
    """Builder for creating TestContext instances with ports.

    Provides a fluent interface for constructing TestContext objects
    with pre-configured ports and data.

    Example:
        >>> ctx = (
        ...     ContextBuilder()
        ...     .with_client_port(http_client)
        ...     .with_database_port(postgres_adapter)
        ...     .with_data("base_url", "https://api.example.com")
        ...     .with_data("timeout", 30)
        ...     .build()
        ... )
    """

    def __init__(self) -> None:
        self._ports: dict[str, Any] = {}
        self._data: dict[str, Any] = {}
        self._step_results: dict[str, Any] = {}

    def with_port(self, name: str, port: Any) -> ContextBuilder:
        """Add a port to the context.

        Args:
            name: Port identifier.
            port: Port instance.

        Returns:
            Self for chaining.
        """
        self._ports[name] = port
        return self

    def with_client_port(self, port: ClientPort) -> ContextBuilder:
        """Add HTTP client port."""
        return self.with_port("client", port)

    def with_state_port(self, port: StatePort) -> ContextBuilder:
        """Add state management port."""
        return self.with_port("state", port)

    def with_database_port(self, port: DatabasePort) -> ContextBuilder:
        """Add database port."""
        return self.with_port("database", port)

    def with_time_port(self, port: TimePort) -> ContextBuilder:
        """Add time manipulation port."""
        return self.with_port("time", port)

    def with_file_port(self, port: FilePort) -> ContextBuilder:
        """Add file system port."""
        return self.with_port("file", port)

    def with_storage_port(self, port: StoragePort) -> ContextBuilder:
        """Add cloud storage port."""
        return self.with_port("storage", port)

    def with_websocket_port(self, port: WebSocketPort) -> ContextBuilder:
        """Add WebSocket port."""
        return self.with_port("websocket", port)

    def with_queue_port(self, port: QueuePort) -> ContextBuilder:
        """Add message queue port."""
        return self.with_port("queue", port)

    def with_mail_port(self, port: MailPort) -> ContextBuilder:
        """Add email port."""
        return self.with_port("mail", port)

    def with_concurrency_port(self, port: ConcurrencyPort) -> ContextBuilder:
        """Add concurrency testing port."""
        return self.with_port("concurrency", port)

    def with_cache_port(self, port: CachePort) -> ContextBuilder:
        """Add cache port."""
        return self.with_port("cache", port)

    def with_search_port(self, port: SearchPort) -> ContextBuilder:
        """Add search engine port."""
        return self.with_port("search", port)

    def with_notification_port(self, port: NotificationPort) -> ContextBuilder:
        """Add push notification port."""
        return self.with_port("notification", port)

    def with_webhook_port(self, port: WebhookPort) -> ContextBuilder:
        """Add webhook testing port."""
        return self.with_port("webhook", port)

    def with_mock_port(self, port: MockPort) -> ContextBuilder:
        """Add mock server port."""
        return self.with_port("mock", port)

    def with_data(self, key: str, value: Any) -> ContextBuilder:
        """Add data to the context.

        Args:
            key: Data key.
            value: Data value.

        Returns:
            Self for chaining.
        """
        self._data[key] = value
        return self

    def with_step_result(self, step_name: str, result: Any) -> ContextBuilder:
        """Add a pre-existing step result.

        Args:
            step_name: Name of the step.
            result: Step result.

        Returns:
            Self for chaining.
        """
        self._step_results[step_name] = result
        return self

    def build(self) -> TestContext:
        """Build the TestContext instance.

        Returns:
            Configured TestContext instance.
        """
        return TestContext(
            _data=deepcopy(self._data),
            _step_results=deepcopy(self._step_results),
            _ports=deepcopy(self._ports),
        )

    def reset(self) -> ContextBuilder:
        """Reset the builder to empty state.

        Returns:
            Self for chaining.
        """
        self._ports.clear()
        self._data.clear()
        self._step_results.clear()
        return self


def create_context(**ports: Any) -> TestContext:
    """Factory function to create a TestContext with ports.

    Convenience function for quickly creating a context with ports.

    Args:
        **ports: Port name to port instance mappings.

    Returns:
        New TestContext instance.

    Example:
        >>> ctx = create_context(
        ...     client=http_client,
        ...     database=postgres_adapter,
        ...     cache=redis_adapter,
        ... )
    """
    return TestContext(_ports=ports)
