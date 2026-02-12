"""Enhanced test context with ports support."""

from __future__ import annotations

from dataclasses import dataclass, field
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

    Provides typed access to ports and maintains execution state.
    """

    _data: dict[str, Any] = field(default_factory=dict)
    _step_results: dict[str, Any] = field(default_factory=dict)
    _ports: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def get_required(self, key: str) -> Any:
        if key not in self._data:
            raise KeyError(f"Required context key not found: {key}")
        return self._data[key]

    def store_step_result(self, step_name: str, result: Any) -> None:
        self._step_results[step_name] = result
        self._data[step_name] = result

    def get_step_result(self, step_name: str) -> Any:
        return self._step_results.get(step_name)

    def clear(self) -> None:
        self._data.clear()
        self._step_results.clear()

    def snapshot(self) -> dict[str, Any]:
        return {
            "data": self._data.copy(),
            "step_results": self._step_results.copy(),
            "ports": self._ports.copy(),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        self._data = snapshot.get("data", {}).copy()
        self._step_results = snapshot.get("step_results", {}).copy()
        self._ports = snapshot.get("ports", {}).copy()

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def to_dict(self) -> dict[str, Any]:
        return self.snapshot()

    def set_port(self, name: str, port: Any) -> None:
        self._ports[name] = port

    def get_port(self, name: str, default: Any = None) -> Any:
        return self._ports.get(name, default)

    def get_typed_port(self, name: str, port_type: type[T]) -> T:
        port = self._ports.get(name)
        if port is None:
            raise KeyError(f"Port not found: {name}")
        if not isinstance(port, port_type):
            raise TypeError(f"Port {name} is not of type {port_type.__name__}")
        return port

    @property
    def client_port(self) -> ClientPort | None:
        return self._ports.get("client")

    @property
    def state_port(self) -> StatePort | None:
        return self._ports.get("state")

    @property
    def database_port(self) -> DatabasePort | None:
        return self._ports.get("database")

    @property
    def time_port(self) -> TimePort | None:
        return self._ports.get("time")

    @property
    def file_port(self) -> FilePort | None:
        return self._ports.get("file")

    @property
    def storage_port(self) -> StoragePort | None:
        return self._ports.get("storage")

    @property
    def websocket_port(self) -> WebSocketPort | None:
        return self._ports.get("websocket")

    @property
    def queue_port(self) -> QueuePort | None:
        return self._ports.get("queue")

    @property
    def mail_port(self) -> MailPort | None:
        return self._ports.get("mail")

    @property
    def concurrency_port(self) -> ConcurrencyPort | None:
        return self._ports.get("concurrency")

    @property
    def cache_port(self) -> CachePort | None:
        return self._ports.get("cache")

    @property
    def search_port(self) -> SearchPort | None:
        return self._ports.get("search")

    @property
    def notification_port(self) -> NotificationPort | None:
        return self._ports.get("notification")

    @property
    def webhook_port(self) -> WebhookPort | None:
        return self._ports.get("webhook")

    @property
    def mock_port(self) -> MockPort | None:
        return self._ports.get("mock")

    @property
    def ports(self) -> dict[str, Any]:
        return self._ports.copy()


@dataclass
class PortConfig:
    """Configuration for a single port."""

    name: str
    adapter_type: str
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class PortsConfiguration:
    """Complete ports configuration."""

    ports: dict[str, PortConfig] = field(default_factory=dict)

    def add_port(self, config: PortConfig) -> None:
        self.ports[config.name] = config

    def get_port(self, name: str) -> PortConfig | None:
        return self.ports.get(name)

    def get_enabled_ports(self) -> list[PortConfig]:
        return [p for p in self.ports.values() if p.enabled]


class ContextBuilder:
    """Builder for creating TestContext instances with ports."""

    def __init__(self) -> None:
        self._ports: dict[str, Any] = {}
        self._data: dict[str, Any] = {}

    def with_port(self, name: str, port: Any) -> ContextBuilder:
        self._ports[name] = port
        return self

    def with_client_port(self, port: ClientPort) -> ContextBuilder:
        return self.with_port("client", port)

    def with_state_port(self, port: StatePort) -> ContextBuilder:
        return self.with_port("state", port)

    def with_database_port(self, port: DatabasePort) -> ContextBuilder:
        return self.with_port("database", port)

    def with_time_port(self, port: TimePort) -> ContextBuilder:
        return self.with_port("time", port)

    def with_file_port(self, port: FilePort) -> ContextBuilder:
        return self.with_port("file", port)

    def with_storage_port(self, port: StoragePort) -> ContextBuilder:
        return self.with_port("storage", port)

    def with_websocket_port(self, port: WebSocketPort) -> ContextBuilder:
        return self.with_port("websocket", port)

    def with_queue_port(self, port: QueuePort) -> ContextBuilder:
        return self.with_port("queue", port)

    def with_mail_port(self, port: MailPort) -> ContextBuilder:
        return self.with_port("mail", port)

    def with_concurrency_port(self, port: ConcurrencyPort) -> ContextBuilder:
        return self.with_port("concurrency", port)

    def with_cache_port(self, port: CachePort) -> ContextBuilder:
        return self.with_port("cache", port)

    def with_search_port(self, port: SearchPort) -> ContextBuilder:
        return self.with_port("search", port)

    def with_notification_port(self, port: NotificationPort) -> ContextBuilder:
        return self.with_port("notification", port)

    def with_webhook_port(self, port: WebhookPort) -> ContextBuilder:
        return self.with_port("webhook", port)

    def with_mock_port(self, port: MockPort) -> ContextBuilder:
        return self.with_port("mock", port)

    def with_data(self, key: str, value: Any) -> ContextBuilder:
        self._data[key] = value
        return self

    def build(self) -> TestContext:
        context = TestContext(_data=self._data.copy(), _ports=self._ports.copy())
        return context


def create_context(**ports: Any) -> TestContext:
    """Factory function to create a TestContext with ports."""
    return TestContext(_ports=ports)
