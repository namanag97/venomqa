"""Mock Mail adapter for testing.

This adapter provides an in-memory email mock for testing purposes.
It implements the MailPort interface with full email capture, filtering,
and injection capabilities.

Example:
    >>> from venomqa.adapters.mail import MockMailAdapter
    >>> from venomqa.ports.mail import Email
    >>> mail = MockMailAdapter(poll_interval=0.1)
    >>> mail.send_email(Email(
    ...     sender="test@example.com",
    ...     recipients=["user@example.com"],
    ...     subject="Test",
    ...     body="Hello"
    ... ))
    >>> emails = mail.get_emails_to("user@example.com")
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from venomqa.ports.mail import Email, MailPort


class EmailValidationError(Exception):
    """Raised when email validation fails."""

    pass


@dataclass
class MockMailConfig:
    """Configuration for Mock Mail adapter.

    Attributes:
        poll_interval: Interval in seconds for polling operations.
        validate_emails: Whether to validate email addresses.
    """

    poll_interval: float = 0.5
    validate_emails: bool = True


class MockMailAdapter(MailPort):
    """In-memory mock mail adapter for testing.

    This adapter provides a fully functional in-memory email capture system
    for testing. It supports email filtering, injection for testing, and
    can simulate unhealthy states.

    Attributes:
        config: Configuration for the mock mail adapter.

    Example:
        >>> mail = MockMailAdapter()
        >>> mail.send_email(Email(
        ...     sender="sender@test.com",
        ...     recipients=["receiver@test.com"],
        ...     subject="Test Email",
        ...     body="Hello World"
        ... ))
        >>> email = mail.wait_for_email(to="receiver@test.com")
    """

    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    def __init__(
        self,
        poll_interval: float = 0.5,
        validate_emails: bool = True,
    ) -> None:
        """Initialize the Mock Mail adapter.

        Args:
            poll_interval: Interval in seconds for polling operations.
                Defaults to 0.5.
            validate_emails: Whether to validate email addresses.
                Defaults to True.

        Raises:
            ValueError: If poll_interval is not positive.
        """
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")

        self.config = MockMailConfig(
            poll_interval=poll_interval,
            validate_emails=validate_emails,
        )
        self._emails: list[Email] = []
        self._healthy: bool = True

    def _validate_email(self, email: str) -> bool:
        """Validate an email address format.

        Args:
            email: Email address to validate.

        Returns:
            True if valid, False otherwise.
        """
        if not self.config.validate_emails:
            return True
        if not email:
            return False
        return bool(self.EMAIL_PATTERN.match(email))

    def _validate_email_list(self, emails: list[str]) -> None:
        """Validate a list of email addresses.

        Args:
            emails: List of email addresses to validate.

        Raises:
            EmailValidationError: If any email is invalid.
        """
        if not self.config.validate_emails:
            return
        for email in emails:
            if not self._validate_email(email):
                raise EmailValidationError(f"Invalid email address: {email}")

    def get_all_emails(self) -> list[Email]:
        """Retrieve all captured emails.

        Returns:
            List of all captured email messages.
        """
        return list(self._emails)

    def get_emails_to(self, recipient: str) -> list[Email]:
        """Retrieve emails sent to a specific recipient.

        This checks recipients, CC, and BCC fields.

        Args:
            recipient: Email address to filter by.

        Returns:
            List of emails sent to the recipient.
        """
        return [
            e
            for e in self._emails
            if recipient in e.recipients
            or (e.cc and recipient in e.cc)
            or (e.bcc and recipient in e.bcc)
        ]

    def get_emails_from(self, sender: str) -> list[Email]:
        """Retrieve emails from a specific sender.

        Args:
            sender: Email address to filter by.

        Returns:
            List of emails from the sender.
        """
        return [e for e in self._emails if sender in e.sender]

    def get_emails_with_subject(self, subject: str, exact: bool = False) -> list[Email]:
        """Retrieve emails matching a subject.

        Args:
            subject: Subject to search for.
            exact: If True, match exact subject; otherwise case-insensitive
                partial match.

        Returns:
            List of matching emails.
        """
        if exact:
            return [e for e in self._emails if e.subject == subject]
        return [e for e in self._emails if subject.lower() in e.subject.lower()]

    def get_emails_with_body(self, text: str, case_sensitive: bool = False) -> list[Email]:
        """Retrieve emails containing specific text in the body.

        Args:
            text: Text to search for in the email body.
            case_sensitive: Whether to do case-sensitive search.

        Returns:
            List of matching emails.
        """
        if case_sensitive:
            return [e for e in self._emails if text in e.body]
        return [e for e in self._emails if text.lower() in e.body.lower()]

    def get_emails_with_html(self, text: str, case_sensitive: bool = False) -> list[Email]:
        """Retrieve emails containing specific text in the HTML body.

        Args:
            text: Text to search for in the HTML body.
            case_sensitive: Whether to do case-sensitive search.

        Returns:
            List of matching emails.
        """
        if case_sensitive:
            return [e for e in self._emails if e.html_body and text in e.html_body]
        return [e for e in self._emails if e.html_body and text.lower() in e.html_body.lower()]

    def get_latest_email(self, timeout: float = 10.0) -> Email | None:
        """Wait for and return the latest email.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            The latest email or None if timeout or no emails.
        """
        start = time.time()
        initial_count = len(self._emails)
        while time.time() - start < timeout:
            if len(self._emails) > initial_count:
                return self._emails[-1]
            time.sleep(self.config.poll_interval)
        return self._emails[-1] if self._emails else None

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
            subject: Subject pattern to match (case-insensitive partial).
            timeout: Maximum time to wait in seconds.

        Returns:
            Matching email or None if timeout.
        """
        start = time.time()
        seen_count = 0
        while time.time() - start < timeout:
            emails = self._emails[seen_count:]
            seen_count = len(self._emails)
            for email in emails:
                if to and to not in email.recipients:
                    continue
                if from_ and from_ not in email.sender:
                    continue
                if subject and subject.lower() not in email.subject.lower():
                    continue
                return email
            time.sleep(self.config.poll_interval)
        return None

    def wait_for_emails(
        self,
        count: int,
        to: str | None = None,
        from_: str | None = None,
        subject: str | None = None,
        timeout: float = 30.0,
    ) -> list[Email]:
        """Wait for multiple emails matching the given criteria.

        Args:
            count: Number of emails to wait for.
            to: Recipient email address to match.
            from_: Sender email address to match.
            subject: Subject pattern to match.
            timeout: Maximum time to wait in seconds.

        Returns:
            List of matching emails (may be less than count on timeout).
        """
        start = time.time()
        found: list[Email] = []

        while time.time() - start < timeout and len(found) < count:
            email = self.wait_for_email(
                to=to,
                from_=from_,
                subject=subject,
                timeout=self.config.poll_interval,
            )
            if email and email not in found:
                found.append(email)

        return found

    def delete_all_emails(self) -> None:
        """Delete all captured emails."""
        self._emails.clear()

    def send_email(self, email: Email) -> str:
        """Send an email (stores in memory).

        Args:
            email: Email to send.

        Returns:
            Message ID of the sent email.

        Raises:
            EmailValidationError: If email validation is enabled and
                any address is invalid.
        """
        self._validate_email_list([email.sender])
        self._validate_email_list(email.recipients)
        if email.cc:
            self._validate_email_list(email.cc)
        if email.bcc:
            self._validate_email_list(email.bcc)

        email.received_at = datetime.now()
        if not email.message_id:
            email.message_id = f"msg-{uuid.uuid4().hex[:8]}"
        self._emails.append(email)
        return email.message_id

    def inject_email(self, email: Email) -> None:
        """Inject an email directly into the captured list.

        Use this to simulate receiving emails in tests.

        Args:
            email: Email to inject.
        """
        if not email.message_id:
            email.message_id = f"msg-{uuid.uuid4().hex[:8]}"
        if not email.received_at:
            email.received_at = datetime.now()
        self._emails.append(email)

    def health_check(self) -> bool:
        """Check if the mail service is healthy.

        Returns:
            True if healthy, False if set_healthy(False) was called.
        """
        return self._healthy

    def set_healthy(self, healthy: bool) -> None:
        """Set the health status of the mail service.

        Use this to simulate unhealthy mail states in tests.

        Args:
            healthy: True for healthy, False for unhealthy.
        """
        self._healthy = healthy

    def count_emails(self) -> int:
        """Get the total number of captured emails.

        Returns:
            Number of emails in the capture.
        """
        return len(self._emails)

    def get_email_by_index(self, index: int) -> Email | None:
        """Get an email by its index in the captured list.

        Args:
            index: Index of the email (0-based).

        Returns:
            Email at the index, or None if index is out of range.
        """
        if 0 <= index < len(self._emails):
            return self._emails[index]
        return None

    def get_email_by_id(self, message_id: str) -> Email | None:
        """Get an email by its message ID.

        Args:
            message_id: Message ID to search for.

        Returns:
            Email with the matching message ID, or None if not found.
        """
        for email in self._emails:
            if email.message_id == message_id:
                return email
        return None

    def delete_email(self, message_id: str) -> bool:
        """Delete a specific email by message ID.

        Args:
            message_id: Message ID of the email to delete.

        Returns:
            True if deleted, False if not found.
        """
        for i, email in enumerate(self._emails):
            if email.message_id == message_id:
                del self._emails[i]
                return True
        return False

    def mark_read(self, message_id: str) -> bool:
        """Mark an email as read.

        Args:
            message_id: Message ID of the email to mark.

        Returns:
            True if marked, False if not found.
        """
        email = self.get_email_by_id(message_id)
        if email:
            email.is_read = True
            return True
        return False

    def get_unread_emails(self) -> list[Email]:
        """Get all unread emails.

        Returns:
            List of unread emails.
        """
        return [e for e in self._emails if not e.is_read]

    def get_emails_with_attachments(self) -> list[Email]:
        """Get all emails that have attachments.

        Returns:
            List of emails with attachments.
        """
        return [e for e in self._emails if e.attachments]

    def get_emails_by_date_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[Email]:
        """Get emails received within a date range.

        Args:
            start: Start of the date range.
            end: End of the date range.

        Returns:
            List of emails within the date range.
        """
        return [e for e in self._emails if e.received_at and start <= e.received_at <= end]
