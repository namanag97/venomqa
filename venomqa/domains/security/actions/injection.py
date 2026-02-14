"""Injection attack testing actions.

This module provides comprehensive injection testing including:
- SQL injection testing with multiple payloads
- XSS testing with various contexts
- Command injection testing
- Auto-injection for parameter fuzzing

Example:
    >>> tester = InjectionTester(client)
    >>> result = tester.test_sql_injection("/api/users", params={"id": "1"})
    >>> auto_injector = AutoInjector(client)
    >>> result = auto_injector.inject_all("/api/search", {"q": "test"})
"""

from __future__ import annotations

import logging
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Final

from venomqa.security.testing import (
    CommandInjectionPayloads,
    SecurityTestResult,
    SQLInjectionPayloads,
    VulnerabilityFinding,
    VulnerabilitySeverity,
    VulnerabilityType,
    XSSPayloads,
)

logger = logging.getLogger(__name__)


@dataclass
class InjectionTestConfig:
    """Configuration for injection tests.

    Attributes:
        max_payloads: Maximum payloads to test per category.
        timeout: Request timeout in seconds.
        follow_redirects: Whether to follow HTTP redirects.
        detect_blind: Whether to test for blind injection.
        blind_delay_seconds: Delay for time-based blind detection.
    """

    max_payloads: int = 50
    timeout: float = 30.0
    follow_redirects: bool = True
    detect_blind: bool = True
    blind_delay_seconds: float = 5.0


