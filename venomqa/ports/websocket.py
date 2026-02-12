from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class WSMessage:
    data: str | bytes
    type: str = "text"
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WSConnection:
    id: str
    url: str
    connected_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    is_connected: bool = True


class WebSocketPort(ABC):
    @abstractmethod
    def connect(self, url: str, headers: dict[str, str] | None = None) -> WSConnection:
        """Connect to a WebSocket server."""
        ...

    @abstractmethod
    def disconnect(self, connection_id: str) -> bool:
        """Disconnect from a WebSocket server."""
        ...

    @abstractmethod
    def send(self, connection_id: str, message: str | bytes) -> bool:
        """Send a message on a WebSocket connection."""
        ...

    @abstractmethod
    def send_json(self, connection_id: str, data: dict[str, Any]) -> bool:
        """Send a JSON message on a WebSocket connection."""
        ...

    @abstractmethod
    def receive(self, connection_id: str, timeout: float = 10.0) -> WSMessage | None:
        """Receive a message from a WebSocket connection."""
        ...

    @abstractmethod
    def receive_json(self, connection_id: str, timeout: float = 10.0) -> dict[str, Any] | None:
        """Receive a JSON message from a WebSocket connection."""
        ...

    @abstractmethod
    def subscribe(self, connection_id: str, callback: Callable[[WSMessage], None]) -> str:
        """Subscribe to messages on a connection."""
        ...

    @abstractmethod
    def unsubscribe(self, connection_id: str, subscription_id: str) -> bool:
        """Unsubscribe from messages."""
        ...

    @abstractmethod
    def is_connected(self, connection_id: str) -> bool:
        """Check if a connection is active."""
        ...

    @abstractmethod
    def get_connection(self, connection_id: str) -> WSConnection | None:
        """Get connection info."""
        ...

    @abstractmethod
    def get_connections(self) -> list[WSConnection]:
        """Get all active connections."""
        ...

    @abstractmethod
    def wait_for_message(self, connection_id: str, timeout: float = 10.0) -> WSMessage | None:
        """Wait for the next message."""
        ...

    @abstractmethod
    def wait_for_json(self, connection_id: str, timeout: float = 10.0) -> dict[str, Any] | None:
        """Wait for the next JSON message."""
        ...

    @abstractmethod
    def broadcast(self, message: str | bytes) -> int:
        """Broadcast a message to all connections."""
        ...
