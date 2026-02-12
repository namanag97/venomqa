"""WebSocket actions for real-time communication.

Reusable WebSocket connection and messaging actions.
"""

import asyncio

from venomqa.clients import HTTPClient
from venomqa.clients.websocket import AsyncWebSocketClient


class WebSocketActions:
    def __init__(self, base_url: str, ws_url: str | None = None):
        self.client = HTTPClient(base_url=base_url)
        self.ws_url = ws_url or base_url.replace("http", "ws").replace("https", "wss")

    def get_ws_client(self, path: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return AsyncWebSocketClient(url=f"{self.ws_url}{path}", default_headers=headers)


async def connect_websocket(context: dict) -> AsyncWebSocketClient:
    ws_url = context.get("ws_url", "ws://localhost:8000")
    token = context.get("token")
    path = context.get("ws_path", "/ws")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    client = AsyncWebSocketClient(url=f"{ws_url}{path}", default_headers=headers)
    await client.connect()
    context["ws_client"] = client
    return client


async def disconnect_websocket(context: dict):
    client = context.get("ws_client")
    if client:
        await client.disconnect()


async def send_ws_message(context: dict, message: dict):
    client = context.get("ws_client")
    if client:
        await client.send(message, as_json=True)


async def receive_ws_message(context: dict, timeout: float = 5.0):
    client = context.get("ws_client")
    if client:
        return await client.receive_json(timeout=timeout)
    return None


def ws_connect(client, context):
    async def _connect():
        ws_actions = WebSocketActions(
            base_url=context.get("base_url", "http://localhost:8000"),
            ws_url=context.get("ws_url"),
        )
        ws_client = ws_actions.get_ws_client(
            path=context.get("ws_path", "/ws"),
            token=context.get("token"),
        )
        await ws_client.connect()
        context["ws_client"] = ws_client
        context["ws_connected"] = True
        return {"connected": True}

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_connect())
        return result
    finally:
        loop.close()


def ws_disconnect(client, context):
    async def _disconnect():
        ws_client = context.get("ws_client")
        if ws_client:
            await ws_client.disconnect()
        context["ws_connected"] = False
        return {"disconnected": True}

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_disconnect())
        return result
    finally:
        loop.close()


def ws_send(client, context):
    async def _send():
        ws_client = context.get("ws_client")
        if ws_client:
            message = context.get("ws_message", {"type": "ping"})
            await ws_client.send(message, as_json=True)
            return {"sent": True, "message": message}
        return {"sent": False}

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_send())
        return result
    finally:
        loop.close()


def ws_receive(client, context):
    async def _receive():
        ws_client = context.get("ws_client")
        if ws_client:
            timeout = context.get("ws_timeout", 5.0)
            message = await ws_client.receive_json(timeout=timeout)
            context["ws_received"] = message
            return {"received": True, "message": message}
        return {"received": False}

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_receive())
        return result
    finally:
        loop.close()


def ws_ping(client, context):
    async def _ping():
        ws_client = context.get("ws_client")
        if ws_client:
            latency = await ws_client.ping()
            context["ws_latency"] = latency
            return {"ping": True, "latency_ms": latency}
        return {"ping": False}

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_ping())
        return result
    finally:
        loop.close()