class SQLInjectionTest:
    """SQL injection vulnerability tester.

    Tests for various SQL injection techniques including:
    - Error-based injection
    - Boolean-based blind injection
    - Time-based blind injection
    - UNION-based injection

    Example:
        >>> test = SQLInjectionTest(client)
        >>> result = test.run("/api/users", params={"id": "1"})
    """

    SQL_ERROR_PATTERNS: Final[list[tuple[str, str]]] = [
        (r"sql syntax", "MySQL syntax error"),
        (r"mysql_fetch", "MySQL error"),
        (r"ORA-\d{5}", "Oracle error"),
        (r"PLS-\d{5}", "Oracle PL/SQL error"),
        (r"pg_query", "PostgreSQL error"),
        (r"Warning: pg_", "PostgreSQL warning"),
        (r"valid PostgreSQL result", "PostgreSQL error"),
        (r"SQLSTATE\[\d+\]", "PDO SQL error"),
        (r"Incorrect syntax near", "MSSQL syntax error"),
        (r"Microsoft OLE DB Provider", "MSSQL OLE error"),
        (r"SQLServer JDBC Driver", "MSSQL JDBC error"),
        (r"sqlite3\.OperationalError", "SQLite error"),
        (r"SQLITE_ERROR", "SQLite error"),
        (r"Unclosed quotation mark", "SQL syntax error"),
        (r"quoted string not properly terminated", "SQL syntax error"),
        (r"You have an error in your SQL", "MySQL error"),
        (r"ERROR:\s*syntax error", "PostgreSQL syntax error"),
        (r"Driver.*?SQL[\-\_\s]*Server", "MSSQL driver error"),
        (r"System\.Data\.SqlClient", ".NET SQL error"),
        (r"System\.Data\.OleDb", ".NET OLE error"),
    ]

    def __init__(
        self,
        client: Any,
        config: InjectionTestConfig | None = None,
    ) -> None:
        """Initialize SQL injection test.

        Args:
            client: HTTP client for making requests.
            config: Test configuration.
        """
        self.client = client
        self.config = config or InjectionTestConfig()

    def run(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> SecurityTestResult:
        """Run SQL injection tests.

        Args:
            endpoint: Target endpoint URL.
            params: Query parameters to test.
            data: Request body data to test.
            headers: Additional headers.
            method: HTTP method to use.

        Returns:
            SecurityTestResult with findings.
        """
        start_time = time.time()
        findings: list[VulnerabilityFinding] = []
        errors: list[str] = []
        payloads_tested = 0

        params = params or {}
        data = data or {}
        headers = headers or {}

        # Get baseline response
        try:
            baseline = self._make_request(endpoint, params, data, headers, method)
            baseline_length = len(baseline.text) if hasattr(baseline, "text") else 0
        except Exception as e:
            return SecurityTestResult(
                target=endpoint,
                vulnerable=False,
                findings=[],
                errors=[f"Failed to get baseline response: {e}"],
            )

        # Test each parameter
        all_params = {**params, **data}

        for param_name, original_value in all_params.items():
            # Test with various SQL injection payloads
            payloads = list(SQLInjectionPayloads.all_payloads())
            if self.config.max_payloads:
                payloads = payloads[: self.config.max_payloads]

            for payload in payloads:
                payloads_tested += 1

                # Inject payload
                if param_name in params:
                    test_params = {**params, param_name: f"{original_value}{payload}"}
                    test_data = data
                else:
                    test_params = params
                    test_data = {**data, param_name: f"{original_value}{payload}"}

                try:
                    response = self._make_request(
                        endpoint, test_params, test_data, headers, method
                    )

                    # Check for SQL error signatures in response
                    finding = self._detect_sql_error(
                        response, endpoint, param_name, payload
                    )
                    if finding:
                        findings.append(finding)
                        break  # One finding per parameter

                    # Check for boolean-based blind injection
                    if self._detect_boolean_blind(
                        response, baseline_length, param_name, payload
                    ):
                        findings.append(
                            VulnerabilityFinding(
                                vuln_type=VulnerabilityType.SQL_INJECTION,
                                severity=VulnerabilitySeverity.HIGH,
                                title="Boolean-Based Blind SQL Injection",
                                description=(
                                    f"Parameter '{param_name}' appears vulnerable to "
                                    "boolean-based blind SQL injection. Response length "
                                    "varies based on injected conditions."
                                ),
                                payload=payload,
                                location=f"{endpoint}?{param_name}=",
                                remediation=(
                                    "Use parameterized queries or prepared statements. "
                                    "Implement input validation and sanitization."
                                ),
                                cwe="CWE-89",
                                owasp="A03:2021 - Injection",
                            )
                        )
                        break

                except Exception as e:
                    errors.append(f"Error testing {param_name} with payload: {e}")

            # Test time-based blind injection
            if self.config.detect_blind:
                finding = self._test_time_based_blind(
                    endpoint, param_name, original_value, params, data, headers, method
                )
                if finding:
                    findings.append(finding)
                    payloads_tested += len(SQLInjectionPayloads.TIME_BASED)

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=endpoint,
            vulnerable=len(findings) > 0,
            findings=findings,
            test_duration_ms=duration,
            payloads_tested=payloads_tested,
            errors=errors,
        )

    def _make_request(
        self,
        endpoint: str,
        params: dict[str, str],
        data: dict[str, Any],
        headers: dict[str, str],
        method: str,
    ) -> Any:
        """Make HTTP request with given parameters."""
        kwargs: dict[str, Any] = {
            "timeout": self.config.timeout,
            "headers": headers,
        }

        if params:
            kwargs["params"] = params

        if method.upper() in ["POST", "PUT", "PATCH"]:
            kwargs["json"] = data

        return self.client.request(method=method, url=endpoint, **kwargs)

    def _detect_sql_error(
        self,
        response: Any,
        endpoint: str,
        param_name: str,
        payload: str,
    ) -> VulnerabilityFinding | None:
        """Detect SQL errors in response."""
        response_text = response.text if hasattr(response, "text") else str(response)

        for pattern, db_type in self.SQL_ERROR_PATTERNS:
            if re.search(pattern, response_text, re.IGNORECASE):
                return VulnerabilityFinding(
                    vuln_type=VulnerabilityType.SQL_INJECTION,
                    severity=VulnerabilitySeverity.HIGH,
                    title=f"SQL Injection - Error Based ({db_type})",
                    description=(
                        f"SQL error detected in response when testing parameter '{param_name}'. "
                        f"Database type appears to be {db_type}."
                    ),
                    payload=payload,
                    location=f"{endpoint}?{param_name}=",
                    evidence=f"Pattern matched: {pattern}",
                    remediation=(
                        "Use parameterized queries or prepared statements. "
                        "Never concatenate user input into SQL queries. "
                        "Implement proper error handling to avoid exposing SQL errors."
                    ),
                    references=[
                        "https://owasp.org/www-community/attacks/SQL_Injection",
                        "https://cwe.mitre.org/data/definitions/89.html",
                    ],
                    cwe="CWE-89",
                    owasp="A03:2021 - Injection",
                )

        return None

    def _detect_boolean_blind(
        self,
        response: Any,
        baseline_length: int,
        param_name: str,
        payload: str,
    ) -> bool:
        """Detect boolean-based blind SQL injection."""
        response_length = len(response.text) if hasattr(response, "text") else 0

        # Significant difference in response size might indicate injection
        if baseline_length > 0:
            diff_ratio = abs(response_length - baseline_length) / baseline_length
            return diff_ratio > 0.3  # 30% difference threshold

        return False

    def _test_time_based_blind(
        self,
        endpoint: str,
        param_name: str,
        original_value: str,
        params: dict[str, str],
        data: dict[str, Any],
        headers: dict[str, str],
        method: str,
    ) -> VulnerabilityFinding | None:
        """Test for time-based blind SQL injection."""
        time_payloads = SQLInjectionPayloads.TIME_BASED

        for payload in time_payloads:
            if param_name in params:
                test_params = {**params, param_name: f"{original_value}{payload}"}
                test_data = data
            else:
                test_params = params
                test_data = {**data, param_name: f"{original_value}{payload}"}

            try:
                start = time.time()
                self._make_request(endpoint, test_params, test_data, headers, method)
                elapsed = time.time() - start

                # If response took significantly longer, might be time-based injection
                if elapsed >= self.config.blind_delay_seconds:
                    return VulnerabilityFinding(
                        vuln_type=VulnerabilityType.SQL_INJECTION,
                        severity=VulnerabilitySeverity.HIGH,
                        title="Time-Based Blind SQL Injection",
                        description=(
                            f"Parameter '{param_name}' appears vulnerable to "
                            f"time-based blind SQL injection. Response delayed by {elapsed:.2f}s."
                        ),
                        payload=payload,
                        location=f"{endpoint}?{param_name}=",
                        evidence=f"Response time: {elapsed:.2f}s (expected: {self.config.blind_delay_seconds}s+)",
                        remediation=(
                            "Use parameterized queries or prepared statements. "
                            "Implement query timeouts."
                        ),
                        cwe="CWE-89",
                        owasp="A03:2021 - Injection",
                    )
            except Exception:
                pass

        return None


