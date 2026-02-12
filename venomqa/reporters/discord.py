"""Discord webhook reporter for notifications."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from venomqa.core.models import JourneyResult, Severity
from venomqa.reporters.base import BaseReporter


class DiscordReporter(BaseReporter):
    """Send test results to Discord via webhook."""

    @property
    def file_extension(self) -> str:
        return ".json"

    def __init__(
        self,
        webhook_url: str,
        output_path: str | Path | None = None,
        username: str = "VenomQA",
        avatar_url: str | None = None,
        report_url: str | None = None,
        mention_on_failure: list[str] | None = None,
    ):
        super().__init__(output_path)
        self.webhook_url = webhook_url
        self.username = username
        self.avatar_url = avatar_url
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
                return response.status == 204
        except urllib.error.URLError:
            return False

    def save(self, results: list[JourneyResult], path: str | Path | None = None) -> Path:
        output_path = Path(path) if path else self.output_path
        if not output_path:
            output_path = Path(f"discord_payload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

        payload = self.generate(results)
        content = json.dumps(payload, indent=2)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path

    def _build_payload(self, results: list[JourneyResult]) -> dict[str, Any]:
        summary = self._calculate_summary(results)
        is_success = summary["failed_journeys"] == 0
        color = 5763719 if is_success else 15548997
        status_emoji = "✅" if is_success else "❌"
        status_text = "PASSED" if is_success else "FAILED"

        embeds = [
            {
                "title": f"{status_emoji} VenomQA Test Report: {status_text}",
                "color": color,
                "timestamp": datetime.now().isoformat(),
                "fields": self._build_fields(summary, results),
                "footer": {"text": "VenomQA Test Framework"},
            }
        ]

        if self.report_url:
            embeds[0]["url"] = self.report_url

        payload: dict[str, Any] = {
            "username": self.username,
            "embeds": embeds,
        }

        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url

        content = ""
        if not is_success and self.mention_on_failure:
            content = " ".join(f"<{m}>" for m in self.mention_on_failure)

        if content:
            payload["content"] = content

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

    def _build_fields(
        self, summary: dict[str, Any], results: list[JourneyResult]
    ) -> list[dict[str, Any]]:
        duration_sec = summary["total_duration_ms"] / 1000

        fields = [
            {
                "name": "📊 Summary",
                "value": (
                    f"**Journeys:** {summary['passed_journeys']}/"
                    f"{summary['total_journeys']} passed\n"
                    f"**Steps:** {summary['passed_steps']}/{summary['total_steps']} passed\n"
                    f"**Duration:** {duration_sec:.2f}s"
                ),
                "inline": True,
            }
        ]

        if summary["total_issues"] > 0:
            severity = summary["severity_counts"]
            severity_text = (
                f"**Total:** {summary['total_issues']}\n"
                f"🔴 Critical: {severity.get('critical', 0)}\n"
                f"🟠 High: {severity.get('high', 0)}\n"
                f"🟡 Medium: {severity.get('medium', 0)}\n"
                f"🔵 Low: {severity.get('low', 0)}"
            )
            fields.append(
                {
                    "name": "🚨 Issues",
                    "value": severity_text,
                    "inline": True,
                }
            )
        else:
            fields.append(
                {
                    "name": "✅ Issues",
                    "value": "No issues found!",
                    "inline": True,
                }
            )

        critical_issues = []
        for r in results:
            for issue in r.issues:
                if issue.severity == Severity.CRITICAL:
                    critical_issues.append(issue)

        if critical_issues:
            issue_lines = []
            for issue in critical_issues[:3]:
                truncated_error = (
                    issue.error[:100] + "..." if len(issue.error) > 100 else issue.error
                )
                issue_lines.append(f"• **{issue.journey}/{issue.step}**: {truncated_error}")

            if len(critical_issues) > 3:
                issue_lines.append(f"_...and {len(critical_issues) - 3} more_")

            fields.append(
                {
                    "name": "🔴 Critical Issues",
                    "value": "\n".join(issue_lines),
                    "inline": False,
                }
            )

        if self.report_url:
            fields.append(
                {
                    "name": "🔗 Report Link",
                    "value": f"[View Full Report]({self.report_url})",
                    "inline": False,
                }
            )

        return fields
