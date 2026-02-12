"""SARIF reporter for GitHub Code Scanning integration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from venomqa.core.models import JourneyResult, Severity
from venomqa.reporters.base import BaseReporter

SARIF_VERSION = "2.1.0"
SCHEMA_URI = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Documents/schemas/sarif-schema-2.1.0.json"


class SARIFReporter(BaseReporter):
    """Generate SARIF reports for GitHub Code Scanning."""

    @property
    def file_extension(self) -> str:
        return ".sarif"

    def __init__(
        self,
        output_path: str | Path | None = None,
        tool_name: str = "VenomQA",
        tool_version: str = "1.0.0",
        tool_uri: str = "https://github.com/venomqa/venomqa",
        repository_root: str | None = None,
    ):
        super().__init__(output_path)
        self.tool_name = tool_name
        self.tool_version = tool_version
        self.tool_uri = tool_uri
        self.repository_root = repository_root

    def generate(self, results: list[JourneyResult]) -> str:
        sarif = self._build_sarif(results)
        return json.dumps(sarif, indent=2)

    def _build_sarif(self, results: list[JourneyResult]) -> dict[str, Any]:
        rules, results_list = self._extract_rules_and_results(results)

        return {
            "$schema": SCHEMA_URI,
            "version": SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": self.tool_name,
                            "version": self.tool_version,
                            "informationUri": self.tool_uri,
                            "rules": rules,
                        }
                    },
                    "results": results_list,
                    "invocations": [self._build_invocation(results)],
                }
            ],
        }

    def _extract_rules_and_results(
        self, results: list[JourneyResult]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rules_map: dict[str, dict[str, Any]] = {}
        sarif_results: list[dict[str, Any]] = []

        for journey_result in results:
            for issue in journey_result.issues:
                rule_id = self._generate_rule_id(issue.error)

                if rule_id not in rules_map:
                    rules_map[rule_id] = self._build_rule(rule_id, issue)

                sarif_results.append(
                    self._build_result(rule_id, journey_result.journey_name, issue)
                )

        rules = list(rules_map.values())
        return rules, sarif_results

    def _generate_rule_id(self, error: str) -> str:
        error_type = "unknown-error"

        error_lower = error.lower()
        if "401" in error_lower or "unauthorized" in error_lower:
            error_type = "authentication-error"
        elif "403" in error_lower or "forbidden" in error_lower:
            error_type = "authorization-error"
        elif "404" in error_lower or "not found" in error_lower:
            error_type = "not-found-error"
        elif "422" in error_lower or "validation" in error_lower:
            error_type = "validation-error"
        elif "500" in error_lower or "internal server error" in error_lower:
            error_type = "server-error"
        elif "timeout" in error_lower:
            error_type = "timeout-error"
        elif "connection" in error_lower:
            error_type = "connection-error"
        elif "assertion" in error_lower:
            error_type = "assertion-failure"

        return f"VENOM{self._get_severity_code(Severity.HIGH)}{error_type}"

    def _get_severity_code(self, severity: Severity) -> str:
        codes = {
            Severity.CRITICAL: "001",
            Severity.HIGH: "002",
            Severity.MEDIUM: "003",
            Severity.LOW: "004",
            Severity.INFO: "005",
        }
        return codes.get(severity, "000")

    def _build_rule(self, rule_id: str, issue: Any) -> dict[str, Any]:
        severity_to_level = {
            Severity.CRITICAL: "error",
            Severity.HIGH: "error",
            Severity.MEDIUM: "warning",
            Severity.LOW: "note",
            Severity.INFO: "note",
        }

        return {
            "id": rule_id,
            "name": self._format_rule_name(rule_id),
            "shortDescription": {"text": f"Test failure: {issue.step}"},
            "fullDescription": {
                "text": issue.error[:500] if issue.error else "Test step failed",
                "markdown": (
                    f"**Error:** {issue.error[:500] if issue.error else 'Test step failed'}\n\n"
                    f"**Suggestion:** {issue.suggestion}"
                    if issue.suggestion
                    else None
                ),
            },
            "defaultConfiguration": {"level": severity_to_level.get(issue.severity, "warning")},
            "help": {
                "text": issue.suggestion or "Review the test failure and fix the underlying issue.",
                "markdown": (
                    f"### Suggestion\n\n"
                    f"{issue.suggestion or 'Review the test failure and fix the underlying issue.'}"
                ),
            },
        }

    def _format_rule_name(self, rule_id: str) -> str:
        parts = rule_id.replace("VENOM", "").split("-")
        formatted_parts = [p.capitalize() for p in parts]
        return " ".join(formatted_parts)

    def _build_result(self, rule_id: str, journey_name: str, issue: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ruleId": rule_id,
            "message": {
                "text": issue.error,
                "markdown": (
                    f"**Journey:** {journey_name}\n**Path:** {issue.path}\n"
                    f"**Step:** {issue.step}\n\n**Error:** {issue.error}"
                ),
            },
            "level": self._get_sarif_level(issue.severity),
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": self._build_artifact_uri(journey_name, issue),
                            "uriBaseId": "%SRCROOT%" if self.repository_root else None,
                        },
                        "region": {
                            "startLine": 1,
                            "startColumn": 1,
                        },
                    },
                    "logicalLocations": [
                        {
                            "name": journey_name,
                            "fullyQualifiedName": f"{journey_name}/{issue.path}/{issue.step}",
                            "kind": "namespace",
                        }
                    ],
                }
            ],
            "partialFingerprints": {
                "primaryLocationLineHash": self._compute_hash(issue),
            },
            "properties": {
                "journey": journey_name,
                "path": issue.path,
                "step": issue.step,
                "severity": issue.severity.value,
                "timestamp": issue.timestamp.isoformat(),
            },
        }

        if issue.request:
            result["properties"]["request"] = issue.request

        if issue.response:
            result["properties"]["response"] = issue.response

        if issue.logs:
            result["properties"]["logs"] = issue.logs

        result["locations"][0]["physicalLocation"]["artifactLocation"].pop("uriBaseId", None)

        return result

    def _build_artifact_uri(self, journey_name: str, issue: Any) -> str:
        sanitized_journey = journey_name.replace(" ", "_").replace("/", "_")
        sanitized_path = issue.path.replace(" ", "_").replace("/", "_")
        return f"tests/journeys/{sanitized_journey}/{sanitized_path}.py"

    def _get_sarif_level(self, severity: Severity) -> str:
        level_map = {
            Severity.CRITICAL: "error",
            Severity.HIGH: "error",
            Severity.MEDIUM: "warning",
            Severity.LOW: "note",
            Severity.INFO: "none",
        }
        return level_map.get(severity, "warning")

    def _compute_hash(self, issue: Any) -> str:
        import hashlib

        content = f"{issue.journey}:{issue.path}:{issue.step}:{issue.error}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _build_invocation(self, results: list[JourneyResult]) -> dict[str, Any]:
        total = len(results)
        passed = sum(1 for r in results if r.success)
        total_issues = sum(len(r.issues) for r in results)

        start_time = min((r.started_at for r in results), default=datetime.now())
        end_time = max((r.finished_at for r in results), default=datetime.now())

        return {
            "executionSuccessful": passed == total,
            "startTimeUtc": start_time.isoformat(),
            "endTimeUtc": end_time.isoformat(),
            "exitCode": 0 if passed == total else 1,
            "exitCodeDescription": "All tests passed"
            if passed == total
            else f"{total - passed} test(s) failed",
            "toolExecutionNotifications": [
                {
                    "level": "error"
                    if issue.severity in (Severity.CRITICAL, Severity.HIGH)
                    else "warning",
                    "message": {"text": f"{issue.journey}/{issue.step}: {issue.error}"},
                    "threadId": i,
                }
                for i, issue in enumerate(
                    [
                        issue
                        for r in results
                        for issue in r.issues
                        if issue.severity in (Severity.CRITICAL, Severity.HIGH)
                    ]
                )
            ],
            "properties": {
                "totalJourneys": total,
                "passedJourneys": passed,
                "failedJourneys": total - passed,
                "totalIssues": total_issues,
            },
        }
