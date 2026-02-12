"""Email testing actions for QA testing.

This module provides reusable email testing action functions supporting:
- MailHog integration (local development)
- Mailtrap integration (testing service)
- Generic email API support

Example:
    >>> from venomqa.tools import get_latest_email, wait_for_email
    >>>
    >>> # Get latest email
    >>> email = get_latest_email(client, context, "user@example.com")
    >>> print(email["subject"])
    >>>
    >>> # Wait for email
    >>> email = wait_for_email(client, context, "user@example.com", timeout=60)
"""

from __future__ import annotations

import base64
import time
from typing import TYPE_CHECKING, Any

import httpx

from venomqa.errors import VenomQAError

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.state.context import Context


class EmailError(VenomQAError):
    """Raised when an email operation fails."""

    pass


def _get_email_config(client: Client, context: Context) -> dict[str, Any]:
    """Get email service configuration from client or context."""
    config = {}

    if hasattr(context, "config") and hasattr(context.config, "email"):
        config = context.config.email or {}
    elif hasattr(client, "email_config"):
        config = client.email_config or {}

    if hasattr(context, "_email_config"):
        config = {**config, **context._email_config}

    return config


def _get_mailhog_url(client: Client, context: Context) -> str:
    """Get MailHog API URL from configuration."""
    config = _get_email_config(client, context)
    return config.get("mailhog_url", "http://localhost:8025")


def _get_mailtrap_config(client: Client, context: Context) -> dict[str, str]:
    """Get Mailtrap API configuration."""
    config = _get_email_config(client, context)
    return {
        "api_url": config.get("mailtrap_url", "https://mailtrap.io"),
        "api_token": config.get("mailtrap_token", ""),
        "inbox_id": config.get("mailtrap_inbox_id", ""),
    }


def list_emails(
    client: Client,
    context: Context,
    to_address: str | None = None,
    from_address: str | None = None,
    subject_contains: str | None = None,
    limit: int = 50,
    email_service: str = "mailhog",
) -> list[dict[str, Any]]:
    """List emails with optional filters.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        to_address: Filter by recipient email address.
        from_address: Filter by sender email address.
        subject_contains: Filter by subject containing string.
        limit: Maximum number of emails to return.
        email_service: Email service to use ('mailhog' or 'mailtrap').

    Returns:
        list: List of email dictionaries.

    Raises:
        EmailError: If listing fails.

    Example:
        >>> emails = list_emails(
        ...     client, context,
        ...     to_address="user@example.com",
        ...     subject_contains="Verify"
        ... )
        >>> for email in emails:
        ...     print(email["subject"])
    """
    if email_service == "mailhog":
        return _list_mailhog_emails(
            client, context, to_address, from_address, subject_contains, limit
        )
    elif email_service == "mailtrap":
        return _list_mailtrap_emails(
            client, context, to_address, from_address, subject_contains, limit
        )
    else:
        raise EmailError(f"Unsupported email service: {email_service}")


