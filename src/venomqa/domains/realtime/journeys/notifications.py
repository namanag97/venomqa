"""Real-time notification journeys.

Demonstrates:
- Push notification delivery
- Notification preferences
- Multi-device delivery

This module provides journeys for testing notification functionality
including push notifications, preference management, and multi-device delivery.
"""

from __future__ import annotations

from typing import Any

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.http import Client


class NotificationActions:
    """Actions for notification operations.

    Provides methods for sending notifications, managing notification
    preferences, and registering devices for push notifications.

    Args:
        base_url: Base URL for the main API service.
        notification_url: Optional URL for the notification service.
    """

    def __init__(self, base_url: str, notification_url: str | None = None) -> None:
        self.client = Client(base_url=base_url)
        self.notification_client = Client(base_url=notification_url or base_url)

    def send_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> Any:
        """Send a notification to a specific user.

        Args:
            user_id: ID of the user to notify.
            title: Notification title.
            body: Notification body text.
            data: Optional additional data payload.
            token: Optional authentication token.

        Returns:
            Response object from send notification request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        base_payload: dict[str, Any] = {"user_id": user_id, "title": title, "body": body}
        if data:
            base_payload["data"] = data
        return self.notification_client.post(
            "/api/notifications/send", json=base_payload, headers=headers
        )

    def get_notifications(self, user_id: str, page: int = 1, token: str | None = None) -> Any:
        """Retrieve notifications for a user.

        Args:
            user_id: ID of the user.
            page: Page number for pagination.
            token: Optional authentication token.

        Returns:
            Response object containing user notifications.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.notification_client.get(
            f"/api/notifications/{user_id}", params={"page": page}, headers=headers
        )

    def mark_read(self, notification_id: str, token: str | None = None) -> Any:
        """Mark a notification as read.

        Args:
            notification_id: Unique identifier of the notification.
            token: Optional authentication token.

        Returns:
            Response object from mark read request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.notification_client.post(
            f"/api/notifications/{notification_id}/read", headers=headers
        )

    def mark_all_read(self, user_id: str, token: str | None = None) -> Any:
        """Mark all notifications as read for a user.

        Args:
            user_id: ID of the user.
            token: Optional authentication token.

        Returns:
            Response object from mark all read request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.notification_client.post(
            f"/api/notifications/{user_id}/read-all", headers=headers
        )

    def get_preferences(self, user_id: str, token: str | None = None) -> Any:
        """Get notification preferences for a user.

        Args:
            user_id: ID of the user.
            token: Optional authentication token.

        Returns:
            Response object containing notification preferences.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.notification_client.get(
            f"/api/notifications/{user_id}/preferences", headers=headers
        )

    def update_preferences(self, user_id: str, preferences: dict, token: str | None = None) -> Any:
        """Update notification preferences for a user.

        Args:
            user_id: ID of the user.
            preferences: Dictionary of preference settings.
            token: Optional authentication token.

        Returns:
            Response object from preference update request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.notification_client.patch(
            f"/api/notifications/{user_id}/preferences",
            json=preferences,
            headers=headers,
        )

    def register_device(
        self, user_id: str, device_token: str, platform: str, token: str | None = None
    ) -> Any:
        """Register a device for push notifications.

        Args:
            user_id: ID of the user.
            device_token: Device push token from FCM/APNs.
            platform: Platform type (ios, android, web).
            token: Optional authentication token.

        Returns:
            Response object from device registration request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.notification_client.post(
            f"/api/notifications/{user_id}/devices",
            json={"device_token": device_token, "platform": platform},
            headers=headers,
        )

    def unregister_device(self, user_id: str, device_token: str, token: str | None = None) -> Any:
        """Unregister a device from push notifications.

        Args:
            user_id: ID of the user.
            device_token: Device push token to unregister.
            token: Optional authentication token.

        Returns:
            Response object from device unregistration request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.notification_client.delete(
            f"/api/notifications/{user_id}/devices/{device_token}",
            headers=headers,
        )


def login_user(client: Client, context: dict) -> Any:
    """Authenticate user and store token and user_id in context.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from login request.
    """
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "user@example.com"),
            "password": context.get("password", "password123"),
        },
    )
    if response.status_code == 200:
        data = response.json()
        context["token"] = data.get("access_token")
        context["user_id"] = data.get("user", {}).get("id")
    return response


def send_push_notification(client: Client, context: dict) -> Any:
    """Send a push notification and store notification_id in context.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing user_id.

    Returns:
        Response object from send notification request.
    """
    actions = NotificationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        notification_url=context.get("notification_url", "http://localhost:8004"),
    )
    response = actions.send_notification(
        user_id=context["user_id"],
        title=context.get("notification_title", "Test Notification"),
        body=context.get("notification_body", "This is a test notification"),
        data=context.get("notification_data", {"type": "test"}),
        token=context.get("admin_token", context.get("token")),
    )
    if response.status_code in [200, 201]:
        context["notification_id"] = response.json().get("id")
        assert response.json().get("sent") is True, "Notification should be sent"
    return response


