from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class WebhookRequest:
    id: str
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str | bytes | dict[str, Any] | None = None
    received_at: datetime = field(default_factory=datetime.now)
    query_params: dict[str, str] = field(default_factory=dict)


@dataclass
class WebhookResponse:
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: str | dict[str, Any] = ""


@dataclass
class WebhookSubscription:
    id: str
    url: str
    events: list[str] = field(default_factory=list)
    secret: str | None = None
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


class WebhookPort(ABC):
    @abstractmethod
    def receive(self, timeout: float = 30.0) -> WebhookRequest | None:
        """Wait for and receive the next webhook."""
        ...

    @abstractmethod
    def receive_all(self) -> list[WebhookRequest]:
        """Get all received webhooks."""
        ...

    @abstractmethod
    def respond(self, request_id: str, response: WebhookResponse) -> bool:
        """Respond to a webhook request."""
        ...

    @abstractmethod
    def get_request(self, request_id: str) -> WebhookRequest | None:
        """Get a specific webhook request by ID."""
        ...

    @abstractmethod
    def get_requests_by_path(self, path: str) -> list[WebhookRequest]:
        """Get all webhook requests for a specific path."""
        ...

    @abstractmethod
    def clear_requests(self) -> None:
        """Clear all received webhook requests."""
        ...

    @abstractmethod
    def subscribe(self, subscription: WebhookSubscription) -> str:
        """Create a webhook subscription."""
        ...

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a webhook subscription."""
        ...

    @abstractmethod
    def get_subscriptions(self) -> list[WebhookSubscription]:
        """Get all webhook subscriptions."""
        ...

    @abstractmethod
    def trigger(self, subscription_id: str, payload: dict[str, Any]) -> bool:
        """Manually trigger a webhook."""
        ...

    @abstractmethod
    def verify_signature(self, request: WebhookRequest, secret: str) -> bool:
        """Verify webhook signature."""
        ...