def _list_mailhog_emails(
    client: Client,
    context: Context,
    to_address: str | None,
    from_address: str | None,
    subject_contains: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """List emails from MailHog."""
    base_url = _get_mailhog_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    try:
        params = {}
        if to_address:
            params["to"] = to_address
        if from_address:
            params["from"] = from_address
        if subject_contains:
            params["subject"] = subject_contains

        params["limit"] = limit

        response = http_client.get(f"{base_url}/api/v2/messages", params=params)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as e:
        raise EmailError(f"Failed to list emails from MailHog: {e}") from e

    emails = []
    for item in data.get("items", []):
        content = item.get("Content", {})
        headers = content.get("Headers", {})

        email = {
            "id": item.get("ID"),
            "from": _extract_address(headers.get("From", [None])),
            "to": _extract_addresses(headers.get("To", [])),
            "subject": _extract_header_value(headers.get("Subject", [""])),
            "body_text": _decode_email_body(content.get("Body", "")),
            "body_html": _decode_email_body(content.get("Body", "")),
            "raw": item,
            "created_at": item.get("Created"),
        }
        emails.append(email)

    return emails


def _list_mailtrap_emails(
    client: Client,
    context: Context,
    to_address: str | None,
    from_address: str | None,
    subject_contains: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """List emails from Mailtrap."""
    config = _get_mailtrap_config(client, context)
    api_url = config["api_url"]
    api_token = config["api_token"]
    inbox_id = config["inbox_id"]

    if not api_token or not inbox_id:
        raise EmailError("Mailtrap API token and inbox ID required")

    http_client = getattr(client, "http_client", None) or httpx.Client()
    headers = {"Api-Token": api_token}

    try:
        response = http_client.get(
            f"{api_url}/api/inboxes/{inbox_id}/messages",
            headers=headers,
            params={"limit": limit},
        )
        response.raise_for_status()
        messages = response.json()
    except httpx.HTTPError as e:
        raise EmailError(f"Failed to list emails from Mailtrap: {e}") from e

    emails = []
    for msg in messages:
        email = {
            "id": msg.get("id"),
            "from": msg.get("from_email"),
            "to": [msg.get("to_email")],
            "subject": msg.get("subject"),
            "body_text": msg.get("text_body", ""),
            "body_html": msg.get("html_body", ""),
            "raw": msg,
            "created_at": msg.get("created_at"),
        }

        if to_address and to_address not in email["to"]:
            continue
        if from_address and email["from"] != from_address:
            continue
        if subject_contains and subject_contains not in (email["subject"] or ""):
            continue

        emails.append(email)

    return emails


def _extract_header_value(header_list: list | str) -> str:
    """Extract header value from MailHog format."""
    if isinstance(header_list, str):
        return header_list
    if isinstance(header_list, list) and header_list:
        return header_list[0] or ""
    return ""


def _extract_address(header: list | str | None) -> str:
    """Extract email address from header."""
    if header is None:
        return ""
    value = _extract_header_value(header)
    if "<" in value and ">" in value:
        start = value.index("<") + 1
        end = value.index(">")
        return value[start:end]
    return value.strip()


def _extract_addresses(headers: list | str) -> list[str]:
    """Extract email addresses from headers."""
    if not headers:
        return []
    if isinstance(headers, str):
        return [_extract_address(headers)]
    return [_extract_address(h) for h in headers]


def _decode_email_body(body: str) -> str:
    """Decode email body from base64 if needed."""
    if not body:
        return ""
    try:
        decoded = base64.b64decode(body).decode("utf-8")
        return decoded
    except Exception:
        return body


def get_latest_email(
    client: Client,
    context: Context,
    to_address: str | None = None,
    from_address: str | None = None,
    subject_contains: str | None = None,
    email_service: str = "mailhog",
) -> dict[str, Any] | None:
    """Get the most recent email matching filters.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        to_address: Filter by recipient email address.
        from_address: Filter by sender email address.
        subject_contains: Filter by subject containing string.
        email_service: Email service to use ('mailhog' or 'mailtrap').

    Returns:
        dict | None: Email dictionary or None if no match found.

    Raises:
        EmailError: If operation fails.

    Example:
        >>> email = get_latest_email(
        ...     client, context,
        ...     to_address="user@example.com",
        ...     subject_contains="Verification"
        ... )
        >>> if email:
        ...     print(f"Subject: {email['subject']}")
    """
    emails = list_emails(
        client=client,
        context=context,
        to_address=to_address,
        from_address=from_address,
        subject_contains=subject_contains,
        limit=1,
        email_service=email_service,
    )

    return emails[0] if emails else None


def get_email_by_subject(
    client: Client,
    context: Context,
    subject: str,
    to_address: str | None = None,
    exact_match: bool = False,
    email_service: str = "mailhog",
) -> dict[str, Any] | None:
    """Get email by subject.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        subject: Subject to search for.
        to_address: Filter by recipient email address.
        exact_match: If True, requires exact subject match.
        email_service: Email service to use.

    Returns:
        dict | None: Email dictionary or None if not found.

    Example:
        >>> email = get_email_by_subject(
        ...     client, context,
        ...     subject="Welcome to Our Service",
        ...     exact_match=True
        ... )
    """
    emails = list_emails(
        client=client,
        context=context,
        to_address=to_address,
        email_service=email_service,
    )

    for email in emails:
        email_subject = email.get("subject", "")
        if exact_match:
            if email_subject == subject:
                return email
        else:
            if subject in email_subject:
                return email

    return None


def wait_for_email(
    client: Client,
    context: Context,
    to_address: str | None = None,
    from_address: str | None = None,
    subject_contains: str | None = None,
    timeout: float = 60.0,
    interval: float = 2.0,
    email_service: str = "mailhog",
) -> dict[str, Any]:
    """Wait for an email to be received.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        to_address: Filter by recipient email address.
        from_address: Filter by sender email address.
        subject_contains: Filter by subject containing string.
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.
        email_service: Email service to use.

    Returns:
        dict: Email dictionary when received.

    Raises:
        EmailError: If timeout is reached without email.

    Example:
        >>> email = wait_for_email(
        ...     client, context,
        ...     to_address="user@example.com",
        ...     subject_contains="Verify",
        ...     timeout=120
        ... )
        >>> print(f"Received: {email['subject']}")
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        email = get_latest_email(
            client=client,
            context=context,
            to_address=to_address,
            from_address=from_address,
            subject_contains=subject_contains,
            email_service=email_service,
        )

        if email:
            return email

        time.sleep(interval)

    elapsed = time.time() - start_time
    filters = []
    if to_address:
        filters.append(f"to={to_address}")
    if from_address:
        filters.append(f"from={from_address}")
    if subject_contains:
        filters.append(f"subject contains '{subject_contains}'")

    filter_str = " with " + ", ".join(filters) if filters else ""
    raise EmailError(f"Timeout after {elapsed:.1f}s waiting for email{filter_str}")


def clear_emails(
    client: Client,
    context: Context,
    email_service: str = "mailhog",
) -> int:
    """Clear all emails from the email service.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        email_service: Email service to use.

    Returns:
        int: Number of emails deleted.

    Raises:
        EmailError: If operation fails.

    Example:
        >>> count = clear_emails(client, context)
        >>> print(f"Cleared {count} emails")
    """
    if email_service == "mailhog":
        return _clear_mailhog_emails(client, context)
    elif email_service == "mailtrap":
        return _clear_mailtrap_emails(client, context)
    else:
        raise EmailError(f"Unsupported email service: {email_service}")


def _clear_mailhog_emails(client: Client, context: Context) -> int:
    """Clear all emails from MailHog."""
    base_url = _get_mailhog_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    try:
        response = http_client.get(f"{base_url}/api/v2/messages?limit=1000")
        response.raise_for_status()
        data = response.json()
        count = data.get("total", 0)
    except httpx.HTTPError as e:
        raise EmailError(f"Failed to count emails in MailHog: {e}") from e

    try:
        http_client.delete(f"{base_url}/api/v1/messages")
        return count
    except httpx.HTTPError as e:
        raise EmailError(f"Failed to clear emails in MailHog: {e}") from e


def _clear_mailtrap_emails(client: Client, context: Context) -> int:
    """Clear all emails from Mailtrap inbox."""
    config = _get_mailtrap_config(client, context)
    api_url = config["api_url"]
    api_token = config["api_token"]
    inbox_id = config["inbox_id"]

    if not api_token or not inbox_id:
        raise EmailError("Mailtrap API token and inbox ID required")

    http_client = getattr(client, "http_client", None) or httpx.Client()
    headers = {"Api-Token": api_token}

    try:
        response = http_client.patch(
            f"{api_url}/api/inboxes/{inbox_id}/clean",
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("count", 0)
    except httpx.HTTPError as e:
        raise EmailError(f"Failed to clear emails in Mailtrap: {e}") from e


def extract_links_from_email(email: dict[str, Any]) -> list[str]:
    """Extract all HTTP links from an email body.

    Args:
        email: Email dictionary.

    Returns:
        list: List of URLs found in the email.

    Example:
        >>> email = get_latest_email(client, context, "user@example.com")
        >>> links = extract_links_from_email(email)
        >>> for link in links:
        ...     if "verify" in link:
        ...         print(f"Verification link: {link}")
    """
    import re

    links = []
    body = email.get("body_html", "") or email.get("body_text", "")

    url_pattern = re.compile(r'https?://[^\s<>"\'\]\)]+')
    matches = url_pattern.findall(body)

    for url in matches:
        cleaned_url = url.rstrip(".,;:!?")
        if cleaned_url not in links:
            links.append(cleaned_url)

    return links


def extract_code_from_email(
    email: dict[str, Any],
    pattern: str = r"\b\d{4,6}\b",
) -> str | None:
    """Extract a verification code from an email body.

    Args:
        email: Email dictionary.
        pattern: Regex pattern for the code (default: 4-6 digit numbers).

    Returns:
        str | None: Extracted code or None if not found.

    Example:
        >>> email = get_latest_email(client, context, "user@example.com")
        >>> code = extract_code_from_email(email)
        >>> print(f"Verification code: {code}")
    """
    import re

    body = email.get("body_text", "") or email.get("body_html", "")

    match = re.search(pattern, body)
    return match.group(0) if match else None


def send_test_email(
    client: Client,
    context: Context,
    to_address: str,
    subject: str,
    body: str,
    from_address: str = "test@venomqa.local",
    email_service: str = "mailhog",
) -> bool:
    """Send a test email through the email service.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        to_address: Recipient email address.
        subject: Email subject.
        body: Email body (plain text).
        from_address: Sender email address.
        email_service: Email service to use.

    Returns:
        bool: True if email was sent successfully.

    Raises:
        EmailError: If sending fails.

    Example:
        >>> send_test_email(
        ...     client, context,
        ...     to_address="user@example.com",
        ...     subject="Test Email",
        ...     body="This is a test"
        ... )
    """
    if email_service == "mailhog":
        return _send_mailhog_email(client, context, to_address, subject, body, from_address)
    else:
        raise EmailError(f"Email sending not supported for {email_service}")


def _send_mailhog_email(
    client: Client,
    context: Context,
    to_address: str,
    subject: str,
    body: str,
    from_address: str,
) -> bool:
    """Send email via MailHog SMTP."""
    import smtplib
    from email.mime.text import MIMEText

    config = _get_email_config(client, context)
    smtp_host = config.get("mailhog_smtp_host", "localhost")
    smtp_port = config.get("mailhog_smtp_port", 1025)

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_address
        msg["To"] = to_address

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.sendmail(from_address, [to_address], msg.as_string())

        return True
    except Exception as e:
        raise EmailError(f"Failed to send email via MailHog: {e}") from e


def configure_email(
    context: Context,
    mailhog_url: str | None = None,
    mailhog_smtp_host: str | None = None,
    mailhog_smtp_port: int | None = None,
    mailtrap_token: str | None = None,
    mailtrap_inbox_id: str | None = None,
    mailtrap_url: str | None = None,
) -> None:
    """Configure email service settings in context.

    Args:
        context: Test context to configure.
        mailhog_url: MailHog API URL.
        mailhog_smtp_host: MailHog SMTP host.
        mailhog_smtp_port: MailHog SMTP port.
        mailtrap_token: Mailtrap API token.
        mailtrap_inbox_id: Mailtrap inbox ID.
        mailtrap_url: Mailtrap API URL.

    Example:
        >>> configure_email(
        ...     context,
        ...     mailhog_url="http://localhost:8025",
        ...     mailhog_smtp_host="localhost",
        ...     mailhog_smtp_port=1025
        ... )
    """
    if not hasattr(context, "_email_config"):
        context._email_config = {}

    if mailhog_url:
        context._email_config["mailhog_url"] = mailhog_url
    if mailhog_smtp_host:
        context._email_config["mailhog_smtp_host"] = mailhog_smtp_host
    if mailhog_smtp_port:
        context._email_config["mailhog_smtp_port"] = mailhog_smtp_port
    if mailtrap_token:
        context._email_config["mailtrap_token"] = mailtrap_token
    if mailtrap_inbox_id:
        context._email_config["mailtrap_inbox_id"] = mailtrap_inbox_id
    if mailtrap_url:
        context._email_config["mailtrap_url"] = mailtrap_url
