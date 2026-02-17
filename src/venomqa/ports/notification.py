from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class PushNotification:
    token: str
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)
    badge: int | None = None
    sound: str | None = None


@dataclass
class SMSMessage:
    to: str
    body: str
    from_number: str | None = None
    status: str = "pending"
    message_id: str | None = None
    sent_at: datetime | None = None


class NotificationPort(ABC):
    @abstractmethod
    def send_push(self, notification: PushNotification) -> str:
        """Send a push notification."""
        ...

    @abstractmethod
    def send_push_many(self, notifications: list[PushNotification]) -> list[str]:
        """Send multiple push notifications."""
        ...

    @abstractmethod
    def send_sms(self, message: SMSMessage) -> str:
        """Send an SMS message."""
        ...

    @abstractmethod
    def send_sms_many(self, messages: list[SMSMessage]) -> list[str]:
        """Send multiple SMS messages."""
        ...

    @abstractmethod
    def get_sms_status(self, message_id: str) -> str | None:
        """Get SMS delivery status."""
        ...

    @abstractmethod
    def get_push_status(self, notification_id: str) -> dict[str, Any] | None:
        """Get push notification status."""
        ...

    @abstractmethod
    def register_device(self, user_id: str, token: str, platform: str) -> bool:
        """Register a device for push notifications."""
        ...

    @abstractmethod
    def unregister_device(self, token: str) -> bool:
        """Unregister a device."""
        ...

    @abstractmethod
    def get_devices(self, user_id: str) -> list[dict[str, Any]]:
        """Get all registered devices for a user."""
        ...
