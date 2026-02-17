"""Mailpit adapter for email testing.

Mailpit is a modern web and API based SMTP testing tool that serves
as a better alternative to MailHog with improved UI and features.

Installation:
    Run Mailpit via Docker:
    docker run -d -p 1025:1025 -p 8025:8025 axllent/mailpit

Example:
    >>> from venomqa.adapters import MailpitAdapter
    >>> adapter = MailpitAdapter(host="localhost", api_port=8025)
    >>> emails = adapter.get_emails_to("test@example.com")
"""

from __future__ import annotations

import smtplib
import time
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage as SMTPMessage
from typing import Any

import requests

from venomqa.ports.mail import Email, EmailAttachment, MailPort


@dataclass
class MailpitConfig:
    """Configuration for Mailpit adapter."""

    host: str = "localhost"
    smtp_port: int = 1025
    api_port: int = 8025
    timeout: float = 10.0
    poll_interval: float = 0.5
    use_tls: bool = False


class MailpitAdapter(MailPort):
    """Adapter for Mailpit email catcher.

    Mailpit provides a modern interface for email testing with
    a REST API and SMTP server.

    Attributes:
        config: Configuration for the Mailpit connection.

    Example:
        >>> adapter = MailpitAdapter()
        >>> email = adapter.wait_for_email(to="user@test.com")
        >>> print(email.subject)
    """

    def __init__(
        self,
        host: str = "localhost",
        smtp_port: int = 1025,
        api_port: int = 8025,
        timeout: float = 10.0,
        use_tls: bool = False,
    ) -> None:
        """Initialize the Mailpit adapter.

        Args:
            host: Mailpit server hostname.
            smtp_port: SMTP server port.
            api_port: API server port.
            timeout: Request timeout in seconds.
            use_tls: Whether to use TLS for SMTP.
        """
        self.config = MailpitConfig(
            host=host,
            smtp_port=smtp_port,
            api_port=api_port,
            timeout=timeout,
            use_tls=use_tls,
        )
        self._api_url = f"http://{host}:{api_port}"

    def _parse_email(self, item: dict[str, Any]) -> Email:
        """Parse a Mailpit API response into an Email object."""
        sender = item.get("From", {})
        sender_email = sender.get("Address", "")

        recipients = []
        for addr in item.get("To", []):
            email = addr.get("Address", "")
            if email:
                recipients.append(email)

        cc = []
        for addr in item.get("Cc", []):
            email = addr.get("Address", "")
            if email:
                cc.append(email)

        bcc = []
        for addr in item.get("Bcc", []):
            email = addr.get("Address", "")
            if email:
                bcc.append(email)

        created_str = item.get("Created", "")
        received_at = None
        if created_str:
            try:
                received_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                received_at = None

        attachments = []
        for att in item.get("Attachments", []):
            attachments.append(
                EmailAttachment(
                    filename=att.get("FileName", "attachment"),
                    content=b"",
                    content_type=att.get("ContentType", "application/octet-stream"),
                    content_id=att.get("ContentID"),
                )
            )

        return Email(
            sender=sender_email,
            recipients=recipients,
            subject=item.get("Subject", ""),
            body=item.get("Text", ""),
            html_body=item.get("HTML", ""),
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            headers=item.get("Headers", {}),
            message_id=item.get("MessageID"),
            received_at=received_at,
            is_read=item.get("Read", False),
        )

    def get_all_emails(self) -> list[Email]:
        """Retrieve all captured emails.

        Returns:
            List of all captured email messages.

        Raises:
            requests.RequestException: If API request fails.
        """
        response = requests.get(
            f"{self._api_url}/api/v1/messages",
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return [self._parse_email(item) for item in data.get("messages", [])]

    def get_emails_to(self, recipient: str) -> list[Email]:
        """Retrieve emails sent to a specific recipient.

        Args:
            recipient: Email address to filter by.

        Returns:
            List of emails sent to the recipient.
        """
        emails = self.get_all_emails()
        return [e for e in emails if recipient in e.recipients]

    def get_emails_from(self, sender: str) -> list[Email]:
        """Retrieve emails from a specific sender.

        Args:
            sender: Email address to filter by.

        Returns:
            List of emails from the sender.
        """
        emails = self.get_all_emails()
        return [e for e in emails if sender in e.sender]

    def get_emails_with_subject(self, subject: str, exact: bool = False) -> list[Email]:
        """Retrieve emails matching a subject.

        Args:
            subject: Subject to search for.
            exact: If True, match exact subject; otherwise partial match.

        Returns:
            List of matching emails.
        """
        emails = self.get_all_emails()
        if exact:
            return [e for e in emails if e.subject == subject]
        return [e for e in emails if subject.lower() in e.subject.lower()]

    def get_latest_email(self, timeout: float = 10.0) -> Email | None:
        """Wait for and return the latest email.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            The latest email or None if timeout.
        """
        start = time.time()
        while time.time() - start < timeout:
            response = requests.get(
                f"{self._api_url}/api/v1/message/latest",
                timeout=self.config.timeout,
            )
            if response.status_code == 200:
                return self._parse_email(response.json())
            time.sleep(self.config.poll_interval)
        return None

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
        start = time.time()
        while time.time() - start < timeout:
            emails = self.get_all_emails()
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

    def delete_all_emails(self) -> None:
        """Delete all captured emails.

        Raises:
            requests.RequestException: If API request fails.
        """
        response = requests.delete(
            f"{self._api_url}/api/v1/messages",
            timeout=self.config.timeout,
        )
        response.raise_for_status()

    def send_email(self, email: Email) -> str:
        """Send an email via SMTP.

        Args:
            email: Email to send.

        Returns:
            Message ID of the sent email.

        Raises:
            smtplib.SMTPException: If sending fails.
        """
        msg = SMTPMessage()
        msg["From"] = email.sender
        msg["To"] = ", ".join(email.recipients)
        msg["Subject"] = email.subject
        if email.cc:
            msg["Cc"] = ", ".join(email.cc)
        for key, value in email.headers.items():
            if key.lower() not in ("from", "to", "subject", "cc"):
                msg[key] = value

        if email.html_body:
            msg.set_content(email.body)
            msg.add_alternative(email.html_body, subtype="html")
        else:
            msg.set_content(email.body)

        for attachment in email.attachments:
            content = attachment.content
            if isinstance(content, bytes):
                data = content
            elif hasattr(content, "read"):
                data = content.read()
            else:
                data = str(content).encode()

            msg.add_attachment(
                data,
                maintype=attachment.content_type.split("/")[0],
                subtype=attachment.content_type.split("/")[1]
                if "/" in attachment.content_type
                else "",
                filename=attachment.filename,
            )

        with smtplib.SMTP(self.config.host, self.config.smtp_port) as server:
            if self.config.use_tls:
                server.starttls()
            server.send_message(msg)

        return msg["Message-ID"] or ""

    def health_check(self) -> bool:
        """Check if the Mailpit service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            response = requests.get(
                f"{self._api_url}/api/v1/info",
                timeout=2.0,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_message(self, message_id: str) -> Email | None:
        """Get a specific email by message ID.

        Args:
            message_id: The message ID to retrieve.

        Returns:
            The email or None if not found.
        """
        try:
            response = requests.get(
                f"{self._api_url}/api/v1/message/{message_id}",
                timeout=self.config.timeout,
            )
            if response.status_code == 200:
                return self._parse_email(response.json())
            return None
        except requests.RequestException:
            return None

    def search(self, query: str) -> list[Email]:
        """Search emails using Mailpit's search syntax.

        Args:
            query: Search query string.

        Returns:
            List of matching emails.
        """
        try:
            response = requests.get(
                f"{self._api_url}/api/v1/search",
                params={"query": query},
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return [self._parse_email(item) for item in data.get("messages", [])]
        except requests.RequestException:
            return []

    def set_read(self, message_id: str, read: bool = True) -> bool:
        """Mark an email as read or unread.

        Args:
            message_id: The message ID.
            read: True to mark as read, False for unread.

        Returns:
            True if successful.
        """
        try:
            response = requests.put(
                f"{self._api_url}/api/v1/message/{message_id}",
                json={"read": read},
                timeout=self.config.timeout,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False
