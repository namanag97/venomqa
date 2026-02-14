"""GraphQL subscription support for VenomQA.

Provides WebSocket-based subscription handling with timeout support,
event filtering, and subscription lifecycle management.

Example:
    >>> from venomqa.graphql import SubscriptionClient, SubscriptionOptions
    >>>
    >>> async with SubscriptionClient("wss://api.example.com/graphql") as client:
    ...     async for event in client.subscribe(
    ...         query='subscription { productCreated { id title } }',
    ...         options=SubscriptionOptions(timeout=30.0, max_events=5)
    ...     ):
    ...         print(f"New product: {event.data}")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from venomqa.clients.base import ValidationError
from venomqa.errors import ConnectionError, RequestTimeoutError

logger = logging.getLogger(__name__)


@dataclass
class SubscriptionEvent:
    """Represents an event received from a subscription.

    Attributes:
        id: Unique event ID.
        subscription_id: ID of the subscription this event belongs to.
        data: The event payload data.
        errors: Any GraphQL errors in the event.
        timestamp: When the event was received.
        sequence: Event sequence number within the subscription.
    """

    id: str
    subscription_id: str
    data: dict[str, Any] | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    sequence: int = 0

    @property
    def has_errors(self) -> bool:
        """Check if the event has errors.

        Returns:
            True if errors are present.
        """
        return len(self.errors) > 0

    @property
    def successful(self) -> bool:
        """Check if the event is successful.

        Returns:
            True if no errors and data is present.
        """
        return not self.has_errors and self.data is not None

    def get_data(self, path: str | None = None) -> Any:
        """Get data from the event, optionally at a path.

        Args:
            path: Dot-notation path to the data.

        Returns:
            Data at the path, or None if not found.
        """
        if self.data is None:
            return None
        if path is None:
            return self.data

        current = self.data
        for key in path.split("."):
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                idx = int(key)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
        return current


@dataclass
class SubscriptionOptions:
    """Options for configuring subscriptions.

    Attributes:
        timeout: Maximum time to wait for events (seconds).
        max_events: Maximum number of events to receive.
        event_timeout: Timeout between events (seconds).
        auto_reconnect: Automatically reconnect on disconnect.
        reconnect_delay: Delay between reconnection attempts (seconds).
        max_reconnect_attempts: Maximum reconnection attempts.
        filter_fn: Optional function to filter events.
    """

    timeout: float | None = None
    max_events: int | None = None
    event_timeout: float = 60.0
    auto_reconnect: bool = True
    reconnect_delay: float = 1.0
    max_reconnect_attempts: int = 3
    filter_fn: Callable[[SubscriptionEvent], bool] | None = None


class SubscriptionHandler:
    """Handles subscription state and callbacks.

    Manages event buffering, filtering, and lifecycle.
    """

    def __init__(
        self,
        subscription_id: str,
        query: str,
        variables: dict[str, Any] | None = None,
        options: SubscriptionOptions | None = None,
    ):
        """Initialize the subscription handler.

        Args:
            subscription_id: Unique subscription ID.
            query: GraphQL subscription query.
            variables: Query variables.
            options: Subscription options.
        """
        self.id = subscription_id
        self.query = query
        self.variables = variables
        self.options = options or SubscriptionOptions()
        self._events: list[SubscriptionEvent] = []
        self._event_queue: asyncio.Queue[SubscriptionEvent] = asyncio.Queue()
        self._callbacks: list[Callable[[SubscriptionEvent], Any]] = []
        self._sequence = 0
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None
        self._active = False
        self._error: Exception | None = None

    @property
    def is_active(self) -> bool:
        """Check if subscription is active.

        Returns:
            True if subscription is receiving events.
        """
        return self._active

    @property
    def event_count(self) -> int:
        """Get the number of events received.

        Returns:
            Count of events received.
        """
        return len(self._events)

    def start(self) -> None:
        """Mark subscription as started."""
        self._active = True
        self._started_at = datetime.now()

    def stop(self, error: Exception | None = None) -> None:
        """Mark subscription as stopped.

        Args:
            error: Optional error that caused the stop.
        """
        self._active = False
        self._stopped_at = datetime.now()
        self._error = error

    async def receive_event(self, payload: dict[str, Any]) -> SubscriptionEvent:
        """Process a received event payload.

        Args:
            payload: The event payload from the WebSocket.

        Returns:
            The processed SubscriptionEvent.
        """
        self._sequence += 1
        event = SubscriptionEvent(
            id=str(uuid.uuid4()),
            subscription_id=self.id,
            data=payload.get("data"),
            errors=payload.get("errors", []),
            sequence=self._sequence,
        )

        # Apply filter if set
        if self.options.filter_fn and not self.options.filter_fn(event):
            return event

        self._events.append(event)
        await self._event_queue.put(event)

        # Invoke callbacks
        for callback in self._callbacks:
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Subscription callback error: {e}")

        return event

    def add_callback(self, callback: Callable[[SubscriptionEvent], Any]) -> Callable[[], None]:
        """Add an event callback.

        Args:
            callback: Function to call with each event.

        Returns:
            Function to remove the callback.
        """
        self._callbacks.append(callback)

        def remove() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return remove

    async def wait_for_event(self, timeout: float | None = None) -> SubscriptionEvent:
        """Wait for the next event.

        Args:
            timeout: Maximum time to wait (seconds).

        Returns:
            The next event.

        Raises:
            RequestTimeoutError: If timeout is reached.
        """
        timeout_val = timeout or self.options.event_timeout

        try:
            return await asyncio.wait_for(self._event_queue.get(), timeout=timeout_val)
        except asyncio.TimeoutError:
            raise RequestTimeoutError(
                message=f"No subscription event received within {timeout_val}s"
            ) from None

    def get_events(self) -> list[SubscriptionEvent]:
        """Get all received events.

        Returns:
            List of events.
        """
        return self._events.copy()

    def clear_events(self) -> None:
        """Clear the event buffer."""
        self._events.clear()


class SubscriptionClient:
    """Client for GraphQL subscriptions over WebSocket.

    Provides subscription lifecycle management, event streaming,
    and automatic reconnection.

    Example:
        >>> async with SubscriptionClient("wss://api.example.com/graphql") as client:
        ...     async for event in client.subscribe(
        ...         query='subscription { userOnline { id name } }'
        ...     ):
        ...         print(f"User online: {event.data}")
    """

    # GraphQL over WebSocket protocol messages
    GQL_CONNECTION_INIT = "connection_init"
    GQL_CONNECTION_ACK = "connection_ack"
    GQL_CONNECTION_ERROR = "connection_error"
    GQL_START = "start"
    GQL_STOP = "stop"
    GQL_DATA = "data"
    GQL_ERROR = "error"
    GQL_COMPLETE = "complete"
    GQL_CONNECTION_TERMINATE = "connection_terminate"

    def __init__(
        self,
        endpoint: str,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        connection_params: dict[str, Any] | None = None,
    ):
        """Initialize the subscription client.

        Args:
            endpoint: WebSocket endpoint URL.
            timeout: Connection timeout (seconds).
            default_headers: Headers for WebSocket handshake.
            connection_params: Parameters for connection_init.
        """
        if not endpoint:
            raise ValidationError(
                "Endpoint cannot be empty",
                field_name="endpoint",
                value=endpoint,
            )

        # Convert http(s) to ws(s) if needed
        if endpoint.startswith("http://"):
            endpoint = endpoint.replace("http://", "ws://", 1)
        elif endpoint.startswith("https://"):
            endpoint = endpoint.replace("https://", "wss://", 1)

        if not endpoint.startswith(("ws://", "wss://")):
            raise ValidationError(
                "Endpoint must be a WebSocket URL (ws:// or wss://)",
                field_name="endpoint",
                value=endpoint,
            )

        self.endpoint = endpoint
        self.timeout = timeout
        self.default_headers = default_headers or {}
        self.connection_params = connection_params or {}

        self._ws: Any = None
        self._connected = False
        self._subscriptions: dict[str, SubscriptionHandler] = {}
        self._receive_task: asyncio.Task | None = None
        self._auth_token: str | None = None

    def set_auth_token(self, token: str, token_type: str = "Bearer") -> None:
        """Set authentication token.

        Args:
            token: The auth token.
            token_type: Token type (default: Bearer).
        """
        self._auth_token = f"{token_type} {token}"

    async def connect(self) -> None:
        """Connect to the WebSocket server.

        Raises:
            ConnectionError: If connection fails.
        """
        import websockets

        if self._connected:
            return

        headers = dict(self.default_headers)
        if self._auth_token:
            headers["Authorization"] = self._auth_token

        try:
            self._ws = await websockets.connect(
                self.endpoint,
                additional_headers=headers,
                close_timeout=self.timeout,
            )

            # Send connection init
            init_payload = {"type": self.GQL_CONNECTION_INIT}
            if self.connection_params:
                init_payload["payload"] = self.connection_params

            await self._ws.send(json.dumps(init_payload))

            # Wait for ack
            response = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=self.timeout))

            if response.get("type") == self.GQL_CONNECTION_ERROR:
                raise ConnectionError(
                    message=f"Connection rejected: {response.get('payload')}"
                )

            if response.get("type") != self.GQL_CONNECTION_ACK:
                raise ConnectionError(
                    message=f"Expected connection_ack, got: {response.get('type')}"
                )

            self._connected = True
            self._receive_task = asyncio.create_task(self._receive_loop())
            logger.info(f"Subscription client connected to {self.endpoint}")

        except asyncio.TimeoutError:
            raise ConnectionError(
                message=f"Connection timed out after {self.timeout}s"
            ) from None
        except Exception as e:
            raise ConnectionError(message=f"Connection failed: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        if not self._connected:
            return

        # Stop all subscriptions
        for sub_id in list(self._subscriptions.keys()):
            await self.unsubscribe(sub_id)

        # Cancel receive task
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        # Close WebSocket
        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": self.GQL_CONNECTION_TERMINATE}))
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self._connected = False
        logger.info("Subscription client disconnected")

    async def _receive_loop(self) -> None:
        """Background loop to receive WebSocket messages."""
        try:
            async for message in self._ws:
                data = json.loads(message)
                await self._handle_message(data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
            self._connected = False

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle a received WebSocket message.

        Args:
            data: The parsed message data.
        """
        msg_type = data.get("type")
        msg_id = data.get("id")

        if msg_type == self.GQL_DATA:
            if msg_id and msg_id in self._subscriptions:
                handler = self._subscriptions[msg_id]
                payload = data.get("payload", {})
                await handler.receive_event(payload)

        elif msg_type == self.GQL_ERROR:
            if msg_id and msg_id in self._subscriptions:
                handler = self._subscriptions[msg_id]
                errors = data.get("payload", {}).get("errors", [])
                await handler.receive_event({"errors": errors})
                handler.stop(Exception(f"Subscription error: {errors}"))

        elif msg_type == self.GQL_COMPLETE:
            if msg_id and msg_id in self._subscriptions:
                handler = self._subscriptions[msg_id]
                handler.stop()

    async def subscribe(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        options: SubscriptionOptions | None = None,
    ) -> AsyncIterator[SubscriptionEvent]:
        """Subscribe to a GraphQL subscription.

        Args:
            query: The subscription query.
            variables: Query variables.
            operation_name: Operation name.
            options: Subscription options.

        Yields:
            SubscriptionEvent for each received event.

        Raises:
            ConnectionError: If not connected.
            RequestTimeoutError: If timeout is reached.
        """
        if not self._connected:
            await self.connect()

        opts = options or SubscriptionOptions()
        subscription_id = str(uuid.uuid4())

        handler = SubscriptionHandler(
            subscription_id=subscription_id,
            query=query,
            variables=variables,
            options=opts,
        )
        self._subscriptions[subscription_id] = handler

        # Send start message
        start_msg = {
            "id": subscription_id,
            "type": self.GQL_START,
            "payload": {
                "query": query,
            },
        }
        if variables:
            start_msg["payload"]["variables"] = variables
        if operation_name:
            start_msg["payload"]["operationName"] = operation_name

        await self._ws.send(json.dumps(start_msg))
        handler.start()

        try:
            event_count = 0
            start_time = time.time()

            while handler.is_active:
                # Check timeout
                if opts.timeout and (time.time() - start_time) > opts.timeout:
                    break

                # Check max events
                if opts.max_events and event_count >= opts.max_events:
                    break

                try:
                    event = await handler.wait_for_event(timeout=opts.event_timeout)
                    event_count += 1
                    yield event
                except RequestTimeoutError:
                    if opts.max_events is None and opts.timeout is None:
                        # No limits set, timeout means no more events
                        break
                    raise

        finally:
            await self.unsubscribe(subscription_id)

    async def subscribe_once(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> SubscriptionEvent:
        """Subscribe and wait for a single event.

        Args:
            query: The subscription query.
            variables: Query variables.
            timeout: Maximum time to wait.

        Returns:
            The first event received.

        Raises:
            RequestTimeoutError: If timeout is reached.
        """
        options = SubscriptionOptions(timeout=timeout, max_events=1)
        async for event in self.subscribe(query, variables, options=options):
            return event
        raise RequestTimeoutError(message=f"No event received within {timeout}s")

    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from a subscription.

        Args:
            subscription_id: The subscription ID to stop.
        """
        if subscription_id not in self._subscriptions:
            return

        handler = self._subscriptions[subscription_id]
        handler.stop()

        if self._connected and self._ws:
            stop_msg = {
                "id": subscription_id,
                "type": self.GQL_STOP,
            }
            try:
                await self._ws.send(json.dumps(stop_msg))
            except Exception:
                pass

        del self._subscriptions[subscription_id]

    def get_subscription(self, subscription_id: str) -> SubscriptionHandler | None:
        """Get a subscription handler by ID.

        Args:
            subscription_id: The subscription ID.

        Returns:
            The handler or None if not found.
        """
        return self._subscriptions.get(subscription_id)

    async def __aenter__(self) -> SubscriptionClient:
        """Enter async context manager."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        await self.disconnect()