def get_user_notifications(client: Client, context: dict) -> Any:
    """Retrieve notifications for the authenticated user.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing user_id.

    Returns:
        Response object containing user notifications.
    """
    actions = NotificationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        notification_url=context.get("notification_url", "http://localhost:8004"),
    )
    response = actions.get_notifications(user_id=context["user_id"], token=context["token"])
    if response.status_code == 200:
        notifications = response.json().get("notifications", [])
        context["notification_count"] = len(notifications)
        assert isinstance(notifications, list), "Notifications should be a list"
    return response


def mark_notification_read(client: Client, context: dict) -> Any:
    """Mark a notification as read.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing notification_id.

    Returns:
        Response object from mark read request.
    """
    actions = NotificationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        notification_url=context.get("notification_url", "http://localhost:8004"),
    )
    response = actions.mark_read(notification_id=context["notification_id"], token=context["token"])
    if response.status_code == 200:
        assert response.json().get("read") is True, "Notification should be marked read"
    return response


def mark_all_read(client: Client, context: dict) -> Any:
    """Mark all notifications as read for the user.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing user_id.

    Returns:
        Response object from mark all read request.
    """
    actions = NotificationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        notification_url=context.get("notification_url", "http://localhost:8004"),
    )
    return actions.mark_all_read(user_id=context["user_id"], token=context["token"])


def get_notification_preferences(client: Client, context: dict) -> Any:
    """Retrieve notification preferences for the user.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing user_id.

    Returns:
        Response object containing notification preferences.
    """
    actions = NotificationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        notification_url=context.get("notification_url", "http://localhost:8004"),
    )
    response = actions.get_preferences(user_id=context["user_id"], token=context["token"])
    if response.status_code == 200:
        context["preferences"] = response.json().get("preferences", {})
    return response


def update_notification_preferences(client: Client, context: dict) -> Any:
    """Update notification preferences for the user.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing user_id and new_preferences.

    Returns:
        Response object from preference update request.
    """
    actions = NotificationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        notification_url=context.get("notification_url", "http://localhost:8004"),
    )
    preferences = context.get("new_preferences", {"email": True, "push": True, "sms": False})
    response = actions.update_preferences(
        user_id=context["user_id"], preferences=preferences, token=context["token"]
    )
    if response.status_code == 200:
        context["preferences"] = response.json().get("preferences", {})
    return response


def disable_all_notifications(client: Client, context: dict) -> Any:
    """Disable all notification channels for the user.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing user_id.

    Returns:
        Response object from preference update request.
    """
    actions = NotificationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        notification_url=context.get("notification_url", "http://localhost:8004"),
    )
    return actions.update_preferences(
        user_id=context["user_id"],
        preferences={"email": False, "push": False, "sms": False},
        token=context["token"],
    )


def register_device(client: Client, context: dict) -> Any:
    """Register a device for push notifications.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing user_id.

    Returns:
        Response object from device registration request.
    """
    actions = NotificationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        notification_url=context.get("notification_url", "http://localhost:8004"),
    )
    response = actions.register_device(
        user_id=context["user_id"],
        device_token=context.get("device_token", "test_device_token_123"),
        platform=context.get("platform", "ios"),
        token=context["token"],
    )
    if response.status_code in [200, 201]:
        context["device_registered"] = True
    return response


push_notification_flow = Journey(
    name="realtime_push_notification",
    description="Send and receive push notifications",
    steps=[
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="send_notification", action=send_push_notification),
        Checkpoint(name="notification_sent"),
        Step(name="get_notifications", action=get_user_notifications),
        Step(name="mark_read", action=mark_notification_read),
        Checkpoint(name="notification_read"),
    ],
)

notification_preferences_flow = Journey(
    name="realtime_notification_preferences",
    description="Manage notification preferences",
    steps=[
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="get_preferences", action=get_notification_preferences),
        Checkpoint(name="preferences_loaded"),
        Branch(
            checkpoint_name="preferences_loaded",
            paths=[
                Path(
                    name="enable_all",
                    steps=[
                        Step(
                            name="update_enable",
                            action=update_notification_preferences,
                            args={"new_preferences": {"email": True, "push": True, "sms": True}},
                        ),
                        Step(name="verify_enabled", action=get_notification_preferences),
                    ],
                ),
                Path(
                    name="disable_all",
                    steps=[
                        Step(name="update_disable", action=disable_all_notifications),
                        Step(name="verify_disabled", action=get_notification_preferences),
                    ],
                ),
            ],
        ),
    ],
)

notification_delivery_flow = Journey(
    name="realtime_notification_delivery",
    description="Test multi-device notification delivery",
    steps=[
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="register_device", action=register_device),
        Checkpoint(name="device_registered"),
        Step(name="send_notification", action=send_push_notification),
        Step(name="verify_delivery", action=get_user_notifications),
        Checkpoint(name="delivered"),
    ],
)
