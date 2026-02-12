"""Markdown reporter for human-readable test reports."""

from __future__ import annotations

from datetime import datetime

from venomqa.core.models import JourneyResult, Severity
from venomqa.reporters.base import BaseReporter


class MarkdownReporter(BaseReporter):
    """Generate human-readable Markdown reports."""

    @property
    def file_extension(self) -> str:
        return ".md"

    def generate(self, results: list[JourneyResult]) -> str:
        """Generate Markdown report from journey results."""
        sections = [
            self._generate_header(results),
            self._generate_summary(results),
            self._generate_journey_details(results),
            self._generate_issues_section(results),
            self._generate_suggestions_section(results),
        ]
        return "\n\n".join(s for s in sections if s)

    def _generate_header(self, results: list[JourneyResult]) -> str:
        """Generate report header."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total = len(results)
        passed = sum(1 for r in results if r.success)
        status = "PASSED" if passed == total else "FAILED"

        return f"""# VenomQA Test Report

**Generated:** {timestamp}
**Status:** {status}
**Journeys:** {passed}/{total} passed"""

    def _generate_summary(self, results: list[JourneyResult]) -> str:
        """Generate summary statistics."""
        total_steps = sum(r.total_steps for r in results)
        passed_steps = sum(r.passed_steps for r in results)
        total_paths = sum(r.total_paths for r in results)
        passed_paths = sum(r.passed_paths for r in results)
        total_issues = sum(len(r.issues) for r in results)

        total_duration = sum(r.duration_ms for r in results)
        duration_sec = total_duration / 1000

        critical = sum(1 for r in results for i in r.issues if i.severity == Severity.CRITICAL)
        high = sum(1 for r in results for i in r.issues if i.severity == Severity.HIGH)
        medium = sum(1 for r in results for i in r.issues if i.severity == Severity.MEDIUM)
        low = sum(1 for r in results for i in r.issues if i.severity == Severity.LOW)

        return f"""## Summary

| Metric | Value |
|--------|-------|
| Total Duration | {duration_sec:.2f}s |
| Steps | {passed_steps}/{total_steps} passed |
| Paths | {passed_paths}/{total_paths} passed |
| Issues | {total_issues} |

### Issue Breakdown
- **Critical:** {critical}
- **High:** {high}
- **Medium:** {medium}
- **Low:** {low}"""

    def _generate_journey_details(self, results: list[JourneyResult]) -> str:
        """Generate detailed journey results."""
        if not results:
            return ""

        sections = ["## Journey Results\n"]

        for result in results:
            status = "✅" if result.success else "❌"
            duration = result.duration_ms / 1000
            sections.append(f"### {status} {result.journey_name}")
            sections.append(f"**Duration:** {duration:.2f}s")
            sections.append(f"**Steps:** {result.passed_steps}/{result.total_steps}")

            if result.step_results:
                sections.append("\n| Step | Status | Duration |")
                sections.append("|------|--------|----------|")
                for step in result.step_results:
                    step_status = "✅" if step.success else "❌"
                    step_duration = step.duration_ms
                    sections.append(f"| {step.step_name} | {step_status} | {step_duration:.0f}ms |")

            if result.branch_results:
                for branch in result.branch_results:
                    sections.append(f"\n**Branch: {branch.checkpoint_name}**")
                    for path in branch.path_results:
                        path_status = "✅" if path.success else "❌"
                        sections.append(f"- {path_status} {path.path_name}")

            sections.append("")

        return "\n".join(sections)

    def _generate_issues_section(self, results: list[JourneyResult]) -> str:
        """Generate issues section."""
        all_issues = [(r.journey_name, i) for r in results for i in r.issues]

        if not all_issues:
            return ""

        sections = ["## Issues\n"]

        for _journey_name, issue in all_issues:
            severity_emoji = {
                Severity.CRITICAL: "🔴",
                Severity.HIGH: "🟠",
                Severity.MEDIUM: "🟡",
                Severity.LOW: "🔵",
                Severity.INFO: "ℹ️",
            }.get(issue.severity, "⚠️")

            sections.append(
                f"### {severity_emoji} [{issue.severity.value.upper()}] {issue.journey}"
            )
            sections.append(f"**Path:** {issue.path}")
            sections.append(f"**Step:** {issue.step}")
            sections.append(f"**Error:** {issue.error}")

            if issue.request:
                sections.append("\n**Request:**")
                sections.append("```json")
                sections.append(str(issue.request))
                sections.append("```")

            if issue.response:
                sections.append("\n**Response:**")
                sections.append("```json")
                sections.append(str(issue.response))
                sections.append("```")

            sections.append("")

        return "\n".join(sections)

    def _generate_suggestions_section(self, results: list[JourneyResult]) -> str:
        """Generate suggestions section."""
        all_issues = [(r.journey_name, i) for r in results for i in r.issues]

        suggestions = {
            f"- **{journey}/{issue.step}:** {issue.suggestion}"
            for journey, issue in all_issues
            if issue.suggestion
        }

        if not suggestions:
            return ""

        sorted_suggestions = sorted(suggestions)
        return "## Suggestions\n\n" + "\n".join(sorted_suggestions)