class XSSInjectionTest:
    """Cross-Site Scripting (XSS) vulnerability tester.

    Tests for various XSS techniques including:
    - Reflected XSS
    - Stored XSS (requires verification endpoint)
    - DOM-based XSS indicators

    Example:
        >>> test = XSSInjectionTest(client)
        >>> result = test.run("/search", params={"q": "test"})
    """

    XSS_REFLECTED_INDICATORS: Final[list[str]] = [
        "<script>",
        "onerror=",
        "onload=",
        "onclick=",
        "onmouseover=",
        "javascript:",
        "<img",
        "<svg",
        "<iframe",
    ]

    def __init__(
        self,
        client: Any,
        config: InjectionTestConfig | None = None,
    ) -> None:
        """Initialize XSS test.

        Args:
            client: HTTP client for making requests.
            config: Test configuration.
        """
        self.client = client
        self.config = config or InjectionTestConfig()

    def run(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> SecurityTestResult:
        """Run XSS tests.

        Args:
            endpoint: Target endpoint URL.
            params: Query parameters to test.
            data: Request body data to test.
            headers: Additional headers.
            method: HTTP method to use.

        Returns:
            SecurityTestResult with findings.
        """
        start_time = time.time()
        findings: list[VulnerabilityFinding] = []
        errors: list[str] = []
        payloads_tested = 0

        params = params or {}
        data = data or {}
        headers = headers or {}

        all_params = {**params, **data}

        for param_name, original_value in all_params.items():
            payloads = list(XSSPayloads.all_payloads())
            if self.config.max_payloads:
                payloads = payloads[: self.config.max_payloads]

            for payload in payloads:
                payloads_tested += 1

                if param_name in params:
                    test_params = {**params, param_name: payload}
                    test_data = data
                else:
                    test_params = params
                    test_data = {**data, param_name: payload}

                try:
                    response = self.client.request(
                        method=method,
                        url=endpoint,
                        params=test_params if method.upper() == "GET" else None,
                        json=test_data if method.upper() != "GET" else None,
                        headers=headers,
                        timeout=self.config.timeout,
                    )

                    response_text = response.text if hasattr(response, "text") else str(response)

                    # Check if payload is reflected without encoding
                    if self._is_reflected_unencoded(payload, response_text):
                        # Determine severity based on context
                        severity = self._determine_xss_severity(payload, response_text)

                        findings.append(
                            VulnerabilityFinding(
                                vuln_type=VulnerabilityType.XSS_REFLECTED,
                                severity=severity,
                                title="Reflected XSS",
                                description=(
                                    f"Parameter '{param_name}' reflects user input without "
                                    "proper encoding, allowing XSS attacks."
                                ),
                                payload=payload[:100],
                                location=f"{endpoint}?{param_name}=",
                                evidence=f"Payload reflected in response",
                                remediation=(
                                    "Encode all user input in output using context-appropriate encoding. "
                                    "Implement Content-Security-Policy headers. "
                                    "Use HttpOnly flag for session cookies."
                                ),
                                references=[
                                    "https://owasp.org/www-community/attacks/xss/",
                                    "https://cwe.mitre.org/data/definitions/79.html",
                                ],
                                cwe="CWE-79",
                                owasp="A03:2021 - Injection",
                            )
                        )
                        break  # One finding per parameter

                except Exception as e:
                    errors.append(f"Error testing {param_name} with XSS payload: {e}")

        # Test for DOM-based XSS indicators
        try:
            response = self.client.get(endpoint, params=params, timeout=self.config.timeout)
            response_text = response.text if hasattr(response, "text") else ""

            dom_findings = self._check_dom_xss_sinks(response_text, endpoint)
            findings.extend(dom_findings)
        except Exception as e:
            errors.append(f"Error checking DOM XSS: {e}")

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=endpoint,
            vulnerable=len(findings) > 0,
            findings=findings,
            test_duration_ms=duration,
            payloads_tested=payloads_tested,
            errors=errors,
        )

    def _is_reflected_unencoded(self, payload: str, response_text: str) -> bool:
        """Check if payload is reflected without encoding."""
        # Check for exact match (unencoded)
        if payload in response_text:
            return True

        # Check for partially encoded (common bypass)
        # e.g., <script> might be present even if quotes are encoded
        for indicator in self.XSS_REFLECTED_INDICATORS:
            if indicator.lower() in payload.lower() and indicator.lower() in response_text.lower():
                return True

        return False

    def _determine_xss_severity(self, payload: str, response_text: str) -> VulnerabilitySeverity:
        """Determine XSS severity based on payload and context."""
        payload_lower = payload.lower()

        # Critical: Script execution
        if "<script>" in payload_lower or "javascript:" in payload_lower:
            return VulnerabilitySeverity.HIGH

        # High: Event handlers
        if any(eh in payload_lower for eh in ["onerror=", "onload=", "onclick="]):
            return VulnerabilitySeverity.HIGH

        # Medium: Other injection vectors
        return VulnerabilitySeverity.MEDIUM

    def _check_dom_xss_sinks(
        self, response_text: str, endpoint: str
    ) -> list[VulnerabilityFinding]:
        """Check for dangerous DOM sinks in JavaScript."""
        findings: list[VulnerabilityFinding] = []

        dom_sinks = [
            (r"document\.write\s*\(", "document.write()"),
            (r"document\.writeln\s*\(", "document.writeln()"),
            (r"\.innerHTML\s*=", "innerHTML assignment"),
            (r"\.outerHTML\s*=", "outerHTML assignment"),
            (r"eval\s*\(", "eval()"),
            (r"setTimeout\s*\([^,]*\+", "setTimeout with concatenation"),
            (r"setInterval\s*\([^,]*\+", "setInterval with concatenation"),
            (r"location\s*=", "location assignment"),
            (r"location\.href\s*=", "location.href assignment"),
            (r"document\.URL", "document.URL usage"),
            (r"document\.location", "document.location usage"),
            (r"window\.location", "window.location usage"),
        ]

        for pattern, sink_name in dom_sinks:
            if re.search(pattern, response_text):
                findings.append(
                    VulnerabilityFinding(
                        vuln_type=VulnerabilityType.XSS_DOM,
                        severity=VulnerabilitySeverity.MEDIUM,
                        title=f"Potential DOM XSS Sink: {sink_name}",
                        description=(
                            f"The page uses {sink_name} which could lead to DOM-based XSS "
                            "if user input reaches this sink without sanitization."
                        ),
                        payload="N/A - Code analysis",
                        location=endpoint,
                        evidence=f"Found pattern: {pattern}",
                        remediation=(
                            "Avoid using dangerous DOM methods. "
                            "Use textContent instead of innerHTML. "
                            "Sanitize data before using in DOM manipulation."
                        ),
                        cwe="CWE-79",
                        owasp="A03:2021 - Injection",
                    )
                )

        return findings


