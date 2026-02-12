"""Mail Port interface for VenomQA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import BinaryIO


@dataclass
class EmailAttachment:
    """Represents an email attachment."""

    filename: str
    content: bytes | BinaryIO
    content_type: str = "application/octet-stream"
    content_id: str | None = None


@dataclass
class Email:
    """Represents an email message."""

    sender: str
    recipients: list[str]
    subject: str
    body: str
    html_body: str | None = None
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    attachments: list[EmailAttachment] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    message_id: str | None = None
    received_at: datetime | None = None
    is_read: bool = False


class MailPort(ABC):
    """Abstract port for mail operations in QA testing.

    This port defines the interface for mail catchers and SMTP servers
    used in testing environments. Implementations should support
    capturing, searching, and verifying email delivery.
    """

    @abstractmethod
    def get_all_emails(self) -> list[Email]:
        """Retrieve all captured emails.

        Returns:
            List of all captured email messages.
        """
        ...

    @abstractmethod
    def get_emails_to(self, recipient: str) -> list[Email]:
        """Retrieve emails sent to a specific recipient.

        Args:
            recipient: Email address to filter by.

        Returns:
            List of emails sent to the recipient.
        """
        ...

    @abstractmethod
    def get_emails_from(self, sender: str) -> list[Email]:
        """Retrieve emails from a specific sender.

        Args:
            sender: Email address to filter by.

        Returns:
            List of emails from the sender.
        """
        ...

    @abstractmethod
    def get_emails_with_subject(self, subject: str, exact: bool = False) -> list[Email]:
        """Retrieve emails matching a subject.

        Args:
            subject: Subject to search for.
            exact: If True, match exact subject; otherwise partial match.

        Returns:
            List of matching emails.
        """
        ...

    @abstractmethod
    def get_latest_email(self, timeout: float = 10.0) -> Email | None:
        """Wait for and return the latest email.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            The latest email or None if timeout.
        """
        ...

    @abstractmethod
    def wait_for_email(
        self,
        to: str | None = None,
        from_: str | None = None,
        subject: str | None = None,
        timeout: float = 30.0,
    ) -> Email | None:
        """Wait for an email matching the given criteria.

        Args:
            to: Recipient email address to match.
            from_: Sender email address to match.
            subject: Subject pattern to match.
            timeout: Maximum time to wait in seconds.

        Returns:
            Matching email or None if timeout.
        """
        ...

    @abstractmethod
    def delete_all_emails(self) -> None:
        """Delete all captured emails."""
        ...

    @abstractmethod
    def send_email(self, email: Email) -> str:
        """Send an email.

        Args:
            email: Email to send.

        Returns:
            Message ID of the sent email.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the mail service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        ...
