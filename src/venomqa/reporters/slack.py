"""Slack webhook reporter for notifications.

Sends test results to Slack channels via incoming webhooks. Creates
rich, formatted messages with Block Kit components including headers,
summary statistics, and issue details.

Example:
    >>> from venomqa.reporters import SlackReporter
    >>> reporter = SlackReporter(
    ...     webhook_url="https://hooks.slack.com/services/...",
    ...     channel="#test-results",
    ...     mention_on_failure=["@team-lead"]
    ... )
    >>> reporter.send(results)
    True
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from venomqa.core.models import JourneyResult, Severity
from venomqa.reporters.base import BaseReporter


class SlackReporter(BaseReporter):
    """Send test results to Slack via incoming webhook.

    Creates rich Slack messages with:
    - Header with pass/fail status
    - Summary statistics in fields
    - Issue breakdown by severity
    - Critical/high issue details
    - Optional link to full report
    - User mentions on failure

    Attributes:
        output_path: Optional default path for saving reports.
        webhook_url: Slack incoming webhook URL.
        channel: Optional channel override (e.g., "#test-results").
        username: Bot display name (default: "VenomQA").
        report_url: Optional link to full HTML report.
        mention_on_failure: List of user IDs to mention on failure.

    Example:
        >>> reporter = SlackReporter(
        ...     webhook_url="https://hooks.slack.com/services/T00/B00/XXX",
        ...     report_url="https://ci.example.com/reports/test.html"
        ... )
        >>> reporter.send(results)
    """

    @property
    def file_extension(self) -> str:
        """Return the JSON file extension for saved payloads."""
        return ".json"

    def __init__(
        self,
        webhook_url: str,
        output_path: str | Path | None = None,
        channel: str | None = None,
        username: str = "VenomQA",
        report_url: str | None = None,
        mention_on_failure: list[str] | None = None,
    ) -> None:
        """Initialize the Slack reporter.

        Args:
            webhook_url: Slack incoming webhook URL. Required.
            output_path: Default path for saving webhook payloads.
            channel: Optional channel to send to (overrides webhook default).
            username: Bot display name in Slack.
            report_url: Optional URL to full HTML report.
            mention_on_failure: List of Slack user IDs/groups to mention on failure.
                               Use format like "<@U12345>" or "<!here>".
        """
        super().__init__(output_path)
        self.webhook_url = webhook_url
        self.channel = channel
        self.username = username
        self.report_url = report_url
        self.mention_on_failure = mention_on_failure or []

    def generate(self, results: list[JourneyResult]) -> dict[str, Any]:
        """Generate the Slack webhook payload.

        Args:
            results: List of JourneyResult objects from test execution.

        Returns:
            Dictionary containing the Slack webhook payload.
        """
        return self._build_payload(results)

    def send(self, results: list[JourneyResult]) -> bool:
        """Send test results to Slack via webhook.

        Args:
            results: List of JourneyResult objects from test execution.

        Returns:
            True if message was sent successfully, False otherwise.
        """
        payload = self.generate(results)
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status == 200
        except urllib.error.URLError:
            return False

    def save(self, results: list[JourneyResult], path: str | Path | None = None) -> Path:
        """Save the webhook payload to a JSON file.

        Useful for debugging or manual inspection of payloads.

        Args:
            results: List of JourneyResult objects.
            path: Optional path to save payload. Auto-generates if not provided.

        Returns:
            Path to the saved payload file.
        """
        output_path = Path(path) if path else self.output_path
        if not output_path:
            output_path = Path(f"slack_payload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

        payload = self.generate(results)
        content = json.dumps(payload, indent=2)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path

    def _build_payload(self, results: list[JourneyResult]) -> dict[str, Any]:
        """Build the complete Slack webhook payload.

        Constructs a Block Kit message with header, summary, issues,
        and optional link/mention sections.

        Args:
            results: List of JourneyResult objects.

        Returns:
            Dictionary containing the complete webhook payload.
        """
        summary = self._calculate_summary(results)
        color = "good" if summary["failed_journeys"] == 0 else "danger"
        status_emoji = ":white_check_mark:" if summary["failed_journeys"] == 0 else ":x:"
        status_text = "PASSED" if summary["failed_journeys"] == 0 else "FAILED"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} VenomQA Test Report: {status_text}",
                },
            },
            {"type": "divider"},
            self._build_summary_block(summary),
            self._build_stats_block(summary),
        ]

        if summary["total_issues"] > 0:
            blocks.append(self._build_issues_block(results, summary))

        if self.report_url:
            blocks.append(self._build_link_block())

        if summary["failed_journeys"] > 0 and self.mention_on_failure:
            blocks.append(self._build_mention_block())

        payload: dict[str, Any] = {
            "username": self.username,
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

    def _calculate_summary(self, results: list[JourneyResult]) -> dict[str, Any]:
        """Calculate aggregate statistics from journey results.

        Args:
            results: List of JourneyResult objects.

        Returns:
            Dictionary containing summary statistics.
        """
        total = len(results)
        passed = sum(1 for r in results if r.success)
        total_steps = sum(r.total_steps for r in results)
        passed_steps = sum(r.passed_steps for r in results)
        total_issues = sum(len(r.issues) for r in results)
        total_duration_ms = sum(r.duration_ms for r in results)

        severity_counts = {s.value: 0 for s in Severity}
        for r in results:
            for issue in r.issues:
                severity_counts[issue.severity.value] += 1

        return {
            "total_journeys": total,
            "passed_journeys": passed,
            "failed_journeys": total - passed,
            "total_steps": total_steps,
            "passed_steps": passed_steps,
            "total_issues": total_issues,
            "total_duration_ms": total_duration_ms,
            "severity_counts": severity_counts,
        }

    def _build_summary_block(self, summary: dict[str, Any]) -> dict[str, Any]:
        """Build the summary section block.

        Creates a section with timestamp, duration, journey count,
        and step count in a two-column layout.

        Args:
            summary: Pre-calculated summary statistics.

        Returns:
            Slack Block Kit section block.
        """
        duration_sec = summary["total_duration_ms"] / 1000
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Timestamp:*\n{timestamp}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Duration:*\n{duration_sec:.2f}s",
                },
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*Journeys:*\n"
                        f"{summary['passed_journeys']}/{summary['total_journeys']} passed"
                    ),
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Steps:*\n{summary['passed_steps']}/{summary['total_steps']} passed",
                },
            ],
        }

    def _build_stats_block(self, summary: dict[str, Any]) -> dict[str, Any]:
        """Build the issue statistics block.

        Shows either a success message or a breakdown of issues by severity.

        Args:
            summary: Pre-calculated summary statistics.

        Returns:
            Slack Block Kit section block.
        """
        if summary["total_issues"] == 0:
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":white_check_mark: *No issues found*",
                },
            }

        severity = summary["severity_counts"]
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":warning: *{summary['total_issues']} issues found*\n"
                    f"• Critical: {severity.get('critical', 0)}\n"
                    f"• High: {severity.get('high', 0)}\n"
                    f"• Medium: {severity.get('medium', 0)}\n"
                    f"• Low: {severity.get('low', 0)}"
                ),
            },
        }

    def _build_issues_block(
        self, results: list[JourneyResult], summary: dict[str, Any]
    ) -> dict[str, Any]:
        """Build the critical/high issues details block.

        Shows details of up to 5 critical or high severity issues.

        Args:
            results: List of JourneyResult objects.
            summary: Pre-calculated summary statistics.

        Returns:
            Slack Block Kit section block.
        """
        critical_high_issues = []
        for r in results:
            for issue in r.issues:
                if issue.severity in (Severity.CRITICAL, Severity.HIGH):
                    critical_high_issues.append(issue)

        if not critical_high_issues:
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_No critical or high severity issues_",
                },
            }

        issue_lines = []
        for issue in critical_high_issues[:5]:
            emoji = ":rotating_light:" if issue.severity == Severity.CRITICAL else ":warning:"
            issue_lines.append(f"{emoji} *{issue.journey}* - {issue.step}: {issue.error[:80]}")

        if len(critical_high_issues) > 5:
            issue_lines.append(f"_...and {len(critical_high_issues) - 5} more_")

        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Critical/High Issues:*\n" + "\n".join(issue_lines),
            },
        }

    def _build_link_block(self) -> dict[str, Any]:
        """Build the report link action block.

        Creates a button linking to the full HTML report.

        Returns:
            Slack Block Kit actions block.
        """
        return {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Full Report",
                    },
                    "url": self.report_url,
                    "style": "primary",
                }
            ],
        }

    def _build_mention_block(self) -> dict[str, Any]:
        """Build the user mention block for failure notifications.

        Mentions specified users/groups when tests fail.

        Returns:
            Slack Block Kit section block with mentions.
        """
        mentions = " ".join(f"<{m}>" for m in self.mention_on_failure)
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":bell: {mentions}",
            },
        }