class CommandInjectionTest:
    """Command injection vulnerability tester.

    Tests for OS command injection by injecting command separators
    and detecting execution indicators.

    Example:
        >>> test = CommandInjectionTest(client)
        >>> result = test.run("/api/ping", params={"host": "localhost"})
    """

    COMMAND_OUTPUT_INDICATORS: Final[list[tuple[str, str]]] = [
        (r"root:.*:0:0:", "Unix /etc/passwd"),
        (r"bin:.*:/bin", "Unix /etc/passwd"),
        (r"\[fonts\]", "Windows win.ini"),
        (r"\[extensions\]", "Windows system.ini"),
        (r"Volume Serial Number", "Windows dir output"),
        (r"Directory of", "Windows dir output"),
        (r"total \d+", "Unix ls output"),
        (r"drwx", "Unix ls -l output"),
        (r"uid=\d+", "Unix id output"),
        (r"gid=\d+", "Unix id output"),
        (r"Linux version", "Unix uname output"),
        (r"Darwin Kernel Version", "macOS uname output"),
    ]

    def __init__(
        self,
        client: Any,
        config: InjectionTestConfig | None = None,
    ) -> None:
        """Initialize command injection test.

        Args:
            client: HTTP client for making requests.
            config: Test configuration.
        """
        self.client = client
        self.config = config or InjectionTestConfig()

    def run(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> SecurityTestResult:
        """Run command injection tests.

        Args:
            endpoint: Target endpoint URL.
            params: Query parameters to test.
            data: Request body data to test.
            headers: Additional headers.
            method: HTTP method to use.

        Returns:
            SecurityTestResult with findings.
        """
        start_time = time.time()
        findings: list[VulnerabilityFinding] = []
        errors: list[str] = []
        payloads_tested = 0

        params = params or {}
        data = data or {}
        headers = headers or {}

        all_params = {**params, **data}

        for param_name, original_value in all_params.items():
            payloads = list(CommandInjectionPayloads.all_payloads())
            if self.config.max_payloads:
                payloads = payloads[: self.config.max_payloads]

            for payload in payloads:
                payloads_tested += 1

                if param_name in params:
                    test_params = {**params, param_name: f"{original_value}{payload}"}
                    test_data = data
                else:
                    test_params = params
                    test_data = {**data, param_name: f"{original_value}{payload}"}

                try:
                    response = self.client.request(
                        method=method,
                        url=endpoint,
                        params=test_params if method.upper() == "GET" else None,
                        json=test_data if method.upper() != "GET" else None,
                        headers=headers,
                        timeout=self.config.timeout,
                    )

                    response_text = response.text if hasattr(response, "text") else str(response)

                    # Check for command output indicators
                    for pattern, indicator_name in self.COMMAND_OUTPUT_INDICATORS:
                        if re.search(pattern, response_text):
                            findings.append(
                                VulnerabilityFinding(
                                    vuln_type=VulnerabilityType.COMMAND_INJECTION,
                                    severity=VulnerabilitySeverity.CRITICAL,
                                    title="OS Command Injection",
                                    description=(
                                        f"Parameter '{param_name}' is vulnerable to "
                                        f"OS command injection. Detected {indicator_name} output."
                                    ),
                                    payload=payload,
                                    location=f"{endpoint}?{param_name}=",
                                    evidence=f"Matched pattern: {pattern}",
                                    remediation=(
                                        "Never pass user input to OS commands. "
                                        "Use allowlists for permitted values. "
                                        "If shell execution is required, use parameterized APIs."
                                    ),
                                    references=[
                                        "https://owasp.org/www-community/attacks/Command_Injection",
                                        "https://cwe.mitre.org/data/definitions/78.html",
                                    ],
                                    cwe="CWE-78",
                                    owasp="A03:2021 - Injection",
                                )
                            )
                            break

                    if findings:
                        break  # Found vulnerability for this parameter

                except Exception as e:
                    errors.append(f"Error testing {param_name} with command payload: {e}")

            # Test time-based blind command injection
            if self.config.detect_blind and not findings:
                finding = self._test_blind_command_injection(
                    endpoint, param_name, original_value, params, data, headers, method
                )
                if finding:
                    findings.append(finding)
                    payloads_tested += 2  # sleep payloads

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=endpoint,
            vulnerable=len(findings) > 0,
            findings=findings,
            test_duration_ms=duration,
            payloads_tested=payloads_tested,
            errors=errors,
        )

    def _test_blind_command_injection(
        self,
        endpoint: str,
        param_name: str,
        original_value: str,
        params: dict[str, str],
        data: dict[str, Any],
        headers: dict[str, str],
        method: str,
    ) -> VulnerabilityFinding | None:
        """Test for time-based blind command injection."""
        delay = int(self.config.blind_delay_seconds)
        sleep_payloads = [
            f"; sleep {delay}",
            f"| sleep {delay}",
            f"&& sleep {delay}",
            f"$(sleep {delay})",
            f"`sleep {delay}`",
            f"& ping -n {delay + 1} 127.0.0.1",  # Windows
        ]

        for payload in sleep_payloads:
            if param_name in params:
                test_params = {**params, param_name: f"{original_value}{payload}"}
                test_data = data
            else:
                test_params = params
                test_data = {**data, param_name: f"{original_value}{payload}"}

            try:
                start = time.time()
                self.client.request(
                    method=method,
                    url=endpoint,
                    params=test_params if method.upper() == "GET" else None,
                    json=test_data if method.upper() != "GET" else None,
                    headers=headers,
                    timeout=self.config.timeout + delay + 5,
                )
                elapsed = time.time() - start

                if elapsed >= delay:
                    return VulnerabilityFinding(
                        vuln_type=VulnerabilityType.COMMAND_INJECTION,
                        severity=VulnerabilitySeverity.CRITICAL,
                        title="Blind OS Command Injection",
                        description=(
                            f"Parameter '{param_name}' appears vulnerable to "
                            f"blind command injection. Response delayed by {elapsed:.2f}s."
                        ),
                        payload=payload,
                        location=f"{endpoint}?{param_name}=",
                        evidence=f"Response time: {elapsed:.2f}s",
                        remediation=(
                            "Never pass user input to OS commands. "
                            "Use allowlists for permitted values."
                        ),
                        cwe="CWE-78",
                        owasp="A03:2021 - Injection",
                    )
            except Exception:
                pass

        return None


