"""WebSocket client for VenomQA real-time testing."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from venomqa.clients.base import BaseAsyncClient, BaseClient
from venomqa.errors import ConnectionError, ConnectionTimeoutError, RequestTimeoutError

if TYPE_CHECKING:
    from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """WebSocket connection state."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CLOSING = "closing"


@dataclass
class WebSocketMessage:
    """Represents a WebSocket message."""

    data: Any
    is_binary: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_text(cls, text: str) -> WebSocketMessage:
        return cls(data=text, is_binary=False)

    @classmethod
    def from_binary(cls, data: bytes) -> WebSocketMessage:
        return cls(data=data, is_binary=True)

    def as_text(self) -> str | None:
        if self.is_binary:
            return None
        return str(self.data)

    def as_json(self) -> Any:
        try:
            return json.loads(self.data) if isinstance(self.data, str) else None
        except json.JSONDecodeError:
            return None


class WebSocketClient(BaseClient[WebSocketMessage]):
    """WebSocket client for real-time communication."""

    def __init__(
        self,
        url: str,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        ping_interval: float | None = 20.0,
        ping_timeout: float | None = 20.0,
        max_size: int = 2 * 1024 * 1024,
    ) -> None:
        super().__init__(url, timeout, default_headers, retry_count, retry_delay)
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.max_size = max_size
        self._ws: Any = None
        self._state = ConnectionState.DISCONNECTED
        self._received_messages: list[WebSocketMessage] = []
        self._subscribers: list[Callable[[WebSocketMessage], None]] = []
        self._receive_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._message_queue: asyncio.Queue | None = None

    def connect(self) -> None:
        """Establish WebSocket connection synchronously.

        Note: For true async WebSocket connections, use AsyncWebSocketClient.
        This method raises NotImplementedError - use AsyncWebSocketClient instead.
        """
        raise NotImplementedError(
            "Synchronous WebSocket connections are not supported. Use AsyncWebSocketClient instead."
        )

    def disconnect(self) -> None:
        """Close WebSocket connection."""
        raise NotImplementedError(
            "Synchronous WebSocket connections are not supported. Use AsyncWebSocketClient instead."
        )

    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED


