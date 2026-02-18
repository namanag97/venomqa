"""Autonomous VenomQA - zero-config API testing.

VenomQA reads your project's docker-compose.yml and OpenAPI spec,
spins up isolated test containers, and explores your API automatically.

Usage:
    venomqa  # Just run in your project directory

What happens:
    1. Finds docker-compose.yml -> understands your stack
    2. Finds openapi.yaml/swagger.json -> generates actions
    3. Runs preflight checks (Docker, auth, etc.)
    4. Spins up ISOLATED test containers (copies your setup)
    5. Runs state hypergraph exploration
    6. Reports bugs found
    7. Tears down containers
"""

from venomqa.autonomous.credentials import AuthType, CredentialLoader, Credentials
from venomqa.autonomous.discovery import ProjectDiscovery
from venomqa.autonomous.preflight import (
    CheckResult,
    FIXES,
    PreflightCheckResult,
    PreflightReport,
    PreflightRunner,
    display_preflight_report,
)
from venomqa.autonomous.runner import AutonomousRunner

__all__ = [
    # Discovery
    "ProjectDiscovery",
    # Runner
    "AutonomousRunner",
    # Credentials
    "AuthType",
    "Credentials",
    "CredentialLoader",
    # Preflight
    "CheckResult",
    "PreflightCheckResult",
    "PreflightReport",
    "PreflightRunner",
    "FIXES",
    "display_preflight_report",
]
