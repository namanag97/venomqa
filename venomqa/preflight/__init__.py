"""VenomQA Preflight -- smoke test an API before running full suites.

This module provides quick, targeted checks to verify an API is minimally
functional before investing time in a full test run.  It was born from
the painful experience of spending hours on combinatorial testing only
to discover that a simple 3-request smoke test would have caught the
real problem immediately (JWT user missing from DB, workspace IDs
referencing non-existent records).

Quick start:
    >>> from venomqa.preflight import SmokeTest, APINotReadyError
    >>> smoke = SmokeTest("http://localhost:8000", token="eyJ...")
    >>> try:
    ...     smoke.assert_ready()
    ... except APINotReadyError as e:
    ...     print(e)

For auto-discovery from an OpenAPI spec:
    >>> from venomqa.preflight import AutoPreflight
    >>> auto = AutoPreflight.from_openapi("http://localhost:8000/openapi.json")
    >>> report = auto.run()
    >>> report.print_report()

Legacy preflight (environment / config checks) is still available via
``PreflightChecker`` and ``run_preflight_checks``.
"""

from venomqa.preflight.auto import AutoPreflight
from venomqa.preflight.checks import (
    AuthCheck,
    BaseCheck,
    CRUDCheck,
    CustomHTTPCheck,
    DatabaseCheck,
    HealthCheck,
    ListCheck,
    OpenAPICheck,
    SmokeTestResult,
)
from venomqa.preflight.config import (
    AuthCheckConfig,
    CRUDCheckConfig,
    CustomCheckConfig,
    HealthCheckConfig,
    ListCheckConfig,
    PreflightConfig,
    generate_example_config,
    substitute_env_vars,
)
from venomqa.preflight.errors import (
    APINotReadyError,
    AuthenticationFailedError,
    ConnectionFailedError,
    PreflightError,
)
from venomqa.preflight.smoke import SmokeTest, SmokeTestReport

# Re-export legacy preflight symbols so existing ``from venomqa.preflight import ...``
# continues to work without changes.
from venomqa.preflight._legacy import (
    CheckResult,
    CheckStatus,
    PreflightChecker,
    PreflightResult,
    run_preflight_checks,
    run_preflight_checks_with_output,
)

__all__ = [
    # New smoke-test API
    "SmokeTest",
    "SmokeTestResult",
    "SmokeTestReport",
    "APINotReadyError",
    "PreflightError",
    "ConnectionFailedError",
    "AuthenticationFailedError",
    "AutoPreflight",
    # Individual checks
    "BaseCheck",
    "HealthCheck",
    "AuthCheck",
    "CRUDCheck",
    "ListCheck",
    "DatabaseCheck",
    "OpenAPICheck",
    # Legacy (environment / config) preflight
    "CheckStatus",
    "CheckResult",
    "PreflightResult",
    "PreflightChecker",
    "run_preflight_checks",
    "run_preflight_checks_with_output",
]
