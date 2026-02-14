"""Notification channels for VenomQA alerting system.

This module provides implementations of various notification channels
including Slack, Discord, Email (SMTP), PagerDuty, and custom webhooks.

Example:
    >>> from venomqa.notifications.channels import SlackChannel, NotificationMessage
    >>>
    >>> channel = SlackChannel(
    ...     webhook_url="https://hooks.slack.com/services/...",
    ...     name="slack-alerts"
    ... )
    >>>
    >>> message = NotificationMessage(
    ...     title="Test Failure Alert",
    ...     body="Journey 'checkout' failed at step 'payment'",
    ...     severity="high",
    ...     event=NotificationEvent.FAILURE
    ... )
    >>>
    >>> success = channel.send(message)
"""

from __future__ import annotations

import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ChannelType(Enum):
    """Types of notification channels supported."""

    SLACK = "slack"
    DISCORD = "discord"
    EMAIL = "email"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"


class NotificationEvent(Enum):
    """Types of notification events."""

    FAILURE = "failure"
    RECOVERY = "recovery"
    WARNING = "warning"
    INFO = "info"
    PERFORMANCE = "performance"
    INVARIANT_VIOLATION = "invariant_violation"


@dataclass
class NotificationMessage:
    """A notification message to be sent through channels.

    Attributes:
        title: Short title/subject for the notification.
        body: Main message body with details.
        event: Type of notification event.
        severity: Severity level (critical, high, medium, low, info).
        journey_name: Name of the journey that triggered the notification.
        step_name: Name of the step that failed (if applicable).
        path_name: Name of the path (if in a branch).
        error: Error message if this is a failure notification.
        report_url: URL to the full test report.
        timestamp: When the event occurred.
        metadata: Additional metadata for context.
        quick_actions: List of quick action URLs/commands.
    """

    title: str
    body: str
    event: NotificationEvent = NotificationEvent.INFO
    severity: str = "info"
    journey_name: str | None = None
    step_name: str | None = None
    path_name: str | None = None
    error: str | None = None
    report_url: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    quick_actions: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "body": self.body,
            "event": self.event.value,
            "severity": self.severity,
            "journey_name": self.journey_name,
            "step_name": self.step_name,
            "path_name": self.path_name,
            "error": self.error,
            "report_url": self.report_url,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "quick_actions": self.quick_actions,
        }


