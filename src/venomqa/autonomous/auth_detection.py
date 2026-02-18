"""Detect authentication requirements from OpenAPI spec.

Checks securitySchemes BEFORE calling the API, so we can prompt
the user for credentials instead of hitting 401.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AuthRequirement:
    """Detected authentication requirement from OpenAPI."""

    auth_type: str  # "apiKey", "http", "oauth2", "openIdConnect"
    name: str  # e.g., "ApiKeyAuth", "BearerAuth"
    location: str | None = None  # "header", "query", "cookie" (for apiKey)
    header_name: str | None = None  # e.g., "X-API-Key", "Authorization"
    scheme: str | None = None  # "bearer", "basic" (for http)

    def get_fix_instructions(self) -> str:
        """Return human-readable instructions for providing this auth."""
        if self.auth_type == "apiKey" and self.location == "header":
            return (
                f"Your API uses {self.header_name} header authentication.\n\n"
                f"  venomqa --api-key YOUR_KEY\n\n"
                f"Or set environment variable:\n"
                f"  export VENOMQA_API_KEY=your-key\n\n"
                f"Or create .env file:\n"
                f"  echo 'VENOMQA_API_KEY=your-key' > .env"
            )
        elif self.auth_type == "http" and self.scheme == "bearer":
            return (
                "Your API uses Bearer token authentication.\n\n"
                "  venomqa --auth-token YOUR_TOKEN\n\n"
                "Or set environment variable:\n"
                "  export VENOMQA_AUTH_TOKEN=your-token\n\n"
                "Or create .env file:\n"
                "  echo 'VENOMQA_AUTH_TOKEN=your-token' > .env"
            )
        elif self.auth_type == "http" and self.scheme == "basic":
            return (
                "Your API uses Basic authentication.\n\n"
                "  venomqa --basic-auth username:password\n\n"
                "Or set environment variable:\n"
                "  export VENOMQA_BASIC_AUTH=username:password"
            )
        else:
            return (
                f"Your API uses {self.auth_type} authentication ({self.name}).\n\n"
                "Try one of:\n"
                "  venomqa --api-key YOUR_KEY\n"
                "  venomqa --auth-token YOUR_TOKEN\n"
                "  venomqa --basic-auth user:pass"
            )


def detect_auth_from_openapi(openapi_path: Path) -> list[AuthRequirement]:
    """Detect authentication requirements from OpenAPI spec.

    Returns list of AuthRequirement objects, one per security scheme.
    """
    if not openapi_path.exists():
        return []

    try:
        with open(openapi_path) as f:
            if openapi_path.suffix == ".json":
                import json
                spec = json.load(f)
            else:
                spec = yaml.safe_load(f)
    except Exception:
        return []

    if not isinstance(spec, dict):
        return []

    # Get security schemes from components (OpenAPI 3) or securityDefinitions (Swagger 2)
    security_schemes = (
        spec.get("components", {}).get("securitySchemes", {})
        or spec.get("securityDefinitions", {})
    )

    if not security_schemes:
        return []

    requirements = []
    for name, scheme in security_schemes.items():
        if not isinstance(scheme, dict):
            continue

        auth_type = scheme.get("type", "")

        if auth_type == "apiKey":
            requirements.append(AuthRequirement(
                auth_type="apiKey",
                name=name,
                location=scheme.get("in", "header"),
                header_name=scheme.get("name", "X-API-Key"),
            ))
        elif auth_type == "http":
            requirements.append(AuthRequirement(
                auth_type="http",
                name=name,
                scheme=scheme.get("scheme", "bearer").lower(),
            ))
        elif auth_type in ("oauth2", "openIdConnect"):
            requirements.append(AuthRequirement(
                auth_type=auth_type,
                name=name,
            ))

    return requirements


def check_auth_configured(
    requirements: list[AuthRequirement],
    credentials: Any,  # Credentials object
) -> tuple[bool, str | None]:
    """Check if credentials satisfy the auth requirements.

    Returns:
        (True, None) if auth is configured or not required
        (False, fix_instructions) if auth is required but not configured
    """
    if not requirements:
        return True, None

    if credentials and credentials.has_api_auth():
        return True, None

    # Auth required but not configured - return fix instructions
    primary = requirements[0]
    return False, primary.get_fix_instructions()
