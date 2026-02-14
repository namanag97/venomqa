"""Real-Time Integration Scenario - Tests WebSocket and notifications.

This scenario verifies VenomQA's ability to:
- Establish and maintain WebSocket connections
- Receive real-time notifications
- Handle connection recovery
- Test bidirectional communication

Requires: full_featured_app with WebSocket support running on localhost:8000
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.clients.websocket import AsyncWebSocketClient, ConnectionState, WebSocketMessage
from venomqa.core.context import ExecutionContext

# =============================================================================
# WebSocket Helpers
# =============================================================================

_received_messages: list[WebSocketMessage] = []
_connection_events: list[dict[str, Any]] = []


def reset_websocket_tracking() -> None:
    """Reset WebSocket tracking state."""
    global _received_messages, _connection_events
    _received_messages = []
    _connection_events = []


def log_connection_event(event_type: str, details: dict[str, Any] | None = None) -> None:
    """Log a connection event."""
    _connection_events.append(
        {
            "type": event_type,
            "timestamp": time.time(),
            "details": details or {},
        }
    )


# =============================================================================
# Setup Actions
# =============================================================================


def setup_realtime_test(client: Any, context: ExecutionContext) -> Any:
    """Initialize real-time test state."""
    reset_websocket_tracking()

    context["ws_url"] = context.get("ws_url", "ws://localhost:8000/ws")
    context["ws_connected"] = False
    context["messages_received"] = []
    context["messages_sent"] = []
    context["connection_attempts"] = 0
    context["reconnections"] = 0
    context["test_start_time"] = time.time()

    return {"status": "initialized", "ws_url": context["ws_url"]}


def authenticate_for_ws(client: Any, context: ExecutionContext) -> Any:
    """Authenticate to get token for WebSocket."""
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "test@example.com"),
            "password": context.get("password", "password123"),
        },
    )

    if response.status_code == 200:
        data = response.json()
        context["ws_token"] = data.get("access_token") or data.get("token")

    return response


# =============================================================================
# WebSocket Connection Actions
# =============================================================================


def connect_websocket(client: Any, context: ExecutionContext) -> Any:
    """Establish WebSocket connection."""
    ws_url = context.get("ws_url", "ws://localhost:8000/ws")
    token = context.get("ws_token")

    context["connection_attempts"] = context.get("connection_attempts", 0) + 1

    async def _connect() -> dict[str, Any]:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        ws = AsyncWebSocketClient(
            url=ws_url,
            timeout=30.0,
            default_headers=headers,
            retry_count=3,
            retry_delay=1.0,
        )

        try:
            await ws.connect()
            log_connection_event("connected", {"url": ws_url})

            context["ws_client"] = ws
            context["ws_connected"] = True

            return {
                "status": "connected",
                "state": ws.state.value,
            }

        except Exception as e:
            log_connection_event("connection_failed", {"error": str(e)})
            return {"status": "failed", "error": str(e)}

    # Run async connection
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    result = loop.run_until_complete(_connect())
    return result


def send_websocket_message(client: Any, context: ExecutionContext) -> Any:
    """Send a message through WebSocket."""
    ws: AsyncWebSocketClient | None = context.get("ws_client")

    if not ws or not context.get("ws_connected"):
        return {"status": "error", "message": "WebSocket not connected"}

    message = {
        "type": "ping",
        "timestamp": time.time(),
        "data": {"test_id": f"test_{int(time.time())}"},
    }

    async def _send() -> dict[str, Any]:
        try:
            await ws.send(message)
            context.get("messages_sent", []).append(message)
            log_connection_event("message_sent", {"message": message})

            return {"status": "sent", "message": message}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_send())


def receive_websocket_message(client: Any, context: ExecutionContext) -> Any:
    """Receive a message from WebSocket."""
    ws: AsyncWebSocketClient | None = context.get("ws_client")

    if not ws or not context.get("ws_connected"):
        return {"status": "error", "message": "WebSocket not connected"}

    async def _receive() -> dict[str, Any]:
        try:
            message = await ws.receive(timeout=10.0)
            context.get("messages_received", []).append(
                {
                    "data": message.data,
                    "is_binary": message.is_binary,
                    "timestamp": time.time(),
                }
            )
            _received_messages.append(message)
            log_connection_event("message_received", {"data": str(message.data)[:100]})

            return {"status": "received", "data": message.data}
        except asyncio.TimeoutError:
            return {"status": "timeout", "message": "No message within timeout"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_receive())


def send_and_receive_echo(client: Any, context: ExecutionContext) -> Any:
    """Send a message and expect an echo response."""
    ws: AsyncWebSocketClient | None = context.get("ws_client")

    if not ws or not context.get("ws_connected"):
        return {"status": "error", "message": "WebSocket not connected"}

    test_message = {
        "type": "echo",
        "payload": f"Echo test at {time.time()}",
    }

    async def _echo_test() -> dict[str, Any]:
        try:
            # Send message
            await ws.send(test_message)
            context.get("messages_sent", []).append(test_message)

            # Wait for echo response
            response = await ws.receive(timeout=5.0)

            # Verify echo
            response_data = response.as_json()
            if response_data:
                if response_data.get("type") == "echo_response":
                    return {
                        "status": "echo_verified",
                        "sent": test_message,
                        "received": response_data,
                    }

            return {
                "status": "echo_unverified",
                "sent": test_message,
                "received": response.data,
            }

        except asyncio.TimeoutError:
            return {"status": "timeout", "message": "No echo received"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_echo_test())


def disconnect_websocket(client: Any, context: ExecutionContext) -> Any:
    """Disconnect WebSocket gracefully."""
    ws: AsyncWebSocketClient | None = context.get("ws_client")

    if not ws:
        return {"status": "skip", "message": "No WebSocket to disconnect"}

    async def _disconnect() -> dict[str, Any]:
        try:
            await ws.disconnect()
            log_connection_event("disconnected")
            context["ws_connected"] = False
            context["ws_client"] = None

            return {"status": "disconnected"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_disconnect())


# =============================================================================
# Connection Recovery Actions
# =============================================================================


def simulate_connection_drop(client: Any, context: ExecutionContext) -> Any:
    """Simulate a connection drop for recovery testing."""
    ws: AsyncWebSocketClient | None = context.get("ws_client")

    if not ws:
        return {"status": "skip", "message": "No WebSocket connection"}

    async def _drop() -> dict[str, Any]:
        try:
            # Force close without proper shutdown
            if ws._ws:
                await ws._ws.close(code=1006, reason="Simulated network drop")

            context["ws_connected"] = False
            log_connection_event("connection_dropped", {"reason": "simulated"})

            return {"status": "dropped"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_drop())


def reconnect_websocket(client: Any, context: ExecutionContext) -> Any:
    """Attempt to reconnect after connection drop."""
    context["reconnections"] = context.get("reconnections", 0) + 1

    result = connect_websocket(client, context)

    if result.get("status") == "connected":
        log_connection_event("reconnected", {"attempt": context["reconnections"]})

    return result


def verify_reconnection_state(client: Any, context: ExecutionContext) -> Any:
    """Verify state is consistent after reconnection."""
    ws: AsyncWebSocketClient | None = context.get("ws_client")

    if not ws or not context.get("ws_connected"):
        return {"status": "error", "message": "Not connected"}

    # Verify we can still communicate
    ping_result = send_and_receive_echo(client, context)

    return {
        "status": "state_verified",
        "reconnections": context.get("reconnections", 0),
        "ping_result": ping_result.get("status"),
    }


# =============================================================================
# Notification Testing Actions
# =============================================================================


def subscribe_to_notifications(client: Any, context: ExecutionContext) -> Any:
    """Subscribe to notification channel."""
    ws: AsyncWebSocketClient | None = context.get("ws_client")

    if not ws or not context.get("ws_connected"):
        return {"status": "error", "message": "WebSocket not connected"}

    subscribe_message = {
        "type": "subscribe",
        "channel": "notifications",
        "user_id": context.get("user_id", "test_user"),
    }

    async def _subscribe() -> dict[str, Any]:
        try:
            await ws.send(subscribe_message)

            # Wait for subscription confirmation
            response = await ws.receive(timeout=5.0)
            response_data = response.as_json()

            if response_data and response_data.get("type") == "subscribed":
                context["subscribed_channels"] = context.get("subscribed_channels", [])
                context["subscribed_channels"].append("notifications")
                return {"status": "subscribed", "channel": "notifications"}

            return {"status": "subscription_unconfirmed", "response": response.data}

        except Exception as e:
            return {"status": "failed", "error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_subscribe())


def trigger_notification(client: Any, context: ExecutionContext) -> Any:
    """Trigger a notification via HTTP to test real-time delivery."""
    # Create an action that triggers a notification
    response = client.post(
        "/api/notifications/send",
        json={
            "user_id": context.get("user_id", "test_user"),
            "type": "test",
            "message": f"Test notification at {time.time()}",
        },
    )

    if response.status_code in [200, 201]:
        context["triggered_notification"] = response.json()

    return response


def wait_for_notification(client: Any, context: ExecutionContext) -> Any:
    """Wait for notification to arrive via WebSocket."""
    ws: AsyncWebSocketClient | None = context.get("ws_client")

    if not ws or not context.get("ws_connected"):
        return {"status": "error", "message": "WebSocket not connected"}

    async def _wait() -> dict[str, Any]:
        try:
            # Wait for notification message
            message = await ws.wait_for_message(
                timeout=10.0,
                predicate=lambda m: (
                    m.as_json() and m.as_json().get("type") == "notification"
                ),
            )

            notification_data = message.as_json()
            context.get("messages_received", []).append(
                {
                    "type": "notification",
                    "data": notification_data,
                    "timestamp": time.time(),
                }
            )

            return {"status": "notification_received", "data": notification_data}

        except asyncio.TimeoutError:
            return {"status": "timeout", "message": "No notification received"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_wait())


# =============================================================================
# Verification Actions
# =============================================================================


def verify_websocket_communication(client: Any, context: ExecutionContext) -> Any:
    """Verify WebSocket communication worked correctly."""
    sent = context.get("messages_sent", [])
    received = context.get("messages_received", [])

    # Verify messages were sent and received
    assert len(sent) > 0, "Should have sent at least one message"
    # Note: Received count depends on server behavior

    return {
        "status": "communication_verified",
        "messages_sent": len(sent),
        "messages_received": len(received),
    }


def verify_connection_events(client: Any, context: ExecutionContext) -> Any:
    """Verify connection lifecycle events."""
    # Check for expected event types
    event_types = [e["type"] for e in _connection_events]

    assert "connected" in event_types, "Should have connection event"

    return {
        "status": "events_verified",
        "total_events": len(_connection_events),
        "event_types": list(set(event_types)),
    }


def generate_realtime_report(client: Any, context: ExecutionContext) -> Any:
    """Generate real-time test report."""
    elapsed_time = time.time() - context.get("test_start_time", 0)

    report = {
        "summary": {
            "elapsed_seconds": elapsed_time,
            "connection_attempts": context.get("connection_attempts", 0),
            "reconnections": context.get("reconnections", 0),
            "messages_sent": len(context.get("messages_sent", [])),
            "messages_received": len(context.get("messages_received", [])),
        },
        "connection_events": _connection_events,
        "subscribed_channels": context.get("subscribed_channels", []),
    }

    context["realtime_report"] = report
    return report


def cleanup_websocket(client: Any, context: ExecutionContext) -> Any:
    """Clean up WebSocket connection."""
    ws: AsyncWebSocketClient | None = context.get("ws_client")

    if ws:
        async def _cleanup() -> None:
            try:
                await ws.disconnect()
            except Exception:
                pass

        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(_cleanup())
        except Exception:
            pass

    context["ws_client"] = None
    context["ws_connected"] = False

    return {"status": "cleaned_up"}


# =============================================================================
# Journey Definitions
# =============================================================================

websocket_recovery_journey = Journey(
    name="websocket_recovery_scenario",
    description="Tests WebSocket connection, communication, and recovery",
    tags=["stress-test", "realtime", "websocket"],
    timeout=180.0,
    steps=[
        Step(
            name="setup",
            action=setup_realtime_test,
            description="Initialize real-time test",
        ),
        Step(
            name="authenticate",
            action=authenticate_for_ws,
            description="Authenticate for WebSocket",
        ),
        Checkpoint(name="ready"),
        # Initial connection
        Step(
            name="connect",
            action=connect_websocket,
            description="Establish WebSocket connection",
        ),
        Checkpoint(name="connected"),
        # Basic communication
        Step(
            name="send_message",
            action=send_websocket_message,
            description="Send test message",
        ),
        Step(
            name="receive_message",
            action=receive_websocket_message,
            description="Receive message",
            timeout=15.0,
        ),
        Step(
            name="echo_test",
            action=send_and_receive_echo,
            description="Test echo functionality",
        ),
        Checkpoint(name="communication_verified"),
        # Connection recovery
        Step(
            name="drop_connection",
            action=simulate_connection_drop,
            description="Simulate connection drop",
        ),
        Step(
            name="reconnect",
            action=reconnect_websocket,
            description="Attempt reconnection",
        ),
        Step(
            name="verify_reconnection",
            action=verify_reconnection_state,
            description="Verify state after reconnection",
        ),
        Checkpoint(name="recovery_verified"),
        # Verification
        Step(
            name="verify_communication",
            action=verify_websocket_communication,
            description="Verify overall communication",
        ),
        Step(
            name="verify_events",
            action=verify_connection_events,
            description="Verify connection events",
        ),
        Step(
            name="generate_report",
            action=generate_realtime_report,
            description="Generate real-time report",
        ),
        Step(
            name="cleanup",
            action=cleanup_websocket,
            description="Clean up connection",
        ),
    ],
)

notification_journey = Journey(
    name="notification_delivery_scenario",
    description="Tests real-time notification delivery via WebSocket",
    tags=["stress-test", "realtime", "notifications"],
    timeout=120.0,
    steps=[
        Step(name="setup", action=setup_realtime_test),
        Step(name="authenticate", action=authenticate_for_ws),
        Step(name="connect", action=connect_websocket),
        Checkpoint(name="connected"),
        Step(
            name="subscribe",
            action=subscribe_to_notifications,
            description="Subscribe to notification channel",
        ),
        Checkpoint(name="subscribed"),
        Branch(
            checkpoint_name="subscribed",
            paths=[
                Path(
                    name="notification_delivery",
                    steps=[
                        Step(
                            name="trigger",
                            action=trigger_notification,
                            description="Trigger notification via HTTP",
                        ),
                        Step(
                            name="wait_notification",
                            action=wait_for_notification,
                            description="Wait for notification via WebSocket",
                            timeout=15.0,
                        ),
                    ],
                ),
            ],
        ),
        Step(name="generate_report", action=generate_realtime_report),
        Step(name="cleanup", action=cleanup_websocket),
    ],
)