class BaseChannel(ABC):
    """Abstract base class for all notification channels.

    Provides common functionality for notification channels including
    event filtering and send abstractions.

    Attributes:
        name: Unique identifier for this channel instance.
        enabled: Whether this channel is active.
        events: List of events this channel should handle.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        name: str,
        enabled: bool = True,
        events: list[NotificationEvent] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the channel.

        Args:
            name: Unique identifier for this channel.
            enabled: Whether notifications should be sent.
            events: List of events to handle. None means all events.
            timeout: Request timeout in seconds.
        """
        self.name = name
        self.enabled = enabled
        self.events = events or list(NotificationEvent)
        self.timeout = timeout

    @abstractmethod
    def send(self, message: NotificationMessage) -> bool:
        """Send a notification message.

        Args:
            message: The notification message to send.

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        ...

    @property
    @abstractmethod
    def channel_type(self) -> ChannelType:
        """Return the type of this channel."""
        ...

    def should_send(self, message: NotificationMessage) -> bool:
        """Check if this channel should send the given message.

        Args:
            message: The notification message to check.

        Returns:
            True if the channel should handle this message.
        """
        if not self.enabled:
            return False
        return message.event in self.events

    def send_if_applicable(self, message: NotificationMessage) -> bool:
        """Send a message if applicable for this channel.

        Args:
            message: The notification message to potentially send.

        Returns:
            True if sent successfully or not applicable, False if send failed.
        """
        if not self.should_send(message):
            return True  # Not applicable, considered success
        return self.send(message)


class SlackChannel(BaseChannel):
    """Slack webhook notification channel.

    Sends notifications to Slack channels via incoming webhooks.
    Creates rich Block Kit messages with formatting.

    Attributes:
        webhook_url: Slack incoming webhook URL.
        channel: Optional channel override.
        username: Bot display name.
        icon_emoji: Bot icon emoji.
        mention_on_failure: Users to mention on failure events.

    Example:
        >>> slack = SlackChannel(
        ...     name="alerts",
        ...     webhook_url="https://hooks.slack.com/services/...",
        ...     mention_on_failure=["<@U12345>", "<!channel>"]
        ... )
        >>> slack.send(message)
    """

    def __init__(
        self,
        webhook_url: str,
        name: str = "slack",
        channel: str | None = None,
        username: str = "VenomQA",
        icon_emoji: str = ":test_tube:",
        mention_on_failure: list[str] | None = None,
        enabled: bool = True,
        events: list[NotificationEvent] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize Slack channel.

        Args:
            webhook_url: Slack incoming webhook URL.
            name: Unique identifier for this channel.
            channel: Optional channel override (e.g., "#alerts").
            username: Bot display name in Slack.
            icon_emoji: Bot icon emoji (e.g., ":robot_face:").
            mention_on_failure: List of user/group mentions for failures.
            enabled: Whether notifications should be sent.
            events: List of events to handle.
            timeout: Request timeout in seconds.
        """
        super().__init__(name, enabled, events, timeout)
        self.webhook_url = webhook_url
        self.channel = channel
        self.username = username
        self.icon_emoji = icon_emoji
        self.mention_on_failure = mention_on_failure or []

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.SLACK

    def send(self, message: NotificationMessage) -> bool:
        """Send a notification to Slack.

        Args:
            message: The notification message to send.

        Returns:
            True if sent successfully (HTTP 200), False otherwise.
        """
        payload = self._build_payload(message)
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                success = response.status == 200
                if success:
                    logger.info(f"Slack notification sent to channel '{self.name}'")
                return success
        except urllib.error.URLError as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Slack notification: {e}")
            return False

    def _build_payload(self, message: NotificationMessage) -> dict[str, Any]:
        """Build Slack webhook payload with Block Kit formatting."""
        color = self._get_color(message)
        emoji = self._get_emoji(message)

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {message.title}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message.body,
                },
            },
        ]

        # Add context fields
        context_elements = []
        if message.journey_name:
            context_elements.append({
                "type": "mrkdwn",
                "text": f"*Journey:* {message.journey_name}",
            })
        if message.step_name:
            context_elements.append({
                "type": "mrkdwn",
                "text": f"*Step:* {message.step_name}",
            })
        if message.path_name:
            context_elements.append({
                "type": "mrkdwn",
                "text": f"*Path:* {message.path_name}",
            })

        if context_elements:
            blocks.append({
                "type": "context",
                "elements": context_elements,
            })

        # Add error details if present
        if message.error:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n```{message.error[:1000]}```",
                },
            })

        # Add report link
        if message.report_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Report"},
                        "url": message.report_url,
                        "style": "primary",
                    }
                ],
            })

        # Add quick actions
        if message.quick_actions:
            action_elements = []
            for action in message.quick_actions[:5]:  # Max 5 buttons
                action_elements.append({
                    "type": "button",
                    "text": {"type": "plain_text", "text": action.get("label", "Action")},
                    "url": action.get("url", "#"),
                })
            if action_elements:
                blocks.append({"type": "actions", "elements": action_elements})

        # Add mentions for failure events
        mention_text = ""
        if message.event == NotificationEvent.FAILURE and self.mention_on_failure:
            mention_text = " ".join(self.mention_on_failure)
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f":bell: {mention_text}"},
            })

        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f":clock1: {message.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                }
            ],
        })

        payload: dict[str, Any] = {
            "username": self.username,
            "icon_emoji": self.icon_emoji,
            "attachments": [
                {
                    "color": color,
                    "blocks": blocks,
                }
            ],
        }

        if self.channel:
            payload["channel"] = self.channel

        return payload

    def _get_color(self, message: NotificationMessage) -> str:
        """Get attachment color based on event/severity."""
        if message.event == NotificationEvent.RECOVERY:
            return "good"  # Green
        if message.event == NotificationEvent.FAILURE:
            return "danger"  # Red
        if message.severity == "critical":
            return "danger"
        if message.severity == "high":
            return "#FF6B6B"  # Light red
        if message.severity == "medium":
            return "warning"  # Yellow
        return "#36C5F0"  # Slack blue

    def _get_emoji(self, message: NotificationMessage) -> str:
        """Get emoji based on event type."""
        emoji_map = {
            NotificationEvent.FAILURE: ":x:",
            NotificationEvent.RECOVERY: ":white_check_mark:",
            NotificationEvent.WARNING: ":warning:",
            NotificationEvent.PERFORMANCE: ":stopwatch:",
            NotificationEvent.INVARIANT_VIOLATION: ":rotating_light:",
            NotificationEvent.INFO: ":information_source:",
        }
        return emoji_map.get(message.event, ":bell:")


