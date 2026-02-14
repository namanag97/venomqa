"""Security testing journey definitions.

This module provides pre-built journeys for testing common security
vulnerabilities following the VenomQA journey pattern.

Example:
    >>> from venomqa.domains.security import full_security_journey
    >>> result = runner.run(full_security_journey)
    >>> for issue in result.issues:
    ...     print(f"{issue.severity}: {issue.error}")
"""

from __future__ import annotations

from typing import Any

from venomqa import Journey, Step, Checkpoint, Branch, Path
from venomqa.domains.security.actions.authentication import (
    AuthenticationTester,
    AuthTestConfig,
    InvalidTokenTest,
    PermissionBoundaryTest,
    TokenExpirationTest,
    TokenRefreshTest,
)
from venomqa.domains.security.actions.injection import (
    InjectionTester,
    InjectionTestConfig,
)
from venomqa.domains.security.actions.owasp import (
    OWASPChecker,
    OWASPCheckConfig,
    SecurityHeadersCheck,
    CORSPolicyCheck,
    RateLimitCheck,
    ErrorLeakageCheck,
)


class SecurityJourney(Journey):
    """Base class for security testing journeys.

    Provides common security testing functionality and assertion helpers.

    Example:
        >>> class MySecurityJourney(SecurityJourney):
        ...     pass
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize security journey."""
        super().__init__(**kwargs)
        self._test_results: list[Any] = []

    def assert_no_vulnerabilities(self, result: Any) -> None:
        """Assert that no vulnerabilities were found.

        Args:
            result: SecurityTestResult to check.

        Raises:
            AssertionError: If vulnerabilities were found.
        """
        if result.vulnerable:
            finding_summary = ", ".join(
                f"{f.severity.value}: {f.title}" for f in result.findings[:5]
            )
            raise AssertionError(
                f"Found {len(result.findings)} vulnerabilities: {finding_summary}"
            )

    def assert_no_critical_vulnerabilities(self, result: Any) -> None:
        """Assert that no critical/high vulnerabilities were found.

        Args:
            result: SecurityTestResult to check.

        Raises:
            AssertionError: If critical vulnerabilities were found.
        """
        critical_findings = [
            f for f in result.findings
            if f.severity.value in ("critical", "high")
        ]
        if critical_findings:
            finding_summary = ", ".join(
                f"{f.severity.value}: {f.title}" for f in critical_findings[:5]
            )
            raise AssertionError(
                f"Found {len(critical_findings)} critical vulnerabilities: {finding_summary}"
            )


