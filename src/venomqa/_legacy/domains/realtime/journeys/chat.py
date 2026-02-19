"""Chat and messaging journeys for real-time communication.

Demonstrates:
- WebSocket-based real-time messaging
- Direct and group chat flows
- Message delivery confirmation

This module provides journeys for testing real-time chat functionality
including direct messaging, group chats, and message delivery tracking.
"""

from __future__ import annotations

from typing import Any

from venomqa import Branch, JourneyCheckpoint as Checkpoint, Journey, Path, Step
from venomqa.http import Client
from venomqa.http.websocket import AsyncWebSocketClient


class ChatActions:
    """Actions for chat and messaging operations.

    Provides methods for creating conversations, sending messages,
    and managing chat groups via HTTP and WebSocket protocols.

    Args:
        base_url: Base URL for the main API service.
        ws_url: Optional WebSocket URL. Defaults to base_url with ws:// protocol.
    """

    def __init__(self, base_url: str, ws_url: str | None = None) -> None:
        self.client = Client(base_url=base_url)
        self.ws_url = ws_url or base_url.replace("http", "ws")

    def create_conversation(self, participant_ids: list, token: str | None = None) -> Any:
        """Create a new conversation with specified participants.

        Args:
            participant_ids: List of user IDs to include in conversation.
            token: Optional authentication token.

        Returns:
            Response object from conversation creation request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(
            "/api/conversations", json={"participant_ids": participant_ids}, headers=headers
        )

    def get_conversation(self, conversation_id: str, token: str | None = None) -> Any:
        """Retrieve conversation details by ID.

        Args:
            conversation_id: Unique identifier of the conversation.
            token: Optional authentication token.

        Returns:
            Response object containing conversation details.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(f"/api/conversations/{conversation_id}", headers=headers)

    def send_message(self, conversation_id: str, content: str, token: str | None = None) -> Any:
        """Send a message in a conversation.

        Args:
            conversation_id: Unique identifier of the conversation.
            content: Message content to send.
            token: Optional authentication token.

        Returns:
            Response object from message send request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": content},
            headers=headers,
        )

    def get_messages(self, conversation_id: str, page: int = 1, token: str | None = None) -> Any:
        """Retrieve messages from a conversation.

        Args:
            conversation_id: Unique identifier of the conversation.
            page: Page number for pagination.
            token: Optional authentication token.

        Returns:
            Response object containing paginated messages.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(
            f"/api/conversations/{conversation_id}/messages",
            params={"page": page},
            headers=headers,
        )

    def mark_read(self, conversation_id: str, message_id: str, token: str | None = None) -> Any:
        """Mark a message as read.

        Args:
            conversation_id: Unique identifier of the conversation.
            message_id: Unique identifier of the message to mark read.
            token: Optional authentication token.

        Returns:
            Response object from mark read request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(
            f"/api/conversations/{conversation_id}/messages/{message_id}/read",
            headers=headers,
        )

    def create_group(self, name: str, member_ids: list, token: str | None = None) -> Any:
        """Create a new group chat.

        Args:
            name: Name for the group chat.
            member_ids: List of user IDs to add as members.
            token: Optional authentication token.

        Returns:
            Response object from group creation request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(
            "/api/groups", json={"name": name, "member_ids": member_ids}, headers=headers
        )

    def add_group_member(self, group_id: str, user_id: str, token: str | None = None) -> Any:
        """Add a member to an existing group.

        Args:
            group_id: Unique identifier of the group.
            user_id: User ID to add to the group.
            token: Optional authentication token.

        Returns:
            Response object from add member request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(
            f"/api/groups/{group_id}/members", json={"user_id": user_id}, headers=headers
        )

    def get_ws_client(self, token: str) -> AsyncWebSocketClient:
        """Get a configured WebSocket client for real-time messaging.

        Args:
            token: Authentication token for WebSocket connection.

        Returns:
            Configured AsyncWebSocketClient instance.
        """
        return AsyncWebSocketClient(
            url=f"{self.ws_url}/ws/chat", default_headers={"Authorization": f"Bearer {token}"}
        )


def login_user1(client: Client, context: dict) -> Any:
    """Authenticate first test user and store token in context.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from login request.
    """
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("user1_email", "user1@example.com"),
            "password": context.get("password", "password123"),
        },
    )
    if response.status_code == 200:
        context["user1_token"] = response.json().get("access_token")
        context["user1_id"] = response.json().get("user", {}).get("id")
    return response


def login_user2(client: Client, context: dict) -> Any:
    """Authenticate second test user and store token in context.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from login request.
    """
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("user2_email", "user2@example.com"),
            "password": context.get("password", "password123"),
        },
    )
    if response.status_code == 200:
        context["user2_token"] = response.json().get("access_token")
        context["user2_id"] = response.json().get("user", {}).get("id")
    return response


def create_direct_conversation(client: Client, context: dict) -> Any:
    """Create a direct conversation between two users.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing user IDs.

    Returns:
        Response object from conversation creation request.
    """
    actions = ChatActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        ws_url=context.get("ws_url", "ws://localhost:8000"),
    )
    response = actions.create_conversation(
        participant_ids=[context["user1_id"], context["user2_id"]],
        token=context["user1_token"],
    )
    if response.status_code in [200, 201]:
        context["conversation_id"] = response.json().get("id")
    return response


def send_direct_message(client: Client, context: dict) -> Any:
    """Send a message in the direct conversation.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing conversation_id.

    Returns:
        Response object from message send request.
    """
    actions = ChatActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        ws_url=context.get("ws_url", "ws://localhost:8000"),
    )
    response = actions.send_message(
        conversation_id=context["conversation_id"],
        content=context.get("message_content", "Hello from user 1!"),
        token=context["user1_token"],
    )
    if response.status_code in [200, 201]:
        context["message_id"] = response.json().get("id")
    return response


def receive_messages(client: Client, context: dict) -> Any:
    """Retrieve messages as the second user.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing conversation_id.

    Returns:
        Response object containing received messages.
    """
    actions = ChatActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        ws_url=context.get("ws_url", "ws://localhost:8000"),
    )
    response = actions.get_messages(
        conversation_id=context["conversation_id"],
        token=context["user2_token"],
    )
    if response.status_code == 200:
        messages = response.json().get("messages", [])
        assert len(messages) > 0, "Should have received messages"
    return response


def mark_message_read(client: Client, context: dict) -> Any:
    """Mark a message as read by recipient.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing message_id.

    Returns:
        Response object from mark read request.
    """
    actions = ChatActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        ws_url=context.get("ws_url", "ws://localhost:8000"),
    )
    return actions.mark_read(
        conversation_id=context["conversation_id"],
        message_id=context["message_id"],
        token=context["user2_token"],
    )


def create_group_chat(client: Client, context: dict) -> Any:
    """Create a group chat with multiple members.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing user IDs.

    Returns:
        Response object from group creation request.
    """
    actions = ChatActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        ws_url=context.get("ws_url", "ws://localhost:8000"),
    )
    response = actions.create_group(
        name=context.get("group_name", "Test Group"),
        member_ids=[context["user1_id"], context["user2_id"]],
        token=context["user1_token"],
    )
    if response.status_code in [200, 201]:
        context["group_id"] = response.json().get("id")
    return response


def send_group_message(client: Client, context: dict) -> Any:
    """Send a message in the group chat.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing group_id.

    Returns:
        Response object from message send request.
    """
    actions = ChatActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        ws_url=context.get("ws_url", "ws://localhost:8000"),
    )
    return actions.send_message(
        conversation_id=context["group_id"],
        content=context.get("group_message", "Hello group!"),
        token=context["user1_token"],
    )


def get_group_messages(client: Client, context: dict) -> Any:
    """Retrieve messages from the group chat.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing group_id.

    Returns:
        Response object containing group messages.
    """
    actions = ChatActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        ws_url=context.get("ws_url", "ws://localhost:8000"),
    )
    return actions.get_messages(
        conversation_id=context["group_id"],
        token=context["user2_token"],
    )


direct_message_flow = Journey(
    name="realtime_direct_message",
    description="Direct messaging between two users",
    steps=[
        Step(name="login_user1", action=login_user1),
        Step(name="login_user2", action=login_user2),
        Checkpoint(name="both_authenticated"),
        Step(name="create_conversation", action=create_direct_conversation),
        Checkpoint(name="conversation_created"),
        Step(name="send_message", action=send_direct_message),
        Checkpoint(name="message_sent"),
        Step(name="receive_messages", action=receive_messages),
        Step(name="mark_read", action=mark_message_read),
        Checkpoint(name="message_delivered"),
    ],
)

group_chat_flow = Journey(
    name="realtime_group_chat",
    description="Group chat with multiple members",
    steps=[
        Step(name="login_user1", action=login_user1),
        Step(name="login_user2", action=login_user2),
        Checkpoint(name="authenticated"),
        Step(name="create_group", action=create_group_chat),
        Checkpoint(name="group_created"),
        Step(name="send_group_message", action=send_group_message),
        Step(name="get_group_messages", action=get_group_messages),
        Checkpoint(name="messages_received"),
    ],
)

message_delivery_flow = Journey(
    name="realtime_message_delivery",
    description="Test message delivery confirmation",
    steps=[
        Step(name="login_user1", action=login_user1),
        Step(name="login_user2", action=login_user2),
        Checkpoint(name="authenticated"),
        Step(name="create_conversation", action=create_direct_conversation),
        Step(name="send_message", action=send_direct_message),
        Checkpoint(name="message_sent"),
        Branch(
            checkpoint_name="message_sent",
            paths=[
                Path(
                    name="delivery_confirmed",
                    steps=[
                        Step(name="receive", action=receive_messages),
                        Step(name="read_receipt", action=mark_message_read),
                    ],
                ),
                Path(
                    name="pending_delivery",
                    steps=[Step(name="check_pending", action=receive_messages)],
                ),
            ],
        ),
    ],
)