class DiscordChannel(BaseChannel):
    """Discord webhook notification channel.

    Sends notifications to Discord channels via webhooks.
    Creates rich embed messages with color coding.

    Example:
        >>> discord = DiscordChannel(
        ...     name="alerts",
        ...     webhook_url="https://discord.com/api/webhooks/..."
        ... )
        >>> discord.send(message)
    """

    def __init__(
        self,
        webhook_url: str,
        name: str = "discord",
        username: str = "VenomQA",
        avatar_url: str | None = None,
        mention_on_failure: list[str] | None = None,
        enabled: bool = True,
        events: list[NotificationEvent] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize Discord channel.

        Args:
            webhook_url: Discord webhook URL.
            name: Unique identifier for this channel.
            username: Bot display name.
            avatar_url: URL for bot avatar image.
            mention_on_failure: List of user/role mentions for failures.
            enabled: Whether notifications should be sent.
            events: List of events to handle.
            timeout: Request timeout in seconds.
        """
        super().__init__(name, enabled, events, timeout)
        self.webhook_url = webhook_url
        self.username = username
        self.avatar_url = avatar_url
        self.mention_on_failure = mention_on_failure or []

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.DISCORD

    def send(self, message: NotificationMessage) -> bool:
        """Send a notification to Discord.

        Args:
            message: The notification message to send.

        Returns:
            True if sent successfully (HTTP 204), False otherwise.
        """
        payload = self._build_payload(message)
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                success = response.status == 204
                if success:
                    logger.info(f"Discord notification sent to channel '{self.name}'")
                return success
        except urllib.error.URLError as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Discord notification: {e}")
            return False

    def _build_payload(self, message: NotificationMessage) -> dict[str, Any]:
        """Build Discord webhook payload with embed."""
        color = self._get_color(message)
        emoji = self._get_emoji(message)

        fields = []
        if message.journey_name:
            fields.append({
                "name": "Journey",
                "value": message.journey_name,
                "inline": True,
            })
        if message.step_name:
            fields.append({
                "name": "Step",
                "value": message.step_name,
                "inline": True,
            })
        if message.path_name:
            fields.append({
                "name": "Path",
                "value": message.path_name,
                "inline": True,
            })
        if message.error:
            error_text = message.error[:1000]
            fields.append({
                "name": "Error",
                "value": f"```{error_text}```",
                "inline": False,
            })
        if message.report_url:
            fields.append({
                "name": "Report",
                "value": f"[View Full Report]({message.report_url})",
                "inline": False,
            })

        embed = {
            "title": f"{emoji} {message.title}",
            "description": message.body,
            "color": color,
            "fields": fields,
            "timestamp": message.timestamp.isoformat(),
            "footer": {"text": "VenomQA Notification"},
        }

        payload: dict[str, Any] = {
            "username": self.username,
            "embeds": [embed],
        }

        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url

        # Add mentions for failure events
        if message.event == NotificationEvent.FAILURE and self.mention_on_failure:
            payload["content"] = " ".join(self.mention_on_failure)

        return payload

    def _get_color(self, message: NotificationMessage) -> int:
        """Get embed color based on event/severity."""
        if message.event == NotificationEvent.RECOVERY:
            return 5763719  # Green
        if message.event == NotificationEvent.FAILURE:
            return 15548997  # Red
        if message.severity == "critical":
            return 15548997
        if message.severity == "high":
            return 16744576  # Orange
        if message.severity == "medium":
            return 16776960  # Yellow
        return 3447003  # Blue

    def _get_emoji(self, message: NotificationMessage) -> str:
        """Get emoji based on event type."""
        emoji_map = {
            NotificationEvent.FAILURE: "X",
            NotificationEvent.RECOVERY: "CHECK",
            NotificationEvent.WARNING: "WARNING",
            NotificationEvent.PERFORMANCE: "STOPWATCH",
            NotificationEvent.INVARIANT_VIOLATION: "SIREN",
            NotificationEvent.INFO: "INFO",
        }
        return emoji_map.get(message.event, "BELL")


class EmailChannel(BaseChannel):
    """Email notification channel via SMTP.

    Sends notifications as HTML emails via SMTP.
    Supports TLS/SSL encryption.

    Example:
        >>> email = EmailChannel(
        ...     name="email-alerts",
        ...     smtp_host="smtp.gmail.com",
        ...     smtp_port=587,
        ...     username="alerts@example.com",
        ...     password="app-password",
        ...     from_addr="alerts@example.com",
        ...     to_addrs=["team@example.com"]
        ... )
        >>> email.send(message)
    """

    def __init__(
        self,
        smtp_host: str,
        from_addr: str,
        to_addrs: list[str],
        name: str = "email",
        smtp_port: int = 587,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        use_ssl: bool = False,
        enabled: bool = True,
        events: list[NotificationEvent] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize Email channel.

        Args:
            smtp_host: SMTP server hostname.
            from_addr: Sender email address.
            to_addrs: List of recipient email addresses.
            name: Unique identifier for this channel.
            smtp_port: SMTP server port (default 587 for TLS).
            username: SMTP authentication username.
            password: SMTP authentication password.
            use_tls: Use STARTTLS encryption.
            use_ssl: Use SSL/TLS encryption (port 465).
            enabled: Whether notifications should be sent.
            events: List of events to handle.
            timeout: Connection timeout in seconds.
        """
        super().__init__(name, enabled, events, timeout)
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.use_tls = use_tls
        self.use_ssl = use_ssl

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.EMAIL

    def send(self, message: NotificationMessage) -> bool:
        """Send a notification via email.

        Args:
            message: The notification message to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        try:
            msg = self._build_message(message)

            context = ssl.create_default_context() if (self.use_tls or self.use_ssl) else None

            if self.use_ssl:
                server = smtplib.SMTP_SSL(
                    self.smtp_host,
                    self.smtp_port,
                    context=context,
                    timeout=self.timeout,
                )
            else:
                server = smtplib.SMTP(
                    self.smtp_host,
                    self.smtp_port,
                    timeout=self.timeout,
                )
                if self.use_tls and context:
                    server.starttls(context=context)

            try:
                if self.username and self.password:
                    server.login(self.username, self.password)

                server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
                logger.info(f"Email notification sent via channel '{self.name}'")
                return True
            finally:
                server.quit()

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False

    def _build_message(self, message: NotificationMessage) -> MIMEMultipart:
        """Build email message with HTML body."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[VenomQA] {message.title}"
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)

        # Plain text version
        text_body = self._build_text_body(message)
        msg.attach(MIMEText(text_body, "plain"))

        # HTML version
        html_body = self._build_html_body(message)
        msg.attach(MIMEText(html_body, "html"))

        return msg

    def _build_text_body(self, message: NotificationMessage) -> str:
        """Build plain text email body."""
        lines = [
            message.title,
            "=" * len(message.title),
            "",
            message.body,
            "",
        ]

        if message.journey_name:
            lines.append(f"Journey: {message.journey_name}")
        if message.step_name:
            lines.append(f"Step: {message.step_name}")
        if message.path_name:
            lines.append(f"Path: {message.path_name}")
        if message.error:
            lines.extend(["", "Error:", message.error])
        if message.report_url:
            lines.extend(["", f"Report: {message.report_url}"])

        lines.extend(["", f"Time: {message.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"])

        return "\n".join(lines)

    def _build_html_body(self, message: NotificationMessage) -> str:
        """Build HTML email body."""
        color = self._get_color(message)

        details_html = ""
        if message.journey_name:
            details_html += f"<p><strong>Journey:</strong> {message.journey_name}</p>"
        if message.step_name:
            details_html += f"<p><strong>Step:</strong> {message.step_name}</p>"
        if message.path_name:
            details_html += f"<p><strong>Path:</strong> {message.path_name}</p>"
        if message.error:
            error_escaped = message.error.replace("<", "&lt;").replace(">", "&gt;")
            details_html += f"<p><strong>Error:</strong></p><pre style='background:#f5f5f5;padding:10px;border-radius:4px;overflow:auto;'>{error_escaped}</pre>"

        report_html = ""
        if message.report_url:
            report_html = f"""
            <p style="margin-top:20px;">
                <a href="{message.report_url}"
                   style="background:{color};color:white;padding:10px 20px;
                          text-decoration:none;border-radius:4px;">
                    View Full Report
                </a>
            </p>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ background: {color}; color: white; padding: 20px; }}
                .content {{ padding: 20px; }}
                .footer {{ padding: 15px 20px; background: #f9f9f9; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin:0;font-size:24px;">{message.title}</h1>
                </div>
                <div class="content">
                    <p>{message.body}</p>
                    {details_html}
                    {report_html}
                </div>
                <div class="footer">
                    <p>VenomQA Notification - {message.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                </div>
            </div>
        </body>
        </html>
        """

    def _get_color(self, message: NotificationMessage) -> str:
        """Get color based on event/severity."""
        if message.event == NotificationEvent.RECOVERY:
            return "#22c55e"  # Green
        if message.event == NotificationEvent.FAILURE:
            return "#ef4444"  # Red
        if message.severity == "critical":
            return "#ef4444"
        if message.severity == "high":
            return "#f97316"  # Orange
        if message.severity == "medium":
            return "#eab308"  # Yellow
        return "#3b82f6"  # Blue


