"""MailHog adapter for email testing.

MailHog is an email testing tool for developers that captures emails
sent by your application and provides a web UI to view them.

Installation:
    pip install requests

Or run MailHog via Docker:
    docker run -d -p 1025:1025 -p 8025:8025 mailhog/mailhog

Example:
    >>> from venomqa.adapters import MailhogAdapter
    >>> adapter = MailhogAdapter(host="localhost", api_port=8025)
    >>> emails = adapter.get_emails_to("test@example.com")
    >>> adapter.delete_all_emails()
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

import requests

from venomqa.ports.mail import Email, EmailAttachment, MailPort


@dataclass
class MailhogConfig:
    """Configuration for MailHog adapter."""

    host: str = "localhost"
    smtp_port: int = 1025
    api_port: int = 8025
    timeout: float = 10.0
    poll_interval: float = 0.5


class MailhogAdapter(MailPort):
    """Adapter for MailHog email catcher.

    This adapter provides integration with MailHog for capturing
    and verifying emails in test environments.

    Attributes:
        config: Configuration for the MailHog connection.

    Example:
        >>> adapter = MailhogAdapter(host="localhost")
        >>> adapter.wait_for_email(to="user@example.com", timeout=30)
    """

    def __init__(
        self,
        host: str = "localhost",
        smtp_port: int = 1025,
        api_port: int = 8025,
        timeout: float = 10.0,
    ) -> None:
        """Initialize the MailHog adapter.

        Args:
            host: MailHog server hostname.
            smtp_port: SMTP server port.
            api_port: API server port.
            timeout: Request timeout in seconds.
        """
        self.config = MailhogConfig(
            host=host,
            smtp_port=smtp_port,
            api_port=api_port,
            timeout=timeout,
        )
        self._api_url = f"http://{host}:{api_port}"
        self._smtp_url = (host, smtp_port)

    def _parse_email(self, item: dict[str, Any]) -> Email:
        """Parse a MailHog API response into an Email object."""
        content = item.get("Content", {})
        headers = {h["Name"]: h["Value"] for h in content.get("Headers", [])}

        sender = headers.get("From", "")
        _, sender_email = parseaddr(sender)

        recipients = []
        to_header = headers.get("To", "")
        for addr in to_header.split(","):
            _, email = parseaddr(addr.strip())
            if email:
                recipients.append(email)

        cc = []
        cc_header = headers.get("Cc", "")
        for addr in cc_header.split(","):
            _, email = parseaddr(addr.strip())
            if email:
                cc.append(email)

        body = content.get("Body", "")

        received_str = headers.get("Date", "")
        received_at = None
        if received_str:
            try:
                received_at = parsedate_to_datetime(received_str)
            except (ValueError, TypeError):
                received_at = None

        attachments = []
        for part in content.get("MIME", {}).get("Parts", []):
            if part.get("Content-Type", "").startswith("application/"):
                attachments.append(
                    EmailAttachment(
                        filename=part.get("FileName", "attachment"),
                        content=part.get("Body", "").encode(),
                        content_type=part.get("Content-Type", "application/octet-stream"),
                    )
                )

        return Email(
            sender=sender_email or sender,
            recipients=recipients,
            subject=headers.get("Subject", ""),
            body=body,
            html_body=None,
            cc=cc,
            bcc=[],
            attachments=attachments,
            headers=headers,
            message_id=headers.get("Message-ID"),
            received_at=received_at,
            is_read=False,
        )

    def get_all_emails(self) -> list[Email]:
        """Retrieve all captured emails.

        Returns:
            List of all captured email messages.

        Raises:
            requests.RequestException: If API request fails.
        """
        response = requests.get(
            f"{self._api_url}/api/v2/messages",
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return [self._parse_email(item) for item in data.get("items", [])]

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
            emails = self.get_all_emails()
            if emails:
                return emails[0]
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
        import smtplib
        from email.message import EmailMessage as SMTPMessage

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
            msg.add_attachment(
                attachment.content
                if isinstance(attachment.content, bytes)
                else attachment.content.read(),
                maintype=attachment.content_type.split("/")[0],
                subtype=attachment.content_type.split("/")[1]
                if "/" in attachment.content_type
                else "",
                filename=attachment.filename,
            )

        with smtplib.SMTP(self.config.host, self.config.smtp_port) as server:
            server.send_message(msg)

        return msg["Message-ID"] or ""

    def health_check(self) -> bool:
        """Check if the MailHog service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            response = requests.get(
                f"{self._api_url}/api/v2/messages",
                timeout=2.0,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False
