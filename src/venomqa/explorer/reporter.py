"""
Exploration Reporter for the VenomQA State Explorer module.

This module provides the ExplorationReporter class which generates
comprehensive reports from exploration results. Reports can be generated
in multiple formats including HTML, JSON, Markdown, and JUnit XML.

Reports include coverage metrics, discovered issues, state graphs,
and actionable recommendations.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from venomqa.explorer.models import (
    ExplorationResult,
    IssueSeverity,
)
from venomqa.explorer.visualizer import GraphVisualizer, OutputFormat


class ReportFormat(str, Enum):
    """Supported report output formats."""

    HTML = "html"  # Rich HTML report with embedded visualizations
    JSON = "json"  # Machine-readable JSON
    MARKDOWN = "markdown"  # Markdown for documentation
    JUNIT = "junit"  # JUnit XML for CI integration
    SARIF = "sarif"  # SARIF for security tooling
    TEXT = "text"  # Plain text summary


class ExplorationReporter:
    """
    Generates comprehensive exploration reports.

    The ExplorationReporter creates detailed reports from exploration
    results, suitable for both human review and automated processing.

    Features:
    - Multiple output formats (HTML, JSON, Markdown, JUnit, SARIF)
    - Embedded state graph visualizations
    - Issue summaries with recommendations
    - Coverage metrics and trends
    - Export to file or string

    Attributes:
        result: The exploration result to report on
        visualizer: Graph visualizer for diagram generation
        options: Report generation options

    Example:
        reporter = ExplorationReporter(result)
        reporter.generate("report.html", ReportFormat.HTML)
        print(f"Report saved with {len(result.issues)} issues")
    """

    def __init__(
        self,
        result: ExplorationResult | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the exploration reporter.

        Args:
            result: The exploration result to report on
            options: Optional report generation options
        """
        self.result = result
        self.options = options or {}
        self.visualizer = GraphVisualizer()

        # Default options
        self._default_options = {
            "include_graph": True,
            "include_issues": True,
            "include_coverage": True,
            "include_recommendations": True,
            "include_raw_data": False,
            "graph_format": OutputFormat.SVG,
            "title": "VenomQA State Exploration Report",
            "theme": "light",
        }

    def set_result(self, result: ExplorationResult) -> None:
        """
        Set the exploration result to report on.

        Args:
            result: The exploration result
        """
        self.result = result
        if result.graph:
            self.visualizer.set_graph(result.graph)
        if result.issues:
            self.visualizer.highlight_issues(result.issues)

    def generate(
        self,
        output_path: str,
        format: ReportFormat = ReportFormat.HTML,
    ) -> str:
        """
        Generate and save a report to a file.

        Args:
            output_path: Path to save the report
            format: Report format to use

        Returns:
            Path to the generated report

        Raises:
            ValueError: If result is not set
        """
        if not self.result:
            raise ValueError("Result is not set. Call set_result() first.")

        output_file = Path(output_path)

        if format == ReportFormat.HTML:
            content = self.generate_html()
            output_file.write_text(content, encoding="utf-8")
        elif format == ReportFormat.JSON:
            content = json.dumps(self.generate_json(), indent=2)
            output_file.write_text(content, encoding="utf-8")
        elif format == ReportFormat.MARKDOWN:
            content = self.generate_markdown()
            output_file.write_text(content, encoding="utf-8")
        elif format == ReportFormat.JUNIT:
            content = self.generate_junit()
            output_file.write_text(content, encoding="utf-8")
        elif format == ReportFormat.SARIF:
            content = json.dumps(self.generate_sarif(), indent=2)
            output_file.write_text(content, encoding="utf-8")
        elif format == ReportFormat.TEXT:
            content = self.generate_text()
            output_file.write_text(content, encoding="utf-8")
        else:
            raise ValueError(f"Unsupported format: {format}")

        return str(output_file.absolute())

    def generate_to_string(
        self,
        format: ReportFormat = ReportFormat.MARKDOWN,
    ) -> str:
        """
        Generate a report as a string.

        Args:
            format: Report format to use

        Returns:
            Report content as string
        """
        if not self.result:
            raise ValueError("Result is not set. Call set_result() first.")

        if format == ReportFormat.HTML:
            return self.generate_html()
        elif format == ReportFormat.JSON:
            return json.dumps(self.generate_json(), indent=2)
        elif format == ReportFormat.MARKDOWN:
            return self.generate_markdown()
        elif format == ReportFormat.JUNIT:
            return self.generate_junit()
        elif format == ReportFormat.SARIF:
            return json.dumps(self.generate_sarif(), indent=2)
        elif format == ReportFormat.TEXT:
            return self.generate_text()
        else:
            raise ValueError(f"Unsupported format: {format}")

    def generate_html(self) -> str:
        """
        Generate an HTML report.

        Returns:
            HTML report content
        """
        if not self.result:
            raise ValueError("Result is not set. Call set_result() first.")

        summary = self._get_summary()
        self._get_issue_summary_by_severity()
        recommendations = self._generate_recommendations()
        title = self.options.get("title", self._default_options["title"])

        # Generate mermaid diagram
        mermaid_diagram = ""
        if self.options.get("include_graph", self._default_options["include_graph"]):
            try:
                mermaid_diagram = self.visualizer.to_mermaid()
            except Exception:
                mermaid_diagram = "<!-- Graph generation failed -->"

        # Generate issues table rows
        issues_html = ""
        if self.options.get("include_issues", self._default_options["include_issues"]):
            for issue in self.result.issues:
                severity_class = f"issue-{issue.severity.value}"
                issues_html += f"""
                <tr class="{severity_class}">
                    <td><span class="severity-badge {severity_class}">{issue.severity.value.upper()}</span></td>
                    <td>{self._escape_html(issue.state or 'N/A')}</td>
                    <td>{self._escape_html(issue.error)}</td>
                    <td>{self._escape_html(issue.suggestion or 'N/A')}</td>
                </tr>
                """

        # Generate recommendations list
        recommendations_html = ""
        if self.options.get("include_recommendations", self._default_options["include_recommendations"]):
            for rec in recommendations:
                recommendations_html += f"<li>{self._escape_html(rec)}</li>\n"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self._escape_html(title)}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        h1, h2, h3 {{ color: #2c3e50; }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-card.success {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }}
        .stat-card.warning {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }}
        .stat-card.error {{ background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%); }}
        .stat-value {{ font-size: 32px; font-weight: bold; }}
        .stat-label {{ font-size: 14px; opacity: 0.9; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{ background-color: #f8f9fa; font-weight: 600; }}
        .severity-badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }}
        .severity-badge.issue-critical {{ background: #e74c3c; color: white; }}
        .severity-badge.issue-high {{ background: #e67e22; color: white; }}
        .severity-badge.issue-medium {{ background: #f1c40f; color: #333; }}
        .severity-badge.issue-low {{ background: #3498db; color: white; }}
        .severity-badge.issue-info {{ background: #95a5a6; color: white; }}
        .mermaid {{ text-align: center; margin: 20px 0; }}
        .recommendations {{ padding-left: 20px; }}
        .recommendations li {{ margin-bottom: 8px; }}
        .meta {{ color: #666; font-size: 14px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{self._escape_html(title)}</h1>

        <div class="stats-grid">
            <div class="stat-card {'success' if summary.get('success') else 'error'}">
                <div class="stat-value">{'PASS' if summary.get('success') else 'FAIL'}</div>
                <div class="stat-label">Status</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{summary.get('states_found', 0)}</div>
                <div class="stat-label">States Found</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{summary.get('transitions_found', 0)}</div>
                <div class="stat-label">Transitions</div>
            </div>
            <div class="stat-card {'warning' if summary.get('issues_found', 0) > 0 else 'success'}">
                <div class="stat-value">{summary.get('issues_found', 0)}</div>
                <div class="stat-label">Issues</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{summary.get('coverage_percent', 0):.1f}%</div>
                <div class="stat-label">Coverage</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{self._format_duration(summary.get('duration_seconds', 0))}</div>
                <div class="stat-label">Duration</div>
            </div>
        </div>

        <div class="card">
            <h2>State Graph</h2>
            <div class="mermaid">
{mermaid_diagram}
            </div>
        </div>

        <div class="card">
            <h2>Issues ({len(self.result.issues)})</h2>
            <table>
                <thead>
                    <tr>
                        <th>Severity</th>
                        <th>State</th>
                        <th>Error</th>
                        <th>Suggestion</th>
                    </tr>
                </thead>
                <tbody>
                    {issues_html if issues_html else '<tr><td colspan="4" style="text-align:center">No issues found</td></tr>'}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>Recommendations</h2>
            <ul class="recommendations">
                {recommendations_html if recommendations_html else '<li>No recommendations at this time.</li>'}
            </ul>
        </div>

        <div class="meta">
            <p>Generated at: {datetime.now().isoformat()}</p>
            <p>Exploration started: {self.result.started_at.isoformat()}</p>
            <p>Exploration finished: {self.result.finished_at.isoformat()}</p>
        </div>
    </div>

    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
</body>
</html>
"""
        return html

    def generate_json(self) -> dict[str, Any]:
        """
        Generate a JSON report.

        Returns:
            Report as dictionary
        """
        if not self.result:
            raise ValueError("Result is not set. Call set_result() first.")

        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "title": self.options.get("title", self._default_options["title"]),
                "version": "1.0.0",
            },
            "summary": self._get_summary(),
            "issue_breakdown": self._get_issue_summary_by_severity(),
            "recommendations": self._generate_recommendations(),
            "result": self.result.to_dict(),
        }

    def generate_markdown(self) -> str:
        """
        Generate a Markdown report.

        Returns:
            Markdown report content
        """
        if not self.result:
            raise ValueError("Result is not set. Call set_result() first.")

        summary = self._get_summary()
        self._get_issue_summary_by_severity()
        recommendations = self._generate_recommendations()
        title = self.options.get("title", self._default_options["title"])

        # Generate mermaid diagram
        mermaid_diagram = ""
        if self.options.get("include_graph", self._default_options["include_graph"]):
            try:
                mermaid_diagram = self.visualizer.to_mermaid()
            except Exception:
                mermaid_diagram = "<!-- Graph generation failed -->"

        md = f"""# {title}

## Summary

| Metric | Value |
|--------|-------|
| Status | {'PASS' if summary.get('success') else 'FAIL'} |
| States Found | {summary.get('states_found', 0)} |
| Transitions | {summary.get('transitions_found', 0)} |
| Issues | {summary.get('issues_found', 0)} |
| Coverage | {summary.get('coverage_percent', 0):.1f}% |
| Duration | {self._format_duration(summary.get('duration_seconds', 0))} |

## State Graph

```mermaid
{mermaid_diagram}
```

## Issues

"""
        if self.result.issues:
            md += "| Severity | State | Error | Suggestion |\n"
            md += "|----------|-------|-------|------------|\n"
            for issue in self.result.issues:
                state = issue.state or "N/A"
                suggestion = issue.suggestion or "N/A"
                md += f"| {issue.severity.value.upper()} | {state} | {issue.error} | {suggestion} |\n"
        else:
            md += "No issues found.\n"

        md += "\n## Recommendations\n\n"
        if recommendations:
            for rec in recommendations:
                md += f"- {rec}\n"
        else:
            md += "No recommendations at this time.\n"

        md += f"""
---

*Generated at: {datetime.now().isoformat()}*
"""
        return md

    def generate_junit(self) -> str:
        """
        Generate a JUnit XML report.

        Returns:
            JUnit XML content
        """
        if not self.result:
            raise ValueError("Result is not set. Call set_result() first.")

        # Create root testsuite element
        testsuite = ET.Element("testsuite")
        testsuite.set("name", "VenomQA State Exploration")
        testsuite.set("tests", str(len(self.result.graph.states)))
        testsuite.set("failures", str(len(self.result.issues)))
        testsuite.set("errors", str(len([i for i in self.result.issues if i.severity == IssueSeverity.CRITICAL])))
        testsuite.set("time", str(self.result.duration.total_seconds()))
        testsuite.set("timestamp", self.result.started_at.isoformat())

        # Add testcase for each state
        for state_id, state in self.result.graph.states.items():
            testcase = ET.SubElement(testsuite, "testcase")
            testcase.set("name", f"State: {state.name}")
            testcase.set("classname", "StateExploration")

            # Check if there are issues for this state
            state_issues = [i for i in self.result.issues if i.state == state_id]
            for issue in state_issues:
                if issue.severity in (IssueSeverity.CRITICAL, IssueSeverity.HIGH):
                    failure = ET.SubElement(testcase, "failure")
                    failure.set("type", issue.severity.value)
                    failure.set("message", issue.error)
                    if issue.suggestion:
                        failure.text = issue.suggestion

        # Add system-out with summary
        system_out = ET.SubElement(testsuite, "system-out")
        summary = self._get_summary()
        system_out.text = f"""
States Found: {summary.get('states_found', 0)}
Transitions: {summary.get('transitions_found', 0)}
Coverage: {summary.get('coverage_percent', 0):.1f}%
"""

        # Convert to string with proper XML declaration
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(testsuite, encoding="unicode")

    def generate_sarif(self) -> dict[str, Any]:
        """
        Generate a SARIF report for security tooling.

        Returns:
            SARIF report as dictionary
        """
        if not self.result:
            raise ValueError("Result is not set. Call set_result() first.")

        # SARIF 2.1.0 structure
        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "VenomQA State Explorer",
                            "version": "1.0.0",
                            "informationUri": "https://github.com/venomqa/venomqa",
                            "rules": self._generate_sarif_rules(),
                        }
                    },
                    "results": self._generate_sarif_results(),
                    "invocations": [
                        {
                            "executionSuccessful": self.result.success,
                            "startTimeUtc": self.result.started_at.isoformat() + "Z",
                            "endTimeUtc": self.result.finished_at.isoformat() + "Z",
                        }
                    ],
                }
            ],
        }

        return sarif

    def _generate_sarif_rules(self) -> list[dict[str, Any]]:
        """Generate SARIF rule definitions."""
        rules = []
        seen_categories = set()

        for issue in self.result.issues if self.result else []:
            category = issue.category or "general"
            if category not in seen_categories:
                seen_categories.add(category)
                rules.append({
                    "id": f"VENOMQA-{category.upper()}",
                    "name": f"{category.title()} Issue",
                    "shortDescription": {"text": f"State exploration {category} issue"},
                    "defaultConfiguration": {
                        "level": self._severity_to_sarif_level(issue.severity)
                    },
                })

        return rules

    def _generate_sarif_results(self) -> list[dict[str, Any]]:
        """Generate SARIF results from issues."""
        results = []

        for _i, issue in enumerate(self.result.issues if self.result else []):
            category = issue.category or "general"
            result = {
                "ruleId": f"VENOMQA-{category.upper()}",
                "level": self._severity_to_sarif_level(issue.severity),
                "message": {"text": issue.error},
                "locations": [],
            }

            if issue.state:
                result["locations"].append({
                    "physicalLocation": {
                        "artifactLocation": {"uri": f"state://{issue.state}"},
                    }
                })

            if issue.suggestion:
                result["fixes"] = [
                    {"description": {"text": issue.suggestion}}
                ]

            results.append(result)

        return results

    def _severity_to_sarif_level(self, severity: IssueSeverity) -> str:
        """Convert IssueSeverity to SARIF level."""
        mapping = {
            IssueSeverity.CRITICAL: "error",
            IssueSeverity.HIGH: "error",
            IssueSeverity.MEDIUM: "warning",
            IssueSeverity.LOW: "note",
            IssueSeverity.INFO: "none",
        }
        return mapping.get(severity, "warning")

    def generate_text(self) -> str:
        """
        Generate a plain text summary.

        Returns:
            Text summary content
        """
        if not self.result:
            raise ValueError("Result is not set. Call set_result() first.")

        summary = self._get_summary()
        recommendations = self._generate_recommendations()
        title = self.options.get("title", self._default_options["title"])

        text = f"""
{'='*60}
{title.center(60)}
{'='*60}

SUMMARY
-------
Status:        {'PASS' if summary.get('success') else 'FAIL'}
States Found:  {summary.get('states_found', 0)}
Transitions:   {summary.get('transitions_found', 0)}
Issues Found:  {summary.get('issues_found', 0)}
Coverage:      {summary.get('coverage_percent', 0):.1f}%
Duration:      {self._format_duration(summary.get('duration_seconds', 0))}

ISSUES
------
"""
        if self.result.issues:
            for issue in self.result.issues:
                text += f"[{issue.severity.value.upper()}] {issue.error}\n"
                if issue.state:
                    text += f"    State: {issue.state}\n"
                if issue.suggestion:
                    text += f"    Suggestion: {issue.suggestion}\n"
                text += "\n"
        else:
            text += "No issues found.\n\n"

        text += "RECOMMENDATIONS\n---------------\n"
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                text += f"{i}. {rec}\n"
        else:
            text += "No recommendations at this time.\n"

        text += f"""
{'='*60}
Generated at: {datetime.now().isoformat()}
{'='*60}
"""
        return text

    def _get_summary(self) -> dict[str, Any]:
        """
        Generate summary statistics.

        Returns:
            Summary dictionary
        """
        if not self.result:
            return {
                "states_found": 0,
                "transitions_found": 0,
                "issues_found": 0,
                "critical_issues": 0,
                "coverage_percent": 0.0,
                "duration_seconds": 0.0,
                "success": False,
            }

        return {
            "states_found": len(self.result.graph.states),
            "transitions_found": len(self.result.graph.transitions),
            "issues_found": len(self.result.issues),
            "critical_issues": len(self.result.get_critical_issues()),
            "coverage_percent": self.result.coverage.coverage_percent,
            "duration_seconds": self.result.duration.total_seconds(),
            "success": self.result.success,
        }

    def _get_issue_summary_by_severity(self) -> dict[str, int]:
        """
        Get issue counts by severity.

        Returns:
            Dictionary mapping severity to count
        """
        if not self.result:
            return {}

        summary: dict[str, int] = {}
        for severity in IssueSeverity:
            count = len(self.result.get_issues_by_severity(severity))
            if count > 0:
                summary[severity.value] = count
        return summary

    def _generate_recommendations(self) -> list[str]:
        """
        Generate actionable recommendations based on results.

        Returns:
            List of recommendation strings
        """
        if not self.result:
            return []

        recommendations: list[str] = []

        # Analyze issues
        critical_count = len([i for i in self.result.issues if i.severity == IssueSeverity.CRITICAL])
        high_count = len([i for i in self.result.issues if i.severity == IssueSeverity.HIGH])

        if critical_count > 0:
            recommendations.append(
                f"Address {critical_count} critical issue(s) immediately - these may indicate severe security or functional problems."
            )

        if high_count > 0:
            recommendations.append(
                f"Review and fix {high_count} high-severity issue(s) as soon as possible."
            )

        # Analyze coverage
        coverage = self.result.coverage.coverage_percent
        if coverage < 50:
            recommendations.append(
                f"Coverage is low ({coverage:.1f}%). Consider adding more seed endpoints or increasing exploration depth."
            )
        elif coverage < 80:
            recommendations.append(
                f"Coverage is moderate ({coverage:.1f}%). Consider exploring additional authentication scenarios or edge cases."
            )

        # Analyze uncovered actions
        uncovered_count = len(self.result.coverage.uncovered_actions)
        if uncovered_count > 0:
            recommendations.append(
                f"There are {uncovered_count} uncovered action(s). Consider manually testing these endpoints."
            )

        # Analyze state distribution
        state_breakdown = self.result.coverage.state_breakdown
        error_states = state_breakdown.get("error", 0)
        if error_states > 0:
            total_states = len(self.result.graph.states)
            error_ratio = error_states / total_states if total_states > 0 else 0
            if error_ratio > 0.2:
                recommendations.append(
                    f"High proportion of error states ({error_ratio:.0%}). Review API authentication and input validation."
                )

        # General recommendations
        if not recommendations:
            recommendations.append(
                "Exploration completed successfully with good coverage. Consider running periodic regression tests."
            )

        return recommendations

    def _format_duration(self, seconds: float) -> str:
        """
        Format duration in human-readable form.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string
        """
        if seconds < 60:
            return f"{seconds:.2f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.0f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def _escape_html(self, text: str) -> str:
        """
        Escape HTML special characters.

        Args:
            text: Text to escape

        Returns:
            Escaped text
        """
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )

    def set_option(self, key: str, value: Any) -> None:
        """
        Set a report generation option.

        Args:
            key: Option key
            value: Option value
        """
        self.options[key] = value