class PagerDutyChannel(BaseChannel):
    """PagerDuty notification channel via Events API v2.

    Sends notifications to PagerDuty for incident management.
    Supports triggering, acknowledging, and resolving incidents.

    Example:
        >>> pagerduty = PagerDutyChannel(
        ...     name="oncall",
        ...     routing_key="your-integration-key",
        ...     service_name="VenomQA Tests"
        ... )
        >>> pagerduty.send(message)
    """

    EVENTS_API_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(
        self,
        routing_key: str,
        name: str = "pagerduty",
        service_name: str = "VenomQA",
        enabled: bool = True,
        events: list[NotificationEvent] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize PagerDuty channel.

        Args:
            routing_key: PagerDuty integration/routing key.
            name: Unique identifier for this channel.
            service_name: Service name shown in PagerDuty.
            enabled: Whether notifications should be sent.
            events: List of events to handle.
            timeout: Request timeout in seconds.
        """
        super().__init__(name, enabled, events, timeout)
        self.routing_key = routing_key
        self.service_name = service_name
        # Track dedup keys for recovery correlation
        self._active_incidents: dict[str, str] = {}

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.PAGERDUTY

    def send(self, message: NotificationMessage) -> bool:
        """Send a notification to PagerDuty.

        Args:
            message: The notification message to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        payload = self._build_payload(message)
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self.EVENTS_API_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                success = response.status == 202
                if success:
                    logger.info(f"PagerDuty notification sent via channel '{self.name}'")
                return success
        except urllib.error.URLError as e:
            logger.error(f"Failed to send PagerDuty notification: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending PagerDuty notification: {e}")
            return False

    def _build_payload(self, message: NotificationMessage) -> dict[str, Any]:
        """Build PagerDuty Events API v2 payload."""
        # Determine event action based on notification event
        event_action = "trigger"
        if message.event == NotificationEvent.RECOVERY:
            event_action = "resolve"

        # Generate dedup key for incident correlation
        dedup_key = self._generate_dedup_key(message)

        severity = self._map_severity(message.severity)

        custom_details: dict[str, Any] = {
            "event_type": message.event.value,
            "timestamp": message.timestamp.isoformat(),
        }
        if message.journey_name:
            custom_details["journey"] = message.journey_name
        if message.step_name:
            custom_details["step"] = message.step_name
        if message.path_name:
            custom_details["path"] = message.path_name
        if message.error:
            custom_details["error"] = message.error[:2000]
        if message.metadata:
            custom_details["metadata"] = message.metadata

        payload: dict[str, Any] = {
            "routing_key": self.routing_key,
            "event_action": event_action,
            "dedup_key": dedup_key,
            "payload": {
                "summary": message.title[:1024],
                "severity": severity,
                "source": self.service_name,
                "component": message.journey_name or "VenomQA",
                "group": message.path_name or "main",
                "custom_details": custom_details,
            },
        }

        if message.report_url:
            payload["links"] = [
                {
                    "href": message.report_url,
                    "text": "View Test Report",
                }
            ]

        return payload

    def _generate_dedup_key(self, message: NotificationMessage) -> str:
        """Generate a dedup key for incident correlation."""
        parts = ["venomqa"]
        if message.journey_name:
            parts.append(message.journey_name)
        if message.step_name:
            parts.append(message.step_name)
        if message.path_name:
            parts.append(message.path_name)
        return "-".join(parts)

    def _map_severity(self, severity: str) -> str:
        """Map VenomQA severity to PagerDuty severity."""
        severity_map = {
            "critical": "critical",
            "high": "error",
            "medium": "warning",
            "low": "info",
            "info": "info",
        }
        return severity_map.get(severity.lower(), "warning")


class CustomWebhookChannel(BaseChannel):
    """Custom webhook notification channel.

    Sends notifications to any HTTP endpoint.
    Supports customizable headers, payload templates, and HTTP methods.

    Example:
        >>> webhook = CustomWebhookChannel(
        ...     name="custom",
        ...     webhook_url="https://api.example.com/notifications",
        ...     headers={"Authorization": "Bearer token123"}
        ... )
        >>> webhook.send(message)
    """

    def __init__(
        self,
        webhook_url: str,
        name: str = "webhook",
        method: str = "POST",
        headers: dict[str, str] | None = None,
        payload_template: dict[str, Any] | None = None,
        enabled: bool = True,
        events: list[NotificationEvent] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize custom webhook channel.

        Args:
            webhook_url: Target webhook URL.
            name: Unique identifier for this channel.
            method: HTTP method (POST, PUT, PATCH).
            headers: Additional HTTP headers.
            payload_template: Custom payload template. Message fields are merged.
            enabled: Whether notifications should be sent.
            events: List of events to handle.
            timeout: Request timeout in seconds.
        """
        super().__init__(name, enabled, events, timeout)
        self.webhook_url = webhook_url
        self.method = method.upper()
        self.headers = headers or {}
        self.payload_template = payload_template or {}

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.WEBHOOK

    def send(self, message: NotificationMessage) -> bool:
        """Send a notification via custom webhook.

        Args:
            message: The notification message to send.

        Returns:
            True if sent successfully (2xx status), False otherwise.
        """
        payload = self._build_payload(message)
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            **self.headers,
        }

        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers=headers,
            method=self.method,
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                success = 200 <= response.status < 300
                if success:
                    logger.info(f"Webhook notification sent to '{self.name}'")
                return success
        except urllib.error.URLError as e:
            logger.error(f"Failed to send webhook notification: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending webhook notification: {e}")
            return False

    def _build_payload(self, message: NotificationMessage) -> dict[str, Any]:
        """Build webhook payload from template and message."""
        # Start with template
        payload = dict(self.payload_template)

        # Add message data
        payload.update({
            "venomqa": {
                "title": message.title,
                "body": message.body,
                "event": message.event.value,
                "severity": message.severity,
                "journey_name": message.journey_name,
                "step_name": message.step_name,
                "path_name": message.path_name,
                "error": message.error,
                "report_url": message.report_url,
                "timestamp": message.timestamp.isoformat(),
                "metadata": message.metadata,
            }
        })

        return payload


def create_channel(config: dict[str, Any]) -> BaseChannel:
    """Factory function to create a channel from configuration.

    Args:
        config: Channel configuration dictionary with 'type' key.

    Returns:
        Configured channel instance.

    Raises:
        ValueError: If channel type is unknown.

    Example:
        >>> config = {
        ...     "type": "slack",
        ...     "name": "alerts",
        ...     "webhook_url": "https://hooks.slack.com/...",
        ...     "on": ["failure", "recovery"]
        ... }
        >>> channel = create_channel(config)
    """
    channel_type = config.get("type", "").lower()

    # Parse events
    events = None
    if "on" in config:
        events = [NotificationEvent(e) for e in config["on"]]

    if channel_type == "slack":
        return SlackChannel(
            webhook_url=config["webhook_url"],
            name=config.get("name", "slack"),
            channel=config.get("channel"),
            username=config.get("username", "VenomQA"),
            icon_emoji=config.get("icon_emoji", ":test_tube:"),
            mention_on_failure=config.get("mention_on_failure"),
            enabled=config.get("enabled", True),
            events=events,
            timeout=config.get("timeout", 30.0),
        )

    if channel_type == "discord":
        return DiscordChannel(
            webhook_url=config["webhook_url"],
            name=config.get("name", "discord"),
            username=config.get("username", "VenomQA"),
            avatar_url=config.get("avatar_url"),
            mention_on_failure=config.get("mention_on_failure"),
            enabled=config.get("enabled", True),
            events=events,
            timeout=config.get("timeout", 30.0),
        )

    if channel_type == "email":
        return EmailChannel(
            smtp_host=config["smtp_host"],
            from_addr=config["from"],
            to_addrs=config["to"] if isinstance(config["to"], list) else [config["to"]],
            name=config.get("name", "email"),
            smtp_port=config.get("smtp_port", 587),
            username=config.get("username"),
            password=config.get("password"),
            use_tls=config.get("use_tls", True),
            use_ssl=config.get("use_ssl", False),
            enabled=config.get("enabled", True),
            events=events,
            timeout=config.get("timeout", 30.0),
        )

    if channel_type == "pagerduty":
        return PagerDutyChannel(
            routing_key=config["routing_key"],
            name=config.get("name", "pagerduty"),
            service_name=config.get("service_name", "VenomQA"),
            enabled=config.get("enabled", True),
            events=events,
            timeout=config.get("timeout", 30.0),
        )

    if channel_type == "webhook":
        return CustomWebhookChannel(
            webhook_url=config["webhook_url"],
            name=config.get("name", "webhook"),
            method=config.get("method", "POST"),
            headers=config.get("headers"),
            payload_template=config.get("payload_template"),
            enabled=config.get("enabled", True),
            events=events,
            timeout=config.get("timeout", 30.0),
        )

    raise ValueError(f"Unknown channel type: {channel_type}")
