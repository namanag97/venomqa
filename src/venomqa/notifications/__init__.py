"""VenomQA Notification and Alerting System.

This module provides a comprehensive notification and alerting system for
VenomQA that supports multiple notification channels and customizable
alert conditions.

Features:
    - Multiple notification channels (Slack, Discord, Email, PagerDuty, Custom Webhook)
    - Configurable alert conditions based on test results
    - Rate limiting to prevent notification spam
    - Alert aggregation for similar issues
    - Recovery notifications when tests pass after failures
    - Message formatting with rich context

Example:
    >>> from venomqa.notifications import NotificationManager, SlackChannel
    >>> from venomqa.notifications import AlertCondition, AlertTrigger
    >>>
    >>> # Create notification channels
    >>> slack = SlackChannel(
    ...     webhook_url="https://hooks.slack.com/services/...",
    ...     name="slack-alerts"
    ... )
    >>>
    >>> # Create alert conditions
    >>> high_failure_rate = AlertCondition(
    ...     name="high_failure_rate",
    ...     trigger=AlertTrigger.FAILURE_RATE,
    ...     threshold=10.0,  # 10%
    ...     channels=["slack-alerts"]
    ... )
    >>>
    >>> # Create notification manager
    >>> manager = NotificationManager(
    ...     channels=[slack],
    ...     alerts=[high_failure_rate]
    ... )
    >>>
    >>> # Send notifications based on results
    >>> manager.process_results(journey_results)

Configuration via YAML:
    notifications:
      channels:
        - type: slack
          webhook_url: ${SLACK_WEBHOOK}
          on: [failure, recovery]
        - type: email
          smtp_host: smtp.example.com
          to: team@example.com
          on: [failure]

      alerts:
        - name: high_failure_rate
          condition: failure_rate > 10%
          channels: [slack, pagerduty]
        - name: slow_response
          condition: p99_latency > 1000ms
          channels: [slack]
"""

from venomqa.notifications.alerts import (
    AlertCondition,
    AlertManager,
    AlertSeverity,
    AlertState,
    AlertTrigger,
    NotificationConfig,
    NotificationManager,
    RateLimiter,
    create_notification_manager_from_config,
)
from venomqa.notifications.channels import (
    BaseChannel,
    ChannelType,
    CustomWebhookChannel,
    DiscordChannel,
    EmailChannel,
    NotificationEvent,
    NotificationMessage,
    PagerDutyChannel,
    SlackChannel,
)

__all__ = [
    # Channel types
    "BaseChannel",
    "ChannelType",
    "SlackChannel",
    "DiscordChannel",
    "EmailChannel",
    "PagerDutyChannel",
    "CustomWebhookChannel",
    # Message types
    "NotificationEvent",
    "NotificationMessage",
    # Alert types
    "AlertCondition",
    "AlertManager",
    "AlertSeverity",
    "AlertState",
    "AlertTrigger",
    # Configuration and management
    "NotificationConfig",
    "NotificationManager",
    "RateLimiter",
    "create_notification_manager_from_config",
]