class AutoInjector:
    """Automatically inject payloads into all parameters.

    Combines SQL injection, XSS, and command injection testing
    and automatically injects into all discovered parameters.

    Example:
        >>> injector = AutoInjector(client)
        >>> result = injector.inject_all("/api/search", {"q": "test", "page": "1"})
    """

    def __init__(
        self,
        client: Any,
        config: InjectionTestConfig | None = None,
    ) -> None:
        """Initialize auto-injector.

        Args:
            client: HTTP client for making requests.
            config: Test configuration.
        """
        self.client = client
        self.config = config or InjectionTestConfig()
        self.sql_test = SQLInjectionTest(client, config)
        self.xss_test = XSSInjectionTest(client, config)
        self.cmd_test = CommandInjectionTest(client, config)

    def inject_all(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        injection_types: list[str] | None = None,
    ) -> SecurityTestResult:
        """Run all injection tests on all parameters.

        Args:
            endpoint: Target endpoint URL.
            params: Query parameters to test.
            data: Request body data to test.
            headers: Additional headers.
            method: HTTP method to use.
            injection_types: List of injection types to test.
                            Options: 'sql', 'xss', 'command'

        Returns:
            Combined SecurityTestResult with all findings.
        """
        start_time = time.time()
        all_findings: list[VulnerabilityFinding] = []
        all_errors: list[str] = []
        total_payloads = 0

        injection_types = injection_types or ["sql", "xss", "command"]

        if "sql" in injection_types:
            result = self.sql_test.run(endpoint, params, data, headers, method)
            all_findings.extend(result.findings)
            all_errors.extend(result.errors)
            total_payloads += result.payloads_tested

        if "xss" in injection_types:
            result = self.xss_test.run(endpoint, params, data, headers, method)
            all_findings.extend(result.findings)
            all_errors.extend(result.errors)
            total_payloads += result.payloads_tested

        if "command" in injection_types:
            result = self.cmd_test.run(endpoint, params, data, headers, method)
            all_findings.extend(result.findings)
            all_errors.extend(result.errors)
            total_payloads += result.payloads_tested

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=endpoint,
            vulnerable=len(all_findings) > 0,
            findings=all_findings,
            test_duration_ms=duration,
            payloads_tested=total_payloads,
            errors=all_errors,
        )


