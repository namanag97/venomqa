"""Slack notification plugin for VenomQA.

This plugin sends notifications to Slack on test events:
- Journey start/completion
- Test failures
- Summary reports

Configuration:
    ```yaml
    plugins:
      - name: venomqa.plugins.examples.slack_notifier
        config:
          webhook_url: https://hooks.slack.com/services/T00/B00/XXX
          channel: "#qa-alerts"
          notify_on_success: false
          notify_on_failure: true
          mention_on_failure: "@qa-team"
    ```

Example:
    >>> from venomqa.plugins.examples import SlackNotifierPlugin
    >>>
    >>> plugin = SlackNotifierPlugin()
    >>> plugin.on_load({
    ...     "webhook_url": "https://hooks.slack.com/...",
    ...     "channel": "#testing",
    ... })
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.request import Request, urlopen
from urllib.error import URLError

from venomqa.plugins.base import HookPlugin
from venomqa.plugins.types import (
    FailureContext,
    HookPriority,
    JourneyContext,
    PluginType,
)

if TYPE_CHECKING:
    from venomqa.core.models import Journey, JourneyResult

logger = logging.getLogger(__name__)


class SlackNotifierPlugin(HookPlugin):
    """Send Slack notifications on test events.

    This plugin integrates with Slack via incoming webhooks to send
    notifications about test execution events.

    Configuration Options:
        webhook_url: Slack webhook URL (required)
        channel: Override channel (optional)
        username: Bot username (default: "VenomQA")
        icon_emoji: Bot icon (default: ":robot_face:")
        notify_on_success: Send on success (default: False)
        notify_on_failure: Send on failure (default: True)
        notify_on_start: Send on journey start (default: False)
        mention_on_failure: User/group to mention (optional)
        include_details: Include step details (default: True)
    """

    name = "slack-notifier"
    version = "1.0.0"
    plugin_type = PluginType.HOOK
    description = "Send Slack notifications on test events"
    author = "VenomQA Team"
    priority = HookPriority.LOW  # Run after other plugins

    def __init__(self) -> None:
        super().__init__()
        self.webhook_url: str = ""
        self.channel: str | None = None
        self.username: str = "VenomQA"
        self.icon_emoji: str = ":robot_face:"
        self.notify_on_success: bool = False
        self.notify_on_failure: bool = True
        self.notify_on_start: bool = False
        self.mention_on_failure: str | None = None
        self.include_details: bool = True

    def on_load(self, config: dict[str, Any]) -> None:
        """Load plugin configuration.

        Args:
            config: Plugin configuration from venomqa.yaml

        Raises:
            ValueError: If webhook_url is not provided
        """
        super().on_load(config)

        self.webhook_url = config.get("webhook_url", "")
        if not self.webhook_url:
            raise ValueError("Slack webhook_url is required")

        self.channel = config.get("channel")
        self.username = config.get("username", "VenomQA")
        self.icon_emoji = config.get("icon_emoji", ":robot_face:")
        self.notify_on_success = config.get("notify_on_success", False)
        self.notify_on_failure = config.get("notify_on_failure", True)
        self.notify_on_start = config.get("notify_on_start", False)
        self.mention_on_failure = config.get("mention_on_failure")
        self.include_details = config.get("include_details", True)

        self._logger.info(f"Slack notifier configured for channel: {self.channel or 'default'}")

    def on_journey_start(self, context: JourneyContext) -> None:
        """Send notification when journey starts.

        Args:
            context: Journey context
        """
        if not self.notify_on_start:
            return

        journey = context.journey
        message = self._build_start_message(journey)
        self._send_message(message)

    def on_journey_complete(
        self,
        journey: Journey,
        result: JourneyResult,
        context: JourneyContext,
    ) -> None:
        """Send notification when journey completes.

        Args:
            journey: The completed journey
            result: Journey result
            context: Journey context
        """
        if result.success and not self.notify_on_success:
            return

        if not result.success and not self.notify_on_failure:
            return

        message = self._build_completion_message(journey, result)
        self._send_message(message)

    def on_failure(self, context: FailureContext) -> None:
        """Send immediate notification on failure.

        Args:
            context: Failure context
        """
        if not self.notify_on_failure:
            return

        # Don't send immediate failure notifications if we'll send
        # a completion notification (to avoid duplicates)
        # This hook is useful for immediate alerts in long-running journeys
        pass

    def _build_start_message(self, journey: Any) -> dict[str, Any]:
        """Build Slack message for journey start.

        Args:
            journey: The journey object

        Returns:
            Slack message payload
        """
        return {
            "text": f":arrow_forward: Starting journey: *{journey.name}*",
            "attachments": [
                {
                    "color": "#36a64f",
                    "fields": [
                        {
                            "title": "Journey",
                            "value": journey.name,
                            "short": True,
                        },
                        {
                            "title": "Description",
                            "value": journey.description or "No description",
                            "short": True,
                        },
                    ],
                    "footer": "VenomQA",
                    "ts": int(datetime.now().timestamp()),
                }
            ],
        }

    def _build_completion_message(
        self,
        journey: Any,
        result: Any,
    ) -> dict[str, Any]:
        """Build Slack message for journey completion.

        Args:
            journey: The journey object
            result: Journey result

        Returns:
            Slack message payload
        """
        if result.success:
            color = "#36a64f"  # Green
            emoji = ":white_check_mark:"
            status = "PASSED"
        else:
            color = "#ff0000"  # Red
            emoji = ":x:"
            status = "FAILED"

        # Build mention text
        mention = ""
        if not result.success and self.mention_on_failure:
            mention = f" {self.mention_on_failure}"

        text = f"{emoji} Journey *{journey.name}* {status}{mention}"

        # Build fields
        fields = [
            {
                "title": "Status",
                "value": status,
                "short": True,
            },
            {
                "title": "Duration",
                "value": f"{result.duration_ms / 1000:.2f}s",
                "short": True,
            },
            {
                "title": "Steps",
                "value": f"{result.passed_steps}/{result.total_steps} passed",
                "short": True,
            },
        ]

        if result.total_paths > 0:
            fields.append({
                "title": "Paths",
                "value": f"{result.passed_paths}/{result.total_paths} passed",
                "short": True,
            })

        if result.issues and self.include_details:
            issue_summary = "\n".join(
                f"- {issue.step}: {issue.error[:50]}..."
                for issue in result.issues[:3]
            )
            if len(result.issues) > 3:
                issue_summary += f"\n... and {len(result.issues) - 3} more"

            fields.append({
                "title": "Issues",
                "value": issue_summary,
                "short": False,
            })

        return {
            "text": text,
            "attachments": [
                {
                    "color": color,
                    "fields": fields,
                    "footer": "VenomQA",
                    "ts": int(datetime.now().timestamp()),
                }
            ],
        }

    def _send_message(self, message: dict[str, Any]) -> bool:
        """Send message to Slack webhook.

        Args:
            message: Slack message payload

        Returns:
            True if message was sent successfully
        """
        # Add channel override if configured
        if self.channel:
            message["channel"] = self.channel
        message["username"] = self.username
        message["icon_emoji"] = self.icon_emoji

        try:
            data = json.dumps(message).encode("utf-8")
            request = Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )

            with urlopen(request, timeout=10) as response:
                if response.status == 200:
                    self._logger.debug("Slack message sent successfully")
                    return True
                else:
                    self._logger.warning(f"Slack responded with status {response.status}")
                    return False

        except URLError as e:
            self._logger.error(f"Failed to send Slack message: {e}")
            return False
        except Exception as e:
            self._logger.error(f"Unexpected error sending Slack message: {e}")
            return False


# Allow direct import as plugin
Plugin = SlackNotifierPlugin
plugin = SlackNotifierPlugin()
