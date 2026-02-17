"""Security scanner for comprehensive vulnerability detection.

This module provides a unified security scanner that runs all security
tests against a target application and generates detailed reports.

Example:
    >>> from venomqa.domains.security import SecurityScanner, ScanConfig
    >>> scanner = SecurityScanner("http://localhost:8000")
    >>> result = scanner.run_full_scan()
    >>> scanner.generate_sarif_report(result, "security-report.sarif")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from venomqa.domains.security.actions.authentication import (
    AuthenticationTester,
    AuthTestConfig,
)
from venomqa.domains.security.actions.injection import (
    InjectionTestConfig,
    InjectionTester,
)
from venomqa.domains.security.actions.owasp import (
    OWASPCheckConfig,
    OWASPChecker,
)
from venomqa.security.testing import (
    SecurityTestResult,
    VulnerabilityFinding,
    VulnerabilitySeverity,
)

logger = logging.getLogger(__name__)


@dataclass
class ScanConfig:
    """Configuration for security scanning.

    Attributes:
        target_url: Base URL of the target application.
        endpoints: List of endpoints to scan.
        auth_endpoints: Authentication endpoints for specific tests.
        admin_endpoints: Admin endpoints for privilege escalation tests.
        user_token: Valid user token for authenticated tests.
        admin_token: Valid admin token for comparison.
        refresh_token: Refresh token for token refresh tests.
        credentials: Credentials for obtaining tokens.
        timeout: Request timeout in seconds.
        max_payloads: Maximum payloads per test category.
        skip_tests: List of test categories to skip.
        follow_redirects: Whether to follow HTTP redirects.
        rate_limit_requests: Number of requests for rate limit testing.
        verify_ssl: Whether to verify SSL certificates.
    """

    target_url: str
    endpoints: list[str] = field(default_factory=lambda: ["/", "/api"])
    auth_endpoints: list[str] = field(default_factory=lambda: ["/api/login", "/api/auth/token"])
    admin_endpoints: list[str] = field(default_factory=lambda: ["/api/admin", "/api/users"])
    user_token: str | None = None
    admin_token: str | None = None
    refresh_token: str | None = None
    credentials: dict[str, str] = field(
        default_factory=lambda: {"username": "test", "password": "test"}
    )
    timeout: float = 30.0
    max_payloads: int = 50
    skip_tests: list[str] = field(default_factory=list)
    follow_redirects: bool = True
    rate_limit_requests: int = 100
    verify_ssl: bool = True


@dataclass
class SecurityScanResult:
    """Result of a complete security scan.

    Attributes:
        target: Target URL that was scanned.
        scan_started: When the scan started.
        scan_finished: When the scan finished.
        total_findings: Total number of vulnerability findings.
        findings_by_severity: Count of findings per severity level.
        findings_by_type: Count of findings per vulnerability type.
        all_findings: List of all vulnerability findings.
        test_results: Individual test results.
        errors: Errors encountered during scanning.
        scan_duration_ms: Total scan duration in milliseconds.
    """

    target: str
    scan_started: datetime
    scan_finished: datetime
    total_findings: int
    findings_by_severity: dict[str, int]
    findings_by_type: dict[str, int]
    all_findings: list[VulnerabilityFinding]
    test_results: dict[str, SecurityTestResult]
    errors: list[str]
    scan_duration_ms: float

    @property
    def critical_count(self) -> int:
        """Number of critical severity findings."""
        return self.findings_by_severity.get("critical", 0)

    @property
    def high_count(self) -> int:
        """Number of high severity findings."""
        return self.findings_by_severity.get("high", 0)

    @property
    def is_vulnerable(self) -> bool:
        """Whether any vulnerabilities were found."""
        return self.total_findings > 0

    @property
    def has_critical_issues(self) -> bool:
        """Whether any critical issues were found."""
        return self.critical_count > 0 or self.high_count > 0


class SecurityScanner:
    """Comprehensive security scanner.

    Runs all security tests against a target application and provides
    detailed vulnerability reports in multiple formats.

    Example:
        >>> scanner = SecurityScanner("http://localhost:8000")
        >>> config = ScanConfig(
        ...     target_url="http://localhost:8000",
        ...     endpoints=["/api/users", "/api/products"],
        ...     user_token="jwt_token_here"
        ... )
        >>> result = scanner.run_full_scan(config)
        >>> print(f"Found {result.total_findings} vulnerabilities")
    """

    def __init__(self, client: Any) -> None:
        """Initialize security scanner.

        Args:
            client: HTTP client for making requests.
        """
        self.client = client

    def run_full_scan(self, config: ScanConfig) -> SecurityScanResult:
        """Run a comprehensive security scan.

        Args:
            config: Scan configuration.

        Returns:
            SecurityScanResult with all findings.
        """
        scan_started = datetime.now()
        all_findings: list[VulnerabilityFinding] = []
        test_results: dict[str, SecurityTestResult] = {}
        all_errors: list[str] = []

        logger.info(f"Starting security scan of {config.target_url}")

        # Run authentication tests
        if "authentication" not in config.skip_tests:
            logger.info("Running authentication tests...")
            try:
                auth_config = AuthTestConfig(
                    token_endpoint=config.auth_endpoints[0] if config.auth_endpoints else "/api/auth/token",
                    refresh_endpoint="/api/auth/refresh",
                    protected_endpoints=config.endpoints,
                    admin_endpoints=config.admin_endpoints,
                )
                auth_tester = AuthenticationTester(self.client, config.timeout)
                result = auth_tester.run_all_tests(
                    auth_config,
                    config.user_token,
                    config.refresh_token,
                )
                test_results["authentication"] = result
                all_findings.extend(result.findings)
                all_errors.extend(result.errors)
            except Exception as e:
                all_errors.append(f"Authentication tests failed: {e}")
                logger.error(f"Authentication tests failed: {e}")

        # Run injection tests
        if "injection" not in config.skip_tests:
            logger.info("Running injection tests...")
            try:
                injection_config = InjectionTestConfig(
                    max_payloads=config.max_payloads,
                    timeout=config.timeout,
                    follow_redirects=config.follow_redirects,
                )
                injection_tester = InjectionTester(self.client, injection_config)

                for endpoint in config.endpoints:
                    result = injection_tester.test_all(endpoint)
                    test_results[f"injection_{endpoint}"] = result
                    all_findings.extend(result.findings)
                    all_errors.extend(result.errors)
            except Exception as e:
                all_errors.append(f"Injection tests failed: {e}")
                logger.error(f"Injection tests failed: {e}")

        # Run OWASP checks
        if "owasp" not in config.skip_tests:
            logger.info("Running OWASP checks...")
            try:
                owasp_config = OWASPCheckConfig(
                    timeout=config.timeout,
                    rate_limit_requests=config.rate_limit_requests,
                )
                owasp_checker = OWASPChecker(self.client, owasp_config)
                result = owasp_checker.run_all_checks(
                    config.target_url,
                    config.endpoints,
                    config.auth_endpoints,
                )
                test_results["owasp"] = result
                all_findings.extend(result.findings)
                all_errors.extend(result.errors)
            except Exception as e:
                all_errors.append(f"OWASP checks failed: {e}")
                logger.error(f"OWASP checks failed: {e}")

        scan_finished = datetime.now()
        scan_duration = (scan_finished - scan_started).total_seconds() * 1000

        # Aggregate findings by severity
        findings_by_severity: dict[str, int] = {}
        for finding in all_findings:
            severity = finding.severity.value
            findings_by_severity[severity] = findings_by_severity.get(severity, 0) + 1

        # Aggregate findings by type
        findings_by_type: dict[str, int] = {}
        for finding in all_findings:
            vuln_type = finding.vuln_type.value
            findings_by_type[vuln_type] = findings_by_type.get(vuln_type, 0) + 1

        logger.info(f"Scan completed. Found {len(all_findings)} vulnerabilities.")

        return SecurityScanResult(
            target=config.target_url,
            scan_started=scan_started,
            scan_finished=scan_finished,
            total_findings=len(all_findings),
            findings_by_severity=findings_by_severity,
            findings_by_type=findings_by_type,
            all_findings=all_findings,
            test_results=test_results,
            errors=all_errors,
            scan_duration_ms=scan_duration,
        )

    def generate_sarif_report(
        self,
        result: SecurityScanResult,
        output_path: str | Path,
    ) -> str:
        """Generate a SARIF report from scan results.

        Args:
            result: Security scan result.
            output_path: Path to write the SARIF file.

        Returns:
            Path to the generated report.
        """
        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Documents/schemas/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "VenomQA Security Scanner",
                            "version": "1.0.0",
                            "informationUri": "https://github.com/venomqa/venomqa",
                            "rules": self._generate_sarif_rules(result.all_findings),
                        }
                    },
                    "results": self._generate_sarif_results(result.all_findings, result.target),
                    "invocations": [
                        {
                            "executionSuccessful": True,
                            "startTimeUtc": result.scan_started.isoformat(),
                            "endTimeUtc": result.scan_finished.isoformat(),
                        }
                    ],
                }
            ],
        }

        output_path = Path(output_path)
        output_path.write_text(json.dumps(sarif, indent=2))
        logger.info(f"SARIF report written to {output_path}")

        return str(output_path)

    def _generate_sarif_rules(
        self,
        findings: list[VulnerabilityFinding],
    ) -> list[dict[str, Any]]:
        """Generate SARIF rules from findings."""
        rules: dict[str, dict[str, Any]] = {}

        for finding in findings:
            rule_id = f"VENOM-{finding.vuln_type.value.upper().replace('_', '-')}"

            if rule_id not in rules:
                severity_map = {
                    VulnerabilitySeverity.CRITICAL: "error",
                    VulnerabilitySeverity.HIGH: "error",
                    VulnerabilitySeverity.MEDIUM: "warning",
                    VulnerabilitySeverity.LOW: "note",
                    VulnerabilitySeverity.INFO: "none",
                }

                rules[rule_id] = {
                    "id": rule_id,
                    "name": finding.vuln_type.value.replace("_", " ").title(),
                    "shortDescription": {"text": finding.title},
                    "fullDescription": {"text": finding.description},
                    "defaultConfiguration": {
                        "level": severity_map.get(finding.severity, "warning")
                    },
                    "help": {
                        "text": finding.remediation,
                        "markdown": f"## Remediation\n\n{finding.remediation}",
                    },
                    "properties": {
                        "security-severity": self._get_cvss_score(finding.severity),
                        "tags": ["security", finding.owasp or "A00:2021"],
                    },
                }

        return list(rules.values())

    def _generate_sarif_results(
        self,
        findings: list[VulnerabilityFinding],
        target: str,
    ) -> list[dict[str, Any]]:
        """Generate SARIF results from findings."""
        results: list[dict[str, Any]] = []

        for i, finding in enumerate(findings):
            rule_id = f"VENOM-{finding.vuln_type.value.upper().replace('_', '-')}"

            severity_map = {
                VulnerabilitySeverity.CRITICAL: "error",
                VulnerabilitySeverity.HIGH: "error",
                VulnerabilitySeverity.MEDIUM: "warning",
                VulnerabilitySeverity.LOW: "note",
                VulnerabilitySeverity.INFO: "none",
            }

            result = {
                "ruleId": rule_id,
                "level": severity_map.get(finding.severity, "warning"),
                "message": {
                    "text": finding.description,
                    "markdown": (
                        f"**{finding.title}**\n\n"
                        f"{finding.description}\n\n"
                        f"**Payload:** `{finding.payload}`\n\n"
                        f"**Evidence:** {finding.evidence}\n\n"
                        f"**Remediation:** {finding.remediation}"
                    ),
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": finding.location or target,
                            },
                        },
                    }
                ],
                "fingerprints": {
                    "primaryLocationLineHash": f"{rule_id}-{i}",
                },
                "properties": {
                    "severity": finding.severity.value,
                    "cwe": finding.cwe,
                    "owasp": finding.owasp,
                },
            }

            if finding.references:
                result["properties"]["references"] = finding.references

            results.append(result)

        return results

    def _get_cvss_score(self, severity: VulnerabilitySeverity) -> str:
        """Map severity to CVSS score range."""
        scores = {
            VulnerabilitySeverity.CRITICAL: "9.0",
            VulnerabilitySeverity.HIGH: "7.0",
            VulnerabilitySeverity.MEDIUM: "5.0",
            VulnerabilitySeverity.LOW: "3.0",
            VulnerabilitySeverity.INFO: "0.0",
        }
        return scores.get(severity, "5.0")

    def generate_json_report(
        self,
        result: SecurityScanResult,
        output_path: str | Path,
    ) -> str:
        """Generate a JSON report from scan results.

        Args:
            result: Security scan result.
            output_path: Path to write the JSON file.

        Returns:
            Path to the generated report.
        """
        report = {
            "scan_info": {
                "target": result.target,
                "started_at": result.scan_started.isoformat(),
                "finished_at": result.scan_finished.isoformat(),
                "duration_ms": result.scan_duration_ms,
            },
            "summary": {
                "total_findings": result.total_findings,
                "findings_by_severity": result.findings_by_severity,
                "findings_by_type": result.findings_by_type,
                "is_vulnerable": result.is_vulnerable,
                "has_critical_issues": result.has_critical_issues,
            },
            "findings": [
                {
                    "type": f.vuln_type.value,
                    "severity": f.severity.value,
                    "title": f.title,
                    "description": f.description,
                    "payload": f.payload,
                    "location": f.location,
                    "evidence": f.evidence,
                    "remediation": f.remediation,
                    "cwe": f.cwe,
                    "owasp": f.owasp,
                    "references": f.references,
                }
                for f in result.all_findings
            ],
            "errors": result.errors,
        }

        output_path = Path(output_path)
        output_path.write_text(json.dumps(report, indent=2))
        logger.info(f"JSON report written to {output_path}")

        return str(output_path)

    def generate_markdown_report(
        self,
        result: SecurityScanResult,
        output_path: str | Path,
    ) -> str:
        """Generate a Markdown report from scan results.

        Args:
            result: Security scan result.
            output_path: Path to write the Markdown file.

        Returns:
            Path to the generated report.
        """
        lines = [
            "# VenomQA Security Scan Report\n",
            f"**Target:** {result.target}  ",
            f"**Scan Date:** {result.scan_started.strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Duration:** {result.scan_duration_ms:.0f}ms\n",
            "## Summary\n",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Findings | {result.total_findings} |",
            f"| Critical | {result.findings_by_severity.get('critical', 0)} |",
            f"| High | {result.findings_by_severity.get('high', 0)} |",
            f"| Medium | {result.findings_by_severity.get('medium', 0)} |",
            f"| Low | {result.findings_by_severity.get('low', 0)} |",
            f"| Info | {result.findings_by_severity.get('info', 0)} |\n",
        ]

        if result.all_findings:
            lines.append("## Findings\n")

            # Group by severity
            severity_order = ["critical", "high", "medium", "low", "info"]

            for severity in severity_order:
                severity_findings = [
                    f for f in result.all_findings if f.severity.value == severity
                ]

                if severity_findings:
                    lines.append(f"### {severity.upper()} Severity\n")

                    for finding in severity_findings:
                        lines.extend([
                            f"#### {finding.title}\n",
                            f"**Type:** {finding.vuln_type.value}  ",
                            f"**Location:** {finding.location}  ",
                            f"**CWE:** {finding.cwe or 'N/A'}  ",
                            f"**OWASP:** {finding.owasp or 'N/A'}\n",
                            "**Description:**  ",
                            f"{finding.description}\n",
                            "**Payload:**  ",
                            "```",
                            f"{finding.payload}",
                            "```\n",
                            "**Evidence:**  ",
                            f"{finding.evidence}\n",
                            "**Remediation:**  ",
                            f"{finding.remediation}\n",
                            "---\n",
                        ])

        if result.errors:
            lines.append("## Errors\n")
            for error in result.errors:
                lines.append(f"- {error}")
            lines.append("")

        output_path = Path(output_path)
        output_path.write_text("\n".join(lines))
        logger.info(f"Markdown report written to {output_path}")

        return str(output_path)