class InjectionTester:
    """Comprehensive injection vulnerability tester.

    Main interface for all injection testing with convenient methods
    for each injection type.

    Example:
        >>> tester = InjectionTester(client)
        >>> result = tester.test_all("/api/search", {"q": "test"})
    """

    def __init__(
        self,
        client: Any,
        config: InjectionTestConfig | None = None,
    ) -> None:
        """Initialize injection tester.

        Args:
            client: HTTP client for making requests.
            config: Test configuration.
        """
        self.client = client
        self.config = config or InjectionTestConfig()
        self.auto_injector = AutoInjector(client, config)
        self.sql_test = SQLInjectionTest(client, config)
        self.xss_test = XSSInjectionTest(client, config)
        self.cmd_test = CommandInjectionTest(client, config)

    def test_sql_injection(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> SecurityTestResult:
        """Test for SQL injection vulnerabilities."""
        return self.sql_test.run(endpoint, params, data, headers, method)

    def test_xss(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> SecurityTestResult:
        """Test for XSS vulnerabilities."""
        return self.xss_test.run(endpoint, params, data, headers, method)

    def test_command_injection(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> SecurityTestResult:
        """Test for command injection vulnerabilities."""
        return self.cmd_test.run(endpoint, params, data, headers, method)

    def test_all(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> SecurityTestResult:
        """Test for all injection types."""
        return self.auto_injector.inject_all(endpoint, params, data, headers, method)
