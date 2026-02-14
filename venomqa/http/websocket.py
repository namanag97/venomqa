"""WebSocket client for VenomQA real-time testing.

This module provides WebSocket clients for real-time bidirectional
communication, supporting both synchronous and asynchronous patterns.

Classes:
    ConnectionState: Enum for connection lifecycle states.
    WebSocketMessage: Data class for WebSocket messages.
    WebSocketClient: Synchronous WebSocket client (placeholder).
    AsyncWebSocketClient: Full-featured async WebSocket client.

Example:
    >>> import asyncio
    >>> from venomqa.clients.websocket import AsyncWebSocketClient
    >>> async def main():
    ...     async with AsyncWebSocketClient("wss://echo.websocket.org") as ws:
    ...         await ws.send({"type": "ping"})
    ...         response = await ws.receive()
    ...         print(response.data)
"""

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

from venomqa.http.base import (
    BaseAsyncClient,
    BaseClient,
    ValidationError,
    _validate_positive_number,
)
from venomqa.errors import ConnectionError, ConnectionTimeoutError, RequestTimeoutError

if TYPE_CHECKING:
    from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """WebSocket connection lifecycle states.

    Attributes:
        DISCONNECTED: No active connection.
        CONNECTING: Connection in progress.
        CONNECTED: Connection established and ready.
        CLOSING: Connection shutdown in progress.
    """

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CLOSING = "closing"


@dataclass
class WebSocketMessage:
    """Represents a WebSocket message with metadata.

    Supports both text and binary messages with automatic JSON parsing.

    Attributes:
        data: The message payload (str for text, bytes for binary).
        is_binary: True if message is binary, False for text.
        timestamp: When the message was received/sent.

    Example:
        >>> msg = WebSocketMessage.from_text('{"type": "ping"}')
        >>> msg.is_binary
        False
        >>> msg.as_json()
        {'type': 'ping'}
    """

    data: Any
    is_binary: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_text(cls, text: str) -> WebSocketMessage:
        """Create a text WebSocket message.

        Args:
            text: The text content.

        Returns:
            WebSocketMessage with is_binary=False.

        Raises:
            ValidationError: If text is empty.
        """
        if not isinstance(text, str):
            raise ValidationError(
                "Text message must be a string",
                field_name="text",
                value=type(text).__name__,
            )
        return cls(data=text, is_binary=False)

    @classmethod
    def from_binary(cls, data: bytes) -> WebSocketMessage:
        """Create a binary WebSocket message.

        Args:
            data: The binary content.

        Returns:
            WebSocketMessage with is_binary=True.

        Raises:
            ValidationError: If data is not bytes.
        """
        if not isinstance(data, bytes):
            raise ValidationError(
                "Binary message must be bytes",
                field_name="data",
                value=type(data).__name__,
            )
        return cls(data=data, is_binary=True)

    def as_text(self) -> str | None:
        """Get message as text if it's a text message.

        Returns:
            String data if text message, None if binary.
        """
        if self.is_binary:
            return None
        return str(self.data)

    def as_json(self) -> Any:
        """Parse message data as JSON.

        Returns:
            Parsed JSON data, or None if parsing fails or message is binary.
        """
        if self.is_binary:
            return None
        try:
            return json.loads(self.data) if isinstance(self.data, str) else None
        except json.JSONDecodeError:
            return None

    def __repr__(self) -> str:
        preview = str(self.data)[:50]
        if len(str(self.data)) > 50:
            preview += "..."
        return f"WebSocketMessage(data={preview!r}, is_binary={self.is_binary})"


def _validate_websocket_url(url: str) -> str:
    """Validate WebSocket URL format.

    Args:
        url: The WebSocket URL to validate.

    Returns:
        Validated URL.

    Raises:
        ValidationError: If URL is invalid.
    """
    if not url:
        raise ValidationError(
            "WebSocket URL cannot be empty",
            field_name="url",
            value=url,
        )
    url = url.strip()
    if not url.startswith(("ws://", "wss://")):
        raise ValidationError(
            "WebSocket URL must start with ws:// or wss://",
            field_name="url",
            value=url,
        )
    return url


