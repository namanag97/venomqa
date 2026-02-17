"""OWASP security checks for VenomQA.

This module provides OWASP-based security verification including:
- Security headers validation
- CORS policy testing
- Rate limiting verification
- Error message leakage detection

Example:
    >>> checker = OWASPChecker(client)
    >>> result = checker.run_all_checks("http://localhost:8000")
    >>> for finding in result.findings:
    ...     print(f"{finding.severity}: {finding.title}")
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Final

from venomqa.security.testing import (
    SecurityTestResult,
    VulnerabilityFinding,
    VulnerabilitySeverity,
    VulnerabilityType,
)

logger = logging.getLogger(__name__)


@dataclass
class OWASPCheckConfig:
    """Configuration for OWASP checks.

    Attributes:
        timeout: Request timeout in seconds.
        rate_limit_requests: Number of requests for rate limit testing.
        rate_limit_threshold: Expected requests before rate limiting.
        cors_test_origin: Origin to use for CORS testing.
    """

    timeout: float = 30.0
    rate_limit_requests: int = 100
    rate_limit_threshold: int = 50
    cors_test_origin: str = "https://evil.com"


class SecurityHeadersCheck:
    """Check for missing or misconfigured security headers.

    Validates presence and configuration of:
    - Content-Security-Policy
    - X-Content-Type-Options
    - X-Frame-Options
    - Strict-Transport-Security
    - X-XSS-Protection
    - Referrer-Policy
    - Permissions-Policy

    Example:
        >>> check = SecurityHeadersCheck(client)
        >>> result = check.run("/")
    """

    REQUIRED_HEADERS: Final[dict[str, dict[str, Any]]] = {
        "content-security-policy": {
            "severity": VulnerabilitySeverity.MEDIUM,
            "title": "Missing Content-Security-Policy Header",
            "description": (
                "Content-Security-Policy header is missing. CSP helps prevent XSS and "
                "data injection attacks by controlling which resources can be loaded."
            ),
            "remediation": (
                "Add Content-Security-Policy header. Example: "
                "Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'"
            ),
            "reference": "https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP",
        },
        "x-content-type-options": {
            "severity": VulnerabilitySeverity.LOW,
            "title": "Missing X-Content-Type-Options Header",
            "description": (
                "X-Content-Type-Options header is missing. This allows browsers to "
                "perform MIME-sniffing which can lead to security vulnerabilities."
            ),
            "remediation": "Add X-Content-Type-Options: nosniff header.",
            "expected_value": "nosniff",
            "reference": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options",
        },
        "x-frame-options": {
            "severity": VulnerabilitySeverity.MEDIUM,
            "title": "Missing X-Frame-Options Header",
            "description": (
                "X-Frame-Options header is missing. This allows the page to be "
                "embedded in iframes, enabling clickjacking attacks."
            ),
            "remediation": "Add X-Frame-Options: DENY or SAMEORIGIN header.",
            "expected_values": ["deny", "sameorigin"],
            "reference": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options",
        },
        "strict-transport-security": {
            "severity": VulnerabilitySeverity.MEDIUM,
            "title": "Missing Strict-Transport-Security Header",
            "description": (
                "HSTS header is missing. This allows downgrade attacks where "
                "HTTPS connections could be intercepted via HTTP."
            ),
            "remediation": (
                "Add Strict-Transport-Security header. Example: "
                "Strict-Transport-Security: max-age=31536000; includeSubDomains"
            ),
            "reference": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security",
        },
        "referrer-policy": {
            "severity": VulnerabilitySeverity.LOW,
            "title": "Missing Referrer-Policy Header",
            "description": (
                "Referrer-Policy header is missing. URLs in the Referer header "
                "might leak sensitive information to third parties."
            ),
            "remediation": "Add Referrer-Policy: strict-origin-when-cross-origin header.",
            "reference": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy",
        },
        "permissions-policy": {
            "severity": VulnerabilitySeverity.INFO,
            "title": "Missing Permissions-Policy Header",
            "description": (
                "Permissions-Policy header is missing. This header controls which "
                "browser features can be used on the page."
            ),
            "remediation": (
                "Add Permissions-Policy header. Example: "
                "Permissions-Policy: geolocation=(), camera=(), microphone=()"
            ),
            "reference": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Permissions-Policy",
        },
    }

    DANGEROUS_HEADERS: Final[dict[str, dict[str, Any]]] = {
        "server": {
            "severity": VulnerabilitySeverity.INFO,
            "title": "Server Version Disclosure",
            "description": "Server header reveals version information that could help attackers.",
            "remediation": "Configure server to hide or obfuscate version information.",
        },
        "x-powered-by": {
            "severity": VulnerabilitySeverity.INFO,
            "title": "Technology Stack Disclosure",
            "description": "X-Powered-By header reveals technology stack (e.g., PHP, Express).",
            "remediation": "Remove or obfuscate the X-Powered-By header.",
        },
        "x-aspnet-version": {
            "severity": VulnerabilitySeverity.LOW,
            "title": "ASP.NET Version Disclosure",
            "description": "X-AspNet-Version header reveals ASP.NET version.",
            "remediation": "Add <httpRuntime enableVersionHeader=\"false\" /> to web.config.",
        },
        "x-aspnetmvc-version": {
            "severity": VulnerabilitySeverity.LOW,
            "title": "ASP.NET MVC Version Disclosure",
            "description": "X-AspNetMvc-Version header reveals ASP.NET MVC version.",
            "remediation": "Add MvcHandler.DisableMvcResponseHeader = true in Application_Start.",
        },
    }

    def __init__(self, client: Any, config: OWASPCheckConfig | None = None) -> None:
        """Initialize security headers check.

        Args:
            client: HTTP client for making requests.
            config: OWASP check configuration.
        """
        self.client = client
        self.config = config or OWASPCheckConfig()

    def run(self, endpoint: str = "/") -> SecurityTestResult:
        """Run security headers checks.

        Args:
            endpoint: Endpoint to check headers for.

        Returns:
            SecurityTestResult with findings.
        """
        start_time = time.time()
        findings: list[VulnerabilityFinding] = []
        errors: list[str] = []

        try:
            response = self.client.get(endpoint, timeout=self.config.timeout)
            headers = {k.lower(): v for k, v in response.headers.items()}

            # Check for missing security headers
            for header_name, config in self.REQUIRED_HEADERS.items():
                if header_name not in headers:
                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                            severity=config["severity"],
                            title=config["title"],
                            description=config["description"],
                            payload="N/A",
                            location=endpoint,
                            evidence=f"Header '{header_name}' not present",
                            remediation=config["remediation"],
                            references=[config.get("reference", "")],
                            owasp="A05:2021 - Security Misconfiguration",
                        )
                    )
                elif "expected_value" in config:
                    if headers[header_name].lower() != config["expected_value"]:
                        findings.append(
                            VulnerabilityFinding(
                                vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                                severity=config["severity"],
                                title=f"Misconfigured {header_name}",
                                description=(
                                    f"Header {header_name} has unexpected value. "
                                    f"Expected: {config['expected_value']}, "
                                    f"Got: {headers[header_name]}"
                                ),
                                payload="N/A",
                                location=endpoint,
                                evidence=f"Value: {headers[header_name]}",
                                remediation=config["remediation"],
                                owasp="A05:2021 - Security Misconfiguration",
                            )
                        )
                elif "expected_values" in config:
                    if headers[header_name].lower() not in config["expected_values"]:
                        findings.append(
                            VulnerabilityFinding(
                                vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                                severity=config["severity"],
                                title=f"Weak {header_name} Configuration",
                                description=(
                                    f"Header {header_name} has weak value: {headers[header_name]}"
                                ),
                                payload="N/A",
                                location=endpoint,
                                evidence=f"Value: {headers[header_name]}",
                                remediation=config["remediation"],
                                owasp="A05:2021 - Security Misconfiguration",
                            )
                        )

            # Check for information disclosure headers
            for header_name, config in self.DANGEROUS_HEADERS.items():
                if header_name in headers:
                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                            severity=config["severity"],
                            title=config["title"],
                            description=config["description"],
                            payload="N/A",
                            location=endpoint,
                            evidence=f"{header_name}: {headers[header_name]}",
                            remediation=config["remediation"],
                            owasp="A05:2021 - Security Misconfiguration",
                        )
                    )

            # Check for weak CSP if present
            if "content-security-policy" in headers:
                csp_findings = self._analyze_csp(headers["content-security-policy"], endpoint)
                findings.extend(csp_findings)

        except Exception as e:
            errors.append(f"Error checking security headers: {e}")

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=endpoint,
            vulnerable=len(findings) > 0,
            findings=findings,
            test_duration_ms=duration,
            payloads_tested=1,
            errors=errors,
        )

    def _analyze_csp(self, csp_value: str, endpoint: str) -> list[VulnerabilityFinding]:
        """Analyze CSP header for weaknesses."""
        findings: list[VulnerabilityFinding] = []
        csp_lower = csp_value.lower()

        weak_directives = [
            ("'unsafe-inline'", "Unsafe Inline Scripts Allowed", VulnerabilitySeverity.HIGH),
            ("'unsafe-eval'", "Unsafe Eval Allowed", VulnerabilitySeverity.HIGH),
            ("data:", "Data URIs Allowed", VulnerabilitySeverity.MEDIUM),
            ("*", "Wildcard Source Allowed", VulnerabilitySeverity.MEDIUM),
        ]

        for pattern, title, severity in weak_directives:
            if pattern in csp_lower:
                findings.append(
                    VulnerabilityFinding(
                        vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                        severity=severity,
                        title=f"Weak CSP: {title}",
                        description=(
                            f"Content-Security-Policy contains '{pattern}' which "
                            "weakens XSS protection."
                        ),
                        payload="N/A",
                        location=endpoint,
                        evidence=f"CSP value contains: {pattern}",
                        remediation=(
                            f"Remove '{pattern}' from CSP. Use nonces or hashes for inline scripts."
                        ),
                        owasp="A05:2021 - Security Misconfiguration",
                    )
                )

        return findings


class CORSPolicyCheck:
    """Check for CORS misconfigurations.

    Tests for:
    - Wildcard origin acceptance
    - Null origin acceptance
    - Arbitrary origin reflection
    - Credentials with wildcard

    Example:
        >>> check = CORSPolicyCheck(client)
        >>> result = check.run("/api/data")
    """

    def __init__(self, client: Any, config: OWASPCheckConfig | None = None) -> None:
        """Initialize CORS policy check.

        Args:
            client: HTTP client for making requests.
            config: OWASP check configuration.
        """
        self.client = client
        self.config = config or OWASPCheckConfig()

    def run(self, endpoint: str = "/api") -> SecurityTestResult:
        """Run CORS policy checks.

        Args:
            endpoint: Endpoint to check CORS for.

        Returns:
            SecurityTestResult with findings.
        """
        start_time = time.time()
        findings: list[VulnerabilityFinding] = []
        errors: list[str] = []
        payloads_tested = 0

        test_origins = [
            self.config.cors_test_origin,
            "null",
            "https://attacker.com",
            "http://localhost",
            "https://example.com.attacker.com",
        ]

        for origin in test_origins:
            payloads_tested += 1
            try:
                response = self.client.get(
                    endpoint,
                    headers={"Origin": origin},
                    timeout=self.config.timeout,
                )

                acao = response.headers.get("Access-Control-Allow-Origin", "")
                acac = response.headers.get("Access-Control-Allow-Credentials", "")

                # Check for reflected origin
                if acao == origin and origin not in ["", "null"]:
                    severity = VulnerabilitySeverity.HIGH if acac.lower() == "true" else VulnerabilitySeverity.MEDIUM

                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.BROKEN_ACCESS_CONTROL,
                            severity=severity,
                            title="CORS Origin Reflection",
                            description=(
                                f"Server reflects arbitrary Origin header in ACAO. "
                                f"Tested origin '{origin}' was accepted."
                                + (" Credentials are also allowed!" if acac else "")
                            ),
                            payload=f"Origin: {origin}",
                            location=endpoint,
                            evidence=f"Access-Control-Allow-Origin: {acao}",
                            remediation=(
                                "Implement a whitelist of allowed origins. "
                                "Never reflect arbitrary Origin values."
                            ),
                            cwe="CWE-942",
                            owasp="A01:2021 - Broken Access Control",
                        )
                    )

                # Check for wildcard
                if acao == "*":
                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.BROKEN_ACCESS_CONTROL,
                            severity=VulnerabilitySeverity.MEDIUM,
                            title="CORS Wildcard Origin",
                            description=(
                                "Access-Control-Allow-Origin is set to '*', "
                                "allowing any website to make cross-origin requests."
                            ),
                            payload=f"Origin: {origin}",
                            location=endpoint,
                            evidence="Access-Control-Allow-Origin: *",
                            remediation=(
                                "Specify explicit origins instead of using wildcard. "
                                "Consider if CORS is actually needed."
                            ),
                            cwe="CWE-942",
                            owasp="A01:2021 - Broken Access Control",
                        )
                    )
                    break  # Found wildcard, no need to test more origins

                # Check for null origin
                if acao == "null":
                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.BROKEN_ACCESS_CONTROL,
                            severity=VulnerabilitySeverity.HIGH,
                            title="CORS Null Origin Allowed",
                            description=(
                                "Server accepts 'null' as a valid origin. "
                                "Attackers can use sandboxed iframes to send requests with null origin."
                            ),
                            payload="Origin: null",
                            location=endpoint,
                            evidence="Access-Control-Allow-Origin: null",
                            remediation=(
                                "Never allow 'null' as a valid origin. "
                                "Always validate against a whitelist."
                            ),
                            cwe="CWE-942",
                            owasp="A01:2021 - Broken Access Control",
                        )
                    )

            except Exception as e:
                errors.append(f"Error testing CORS with origin '{origin}': {e}")

        # Test preflight requests
        payloads_tested += 1
        try:
            response = self.client.request(
                method="OPTIONS",
                url=endpoint,
                headers={
                    "Origin": self.config.cors_test_origin,
                    "Access-Control-Request-Method": "PUT",
                    "Access-Control-Request-Headers": "X-Custom-Header",
                },
                timeout=self.config.timeout,
            )

            acam = response.headers.get("Access-Control-Allow-Methods", "")
            acah = response.headers.get("Access-Control-Allow-Headers", "")

            if "*" in acam:
                findings.append(
                    VulnerabilityFinding(
                        vuln_type=VulnerabilityType.BROKEN_ACCESS_CONTROL,
                        severity=VulnerabilitySeverity.MEDIUM,
                        title="CORS Wildcard Methods",
                        description="Access-Control-Allow-Methods includes wildcard.",
                        payload="Preflight request",
                        location=endpoint,
                        evidence=f"Access-Control-Allow-Methods: {acam}",
                        remediation="Specify only the HTTP methods that are actually needed.",
                        owasp="A01:2021 - Broken Access Control",
                    )
                )

            if "*" in acah:
                findings.append(
                    VulnerabilityFinding(
                        vuln_type=VulnerabilityType.BROKEN_ACCESS_CONTROL,
                        severity=VulnerabilitySeverity.MEDIUM,
                        title="CORS Wildcard Headers",
                        description="Access-Control-Allow-Headers includes wildcard.",
                        payload="Preflight request",
                        location=endpoint,
                        evidence=f"Access-Control-Allow-Headers: {acah}",
                        remediation="Specify only the headers that are actually needed.",
                        owasp="A01:2021 - Broken Access Control",
                    )
                )

        except Exception as e:
            errors.append(f"Error testing CORS preflight: {e}")

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=endpoint,
            vulnerable=len(findings) > 0,
            findings=findings,
            test_duration_ms=duration,
            payloads_tested=payloads_tested,
            errors=errors,
        )


class RateLimitCheck:
    """Check for rate limiting implementation.

    Verifies that:
    - Rate limiting is implemented on sensitive endpoints
    - Rate limit headers are present
    - Limits are enforced appropriately

    Example:
        >>> check = RateLimitCheck(client)
        >>> result = check.run("/api/login", method="POST")
    """

    SENSITIVE_ENDPOINTS: Final[list[str]] = [
        "/login",
        "/auth",
        "/api/auth",
        "/api/login",
        "/register",
        "/signup",
        "/password",
        "/reset",
        "/forgot",
        "/otp",
        "/verify",
    ]

    def __init__(self, client: Any, config: OWASPCheckConfig | None = None) -> None:
        """Initialize rate limit check.

        Args:
            client: HTTP client for making requests.
            config: OWASP check configuration.
        """
        self.client = client
        self.config = config or OWASPCheckConfig()

    def run(
        self,
        endpoint: str = "/api/login",
        method: str = "POST",
        data: dict[str, Any] | None = None,
    ) -> SecurityTestResult:
        """Run rate limiting checks.

        Args:
            endpoint: Endpoint to test rate limiting on.
            method: HTTP method to use.
            data: Request body for POST requests.

        Returns:
            SecurityTestResult with findings.
        """
        start_time = time.time()
        findings: list[VulnerabilityFinding] = []
        errors: list[str] = []
        rate_limited = False
        rate_limit_headers_found: list[str] = []

        data = data or {"username": "test", "password": "test"}

        try:
            for i in range(self.config.rate_limit_requests):
                response = self.client.request(
                    method=method,
                    url=endpoint,
                    json=data if method.upper() != "GET" else None,
                    timeout=self.config.timeout,
                )

                # Check for rate limit headers
                rate_headers = [
                    "x-ratelimit-limit",
                    "x-ratelimit-remaining",
                    "x-ratelimit-reset",
                    "x-rate-limit-limit",
                    "x-rate-limit-remaining",
                    "retry-after",
                    "ratelimit-limit",
                    "ratelimit-remaining",
                ]

                headers_lower = {k.lower(): v for k, v in response.headers.items()}
                for header in rate_headers:
                    if header in headers_lower and header not in rate_limit_headers_found:
                        rate_limit_headers_found.append(header)

                # Check if we got rate limited
                if response.status_code == 429:
                    rate_limited = True
                    break

                # Small delay to avoid overwhelming
                if i % 10 == 0:
                    time.sleep(0.1)

        except Exception as e:
            errors.append(f"Error during rate limit testing: {e}")

        # Analyze results
        is_sensitive = any(s in endpoint.lower() for s in self.SENSITIVE_ENDPOINTS)

        if not rate_limited and is_sensitive:
            severity = VulnerabilitySeverity.HIGH
            findings.append(
                VulnerabilityFinding(
                    vuln_type=VulnerabilityType.RATE_LIMITING,
                    severity=severity,
                    title="Missing Rate Limiting on Sensitive Endpoint",
                    description=(
                        f"Endpoint '{endpoint}' does not implement rate limiting. "
                        f"Sent {self.config.rate_limit_requests} requests without being blocked. "
                        "This allows brute-force attacks on authentication."
                    ),
                    payload=f"{self.config.rate_limit_requests} requests",
                    location=endpoint,
                    evidence=f"No 429 response after {self.config.rate_limit_requests} requests",
                    remediation=(
                        "Implement rate limiting on authentication endpoints. "
                        "Use exponential backoff or account lockout after failed attempts. "
                        "Consider CAPTCHA for repeated failures."
                    ),
                    cwe="CWE-307",
                    owasp="A07:2021 - Identification and Authentication Failures",
                )
            )
        elif not rate_limited:
            findings.append(
                VulnerabilityFinding(
                    vuln_type=VulnerabilityType.RATE_LIMITING,
                    severity=VulnerabilitySeverity.MEDIUM,
                    title="Missing Rate Limiting",
                    description=(
                        f"Endpoint '{endpoint}' does not implement rate limiting. "
                        f"Sent {self.config.rate_limit_requests} requests without being blocked."
                    ),
                    payload=f"{self.config.rate_limit_requests} requests",
                    location=endpoint,
                    evidence=f"No 429 response after {self.config.rate_limit_requests} requests",
                    remediation=(
                        "Implement rate limiting to prevent DoS attacks. "
                        "Consider using token bucket or sliding window algorithms."
                    ),
                    cwe="CWE-770",
                    owasp="A05:2021 - Security Misconfiguration",
                )
            )

        if not rate_limit_headers_found and not findings:
            findings.append(
                VulnerabilityFinding(
                    vuln_type=VulnerabilityType.RATE_LIMITING,
                    severity=VulnerabilitySeverity.LOW,
                    title="Missing Rate Limit Headers",
                    description=(
                        "No rate limit headers found in response. "
                        "Clients cannot determine rate limit status."
                    ),
                    payload="N/A",
                    location=endpoint,
                    evidence="No X-RateLimit-* or similar headers",
                    remediation=(
                        "Include rate limit headers in responses: "
                        "X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset"
                    ),
                    owasp="A05:2021 - Security Misconfiguration",
                )
            )

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=endpoint,
            vulnerable=len(findings) > 0,
            findings=findings,
            test_duration_ms=duration,
            payloads_tested=self.config.rate_limit_requests,
            errors=errors,
        )


class ErrorLeakageCheck:
    """Check for sensitive information leakage in error messages.

    Verifies that error messages don't expose:
    - Stack traces
    - Database queries
    - Internal paths
    - Configuration details

    Example:
        >>> check = ErrorLeakageCheck(client)
        >>> result = check.run("/api/users/invalid-id")
    """

    SENSITIVE_PATTERNS: Final[list[tuple[str, str, VulnerabilitySeverity]]] = [
        (r"Traceback \(most recent call last\)", "Python stack trace", VulnerabilitySeverity.HIGH),
        (r"at .+\(.+:\d+:\d+\)", "JavaScript stack trace", VulnerabilitySeverity.HIGH),
        (r"Exception in thread", "Java exception", VulnerabilitySeverity.HIGH),
        (r"System\.Exception", ".NET exception", VulnerabilitySeverity.HIGH),
        (r"Stack trace:", "Generic stack trace", VulnerabilitySeverity.HIGH),
        (r"File \".+\", line \d+", "Python file reference", VulnerabilitySeverity.MEDIUM),
        (r"/var/www/|/home/|/usr/|C:\\\\", "Server path", VulnerabilitySeverity.MEDIUM),
        (r"SELECT .+ FROM|INSERT INTO|UPDATE .+ SET|DELETE FROM", "SQL query", VulnerabilitySeverity.HIGH),
        (r"password|secret|api_key|apikey|token", "Sensitive keyword", VulnerabilitySeverity.MEDIUM),
        (r"postgresql://|mysql://|mongodb://|redis://", "Database connection string", VulnerabilitySeverity.CRITICAL),
        (r"AWS_|AZURE_|GCP_", "Cloud credentials", VulnerabilitySeverity.CRITICAL),
        (r"DEBUG\s*=\s*True|debug\s*:\s*true", "Debug mode enabled", VulnerabilitySeverity.MEDIUM),
        (r"DJANGO_SETTINGS_MODULE", "Django settings", VulnerabilitySeverity.LOW),
        (r"node_modules|site-packages|vendor/", "Dependency path", VulnerabilitySeverity.LOW),
    ]

    ERROR_TRIGGERING_INPUTS: Final[list[tuple[str, str]]] = [
        ("id", "invalid-uuid-format"),
        ("id", "-1"),
        ("id", "999999999999"),
        ("id", "' OR '1'='1"),
        ("id", "<script>alert(1)</script>"),
        ("page", "-1"),
        ("limit", "999999999"),
        ("email", "not-an-email"),
        ("date", "invalid-date"),
    ]

    def __init__(self, client: Any, config: OWASPCheckConfig | None = None) -> None:
        """Initialize error leakage check.

        Args:
            client: HTTP client for making requests.
            config: OWASP check configuration.
        """
        self.client = client
        self.config = config or OWASPCheckConfig()

    def run(self, endpoint: str) -> SecurityTestResult:
        """Run error leakage checks.

        Args:
            endpoint: Endpoint to test for error leakage.

        Returns:
            SecurityTestResult with findings.
        """
        start_time = time.time()
        findings: list[VulnerabilityFinding] = []
        errors: list[str] = []
        payloads_tested = 0

        # Test with various error-triggering inputs
        for param, value in self.ERROR_TRIGGERING_INPUTS:
            payloads_tested += 1
            try:
                response = self.client.get(
                    endpoint,
                    params={param: value},
                    timeout=self.config.timeout,
                )

                response_text = response.text if hasattr(response, "text") else str(response)

                for pattern, description, severity in self.SENSITIVE_PATTERNS:
                    match = re.search(pattern, response_text, re.IGNORECASE)
                    if match:
                        findings.append(
                            VulnerabilityFinding(
                                vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                                severity=severity,
                                title=f"Error Leakage: {description}",
                                description=(
                                    f"Error response contains {description}. "
                                    "This exposes internal implementation details."
                                ),
                                payload=f"{param}={value}",
                                location=endpoint,
                                evidence=f"Found: {match.group()[:100]}",
                                remediation=(
                                    "Implement proper error handling. "
                                    "Return generic error messages to clients. "
                                    "Log detailed errors server-side only."
                                ),
                                cwe="CWE-209",
                                owasp="A09:2021 - Security Logging and Monitoring Failures",
                            )
                        )

            except Exception as e:
                errors.append(f"Error testing with {param}={value}: {e}")

        # Test 404 error page
        payloads_tested += 1
        try:
            response = self.client.get(
                f"{endpoint}/nonexistent-path-12345",
                timeout=self.config.timeout,
            )

            response_text = response.text if hasattr(response, "text") else str(response)

            for pattern, description, severity in self.SENSITIVE_PATTERNS:
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                            severity=severity,
                            title=f"404 Error Leakage: {description}",
                            description=(
                                f"404 error page contains {description}. "
                                "This exposes internal implementation details."
                            ),
                            payload="Invalid path",
                            location=endpoint,
                            evidence=f"Found: {match.group()[:100]}",
                            remediation=(
                                "Configure custom error pages. "
                                "Never expose stack traces or internal paths."
                            ),
                            cwe="CWE-209",
                            owasp="A09:2021 - Security Logging and Monitoring Failures",
                        )
                    )

        except Exception as e:
            errors.append(f"Error testing 404 page: {e}")

        # Test 500 error (try to trigger with malformed request)
        payloads_tested += 1
        try:
            response = self.client.post(
                endpoint,
                json={"__proto__": {"admin": True}},  # Prototype pollution attempt
                timeout=self.config.timeout,
            )

            if response.status_code == 500:
                response_text = response.text if hasattr(response, "text") else str(response)

                for pattern, description, severity in self.SENSITIVE_PATTERNS:
                    match = re.search(pattern, response_text, re.IGNORECASE)
                    if match:
                        findings.append(
                            VulnerabilityFinding(
                                vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                                severity=severity,
                                title=f"500 Error Leakage: {description}",
                                description=(
                                    f"500 error response contains {description}. "
                                    "This exposes internal implementation details."
                                ),
                                payload="Malformed request",
                                location=endpoint,
                                evidence=f"Found: {match.group()[:100]}",
                                remediation=(
                                    "Implement proper error handling. "
                                    "Return generic 500 error messages."
                                ),
                                cwe="CWE-209",
                                owasp="A09:2021 - Security Logging and Monitoring Failures",
                            )
                        )

        except Exception as e:
            errors.append(f"Error testing 500 response: {e}")

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=endpoint,
            vulnerable=len(findings) > 0,
            findings=findings,
            test_duration_ms=duration,
            payloads_tested=payloads_tested,
            errors=errors,
        )


class OWASPChecker:
    """Comprehensive OWASP security checker.

    Combines all OWASP checks into a single runner.

    Example:
        >>> checker = OWASPChecker(client)
        >>> result = checker.run_all_checks("http://localhost:8000")
    """

    def __init__(self, client: Any, config: OWASPCheckConfig | None = None) -> None:
        """Initialize OWASP checker.

        Args:
            client: HTTP client for making requests.
            config: OWASP check configuration.
        """
        self.client = client
        self.config = config or OWASPCheckConfig()
        self.headers_check = SecurityHeadersCheck(client, config)
        self.cors_check = CORSPolicyCheck(client, config)
        self.rate_limit_check = RateLimitCheck(client, config)
        self.error_leakage_check = ErrorLeakageCheck(client, config)

    def run_all_checks(
        self,
        base_url: str,
        endpoints: list[str] | None = None,
        auth_endpoints: list[str] | None = None,
    ) -> SecurityTestResult:
        """Run all OWASP security checks.

        Args:
            base_url: Base URL of the target.
            endpoints: List of endpoints to test.
            auth_endpoints: Authentication endpoints for rate limit testing.

        Returns:
            Combined SecurityTestResult with all findings.
        """
        start_time = time.time()
        all_findings: list[VulnerabilityFinding] = []
        all_errors: list[str] = []
        total_payloads = 0

        endpoints = endpoints or ["/", "/api"]
        auth_endpoints = auth_endpoints or ["/api/login", "/api/auth"]

        # Security headers check
        for endpoint in endpoints:
            result = self.headers_check.run(endpoint)
            all_findings.extend(result.findings)
            all_errors.extend(result.errors)
            total_payloads += result.payloads_tested

        # CORS check
        for endpoint in endpoints:
            result = self.cors_check.run(endpoint)
            all_findings.extend(result.findings)
            all_errors.extend(result.errors)
            total_payloads += result.payloads_tested

        # Rate limiting check (only on auth endpoints)
        for endpoint in auth_endpoints:
            result = self.rate_limit_check.run(endpoint)
            all_findings.extend(result.findings)
            all_errors.extend(result.errors)
            total_payloads += result.payloads_tested

        # Error leakage check
        for endpoint in endpoints:
            result = self.error_leakage_check.run(endpoint)
            all_findings.extend(result.findings)
            all_errors.extend(result.errors)
            total_payloads += result.payloads_tested

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=base_url,
            vulnerable=len(all_findings) > 0,
            findings=all_findings,
            test_duration_ms=duration,
            payloads_tested=total_payloads,
            errors=all_errors,
        )