class AsyncWebSocketClient(BaseAsyncClient[WebSocketMessage]):
    """Async WebSocket client for real-time communication."""

    def __init__(
        self,
        url: str,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        ping_interval: float | None = 20.0,
        ping_timeout: float | None = 20.0,
        max_size: int = 2 * 1024 * 1024,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        super().__init__(url, timeout, default_headers, retry_count, retry_delay)
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.max_size = max_size
        self.ssl_context = ssl_context
        self._ws: WebSocketClientProtocol | None = None
        self._state = ConnectionState.DISCONNECTED
        self._received_messages: list[WebSocketMessage] = []
        self._subscribers: list[Callable[[WebSocketMessage], None]] = []
        self._receive_task: asyncio.Task | None = None
        self._message_queue: asyncio.Queue[WebSocketMessage] | None = None
        self._message_event: asyncio.Event | None = None

    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        import websockets

        if self._state == ConnectionState.CONNECTED:
            return

        self._state = ConnectionState.CONNECTING

        headers = dict(self.default_headers)
        headers.update(self.get_auth_header())

        try:
            ssl_context = self.ssl_context
            if ssl_context is None and self.endpoint.startswith("wss://"):
                ssl_context = ssl.create_default_context()

            self._message_queue = asyncio.Queue()
            self._message_event = asyncio.Event()

            self._ws = await websockets.connect(
                self.endpoint,
                additional_headers=headers,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
                max_size=self.max_size,
                ssl=ssl_context,
                close_timeout=self.timeout,
            )

            self._connected = True
            self._state = ConnectionState.CONNECTED
            self._receive_task = asyncio.create_task(self._receive_loop())
            logger.info(f"WebSocket connected to {self.endpoint}")

        except asyncio.TimeoutError as e:
            self._state = ConnectionState.DISCONNECTED
            raise ConnectionTimeoutError(message=f"WebSocket connection timed out: {e}") from e

        except Exception as e:
            self._state = ConnectionState.DISCONNECTED
            raise ConnectionError(message=f"WebSocket connection failed: {e}") from e

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        if self._state == ConnectionState.DISCONNECTED:
            return

        self._state = ConnectionState.CLOSING

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self._connected = False
        self._state = ConnectionState.DISCONNECTED
        logger.info("WebSocket disconnected")

    async def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED and self._ws is not None

    async def _receive_loop(self) -> None:
        """Background task to receive messages."""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                start_time = time.perf_counter()

                if isinstance(message, bytes):
                    ws_message = WebSocketMessage.from_binary(message)
                else:
                    ws_message = WebSocketMessage.from_text(message)

                self._received_messages.append(ws_message)

                if self._message_queue:
                    await self._message_queue.put(ws_message)

                if self._message_event:
                    self._message_event.set()

                for subscriber in self._subscribers:
                    try:
                        result = subscriber(ws_message)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        logger.error(f"Subscriber error: {e}")

                duration_ms = (time.perf_counter() - start_time) * 1000
                self._record_request(
                    operation="receive",
                    request_data=None,
                    response_data=ws_message.data,
                    duration_ms=duration_ms,
                    metadata={"is_binary": ws_message.is_binary},
                )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
            self._state = ConnectionState.DISCONNECTED

    async def send(
        self,
        message: str | bytes | dict[str, Any],
        as_json: bool = True,
    ) -> None:
        """Send a message over WebSocket."""
        self._ensure_connected()
        if not self._ws:
            raise ConnectionError(message="WebSocket not connected")

        start_time = time.perf_counter()

        try:
            if isinstance(message, dict) and as_json:
                data = json.dumps(message)
            elif isinstance(message, bytes):
                data = message
            else:
                data = str(message)

            await self._ws.send(data)

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_request(
                operation="send",
                request_data=message if not isinstance(message, bytes) else "<binary>",
                response_data=None,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_request(
                operation="send",
                request_data=str(message),
                response_data=None,
                duration_ms=duration_ms,
                error=str(e),
            )
            raise ConnectionError(message=f"Failed to send message: {e}") from e

    async def receive(
        self,
        timeout: float | None = None,
    ) -> WebSocketMessage:
        """Wait for and receive the next message."""
        self._ensure_connected()
        if not self._message_queue:
            raise ConnectionError(message="WebSocket not properly initialized")

        timeout_val = timeout or self.timeout

        try:
            return await asyncio.wait_for(
                self._message_queue.get(),
                timeout=timeout_val,
            )
        except asyncio.TimeoutError:
            raise RequestTimeoutError(
                message=f"No message received within {timeout_val}s"
            ) from None

    async def receive_json(
        self,
        timeout: float | None = None,
    ) -> Any:
        """Receive and parse a JSON message."""
        message = await self.receive(timeout)
        data = message.as_json()
        if data is None:
            raise ValueError("Message is not valid JSON")
        return data

    def subscribe(
        self,
        handler: Callable[[WebSocketMessage], None] | Callable[[WebSocketMessage], Any],
    ) -> Callable[[], None]:
        """Subscribe to incoming messages with a handler.

        Returns an unsubscribe function.
        """
        self._subscribers.append(handler)

        def unsubscribe() -> None:
            if handler in self._subscribers:
                self._subscribers.remove(handler)

        return unsubscribe

    def get_received_messages(
        self,
        limit: int | None = None,
        clear: bool = False,
    ) -> list[WebSocketMessage]:
        """Get received messages.

        Args:
            limit: Maximum number of messages to return.
            clear: Whether to clear the message buffer after retrieval.
        """
        messages = self._received_messages
        if limit:
            messages = messages[-limit:]
        if clear:
            self._received_messages.clear()
        return messages

    def clear_messages(self) -> None:
        """Clear the received message buffer."""
        self._received_messages.clear()

    async def wait_for_message(
        self,
        timeout: float | None = None,
        predicate: Callable[[WebSocketMessage], bool] | None = None,
    ) -> WebSocketMessage:
        """Wait for a message matching a predicate.

        Args:
            timeout: Maximum time to wait.
            predicate: Function to match messages. If None, returns first message.
        """
        timeout_val = timeout or self.timeout

        if predicate is None:
            return await self.receive(timeout_val)

        start_time = time.perf_counter()

        while True:
            elapsed = time.perf_counter() - start_time
            remaining = timeout_val - elapsed

            if remaining <= 0:
                raise RequestTimeoutError(message=f"No matching message within {timeout_val}s")

            message = await self.receive(timeout=remaining)
            if predicate(message):
                return message

    async def ping(self) -> float:
        """Send a ping and measure round-trip time."""
        self._ensure_connected()
        if not self._ws:
            raise ConnectionError(message="WebSocket not connected")

        start_time = time.perf_counter()
        await self._ws.ping()
        latency = (time.perf_counter() - start_time) * 1000
        return latency

    async def __aenter__(self) -> AsyncWebSocketClient:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()