class WebSocketClient(BaseClient[WebSocketMessage]):
    """Synchronous WebSocket client placeholder.

    Note: Synchronous WebSocket connections are not supported.
    Use AsyncWebSocketClient instead for full WebSocket functionality.

    This class exists to maintain a consistent interface with other
    protocol clients but will raise NotImplementedError on connect/disconnect.
    """

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
        """Initialize WebSocket client (not functional for sync use).

        Args:
            url: WebSocket server URL (ws:// or wss://).
            timeout: Connection/request timeout in seconds.
            default_headers: Headers to send during handshake.
            retry_count: Maximum retry attempts.
            retry_delay: Base delay between retries.
            ping_interval: WebSocket ping interval in seconds.
            ping_timeout: WebSocket ping timeout in seconds.
            max_size: Maximum message size in bytes.

        Raises:
            ValidationError: If parameters are invalid.
        """
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

        Raises:
            NotImplementedError: Always - use AsyncWebSocketClient.
        """
        raise NotImplementedError(
            "Synchronous WebSocket connections are not supported. Use AsyncWebSocketClient instead."
        )

    def disconnect(self) -> None:
        """Close WebSocket connection synchronously.

        Raises:
            NotImplementedError: Always - use AsyncWebSocketClient.
        """
        raise NotImplementedError(
            "Synchronous WebSocket connections are not supported. Use AsyncWebSocketClient instead."
        )

    def is_connected(self) -> bool:
        """Check if client is connected.

        Returns:
            True if connected (always False for sync client).
        """
        return self._state == ConnectionState.CONNECTED


class AsyncWebSocketClient(BaseAsyncClient[WebSocketMessage]):
    """Async WebSocket client for real-time bidirectional communication.

    Provides comprehensive WebSocket functionality including:
    - Automatic reconnection with retry logic
    - Message queuing for reliable delivery
    - Subscription-based message handling
    - Binary and text message support
    - JSON message parsing

    Example:
        >>> import asyncio
        >>> async def echo_client():
        ...     async with AsyncWebSocketClient("wss://echo.websocket.org") as ws:
        ...         await ws.send({"message": "Hello!"})
        ...         response = await ws.receive(timeout=5.0)
        ...         print(f"Received: {response.data}")
        ...         return response.as_json()

    Attributes:
        ping_interval: WebSocket ping interval in seconds.
        ping_timeout: WebSocket pong timeout in seconds.
        max_size: Maximum message size in bytes.
        ssl_context: Custom SSL context for secure connections.
    """

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
        """Initialize the async WebSocket client.

        Args:
            url: WebSocket server URL (ws:// or wss://).
            timeout: Connection/request timeout in seconds (default: 30.0).
            default_headers: Headers for WebSocket handshake (default: None).
            retry_count: Maximum retry attempts (default: 3).
            retry_delay: Base retry delay in seconds (default: 1.0).
            ping_interval: WebSocket ping interval, None to disable (default: 20.0).
            ping_timeout: WebSocket pong timeout, None to disable (default: 20.0).
            max_size: Maximum message size in bytes (default: 2MB).
            ssl_context: Custom SSL context for wss:// (default: None).

        Raises:
            ValidationError: If parameters are invalid.
        """
        validated_url = _validate_websocket_url(url)
        super().__init__(validated_url, timeout, default_headers, retry_count, retry_delay)

        if ping_interval is not None:
            _validate_positive_number(ping_interval, "ping_interval", allow_zero=True)
        if ping_timeout is not None:
            _validate_positive_number(ping_timeout, "ping_timeout", allow_zero=True)
        if max_size <= 0:
            raise ValidationError(
                "max_size must be positive",
                field_name="max_size",
                value=max_size,
            )

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
        """Get current connection state.

        Returns:
            Current ConnectionState value.
        """
        return self._state

    @property
    def url(self) -> str:
        """Get the WebSocket URL (alias for endpoint).

        Returns:
            The WebSocket server URL.
        """
        return self.endpoint

    async def connect(self) -> None:
        """Establish WebSocket connection asynchronously.

        Performs the WebSocket handshake and starts the message
        receive loop in the background.

        Raises:
            ConnectionTimeoutError: If connection times out.
            ConnectionError: If connection fails.
        """
        import websockets

        if self._state == ConnectionState.CONNECTED:
            return

        self._state = ConnectionState.CONNECTING

        headers = dict(self.default_headers)
        auth_header = await self.get_auth_header()
        headers.update(auth_header)

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
            raise ConnectionTimeoutError(
                message=f"WebSocket connection timed out after {self.timeout}s"
            ) from e

        except Exception as e:
            self._state = ConnectionState.DISCONNECTED
            error_msg = str(e)
            raise ConnectionError(message=f"WebSocket connection failed: {error_msg}") from e

    async def disconnect(self) -> None:
        """Close WebSocket connection gracefully.

        Cancels the receive loop and closes the WebSocket connection.
        Safe to call multiple times.
        """
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
        """Check if WebSocket is connected and ready.

        Returns:
            True if connected with an active WebSocket.
        """
        return self._state == ConnectionState.CONNECTED and self._ws is not None

    async def _receive_loop(self) -> None:
        """Background task to receive and process messages.

        Runs continuously until connection is closed or task is cancelled.
        Distributes received messages to queue and subscribers.
        """
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
        """Send a message over WebSocket.

        Args:
            message: Message to send (str, bytes, or dict).
            as_json: If True and message is dict, serialize to JSON (default: True).

        Raises:
            ValidationError: If message is invalid.
            ConnectionError: If not connected or send fails.
        """
        await self._ensure_connected()
        if not self._ws:
            raise ConnectionError(message="WebSocket not connected")

        if message is None:
            raise ValidationError(
                "Message cannot be None",
                field_name="message",
                value=None,
            )

        start_time = time.perf_counter()

        try:
            if isinstance(message, dict):
                if as_json:
                    data = json.dumps(message)
                else:
                    raise ValidationError(
                        "Dict message must have as_json=True",
                        field_name="message",
                        value=type(message).__name__,
                    )
            elif isinstance(message, bytes):
                data = message
            elif isinstance(message, str):
                data = message
            else:
                raise ValidationError(
                    f"Message must be str, bytes, or dict, got {type(message).__name__}",
                    field_name="message",
                    value=type(message).__name__,
                )

            await self._ws.send(data)

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_request(
                operation="send",
                request_data=message if not isinstance(message, bytes) else "<binary>",
                response_data=None,
                duration_ms=duration_ms,
            )

        except ConnectionError:
            raise
        except ValidationError:
            raise
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
        """Wait for and receive the next message.

        Args:
            timeout: Maximum time to wait in seconds (default: self.timeout).

        Returns:
            The next WebSocketMessage from the queue.

        Raises:
            RequestTimeoutError: If no message received within timeout.
            ConnectionError: If WebSocket not properly initialized.
        """
        await self._ensure_connected()
        if not self._message_queue:
            raise ConnectionError(message="WebSocket not properly initialized")

        timeout_val = timeout if timeout is not None else self.timeout
        if timeout_val <= 0:
            raise ValidationError(
                "Timeout must be positive",
                field_name="timeout",
                value=timeout_val,
            )

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
        """Receive and parse a JSON message.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            Parsed JSON data.

        Raises:
            RequestTimeoutError: If no message received within timeout.
            ValueError: If message is not valid JSON.
        """
        message = await self.receive(timeout)
        data = message.as_json()
        if data is None:
            raise ValueError(f"Message is not valid JSON: {str(message.data)[:100]}")
        return data

    def subscribe(
        self,
        handler: Callable[[WebSocketMessage], None] | Callable[[WebSocketMessage], Any],
    ) -> Callable[[], None]:
        """Subscribe to incoming messages with a handler.

        The handler will be called for each received message.
        Supports both sync and async handlers.

        Args:
            handler: Function to call with each message.

        Returns:
            Unsubscribe function to remove the handler.

        Raises:
            ValidationError: If handler is None.
        """
        if handler is None:
            raise ValidationError(
                "Handler cannot be None",
                field_name="handler",
                value=None,
            )

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
        """Get received messages from buffer.

        Args:
            limit: Maximum number of messages to return (most recent).
            clear: Whether to clear buffer after retrieval.

        Returns:
            List of WebSocketMessage objects.

        Raises:
            ValidationError: If limit is negative.
        """
        if limit is not None and limit < 0:
            raise ValidationError(
                "Limit must be non-negative",
                field_name="limit",
                value=limit,
            )

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
            timeout: Maximum time to wait in seconds.
            predicate: Function to match messages. If None, returns first message.

        Returns:
            First WebSocketMessage matching the predicate.

        Raises:
            RequestTimeoutError: If no matching message within timeout.
            ValidationError: If timeout is invalid.
        """
        timeout_val = timeout if timeout is not None else self.timeout
        if timeout_val <= 0:
            raise ValidationError(
                "Timeout must be positive",
                field_name="timeout",
                value=timeout_val,
            )

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
        """Send a WebSocket ping and measure round-trip time.

        Returns:
            Round-trip time in milliseconds.

        Raises:
            ConnectionError: If not connected.
        """
        await self._ensure_connected()
        if not self._ws:
            raise ConnectionError(message="WebSocket not connected")

        start_time = time.perf_counter()
        await self._ws.ping()
        latency = (time.perf_counter() - start_time) * 1000
        return latency

    async def __aenter__(self) -> AsyncWebSocketClient:
        """Enter async context manager, connecting to WebSocket."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager, disconnecting from WebSocket."""
        await self.disconnect()
