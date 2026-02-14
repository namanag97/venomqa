"""Tests for security testing capabilities in VenomQA."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from venomqa.security.testing import (
    SecurityTestResult,
    VulnerabilityFinding,
    VulnerabilitySeverity,
    VulnerabilityType,
    SQLInjectionPayloads,
    XSSPayloads,
    CommandInjectionPayloads,
)
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
    AutoInjector,
    SQLInjectionTest,
    XSSInjectionTest,
    CommandInjectionTest,
)
from venomqa.domains.security.actions.owasp import (
    OWASPChecker,
    OWASPCheckConfig,
    SecurityHeadersCheck,
    CORSPolicyCheck,
    RateLimitCheck,
    ErrorLeakageCheck,
)
from venomqa.domains.security.scanner import (
    SecurityScanner,
    ScanConfig,
    SecurityScanResult,
)
from venomqa.domains.security.journeys.security_journey import (
    SecurityJourney,
    create_security_journey,
    sql_injection_journey,
    xss_journey,
    full_security_journey,
)


class MockResponse:
    """Mock HTTP response for testing."""

    def __init__(
        self,
        status_code: int = 200,
        text: str = "",
        headers: dict[str, str] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self._json_data = json_data or {}

    def json(self) -> dict[str, Any]:
        return self._json_data


class MockClient:
    """Mock HTTP client for testing."""

    def __init__(self, responses: list[MockResponse] | None = None) -> None:
        self.responses = responses or [MockResponse()]
        self.response_index = 0
        self.requests: list[dict[str, Any]] = []

    def _get_response(self) -> MockResponse:
        if self.response_index < len(self.responses):
            response = self.responses[self.response_index]
            self.response_index += 1
            return response
        return self.responses[-1] if self.responses else MockResponse()

    def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> MockResponse:
        self.requests.append({"method": method, "url": url, **kwargs})
        return self._get_response()

    def get(self, url: str, **kwargs: Any) -> MockResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> MockResponse:
        return self.request("POST", url, **kwargs)


class TestSQLInjectionPayloads:
    """Tests for SQL injection payload generation."""

    def test_basic_payloads_exist(self) -> None:
        """Test that basic SQL injection payloads are defined."""
        assert len(SQLInjectionPayloads.BASIC) > 0
        assert "' OR '1'='1" in SQLInjectionPayloads.BASIC

    def test_union_payloads_exist(self) -> None:
        """Test that UNION-based payloads are defined."""
        assert len(SQLInjectionPayloads.UNION) > 0
        assert any("UNION" in p for p in SQLInjectionPayloads.UNION)

    def test_time_based_payloads_exist(self) -> None:
        """Test that time-based payloads are defined."""
        assert len(SQLInjectionPayloads.TIME_BASED) > 0
        assert any("SLEEP" in p or "WAITFOR" in p or "pg_sleep" in p for p in SQLInjectionPayloads.TIME_BASED)

    def test_all_payloads_iterator(self) -> None:
        """Test that all_payloads yields all payloads."""
        all_payloads = list(SQLInjectionPayloads.all_payloads())
        assert len(all_payloads) > 50  # Should have many payloads

    def test_by_technique(self) -> None:
        """Test getting payloads by technique."""
        basic = SQLInjectionPayloads.by_technique("basic")
        assert basic == SQLInjectionPayloads.BASIC

        mysql = SQLInjectionPayloads.by_technique("mysql")
        assert mysql == SQLInjectionPayloads.MYSQL_SPECIFIC


class TestXSSPayloads:
    """Tests for XSS payload generation."""

    def test_basic_payloads_exist(self) -> None:
        """Test that basic XSS payloads are defined."""
        assert len(XSSPayloads.BASIC) > 0
        assert any("<script>" in p for p in XSSPayloads.BASIC)

    def test_event_handlers_exist(self) -> None:
        """Test that event handler payloads are defined."""
        assert len(XSSPayloads.EVENT_HANDLERS) > 0
        assert any("onerror" in p for p in XSSPayloads.EVENT_HANDLERS)

    def test_polyglot_payloads_exist(self) -> None:
        """Test that polyglot payloads are defined."""
        assert len(XSSPayloads.POLYGLOT) > 0

    def test_all_payloads_iterator(self) -> None:
        """Test that all_payloads yields all payloads."""
        all_payloads = list(XSSPayloads.all_payloads())
        assert len(all_payloads) > 30

    def test_by_category(self) -> None:
        """Test getting payloads by category."""
        basic = XSSPayloads.by_category("basic")
        assert basic == XSSPayloads.BASIC


class TestCommandInjectionPayloads:
    """Tests for command injection payload generation."""

    def test_unix_payloads_exist(self) -> None:
        """Test that Unix command injection payloads are defined."""
        assert len(CommandInjectionPayloads.UNIX_BASIC) > 0
        assert any("; ls" in p or "| ls" in p for p in CommandInjectionPayloads.UNIX_BASIC)

    def test_windows_payloads_exist(self) -> None:
        """Test that Windows command injection payloads are defined."""
        assert len(CommandInjectionPayloads.WINDOWS_BASIC) > 0
        assert any("dir" in p for p in CommandInjectionPayloads.WINDOWS_BASIC)


class TestTokenExpirationTest:
    """Tests for token expiration testing."""

    def test_create_expired_jwt(self) -> None:
        """Test creation of expired JWT."""
        client = MockClient()
        test = TokenExpirationTest(client)

        token = test.create_expired_jwt()
        assert token.count(".") == 2  # JWT has 3 parts

    def test_run_with_expired_token_rejected(self) -> None:
        """Test that expired tokens being rejected is correct behavior."""
        # Response with 401 = expired token correctly rejected
        client = MockClient([MockResponse(status_code=401, text='{"error": "token expired"}')])
        test = TokenExpirationTest(client)

        result = test.run("/api/protected")

        assert result.payloads_tested > 0
        # No vulnerability if expired tokens are rejected
        assert len([f for f in result.findings if f.severity.value == "critical"]) == 0

    def test_run_detects_vulnerability_when_expired_token_accepted(self) -> None:
        """Test that accepting expired tokens is detected as vulnerability."""
        # Response with 200 = expired token incorrectly accepted
        client = MockClient([MockResponse(status_code=200, text='{"user": "test"}')])
        test = TokenExpirationTest(client)

        result = test.run("/api/protected")

        assert result.vulnerable
        assert len(result.findings) > 0
        assert result.findings[0].vuln_type == VulnerabilityType.AUTH_BYPASS


class TestTokenRefreshTest:
    """Tests for token refresh mechanism testing."""

    def test_detects_refresh_token_reuse(self) -> None:
        """Test detection of refresh token reuse vulnerability."""
        # Both requests return 200 = token can be reused
        client = MockClient([
            MockResponse(status_code=200, json_data={"access_token": "new_token"}),
            MockResponse(status_code=200, json_data={"access_token": "another_token"}),
        ])
        test = TokenRefreshTest(client)

        result = test.run("/api/auth/refresh", refresh_token="test_refresh_token")

        assert result.vulnerable
        assert any("Reuse" in f.title for f in result.findings)

    def test_detects_invalid_token_acceptance(self) -> None:
        """Test detection when invalid refresh tokens are accepted."""
        client = MockClient([MockResponse(status_code=200, json_data={"access_token": "bad"})])
        test = TokenRefreshTest(client)

        result = test.run("/api/auth/refresh")

        assert result.vulnerable


class TestInvalidTokenTest:
    """Tests for invalid token handling."""

    def test_detects_auth_bypass_with_empty_token(self) -> None:
        """Test detection when empty token grants access."""
        client = MockClient([MockResponse(status_code=200, text='{"user": "admin"}')])
        test = InvalidTokenTest(client)

        result = test.run("/api/protected")

        assert result.vulnerable
        assert any("Auth Bypass" in f.title for f in result.findings)

    def test_algorithm_none_attack(self) -> None:
        """Test detection of algorithm none vulnerability."""
        # First requests rejected, algorithm none accepted
        responses = [MockResponse(status_code=401)] * 15 + [MockResponse(status_code=200)]
        client = MockClient(responses)
        test = InvalidTokenTest(client)

        result = test.run("/api/protected")

        # Should have tested many tokens
        assert result.payloads_tested >= 10


class TestPermissionBoundaryTest:
    """Tests for permission boundary testing."""

    def test_detects_vertical_privilege_escalation(self) -> None:
        """Test detection of vertical privilege escalation."""
        client = MockClient([MockResponse(status_code=200, text='{"admin_data": "secret"}')])
        test = PermissionBoundaryTest(client)

        result = test.run(
            user_token="user_token",
            admin_endpoints=["/api/admin/users"],
        )

        assert result.vulnerable
        assert any("Vertical Privilege" in f.title for f in result.findings)

    def test_detects_idor(self) -> None:
        """Test detection of IDOR vulnerability."""
        client = MockClient([MockResponse(status_code=200, text='{"user_id": "other_user"}')])
        test = PermissionBoundaryTest(client)

        result = test.run(
            user_token="user_token",
            other_user_resources=["/api/users/999/profile"],
        )

        assert result.vulnerable
        assert any("IDOR" in f.title for f in result.findings)


class TestSQLInjectionTest:
    """Tests for SQL injection detection."""

    def test_detects_error_based_sql_injection(self) -> None:
        """Test detection of error-based SQL injection."""
        # Response contains SQL error
        error_response = MockResponse(
            status_code=500,
            text="Error: You have an error in your SQL syntax near 'users'"
        )
        client = MockClient([error_response])
        test = SQLInjectionTest(client, InjectionTestConfig(max_payloads=5))

        result = test.run("/api/users", params={"id": "1"})

        assert result.vulnerable
        assert any("SQL Injection" in f.title for f in result.findings)

    def test_no_false_positive_on_normal_response(self) -> None:
        """Test no false positives on normal responses."""
        client = MockClient([MockResponse(status_code=200, text='{"users": []}')])
        test = SQLInjectionTest(client, InjectionTestConfig(max_payloads=3))

        result = test.run("/api/users", params={"id": "1"})

        # Should not find SQL injection in normal response
        assert not any(
            f.vuln_type == VulnerabilityType.SQL_INJECTION and f.severity.value == "high"
            for f in result.findings
        )


class TestXSSInjectionTest:
    """Tests for XSS detection."""

    def test_detects_reflected_xss(self) -> None:
        """Test detection of reflected XSS."""
        # Response reflects the XSS payload
        xss_payload = "<script>alert('XSS')</script>"
        client = MockClient([
            MockResponse(status_code=200, text=f'<html>Search: {xss_payload}</html>')
        ])
        test = XSSInjectionTest(client, InjectionTestConfig(max_payloads=5))

        result = test.run("/search", params={"q": "test"})

        assert result.vulnerable
        assert any("XSS" in f.title for f in result.findings)

    def test_detects_dom_xss_sinks(self) -> None:
        """Test detection of DOM XSS sinks in JavaScript."""
        js_code = '''
        <script>
        document.write(userInput);
        element.innerHTML = data;
        eval(userCode);
        </script>
        '''
        client = MockClient([MockResponse(status_code=200, text=js_code)])
        test = XSSInjectionTest(client)

        result = test.run("/page")

        # Should detect DOM XSS sinks
        dom_findings = [f for f in result.findings if f.vuln_type == VulnerabilityType.XSS_DOM]
        assert len(dom_findings) > 0


class TestSecurityHeadersCheck:
    """Tests for security headers validation."""

    def test_detects_missing_csp(self) -> None:
        """Test detection of missing Content-Security-Policy."""
        client = MockClient([MockResponse(status_code=200, headers={})])
        check = SecurityHeadersCheck(client)

        result = check.run("/")

        csp_findings = [f for f in result.findings if "Content-Security-Policy" in f.title]
        assert len(csp_findings) > 0

    def test_detects_missing_security_headers(self) -> None:
        """Test detection of all missing security headers."""
        client = MockClient([MockResponse(status_code=200, headers={})])
        check = SecurityHeadersCheck(client)

        result = check.run("/")

        # Should detect missing X-Frame-Options, HSTS, etc.
        assert len(result.findings) > 3

    def test_detects_server_version_disclosure(self) -> None:
        """Test detection of server version disclosure."""
        client = MockClient([
            MockResponse(
                status_code=200,
                headers={"Server": "Apache/2.4.41 (Ubuntu)", "X-Powered-By": "PHP/7.4.3"}
            )
        ])
        check = SecurityHeadersCheck(client)

        result = check.run("/")

        disclosure_findings = [f for f in result.findings if "Disclosure" in f.title]
        assert len(disclosure_findings) >= 2

    def test_detects_weak_csp(self) -> None:
        """Test detection of weak CSP configuration."""
        client = MockClient([
            MockResponse(
                status_code=200,
                headers={"Content-Security-Policy": "default-src 'self' 'unsafe-inline' 'unsafe-eval'"}
            )
        ])
        check = SecurityHeadersCheck(client)

        result = check.run("/")

        weak_csp_findings = [f for f in result.findings if "Weak CSP" in f.title]
        assert len(weak_csp_findings) > 0


class TestCORSPolicyCheck:
    """Tests for CORS misconfiguration detection."""

    def test_detects_wildcard_origin(self) -> None:
        """Test detection of wildcard CORS origin."""
        client = MockClient([
            MockResponse(
                status_code=200,
                headers={"Access-Control-Allow-Origin": "*"}
            )
        ])
        check = CORSPolicyCheck(client)

        result = check.run("/api")

        assert result.vulnerable
        assert any("Wildcard" in f.title for f in result.findings)

    def test_detects_origin_reflection(self) -> None:
        """Test detection of arbitrary origin reflection."""
        # Server reflects the Origin header
        client = MockClient([
            MockResponse(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "https://evil.com",
                    "Access-Control-Allow-Credentials": "true",
                }
            )
        ])
        check = CORSPolicyCheck(client, OWASPCheckConfig(cors_test_origin="https://evil.com"))

        result = check.run("/api")

        assert result.vulnerable
        assert any("Reflection" in f.title for f in result.findings)

    def test_detects_null_origin_allowed(self) -> None:
        """Test detection of null origin being allowed."""
        client = MockClient([
            MockResponse(status_code=200, headers={}),
            MockResponse(
                status_code=200,
                headers={"Access-Control-Allow-Origin": "null"}
            ),
        ])
        check = CORSPolicyCheck(client)

        result = check.run("/api")

        null_findings = [f for f in result.findings if "Null" in f.title]
        assert len(null_findings) > 0


class TestRateLimitCheck:
    """Tests for rate limiting verification."""

    def test_detects_missing_rate_limiting(self) -> None:
        """Test detection of missing rate limiting."""
        # All requests succeed without rate limiting
        responses = [MockResponse(status_code=200)] * 100
        client = MockClient(responses)
        check = RateLimitCheck(client, OWASPCheckConfig(rate_limit_requests=50))

        result = check.run("/api/login", method="POST")

        assert result.vulnerable
        assert any("Rate Limit" in f.title for f in result.findings)

    def test_recognizes_rate_limiting_present(self) -> None:
        """Test recognition when rate limiting is properly implemented."""
        # First 10 succeed, then 429
        responses = [MockResponse(status_code=200)] * 10 + [MockResponse(status_code=429)]
        client = MockClient(responses)
        check = RateLimitCheck(client, OWASPCheckConfig(rate_limit_requests=20))

        result = check.run("/api/login", method="POST")

        # Should not report missing rate limiting
        missing_findings = [f for f in result.findings if "Missing Rate Limiting" in f.title]
        assert len(missing_findings) == 0


class TestErrorLeakageCheck:
    """Tests for error message leakage detection."""

    def test_detects_stack_trace_leakage(self) -> None:
        """Test detection of stack trace in error response."""
        error_response = MockResponse(
            status_code=500,
            text='''
            Traceback (most recent call last):
              File "/app/server.py", line 42, in handle_request
                result = database.query(user_input)
            '''
        )
        client = MockClient([error_response])
        check = ErrorLeakageCheck(client)

        result = check.run("/api/users")

        assert result.vulnerable
        assert any("Stack trace" in f.title.lower() or "Python" in f.title for f in result.findings)

    def test_detects_sql_query_leakage(self) -> None:
        """Test detection of SQL query in error response."""
        error_response = MockResponse(
            status_code=500,
            text='Error: SELECT * FROM users WHERE id = 1 failed'
        )
        client = MockClient([error_response])
        check = ErrorLeakageCheck(client)

        result = check.run("/api/users")

        assert result.vulnerable
        assert any("SQL" in f.title for f in result.findings)

    def test_detects_database_connection_string_leakage(self) -> None:
        """Test detection of database connection string in error."""
        error_response = MockResponse(
            status_code=500,
            text='Connection failed: postgresql://admin:secretpass@localhost:5432/production'
        )
        client = MockClient([error_response])
        check = ErrorLeakageCheck(client)

        result = check.run("/api/users")

        assert result.vulnerable
        critical_findings = [f for f in result.findings if f.severity.value == "critical"]
        assert len(critical_findings) > 0


class TestOWASPChecker:
    """Tests for combined OWASP checker."""

    def test_runs_all_checks(self) -> None:
        """Test that all OWASP checks are run."""
        # Responses for various checks
        responses = [
            MockResponse(status_code=200, headers={}),  # Headers check
            MockResponse(status_code=200, headers={}),  # CORS check
            MockResponse(status_code=200),  # Rate limit requests
        ] * 50
        client = MockClient(responses)
        checker = OWASPChecker(client, OWASPCheckConfig(rate_limit_requests=10))

        result = checker.run_all_checks(
            "http://localhost:8000",
            endpoints=["/"],
            auth_endpoints=["/api/login"],
        )

        # Should have findings from multiple check categories
        assert len(result.findings) > 0


class TestAutoInjector:
    """Tests for automatic payload injection."""

    def test_injects_all_types(self) -> None:
        """Test that all injection types are tested."""
        client = MockClient([MockResponse(status_code=200, text="OK")] * 100)
        injector = AutoInjector(client, InjectionTestConfig(max_payloads=3))

        result = injector.inject_all("/api/search", params={"q": "test"})

        assert result.payloads_tested > 0
        # Should have tested SQL, XSS, and command injection
        assert result.payloads_tested >= 9  # At least 3 per type

    def test_respects_injection_types_filter(self) -> None:
        """Test filtering of injection types."""
        client = MockClient([MockResponse(status_code=200)] * 50)
        injector = AutoInjector(client, InjectionTestConfig(max_payloads=3))

        result = injector.inject_all(
            "/api/search",
            params={"q": "test"},
            injection_types=["sql"],
        )

        # Should only test SQL injection
        assert result.payloads_tested > 0


class TestSecurityScanner:
    """Tests for the security scanner."""

    def test_runs_full_scan(self) -> None:
        """Test full security scan execution."""
        client = MockClient([MockResponse(status_code=200, headers={})] * 200)
        scanner = SecurityScanner(client)

        config = ScanConfig(
            target_url="http://localhost:8000",
            endpoints=["/api"],
            max_payloads=3,
            rate_limit_requests=10,
        )

        result = scanner.run_full_scan(config)

        assert isinstance(result, SecurityScanResult)
        assert result.target == "http://localhost:8000"
        assert result.scan_finished >= result.scan_started

    def test_respects_skip_tests(self) -> None:
        """Test that skipped tests are not run."""
        client = MockClient([MockResponse(status_code=200)] * 50)
        scanner = SecurityScanner(client)

        config = ScanConfig(
            target_url="http://localhost:8000",
            endpoints=["/api"],
            skip_tests=["injection", "authentication"],
            rate_limit_requests=10,
        )

        result = scanner.run_full_scan(config)

        # Should still have OWASP findings
        assert isinstance(result, SecurityScanResult)


class TestSecurityJourney:
    """Tests for security journey definitions."""

    def test_sql_injection_journey_structure(self) -> None:
        """Test SQL injection journey has correct structure."""
        assert sql_injection_journey.name == "security_sql_injection"
        assert len(sql_injection_journey.steps) > 0
        assert "security" in sql_injection_journey.tags

    def test_xss_journey_structure(self) -> None:
        """Test XSS journey has correct structure."""
        assert xss_journey.name == "security_xss"
        assert len(xss_journey.steps) > 0
        assert "security" in xss_journey.tags

    def test_full_security_journey_structure(self) -> None:
        """Test full security journey has all components."""
        assert full_security_journey.name == "security_full_scan"
        assert len(full_security_journey.steps) > 0
        assert "comprehensive" in full_security_journey.tags

        # Should have checkpoints
        checkpoints = full_security_journey.get_checkpoints()
        assert len(checkpoints) >= 2

        # Should have branches
        branches = full_security_journey.get_branches()
        assert len(branches) >= 1

    def test_create_security_journey(self) -> None:
        """Test dynamic security journey creation."""
        journey = create_security_journey(
            name="custom_security",
            description="Custom security tests",
            target_endpoints=["/api/users"],
            test_types=["sql", "xss"],
        )

        assert journey.name == "custom_security"
        assert len(journey.steps) >= 2
        assert "security" in journey.tags


class TestVulnerabilityFinding:
    """Tests for vulnerability finding data structure."""

    def test_finding_creation(self) -> None:
        """Test creating a vulnerability finding."""
        finding = VulnerabilityFinding(
            vuln_type=VulnerabilityType.SQL_INJECTION,
            severity=VulnerabilitySeverity.HIGH,
            title="SQL Injection in login",
            description="User input not sanitized",
            payload="' OR '1'='1",
            location="/api/login",
            evidence="SQL error in response",
            remediation="Use parameterized queries",
            cwe="CWE-89",
            owasp="A03:2021 - Injection",
        )

        assert finding.vuln_type == VulnerabilityType.SQL_INJECTION
        assert finding.severity == VulnerabilitySeverity.HIGH
        assert finding.cwe == "CWE-89"

    def test_security_test_result_properties(self) -> None:
        """Test SecurityTestResult properties."""
        finding = VulnerabilityFinding(
            vuln_type=VulnerabilityType.XSS_REFLECTED,
            severity=VulnerabilitySeverity.MEDIUM,
            title="Reflected XSS",
            description="XSS in search",
            payload="<script>alert(1)</script>",
        )

        result = SecurityTestResult(
            target="/search",
            vulnerable=True,
            findings=[finding],
            test_duration_ms=100.5,
            payloads_tested=50,
        )

        assert result.vulnerable
        assert len(result.findings) == 1
        assert result.payloads_tested == 50


class TestSecurityScanResult:
    """Tests for security scan result data structure."""

    def test_scan_result_properties(self) -> None:
        """Test SecurityScanResult computed properties."""
        result = SecurityScanResult(
            target="http://localhost:8000",
            scan_started=datetime.now(),
            scan_finished=datetime.now() + timedelta(seconds=10),
            total_findings=5,
            findings_by_severity={"critical": 1, "high": 2, "medium": 2},
            findings_by_type={"sql_injection": 3, "xss_reflected": 2},
            all_findings=[],
            test_results={},
            errors=[],
            scan_duration_ms=10000.0,
        )

        assert result.critical_count == 1
        assert result.high_count == 2
        assert result.is_vulnerable
        assert result.has_critical_issues

    def test_scan_result_no_vulnerabilities(self) -> None:
        """Test SecurityScanResult with no vulnerabilities."""
        result = SecurityScanResult(
            target="http://localhost:8000",
            scan_started=datetime.now(),
            scan_finished=datetime.now(),
            total_findings=0,
            findings_by_severity={},
            findings_by_type={},
            all_findings=[],
            test_results={},
            errors=[],
            scan_duration_ms=1000.0,
        )

        assert result.critical_count == 0
        assert not result.is_vulnerable
        assert not result.has_critical_issues
