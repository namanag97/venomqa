"""Slack webhook reporter for notifications."""

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
    """Send test results to Slack via webhook."""

    @property
    def file_extension(self) -> str:
        return ".json"

    def __init__(
        self,
        webhook_url: str,
        output_path: str | Path | None = None,
        channel: str | None = None,
        username: str = "VenomQA",
        report_url: str | None = None,
        mention_on_failure: list[str] | None = None,
    ):
        super().__init__(output_path)
        self.webhook_url = webhook_url
        self.channel = channel
        self.username = username
        self.report_url = report_url
        self.mention_on_failure = mention_on_failure or []

    def generate(self, results: list[JourneyResult]) -> dict[str, Any]:
        return self._build_payload(results)

    def send(self, results: list[JourneyResult]) -> bool:
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
        mentions = " ".join(f"<{m}>" for m in self.mention_on_failure)
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":bell: {mentions}",
            },
        }
