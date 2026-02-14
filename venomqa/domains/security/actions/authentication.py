"""Authentication security testing actions.

This module provides comprehensive authentication testing including:
- Token expiration testing
- Token refresh mechanism testing
- Invalid token handling
- Permission boundary testing

Example:
    >>> tester = AuthenticationTester(client)
    >>> result = tester.test_token_expiration("/api/protected")
    >>> if result.vulnerable:
    ...     print(f"Vulnerability: {result.findings[0].title}")
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final

from venomqa.security.testing import (
    SecurityTestResult,
    VulnerabilityFinding,
    VulnerabilitySeverity,
    VulnerabilityType,
)

logger = logging.getLogger(__name__)


@dataclass
class AuthTestConfig:
    """Configuration for authentication tests.

    Attributes:
        token_endpoint: Endpoint to obtain tokens.
        refresh_endpoint: Endpoint to refresh tokens.
        protected_endpoints: List of endpoints requiring authentication.
        admin_endpoints: List of admin-only endpoints.
        user_credentials: Test user credentials.
        admin_credentials: Test admin credentials.
    """

    token_endpoint: str = "/api/auth/token"
    refresh_endpoint: str = "/api/auth/refresh"
    protected_endpoints: list[str] = field(default_factory=lambda: ["/api/me", "/api/users"])
    admin_endpoints: list[str] = field(default_factory=lambda: ["/api/admin", "/api/users/all"])
    user_credentials: dict[str, str] = field(
        default_factory=lambda: {"username": "testuser", "password": "testpass"}
    )
    admin_credentials: dict[str, str] = field(
        default_factory=lambda: {"username": "admin", "password": "adminpass"}
    )


class TokenExpirationTest:
    """Test token expiration handling.

    Verifies that:
    - Expired tokens are rejected
    - Token expiration time is enforced
    - Appropriate error responses are returned

    Example:
        >>> test = TokenExpirationTest(client)
        >>> result = test.run("/api/protected", valid_token)
    """

    EXPIRED_TOKEN_TEMPLATES: Final[list[str]] = [
        # JWT with past expiration (common format)
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IlRlc3QiLCJleHAiOjB9.expired",
        # JWT with negative expiration
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjotMX0.invalid",
    ]

    def __init__(self, client: Any, timeout: float = 30.0) -> None:
        """Initialize token expiration test.

        Args:
            client: HTTP client for making requests.
            timeout: Request timeout in seconds.
        """
        self.client = client
        self.timeout = timeout

    def create_expired_jwt(self, secret: str = "test_secret") -> str:
        """Create an expired JWT token for testing.

        Args:
            secret: Secret key for signing (test only).

        Returns:
            Expired JWT token string.
        """
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).decode().rstrip("=")

        # Expired 1 hour ago
        expired_time = int((datetime.now() - timedelta(hours=1)).timestamp())
        payload_data = {"sub": "test_user", "exp": expired_time, "iat": expired_time - 3600}
        payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).decode().rstrip("=")

        signature_input = f"{header}.{payload}"
        signature = base64.urlsafe_b64encode(
            hmac.new(secret.encode(), signature_input.encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")

        return f"{header}.{payload}.{signature}"

    def run(
        self,
        endpoint: str,
        valid_token: str | None = None,
        method: str = "GET",
    ) -> SecurityTestResult:
        """Run token expiration tests.

        Args:
            endpoint: Protected endpoint to test.
            valid_token: A valid token for comparison (optional).
            method: HTTP method to use.

        Returns:
            SecurityTestResult with findings.
        """
        start_time = time.time()
        findings: list[VulnerabilityFinding] = []
        errors: list[str] = []
        payloads_tested = 0

        # Test with expired tokens
        expired_tokens = self.EXPIRED_TOKEN_TEMPLATES + [self.create_expired_jwt()]

        for token in expired_tokens:
            payloads_tested += 1
            try:
                response = self.client.request(
                    method=method,
                    url=endpoint,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=self.timeout,
                )

                # If request succeeds with expired token, that's a vulnerability
                if response.status_code == 200:
                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.AUTH_BYPASS,
                            severity=VulnerabilitySeverity.CRITICAL,
                            title="Expired Token Accepted",
                            description=(
                                "The application accepts expired authentication tokens, "
                                "allowing attackers with old tokens to maintain access."
                            ),
                            payload=token[:50] + "...",
                            location=endpoint,
                            evidence=f"Status: {response.status_code}",
                            remediation=(
                                "Validate token expiration server-side. "
                                "Reject tokens with 'exp' claim in the past. "
                                "Use short-lived tokens with refresh mechanism."
                            ),
                            references=[
                                "https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/06-Session_Management_Testing/",
                                "https://cwe.mitre.org/data/definitions/613.html",
                            ],
                            cwe="CWE-613",
                            owasp="A07:2021 - Identification and Authentication Failures",
                        )
                    )
                    break  # One finding is enough
            except Exception as e:
                errors.append(f"Error testing expired token: {e}")

        # Test with manipulated expiration time
        if valid_token:
            payloads_tested += 1
            try:
                parts = valid_token.split(".")
                if len(parts) == 3:
                    # Try to decode and modify payload
                    try:
                        payload_decoded = json.loads(
                            base64.urlsafe_b64decode(parts[1] + "==")
                        )
                        payload_decoded["exp"] = int(
                            (datetime.now() + timedelta(days=365)).timestamp()
                        )
                        modified_payload = (
                            base64.urlsafe_b64encode(json.dumps(payload_decoded).encode())
                            .decode()
                            .rstrip("=")
                        )
                        tampered_token = f"{parts[0]}.{modified_payload}.{parts[2]}"

                        response = self.client.request(
                            method=method,
                            url=endpoint,
                            headers={"Authorization": f"Bearer {tampered_token}"},
                            timeout=self.timeout,
                        )

                        if response.status_code == 200:
                            findings.append(
                                VulnerabilityFinding(
                                    vuln_type=VulnerabilityType.AUTH_BYPASS,
                                    severity=VulnerabilitySeverity.CRITICAL,
                                    title="Token Tampering Allowed",
                                    description=(
                                        "Modified token with extended expiration was accepted. "
                                        "Token signature is not properly validated."
                                    ),
                                    payload="Token with modified expiration",
                                    location=endpoint,
                                    evidence=f"Status: {response.status_code}",
                                    remediation=(
                                        "Always validate token signatures. "
                                        "Use strong secret keys. "
                                        "Consider asymmetric signing (RS256)."
                                    ),
                                    cwe="CWE-345",
                                    owasp="A07:2021 - Identification and Authentication Failures",
                                )
                            )
                    except Exception:
                        pass  # Token format not compatible
            except Exception as e:
                errors.append(f"Error testing token tampering: {e}")

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=endpoint,
            vulnerable=len(findings) > 0,
            findings=findings,
            test_duration_ms=duration,
            payloads_tested=payloads_tested,
            errors=errors,
        )


class TokenRefreshTest:
    """Test token refresh mechanism security.

    Verifies that:
    - Refresh tokens cannot be reused after rotation
    - Expired refresh tokens are rejected
    - Refresh tokens are properly bound to users

    Example:
        >>> test = TokenRefreshTest(client)
        >>> result = test.run("/api/auth/refresh", refresh_token)
    """

    def __init__(self, client: Any, timeout: float = 30.0) -> None:
        """Initialize token refresh test.

        Args:
            client: HTTP client for making requests.
            timeout: Request timeout in seconds.
        """
        self.client = client
        self.timeout = timeout

    def run(
        self,
        refresh_endpoint: str,
        refresh_token: str | None = None,
        token_endpoint: str | None = None,
        credentials: dict[str, str] | None = None,
    ) -> SecurityTestResult:
        """Run token refresh security tests.

        Args:
            refresh_endpoint: Endpoint for token refresh.
            refresh_token: Refresh token to test with.
            token_endpoint: Endpoint to obtain initial token.
            credentials: Credentials for initial authentication.

        Returns:
            SecurityTestResult with findings.
        """
        start_time = time.time()
        findings: list[VulnerabilityFinding] = []
        errors: list[str] = []
        payloads_tested = 0

        # Test 1: Refresh token reuse after rotation
        if refresh_token:
            payloads_tested += 1
            try:
                # Use refresh token
                response1 = self.client.post(
                    refresh_endpoint,
                    json={"refresh_token": refresh_token},
                    timeout=self.timeout,
                )

                if response1.status_code == 200:
                    # Try to use the same refresh token again
                    response2 = self.client.post(
                        refresh_endpoint,
                        json={"refresh_token": refresh_token},
                        timeout=self.timeout,
                    )

                    if response2.status_code == 200:
                        findings.append(
                            VulnerabilityFinding(
                                vuln_type=VulnerabilityType.AUTH_BYPASS,
                                severity=VulnerabilitySeverity.HIGH,
                                title="Refresh Token Reuse Allowed",
                                description=(
                                    "Refresh tokens can be used multiple times. "
                                    "If a refresh token is compromised, an attacker "
                                    "can maintain persistent access."
                                ),
                                payload="Reused refresh token",
                                location=refresh_endpoint,
                                evidence="Same refresh token accepted twice",
                                remediation=(
                                    "Implement refresh token rotation. "
                                    "Invalidate old refresh tokens after use. "
                                    "Store refresh token families to detect reuse."
                                ),
                                cwe="CWE-384",
                                owasp="A07:2021 - Identification and Authentication Failures",
                            )
                        )
            except Exception as e:
                errors.append(f"Error testing refresh token reuse: {e}")

        # Test 2: Invalid/malformed refresh tokens
        invalid_tokens = [
            "invalid_token",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.invalid",
            "",
            "null",
            "undefined",
            "../../../etc/passwd",
            "<script>alert(1)</script>",
            "' OR '1'='1",
        ]

        for token in invalid_tokens:
            payloads_tested += 1
            try:
                response = self.client.post(
                    refresh_endpoint,
                    json={"refresh_token": token},
                    timeout=self.timeout,
                )

                # Check for unexpected success or error disclosure
                if response.status_code == 200:
                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.AUTH_BYPASS,
                            severity=VulnerabilitySeverity.CRITICAL,
                            title="Invalid Refresh Token Accepted",
                            description=(
                                f"An invalid refresh token was accepted: '{token[:20]}...'"
                            ),
                            payload=token,
                            location=refresh_endpoint,
                            evidence=f"Status: {response.status_code}",
                            remediation="Validate refresh token format and signature.",
                            cwe="CWE-287",
                            owasp="A07:2021 - Identification and Authentication Failures",
                        )
                    )
                elif response.status_code == 500:
                    # Server error might indicate injection vulnerability
                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                            severity=VulnerabilitySeverity.MEDIUM,
                            title="Server Error on Invalid Token",
                            description=(
                                "Server returned 500 error for invalid refresh token, "
                                "which may indicate improper error handling or injection."
                            ),
                            payload=token,
                            location=refresh_endpoint,
                            evidence=f"Status: {response.status_code}",
                            remediation="Handle invalid tokens gracefully with 401 response.",
                            cwe="CWE-209",
                            owasp="A09:2021 - Security Logging and Monitoring Failures",
                        )
                    )
            except Exception as e:
                errors.append(f"Error testing invalid token '{token[:20]}...': {e}")

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=refresh_endpoint,
            vulnerable=len(findings) > 0,
            findings=findings,
            test_duration_ms=duration,
            payloads_tested=payloads_tested,
            errors=errors,
        )


class InvalidTokenTest:
    """Test handling of invalid authentication tokens.

    Verifies proper handling of:
    - Malformed tokens
    - Tokens with invalid signatures
    - Tokens for non-existent users
    - Tokens with modified claims

    Example:
        >>> test = InvalidTokenTest(client)
        >>> result = test.run("/api/protected")
    """

    INVALID_TOKENS: Final[list[tuple[str, str]]] = [
        ("", "Empty token"),
        ("invalid", "Non-JWT string"),
        ("Bearer", "Just bearer prefix"),
        ("eyJhbGciOiJIUzI1NiJ9.e30.", "Empty payload, no signature"),
        ("eyJhbGciOiJub25lIn0.e30.", "Algorithm none attack"),
        ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiYWRtaW4ifQ.forged", "Forged signature"),
        ("null", "Null string"),
        ("undefined", "Undefined string"),
        ("true", "Boolean string"),
        ("[object Object]", "Object string"),
        ("../../../etc/passwd", "Path traversal in token"),
        ("{{7*7}}", "Template injection"),
        ("${7*7}", "Expression injection"),
    ]

    def __init__(self, client: Any, timeout: float = 30.0) -> None:
        """Initialize invalid token test.

        Args:
            client: HTTP client for making requests.
            timeout: Request timeout in seconds.
        """
        self.client = client
        self.timeout = timeout

    def run(
        self,
        endpoint: str,
        method: str = "GET",
        auth_header: str = "Authorization",
    ) -> SecurityTestResult:
        """Run invalid token tests.

        Args:
            endpoint: Protected endpoint to test.
            method: HTTP method to use.
            auth_header: Name of authorization header.

        Returns:
            SecurityTestResult with findings.
        """
        start_time = time.time()
        findings: list[VulnerabilityFinding] = []
        errors: list[str] = []
        payloads_tested = 0

        for token, description in self.INVALID_TOKENS:
            payloads_tested += 1
            try:
                headers = {auth_header: f"Bearer {token}"} if token else {}

                response = self.client.request(
                    method=method,
                    url=endpoint,
                    headers=headers,
                    timeout=self.timeout,
                )

                # Successful auth with invalid token is a critical issue
                if response.status_code == 200:
                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.AUTH_BYPASS,
                            severity=VulnerabilitySeverity.CRITICAL,
                            title=f"Auth Bypass: {description}",
                            description=(
                                f"Protected endpoint accepted invalid token: {description}"
                            ),
                            payload=token[:50] if token else "(empty)",
                            location=endpoint,
                            evidence=f"Status: {response.status_code}",
                            remediation=(
                                "Implement proper token validation. "
                                "Verify token format, signature, and claims."
                            ),
                            cwe="CWE-287",
                            owasp="A07:2021 - Identification and Authentication Failures",
                        )
                    )

                # Check for detailed error messages that leak info
                try:
                    body = response.json() if response.text else {}
                    error_msg = str(body.get("error", "") or body.get("message", ""))

                    sensitive_keywords = [
                        "secret", "key", "signature", "decode", "verify",
                        "algorithm", "hs256", "rs256", "stack trace",
                        "exception", "traceback",
                    ]

                    if any(kw in error_msg.lower() for kw in sensitive_keywords):
                        findings.append(
                            VulnerabilityFinding(
                                vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                                severity=VulnerabilitySeverity.LOW,
                                title="Detailed Auth Error Message",
                                description=(
                                    "Authentication error message reveals internal details."
                                ),
                                payload=token[:50] if token else "(empty)",
                                location=endpoint,
                                evidence=f"Error: {error_msg[:100]}",
                                remediation="Return generic authentication error messages.",
                                cwe="CWE-209",
                                owasp="A09:2021 - Security Logging and Monitoring Failures",
                            )
                        )
                except Exception:
                    pass  # Response might not be JSON

            except Exception as e:
                errors.append(f"Error testing '{description}': {e}")

        # Test algorithm confusion (alg:none attack)
        payloads_tested += 1
        try:
            # Create token with algorithm none
            header = base64.urlsafe_b64encode(
                json.dumps({"alg": "none", "typ": "JWT"}).encode()
            ).decode().rstrip("=")
            payload = base64.urlsafe_b64encode(
                json.dumps({"sub": "admin", "role": "admin"}).encode()
            ).decode().rstrip("=")
            none_token = f"{header}.{payload}."

            response = self.client.request(
                method=method,
                url=endpoint,
                headers={auth_header: f"Bearer {none_token}"},
                timeout=self.timeout,
            )

            if response.status_code == 200:
                findings.append(
                    VulnerabilityFinding(
                        vuln_type=VulnerabilityType.AUTH_BYPASS,
                        severity=VulnerabilitySeverity.CRITICAL,
                        title="JWT Algorithm None Attack",
                        description=(
                            "Server accepts JWT tokens with 'alg': 'none', "
                            "allowing attackers to forge valid tokens without knowing the secret."
                        ),
                        payload=none_token[:50] + "...",
                        location=endpoint,
                        evidence=f"Status: {response.status_code}",
                        remediation=(
                            "Explicitly reject tokens with 'alg': 'none'. "
                            "Whitelist allowed algorithms. "
                            "Use a JWT library that handles this securely."
                        ),
                        references=[
                            "https://auth0.com/blog/critical-vulnerabilities-in-json-web-token-libraries/",
                        ],
                        cwe="CWE-327",
                        owasp="A07:2021 - Identification and Authentication Failures",
                    )
                )
        except Exception as e:
            errors.append(f"Error testing algorithm none attack: {e}")

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target=endpoint,
            vulnerable=len(findings) > 0,
            findings=findings,
            test_duration_ms=duration,
            payloads_tested=payloads_tested,
            errors=errors,
        )


class PermissionBoundaryTest:
    """Test permission boundary enforcement.

    Verifies that:
    - Users cannot access admin-only endpoints
    - Users cannot access other users' data
    - Horizontal privilege escalation is prevented
    - Vertical privilege escalation is prevented

    Example:
        >>> test = PermissionBoundaryTest(client)
        >>> result = test.run(
        ...     user_token="user_jwt",
        ...     admin_endpoints=["/api/admin/users"],
        ...     other_user_resources=["/api/users/123/profile"]
        ... )
    """

    def __init__(self, client: Any, timeout: float = 30.0) -> None:
        """Initialize permission boundary test.

        Args:
            client: HTTP client for making requests.
            timeout: Request timeout in seconds.
        """
        self.client = client
        self.timeout = timeout

    def run(
        self,
        user_token: str,
        admin_endpoints: list[str] | None = None,
        other_user_resources: list[str] | None = None,
        privilege_escalation_params: dict[str, list[str]] | None = None,
    ) -> SecurityTestResult:
        """Run permission boundary tests.

        Args:
            user_token: Token for a regular user.
            admin_endpoints: List of admin-only endpoints to test.
            other_user_resources: List of other users' resources to test.
            privilege_escalation_params: Parameters that might enable escalation.

        Returns:
            SecurityTestResult with findings.
        """
        start_time = time.time()
        findings: list[VulnerabilityFinding] = []
        errors: list[str] = []
        payloads_tested = 0

        admin_endpoints = admin_endpoints or []
        other_user_resources = other_user_resources or []
        privilege_escalation_params = privilege_escalation_params or {
            "role": ["admin", "administrator", "root", "superuser"],
            "is_admin": ["true", "1", "yes"],
            "admin": ["true", "1", "yes"],
            "privilege": ["admin", "elevated", "full"],
            "access_level": ["admin", "full", "all"],
        }

        headers = {"Authorization": f"Bearer {user_token}"}

        # Test 1: Access to admin endpoints
        for endpoint in admin_endpoints:
            payloads_tested += 1
            try:
                response = self.client.get(endpoint, headers=headers, timeout=self.timeout)

                if response.status_code == 200:
                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.BROKEN_ACCESS_CONTROL,
                            severity=VulnerabilitySeverity.CRITICAL,
                            title="Vertical Privilege Escalation",
                            description=(
                                f"Regular user can access admin endpoint: {endpoint}"
                            ),
                            payload=f"GET {endpoint} with user token",
                            location=endpoint,
                            evidence=f"Status: {response.status_code}",
                            remediation=(
                                "Implement role-based access control. "
                                "Verify user roles/permissions on every request."
                            ),
                            cwe="CWE-269",
                            owasp="A01:2021 - Broken Access Control",
                        )
                    )
            except Exception as e:
                errors.append(f"Error testing admin endpoint {endpoint}: {e}")

        # Test 2: Access to other users' resources (IDOR)
        for resource in other_user_resources:
            payloads_tested += 1
            try:
                response = self.client.get(resource, headers=headers, timeout=self.timeout)

                if response.status_code == 200:
                    findings.append(
                        VulnerabilityFinding(
                            vuln_type=VulnerabilityType.IDOR,
                            severity=VulnerabilitySeverity.HIGH,
                            title="Horizontal Privilege Escalation (IDOR)",
                            description=(
                                f"User can access another user's resource: {resource}"
                            ),
                            payload=f"GET {resource}",
                            location=resource,
                            evidence=f"Status: {response.status_code}",
                            remediation=(
                                "Verify resource ownership before access. "
                                "Use indirect object references. "
                                "Implement proper authorization checks."
                            ),
                            cwe="CWE-639",
                            owasp="A01:2021 - Broken Access Control",
                        )
                    )
            except Exception as e:
                errors.append(f"Error testing resource {resource}: {e}")

        # Test 3: Privilege escalation via parameters
        test_endpoint = admin_endpoints[0] if admin_endpoints else "/api/user"

        for param, values in privilege_escalation_params.items():
            for value in values:
                payloads_tested += 1
                try:
                    # Test via query parameter
                    response = self.client.get(
                        test_endpoint,
                        params={param: value},
                        headers=headers,
                        timeout=self.timeout,
                    )

                    if response.status_code == 200:
                        findings.append(
                            VulnerabilityFinding(
                                vuln_type=VulnerabilityType.BROKEN_ACCESS_CONTROL,
                                severity=VulnerabilitySeverity.CRITICAL,
                                title="Privilege Escalation via Parameter",
                                description=(
                                    f"Setting {param}={value} grants elevated access."
                                ),
                                payload=f"{param}={value}",
                                location=test_endpoint,
                                evidence=f"Status: {response.status_code}",
                                remediation=(
                                    "Never trust user-supplied role/permission parameters. "
                                    "Derive permissions from server-side session only."
                                ),
                                cwe="CWE-269",
                                owasp="A01:2021 - Broken Access Control",
                            )
                        )
                        break  # One finding per parameter is enough
                except Exception as e:
                    errors.append(f"Error testing parameter {param}={value}: {e}")

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target="Permission Boundaries",
            vulnerable=len(findings) > 0,
            findings=findings,
            test_duration_ms=duration,
            payloads_tested=payloads_tested,
            errors=errors,
        )


class AuthenticationTester:
    """Comprehensive authentication security tester.

    Combines all authentication tests into a single runner with
    configurable test selection and reporting.

    Example:
        >>> tester = AuthenticationTester(client)
        >>> result = tester.run_all_tests(config)
        >>> for finding in result.findings:
        ...     print(f"{finding.severity}: {finding.title}")
    """

    def __init__(self, client: Any, timeout: float = 30.0) -> None:
        """Initialize authentication tester.

        Args:
            client: HTTP client for making requests.
            timeout: Request timeout in seconds.
        """
        self.client = client
        self.timeout = timeout
        self.token_expiration_test = TokenExpirationTest(client, timeout)
        self.token_refresh_test = TokenRefreshTest(client, timeout)
        self.invalid_token_test = InvalidTokenTest(client, timeout)
        self.permission_boundary_test = PermissionBoundaryTest(client, timeout)

    def run_all_tests(
        self,
        config: AuthTestConfig | None = None,
        user_token: str | None = None,
        refresh_token: str | None = None,
    ) -> SecurityTestResult:
        """Run all authentication security tests.

        Args:
            config: Test configuration.
            user_token: Valid user token for testing.
            refresh_token: Valid refresh token for testing.

        Returns:
            Combined SecurityTestResult with all findings.
        """
        config = config or AuthTestConfig()
        start_time = time.time()
        all_findings: list[VulnerabilityFinding] = []
        all_errors: list[str] = []
        total_payloads = 0

        # Run token expiration tests
        for endpoint in config.protected_endpoints:
            result = self.token_expiration_test.run(endpoint, user_token)
            all_findings.extend(result.findings)
            all_errors.extend(result.errors)
            total_payloads += result.payloads_tested

        # Run token refresh tests
        if config.refresh_endpoint:
            result = self.token_refresh_test.run(
                config.refresh_endpoint,
                refresh_token,
                config.token_endpoint,
                config.user_credentials,
            )
            all_findings.extend(result.findings)
            all_errors.extend(result.errors)
            total_payloads += result.payloads_tested

        # Run invalid token tests
        for endpoint in config.protected_endpoints:
            result = self.invalid_token_test.run(endpoint)
            all_findings.extend(result.findings)
            all_errors.extend(result.errors)
            total_payloads += result.payloads_tested

        # Run permission boundary tests
        if user_token:
            result = self.permission_boundary_test.run(
                user_token,
                config.admin_endpoints,
            )
            all_findings.extend(result.findings)
            all_errors.extend(result.errors)
            total_payloads += result.payloads_tested

        duration = (time.time() - start_time) * 1000

        return SecurityTestResult(
            target="Authentication",
            vulnerable=len(all_findings) > 0,
            findings=all_findings,
            test_duration_ms=duration,
            payloads_tested=total_payloads,
            errors=all_errors,
        )
