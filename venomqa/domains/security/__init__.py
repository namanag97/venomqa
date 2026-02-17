"""Security testing domain for VenomQA.

Provides comprehensive security testing capabilities including:
- Authentication testing (token expiration, refresh, invalid tokens, permissions)
- Injection testing (SQL, XSS, Command injection with auto-injection)
- OWASP compliance checks (security headers, CORS, rate limiting)
- Security journeys for common vulnerability testing

Example:
    >>> from venomqa.domains.security import SecurityScanner, SecurityJourney
    >>> scanner = SecurityScanner("http://localhost:8000")
    >>> result = scanner.run_full_scan()
    >>> print(f"Vulnerabilities found: {len(result.findings)}")
"""

from venomqa.domains.security.actions.authentication import (
    AuthenticationTester,
    InvalidTokenTest,
    PermissionBoundaryTest,
    TokenExpirationTest,
    TokenRefreshTest,
)
from venomqa.domains.security.actions.injection import (
    AutoInjector,
    CommandInjectionTest,
    InjectionTester,
    SQLInjectionTest,
    XSSInjectionTest,
)
from venomqa.domains.security.actions.owasp import (
    CORSPolicyCheck,
    ErrorLeakageCheck,
    OWASPChecker,
    RateLimitCheck,
    SecurityHeadersCheck,
)
from venomqa.domains.security.journeys.security_journey import (
    SecurityJourney,
    auth_bypass_journey,
    create_security_journey,
    full_security_journey,
    idor_journey,
    rate_limit_journey,
    sql_injection_journey,
    xss_journey,
)
from venomqa.domains.security.scanner import (
    ScanConfig,
    SecurityScanner,
    SecurityScanResult,
)

__all__ = [
    # Authentication testing
    "AuthenticationTester",
    "TokenExpirationTest",
    "TokenRefreshTest",
    "InvalidTokenTest",
    "PermissionBoundaryTest",
    # Injection testing
    "InjectionTester",
    "AutoInjector",
    "SQLInjectionTest",
    "XSSInjectionTest",
    "CommandInjectionTest",
    # OWASP checks
    "OWASPChecker",
    "SecurityHeadersCheck",
    "CORSPolicyCheck",
    "RateLimitCheck",
    "ErrorLeakageCheck",
    # Scanner
    "SecurityScanner",
    "SecurityScanResult",
    "ScanConfig",
    # Journeys
    "SecurityJourney",
    "create_security_journey",
    "sql_injection_journey",
    "xss_journey",
    "auth_bypass_journey",
    "idor_journey",
    "rate_limit_journey",
    "full_security_journey",
]
