"""Credential management for autonomous mode.

Loads credentials with precedence: CLI > env > .env > yaml > interactive prompt.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class AuthType(Enum):
    """Authentication type for API requests."""

    NONE = "none"
    BEARER_TOKEN = "bearer_token"
    API_KEY = "api_key"
    BASIC_AUTH = "basic_auth"


@dataclass
class Credentials:
    """Container for all credentials needed by autonomous mode.

    Tracks where each credential came from (CLI, env, .env, yaml, prompt).
    """

    auth_type: AuthType = AuthType.NONE

    # Bearer token auth
    auth_token: str | None = None

    # API key auth
    api_key: str | None = None
    api_key_header: str = "X-API-Key"

    # Basic auth
    basic_auth_user: str | None = None
    basic_auth_password: str | None = None

    # Database credentials
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "postgres"

    # Track source of each credential for debugging
    sources: dict[str, str] = field(default_factory=dict)

    def get_http_headers(self) -> dict[str, str]:
        """Generate HTTP headers based on auth type."""
        headers: dict[str, str] = {}

        if self.auth_type == AuthType.BEARER_TOKEN and self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        elif self.auth_type == AuthType.API_KEY and self.api_key:
            headers[self.api_key_header] = self.api_key
        elif self.auth_type == AuthType.BASIC_AUTH:
            if self.basic_auth_user and self.basic_auth_password:
                import base64

                credentials = f"{self.basic_auth_user}:{self.basic_auth_password}"
                encoded = base64.b64encode(credentials.encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"

        return headers

    def get_db_dsn(self, db_type: str = "postgres") -> str:
        """Generate database connection string."""
        if db_type == "postgres":
            return (
                f"postgresql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        elif db_type == "mysql":
            return (
                f"mysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return ""

    def has_api_auth(self) -> bool:
        """Check if any API authentication is configured."""
        return self.auth_type != AuthType.NONE


class CredentialLoader:
    """Loads credentials with precedence: CLI > env > .env > yaml > prompt.

    Usage:
        loader = CredentialLoader(
            auth_token="cli-token",  # From CLI --auth-token
            project_dir=Path("."),
        )
        credentials = loader.load()
    """

    def __init__(
        self,
        *,
        # CLI overrides
        auth_token: str | None = None,
        api_key: str | None = None,
        basic_auth: str | None = None,  # "user:password"
        db_password: str | None = None,
        api_key_header: str | None = None,
        # Project context
        project_dir: Path | str = ".",
        env_file: str | None = ".env",
        config_file: str | None = "venomqa.yaml",
        # Behavior
        interactive: bool = True,
    ) -> None:
        self.project_dir = Path(project_dir).resolve()

        # CLI overrides
        self._cli_auth_token = auth_token
        self._cli_api_key = api_key
        self._cli_basic_auth = basic_auth
        self._cli_db_password = db_password
        self._cli_api_key_header = api_key_header

        # File paths
        self._env_file = env_file
        self._config_file = config_file

        # Whether to prompt interactively if TTY and not CI
        self._interactive = interactive

    def load(self) -> Credentials:
        """Load credentials from all sources with precedence."""
        creds = Credentials()

        # Load from each source (later sources override earlier)
        self._load_from_yaml(creds)
        self._load_from_env_file(creds)
        self._load_from_env(creds)
        self._load_from_cli(creds)

        # Determine auth type from what was loaded
        self._determine_auth_type(creds)

        # Interactive prompt if no auth and TTY available
        if not creds.has_api_auth() and self._should_prompt():
            self._prompt_for_auth(creds)

        return creds

    def _load_from_yaml(self, creds: Credentials) -> None:
        """Load credentials from venomqa.yaml."""
        if not self._config_file:
            return

        yaml_path = self.project_dir / self._config_file
        if not yaml_path.exists():
            return

        try:
            with open(yaml_path) as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            return

        auth = config.get("auth", {})

        if auth.get("bearer_token"):
            creds.auth_token = auth["bearer_token"]
            creds.sources["auth_token"] = "yaml"

        if auth.get("api_key"):
            creds.api_key = auth["api_key"]
            creds.sources["api_key"] = "yaml"

        if auth.get("api_key_header"):
            creds.api_key_header = auth["api_key_header"]
            creds.sources["api_key_header"] = "yaml"

        if auth.get("basic_auth"):
            basic = auth["basic_auth"]
            if isinstance(basic, dict):
                creds.basic_auth_user = basic.get("user")
                creds.basic_auth_password = basic.get("password")
            elif isinstance(basic, str) and ":" in basic:
                user, password = basic.split(":", 1)
                creds.basic_auth_user = user
                creds.basic_auth_password = password
            creds.sources["basic_auth"] = "yaml"

        # Database credentials
        db = config.get("database", {})
        if db.get("user"):
            creds.db_user = db["user"]
            creds.sources["db_user"] = "yaml"
        if db.get("password"):
            creds.db_password = db["password"]
            creds.sources["db_password"] = "yaml"

    def _load_from_env_file(self, creds: Credentials) -> None:
        """Load credentials from .env file."""
        if not self._env_file:
            return

        env_path = self.project_dir / self._env_file
        if not env_path.exists():
            return

        env_vars: dict[str, str] = {}
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    env_vars[key] = value
        except Exception:
            return

        self._apply_env_vars(creds, env_vars, source=".env")

    def _load_from_env(self, creds: Credentials) -> None:
        """Load credentials from environment variables."""
        self._apply_env_vars(creds, dict(os.environ), source="env")

    def _apply_env_vars(
        self, creds: Credentials, env_vars: dict[str, str], source: str
    ) -> None:
        """Apply environment variables to credentials."""
        # Auth token
        for key in ["VENOMQA_AUTH_TOKEN", "VENOMQA_BEARER_TOKEN", "AUTH_TOKEN"]:
            if key in env_vars:
                creds.auth_token = env_vars[key]
                creds.sources["auth_token"] = source

        # API key
        for key in ["VENOMQA_API_KEY", "API_KEY"]:
            if key in env_vars:
                creds.api_key = env_vars[key]
                creds.sources["api_key"] = source

        # API key header
        if "VENOMQA_API_KEY_HEADER" in env_vars:
            creds.api_key_header = env_vars["VENOMQA_API_KEY_HEADER"]
            creds.sources["api_key_header"] = source

        # Basic auth
        for key in ["VENOMQA_BASIC_AUTH", "BASIC_AUTH"]:
            if key in env_vars and ":" in env_vars[key]:
                user, password = env_vars[key].split(":", 1)
                creds.basic_auth_user = user
                creds.basic_auth_password = password
                creds.sources["basic_auth"] = source

        # Database password
        for key in ["VENOMQA_DB_PASSWORD", "POSTGRES_PASSWORD", "DB_PASSWORD"]:
            if key in env_vars:
                creds.db_password = env_vars[key]
                creds.sources["db_password"] = source

        # Database user
        for key in ["VENOMQA_DB_USER", "POSTGRES_USER", "DB_USER"]:
            if key in env_vars:
                creds.db_user = env_vars[key]
                creds.sources["db_user"] = source

    def _load_from_cli(self, creds: Credentials) -> None:
        """Load credentials from CLI arguments (highest precedence)."""
        if self._cli_auth_token:
            creds.auth_token = self._cli_auth_token
            creds.sources["auth_token"] = "cli"

        if self._cli_api_key:
            creds.api_key = self._cli_api_key
            creds.sources["api_key"] = "cli"

        if self._cli_api_key_header:
            creds.api_key_header = self._cli_api_key_header
            creds.sources["api_key_header"] = "cli"

        if self._cli_basic_auth and ":" in self._cli_basic_auth:
            user, password = self._cli_basic_auth.split(":", 1)
            creds.basic_auth_user = user
            creds.basic_auth_password = password
            creds.sources["basic_auth"] = "cli"

        if self._cli_db_password:
            creds.db_password = self._cli_db_password
            creds.sources["db_password"] = "cli"

    def _determine_auth_type(self, creds: Credentials) -> None:
        """Determine auth type based on loaded credentials."""
        # Order of precedence for auth types
        if creds.auth_token:
            creds.auth_type = AuthType.BEARER_TOKEN
        elif creds.api_key:
            creds.auth_type = AuthType.API_KEY
        elif creds.basic_auth_user and creds.basic_auth_password:
            creds.auth_type = AuthType.BASIC_AUTH
        else:
            creds.auth_type = AuthType.NONE

    def _should_prompt(self) -> bool:
        """Check if we should prompt interactively."""
        if not self._interactive:
            return False

        # Don't prompt in CI environments
        ci_vars = ["CI", "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS_URL", "CIRCLECI"]
        if any(os.environ.get(var) for var in ci_vars):
            return False

        # Check if we have a TTY
        return sys.stdin.isatty() and sys.stdout.isatty()

    def _prompt_for_auth(self, creds: Credentials) -> None:
        """Interactively prompt for authentication if needed."""
        try:
            import click
            from rich.console import Console

            console = Console()
            console.print(
                "\n[yellow]No API authentication configured.[/yellow]"
            )
            console.print(
                "If your API requires auth, you can provide credentials now.\n"
            )

            auth_type = click.prompt(
                "Auth type",
                type=click.Choice(["none", "bearer", "api_key", "basic"]),
                default="none",
            )

            if auth_type == "bearer":
                token = click.prompt("Bearer token", hide_input=True)
                creds.auth_token = token
                creds.auth_type = AuthType.BEARER_TOKEN
                creds.sources["auth_token"] = "prompt"

            elif auth_type == "api_key":
                key = click.prompt("API key", hide_input=True)
                header = click.prompt(
                    "API key header", default="X-API-Key"
                )
                creds.api_key = key
                creds.api_key_header = header
                creds.auth_type = AuthType.API_KEY
                creds.sources["api_key"] = "prompt"

            elif auth_type == "basic":
                user = click.prompt("Username")
                password = click.prompt("Password", hide_input=True)
                creds.basic_auth_user = user
                creds.basic_auth_password = password
                creds.auth_type = AuthType.BASIC_AUTH
                creds.sources["basic_auth"] = "prompt"

        except (ImportError, EOFError, KeyboardInterrupt):
            # No click/rich or user cancelled - continue without auth
            pass