def create_security_journey(
    name: str,
    description: str,
    target_endpoints: list[str],
    test_types: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> Journey:
    """Create a customized security testing journey.

    Args:
        name: Journey name.
        description: Journey description.
        target_endpoints: List of endpoints to test.
        test_types: Types of tests to include (sql, xss, auth, owasp).
        config: Additional configuration.

    Returns:
        Configured Journey instance.

    Example:
        >>> journey = create_security_journey(
        ...     name="api_security",
        ...     description="Test API security",
        ...     target_endpoints=["/api/users", "/api/products"],
        ...     test_types=["sql", "xss", "owasp"]
        ... )
    """
    test_types = test_types or ["sql", "xss", "command", "auth", "owasp"]
    config = config or {}

    steps: list[Step | Checkpoint | Branch] = []

    # SQL injection testing
    if "sql" in test_types:
        def test_sql_injection(client: Any, ctx: dict[str, Any]) -> Any:
            tester = InjectionTester(client)
            all_findings = []
            for endpoint in target_endpoints:
                result = tester.test_sql_injection(
                    endpoint,
                    params=ctx.get("test_params", {"id": "1"}),
                )
                all_findings.extend(result.findings)
                ctx.setdefault("security_findings", []).extend(result.findings)
            ctx["sql_injection_results"] = all_findings
            assert not any(
                f.severity.value in ("critical", "high") for f in all_findings
            ), f"Found SQL injection vulnerabilities: {len(all_findings)}"
            return {"findings": len(all_findings), "status": "passed"}

        steps.append(Step(
            name="test_sql_injection",
            action=test_sql_injection,
            description="Test for SQL injection vulnerabilities",
        ))

    # XSS testing
    if "xss" in test_types:
        def test_xss(client: Any, ctx: dict[str, Any]) -> Any:
            tester = InjectionTester(client)
            all_findings = []
            for endpoint in target_endpoints:
                result = tester.test_xss(
                    endpoint,
                    params=ctx.get("test_params", {"q": "test"}),
                )
                all_findings.extend(result.findings)
                ctx.setdefault("security_findings", []).extend(result.findings)
            ctx["xss_results"] = all_findings
            assert not any(
                f.severity.value in ("critical", "high") for f in all_findings
            ), f"Found XSS vulnerabilities: {len(all_findings)}"
            return {"findings": len(all_findings), "status": "passed"}

        steps.append(Step(
            name="test_xss",
            action=test_xss,
            description="Test for XSS vulnerabilities",
        ))

    # Command injection testing
    if "command" in test_types:
        def test_command_injection(client: Any, ctx: dict[str, Any]) -> Any:
            tester = InjectionTester(client)
            all_findings = []
            for endpoint in target_endpoints:
                result = tester.test_command_injection(
                    endpoint,
                    params=ctx.get("test_params", {"cmd": "ls"}),
                )
                all_findings.extend(result.findings)
                ctx.setdefault("security_findings", []).extend(result.findings)
            ctx["command_injection_results"] = all_findings
            assert not any(
                f.severity.value in ("critical", "high") for f in all_findings
            ), f"Found command injection vulnerabilities: {len(all_findings)}"
            return {"findings": len(all_findings), "status": "passed"}

        steps.append(Step(
            name="test_command_injection",
            action=test_command_injection,
            description="Test for command injection vulnerabilities",
        ))

    # Authentication testing
    if "auth" in test_types:
        def test_auth_bypass(client: Any, ctx: dict[str, Any]) -> Any:
            tester = InvalidTokenTest(client)
            all_findings = []
            for endpoint in target_endpoints:
                result = tester.run(endpoint)
                all_findings.extend(result.findings)
                ctx.setdefault("security_findings", []).extend(result.findings)
            ctx["auth_bypass_results"] = all_findings
            assert not any(
                f.severity.value in ("critical", "high") for f in all_findings
            ), f"Found auth bypass vulnerabilities: {len(all_findings)}"
            return {"findings": len(all_findings), "status": "passed"}

        steps.append(Step(
            name="test_auth_bypass",
            action=test_auth_bypass,
            description="Test for authentication bypass vulnerabilities",
        ))

    # OWASP checks
    if "owasp" in test_types:
        def test_security_headers(client: Any, ctx: dict[str, Any]) -> Any:
            checker = SecurityHeadersCheck(client)
            all_findings = []
            for endpoint in target_endpoints[:1]:  # Only test first endpoint
                result = checker.run(endpoint)
                all_findings.extend(result.findings)
                ctx.setdefault("security_findings", []).extend(result.findings)
            ctx["security_headers_results"] = all_findings
            # Headers are often warnings, not failures
            return {"findings": len(all_findings), "status": "passed"}

        def test_rate_limit(client: Any, ctx: dict[str, Any]) -> Any:
            checker = RateLimitCheck(client, OWASPCheckConfig(rate_limit_requests=20))
            result = checker.run(target_endpoints[0] if target_endpoints else "/api")
            ctx.setdefault("security_findings", []).extend(result.findings)
            ctx["rate_limit_results"] = result.findings
            return {"findings": len(result.findings), "status": "passed"}

        steps.extend([
            Step(
                name="test_security_headers",
                action=test_security_headers,
                description="Test for missing security headers",
            ),
            Step(
                name="test_rate_limit",
                action=test_rate_limit,
                description="Test for rate limiting implementation",
            ),
        ])

    return Journey(
        name=name,
        description=description,
        steps=steps,
        tags=["security", "automated"],
    )


# Pre-built security journeys

def _test_sql_injection_action(client: Any, ctx: dict[str, Any]) -> Any:
    """Action for SQL injection testing."""
    endpoints = ctx.get("target_endpoints", ["/api/users", "/api/search"])
    tester = InjectionTester(client)
    all_findings = []

    for endpoint in endpoints:
        result = tester.test_sql_injection(
            endpoint,
            params=ctx.get("test_params", {"id": "1", "q": "test"}),
        )
        all_findings.extend(result.findings)

    ctx["sql_injection_findings"] = all_findings
    assert not any(
        f.severity.value == "critical" for f in all_findings
    ), f"Critical SQL injection found: {len([f for f in all_findings if f.severity.value == 'critical'])}"

    return {"total_findings": len(all_findings)}


def _test_xss_action(client: Any, ctx: dict[str, Any]) -> Any:
    """Action for XSS testing."""
    endpoints = ctx.get("target_endpoints", ["/api/search", "/api/comments"])
    tester = InjectionTester(client)
    all_findings = []

    for endpoint in endpoints:
        result = tester.test_xss(
            endpoint,
            params=ctx.get("test_params", {"q": "test", "content": "test"}),
        )
        all_findings.extend(result.findings)

    ctx["xss_findings"] = all_findings
    assert not any(
        f.severity.value in ("critical", "high") for f in all_findings
    ), f"XSS vulnerability found"

    return {"total_findings": len(all_findings)}


def _test_auth_bypass_action(client: Any, ctx: dict[str, Any]) -> Any:
    """Action for auth bypass testing."""
    endpoints = ctx.get("protected_endpoints", ["/api/me", "/api/users/1"])
    tester = InvalidTokenTest(client)
    all_findings = []

    for endpoint in endpoints:
        result = tester.run(endpoint)
        all_findings.extend(result.findings)

    ctx["auth_bypass_findings"] = all_findings
    assert not any(
        f.severity.value == "critical" for f in all_findings
    ), f"Critical auth bypass found"

    return {"total_findings": len(all_findings)}


def _test_idor_action(client: Any, ctx: dict[str, Any]) -> Any:
    """Action for IDOR testing."""
    user_token = ctx.get("user_token")
    other_user_resources = ctx.get("other_user_resources", ["/api/users/999/profile"])

    if not user_token:
        return {"skipped": True, "reason": "No user_token in context"}

    tester = PermissionBoundaryTest(client)
    result = tester.run(
        user_token=user_token,
        other_user_resources=other_user_resources,
    )

    ctx["idor_findings"] = result.findings
    assert not result.findings, f"IDOR vulnerability found: {len(result.findings)}"

    return {"total_findings": len(result.findings)}


def _test_rate_limit_action(client: Any, ctx: dict[str, Any]) -> Any:
    """Action for rate limit testing."""
    endpoint = ctx.get("auth_endpoint", "/api/login")
    checker = RateLimitCheck(client, OWASPCheckConfig(rate_limit_requests=50))
    result = checker.run(endpoint, method="POST")

    ctx["rate_limit_findings"] = result.findings
    # Rate limiting is often a warning, not a hard failure
    return {"total_findings": len(result.findings), "rate_limited": not result.vulnerable}


sql_injection_journey = Journey(
    name="security_sql_injection",
    description="Test for SQL injection vulnerabilities across API endpoints",
    steps=[
        Step(
            name="test_sql_injection",
            action=_test_sql_injection_action,
            description="Inject SQL payloads and detect vulnerabilities",
            timeout=120.0,
        ),
    ],
    tags=["security", "injection", "sql"],
)

xss_journey = Journey(
    name="security_xss",
    description="Test for Cross-Site Scripting (XSS) vulnerabilities",
    steps=[
        Step(
            name="test_xss",
            action=_test_xss_action,
            description="Inject XSS payloads and detect reflection",
            timeout=120.0,
        ),
    ],
    tags=["security", "injection", "xss"],
)

auth_bypass_journey = Journey(
    name="security_auth_bypass",
    description="Test for authentication bypass vulnerabilities",
    steps=[
        Step(
            name="test_auth_bypass",
            action=_test_auth_bypass_action,
            description="Test with invalid tokens and bypass techniques",
            timeout=60.0,
        ),
    ],
    tags=["security", "authentication"],
)

idor_journey = Journey(
    name="security_idor",
    description="Test for Insecure Direct Object Reference vulnerabilities",
    steps=[
        Step(
            name="test_idor",
            action=_test_idor_action,
            description="Test access to other users resources",
            timeout=60.0,
        ),
    ],
    tags=["security", "access_control", "idor"],
)

rate_limit_journey = Journey(
    name="security_rate_limit",
    description="Test for rate limiting implementation",
    steps=[
        Step(
            name="test_rate_limit",
            action=_test_rate_limit_action,
            description="Send multiple requests to verify rate limiting",
            timeout=120.0,
        ),
    ],
    tags=["security", "rate_limiting"],
)

full_security_journey = Journey(
    name="security_full_scan",
    description="Comprehensive security testing journey covering all vulnerability categories",
    steps=[
        # SQL Injection
        Step(
            name="test_sql_injection",
            action=_test_sql_injection_action,
            description="Test for SQL injection vulnerabilities",
            timeout=120.0,
        ),
        Checkpoint(name="after_sql_injection"),

        # XSS
        Step(
            name="test_xss",
            action=_test_xss_action,
            description="Test for XSS vulnerabilities",
            timeout=120.0,
        ),
        Checkpoint(name="after_xss"),

        # Auth Bypass
        Step(
            name="test_auth_bypass",
            action=_test_auth_bypass_action,
            description="Test for authentication bypass",
            timeout=60.0,
        ),
        Checkpoint(name="after_auth"),

        # Branch for conditional tests
        Branch(
            checkpoint_name="after_auth",
            paths=[
                Path(
                    name="idor_tests",
                    description="Run IDOR tests if user token available",
                    steps=[
                        Step(
                            name="test_idor",
                            action=_test_idor_action,
                            description="Test for IDOR vulnerabilities",
                            timeout=60.0,
                        ),
                    ],
                ),
                Path(
                    name="rate_limit_tests",
                    description="Run rate limiting tests",
                    steps=[
                        Step(
                            name="test_rate_limit",
                            action=_test_rate_limit_action,
                            description="Test rate limiting implementation",
                            timeout=120.0,
                        ),
                    ],
                ),
            ],
        ),
    ],
    tags=["security", "comprehensive", "automated"],
)
