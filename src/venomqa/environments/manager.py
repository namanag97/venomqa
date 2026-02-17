"""Environment manager for multi-environment testing.

This module provides comprehensive environment management including:
- Environment configuration and switching
- Secret management per environment
- Health checks for environments
- Environment comparison for journey results
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from venomqa.core.models import Journey, JourneyResult

logger = logging.getLogger(__name__)


class EnvironmentMode(Enum):
    """Environment operational modes."""

    FULL = "full"  # Full testing with all operations
    READ_ONLY = "read_only"  # Only read operations allowed
    SMOKE = "smoke"  # Only smoke tests, minimal operations


@dataclass
class EnvironmentConfig:
    """Configuration for a single environment.

    Attributes:
        name: Unique name for the environment (e.g., "local", "staging", "production")
        base_url: Base URL for API requests
        database: Database connection URL (None if no direct DB access)
        read_only: If True, only read operations are allowed
        mode: Environment mode (full, read_only, smoke)
        timeout: Request timeout in seconds
        retry_count: Number of retries for failed requests
        disable_state_management: If True, state management is disabled
        tags: Optional tags for filtering environments
        variables: Custom environment variables
        secrets_provider: Name of the secrets provider to use
        env_file: Path to .env file for this environment
        metadata: Additional metadata
    """

    name: str
    base_url: str
    database: str | None = None
    read_only: bool = False
    mode: EnvironmentMode = EnvironmentMode.FULL
    timeout: int = 30
    retry_count: int = 3
    disable_state_management: bool = False
    tags: list[str] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    secrets_provider: str | None = None
    env_file: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize configuration."""
        if self.read_only:
            self.mode = EnvironmentMode.READ_ONLY
        if self.mode == EnvironmentMode.READ_ONLY:
            self.read_only = True
            self.disable_state_management = True

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> EnvironmentConfig:
        """Create EnvironmentConfig from dictionary."""
        mode_str = data.get("mode", "full")
        mode = EnvironmentMode(mode_str) if isinstance(mode_str, str) else EnvironmentMode.FULL

        return cls(
            name=name,
            base_url=data.get("base_url", "http://localhost:8000"),
            database=data.get("database"),
            read_only=data.get("read_only", False),
            mode=mode,
            timeout=data.get("timeout", 30),
            retry_count=data.get("retry_count", 3),
            disable_state_management=data.get("disable_state_management", False),
            tags=data.get("tags", []),
            variables=data.get("variables", {}),
            secrets_provider=data.get("secrets_provider"),
            env_file=data.get("env_file"),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "base_url": self.base_url,
            "database": self.database,
            "read_only": self.read_only,
            "mode": self.mode.value,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "disable_state_management": self.disable_state_management,
            "tags": self.tags,
            "variables": self.variables,
            "secrets_provider": self.secrets_provider,
            "env_file": self.env_file,
            "metadata": self.metadata,
        }


class SecretProvider(ABC):
    """Abstract base class for secret providers."""

    @abstractmethod
    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a secret by key."""
        pass

    @abstractmethod
    def get_all(self, prefix: str = "") -> dict[str, str]:
        """Get all secrets with optional prefix filter."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a secret exists."""
        pass


class EnvFileSecretProvider(SecretProvider):
    """Secret provider that loads from .env files."""

    def __init__(self, env_file: str | Path) -> None:
        """Initialize with .env file path."""
        self.env_file = Path(env_file)
        self._secrets: dict[str, str] = {}
        self._loaded = False

    def _load(self) -> None:
        """Load secrets from .env file."""
        if self._loaded:
            return

        if not self.env_file.exists():
            logger.debug(f"Environment file not found: {self.env_file}")
            self._loaded = True
            return

        try:
            with open(self.env_file) as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    if "=" not in line:
                        logger.warning(f"Invalid env file format at line {line_num}")
                        continue

                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()

                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    self._secrets[key] = value

            self._loaded = True
            logger.debug(f"Loaded {len(self._secrets)} secrets from {self.env_file}")

        except Exception as e:
            logger.error(f"Failed to load env file: {e}")
            self._loaded = True

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a secret by key."""
        self._load()
        return self._secrets.get(key, default)

    def get_all(self, prefix: str = "") -> dict[str, str]:
        """Get all secrets with optional prefix filter."""
        self._load()
        if not prefix:
            return self._secrets.copy()
        return {k: v for k, v in self._secrets.items() if k.startswith(prefix)}

    def exists(self, key: str) -> bool:
        """Check if a secret exists."""
        self._load()
        return key in self._secrets


class EnvironmentVariableSecretProvider(SecretProvider):
    """Secret provider that reads from environment variables."""

    def __init__(self, prefix: str = "") -> None:
        """Initialize with optional prefix."""
        self.prefix = prefix

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a secret from environment variables."""
        full_key = f"{self.prefix}{key}" if self.prefix else key
        return os.environ.get(full_key, default)

    def get_all(self, prefix: str = "") -> dict[str, str]:
        """Get all environment variables with optional prefix filter."""
        full_prefix = f"{self.prefix}{prefix}" if self.prefix else prefix
        return {k: v for k, v in os.environ.items() if k.startswith(full_prefix)}

    def exists(self, key: str) -> bool:
        """Check if an environment variable exists."""
        full_key = f"{self.prefix}{key}" if self.prefix else key
        return full_key in os.environ


class AWSSecretsManagerProvider(SecretProvider):
    """Secret provider for AWS Secrets Manager."""

    def __init__(
        self,
        region: str | None = None,
        secret_name: str | None = None,
        prefix: str = "",
    ) -> None:
        """Initialize AWS Secrets Manager provider."""
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.secret_name = secret_name
        self.prefix = prefix
        self._client: Any = None
        self._cache: dict[str, str] = {}
        self._cache_loaded = False

    def _get_client(self) -> Any:
        """Get or create boto3 client."""
        if self._client is not None:
            return self._client

        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 package not installed. Install with: pip install boto3"
            ) from None

        self._client = boto3.client("secretsmanager", region_name=self.region)
        return self._client

    def _load_secrets(self) -> None:
        """Load secrets from AWS Secrets Manager."""
        if self._cache_loaded:
            return

        if not self.secret_name:
            logger.warning("No secret_name specified for AWS Secrets Manager")
            self._cache_loaded = True
            return

        try:
            client = self._get_client()
            response = client.get_secret_value(SecretId=self.secret_name)

            if "SecretString" in response:
                secret_data = json.loads(response["SecretString"])
                if isinstance(secret_data, dict):
                    self._cache = {str(k): str(v) for k, v in secret_data.items()}

            self._cache_loaded = True
            logger.debug(
                f"Loaded {len(self._cache)} secrets from AWS Secrets Manager: {self.secret_name}"
            )

        except Exception as e:
            logger.error(f"Failed to load secrets from AWS Secrets Manager: {e}")
            self._cache_loaded = True

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a secret from AWS Secrets Manager."""
        self._load_secrets()
        full_key = f"{self.prefix}{key}" if self.prefix else key
        return self._cache.get(full_key, default)

    def get_all(self, prefix: str = "") -> dict[str, str]:
        """Get all secrets with optional prefix filter."""
        self._load_secrets()
        full_prefix = f"{self.prefix}{prefix}" if self.prefix else prefix
        return {k: v for k, v in self._cache.items() if k.startswith(full_prefix)}

    def exists(self, key: str) -> bool:
        """Check if a secret exists."""
        self._load_secrets()
        full_key = f"{self.prefix}{key}" if self.prefix else key
        return full_key in self._cache


class VaultSecretProvider(SecretProvider):
    """Secret provider for HashiCorp Vault."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        mount_point: str = "secret",
        path: str = "",
    ) -> None:
        """Initialize Vault provider."""
        self.url = url or os.environ.get("VAULT_ADDR", "http://localhost:8200")
        self._token = token or os.environ.get("VAULT_TOKEN")
        self.mount_point = mount_point
        self.path = path
        self._client: Any = None
        self._cache: dict[str, str] = {}
        self._cache_loaded = False

    def _get_client(self) -> Any:
        """Get or create Vault client."""
        if self._client is not None:
            return self._client

        try:
            import hvac
        except ImportError:
            raise ImportError(
                "hvac package not installed. Install with: pip install hvac"
            ) from None

        if not self._token:
            raise ValueError("No Vault token provided")

        self._client = hvac.Client(url=self.url, token=self._token)
        if not self._client.is_authenticated():
            raise ValueError("Vault authentication failed")

        return self._client

    def _load_secrets(self) -> None:
        """Load secrets from Vault."""
        if self._cache_loaded:
            return

        try:
            client = self._get_client()
            response = client.secrets.kv.v2.read_secret_version(
                path=self.path,
                mount_point=self.mount_point,
            )
            secret_data = response.get("data", {}).get("data", {})
            self._cache = {str(k): str(v) for k, v in secret_data.items()}
            self._cache_loaded = True
            logger.debug(f"Loaded {len(self._cache)} secrets from Vault: {self.path}")

        except Exception as e:
            logger.error(f"Failed to load secrets from Vault: {e}")
            self._cache_loaded = True

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a secret from Vault."""
        self._load_secrets()
        return self._cache.get(key, default)

    def get_all(self, prefix: str = "") -> dict[str, str]:
        """Get all secrets with optional prefix filter."""
        self._load_secrets()
        if not prefix:
            return self._cache.copy()
        return {k: v for k, v in self._cache.items() if k.startswith(prefix)}

    def exists(self, key: str) -> bool:
        """Check if a secret exists."""
        self._load_secrets()
        return key in self._cache


@dataclass
class EnvironmentSecrets:
    """Manages secrets for an environment using multiple providers."""

    providers: list[SecretProvider] = field(default_factory=list)

    def add_provider(self, provider: SecretProvider) -> None:
        """Add a secret provider."""
        self.providers.append(provider)

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a secret from any provider."""
        for provider in self.providers:
            value = provider.get(key)
            if value is not None:
                return value
        return default

    def get_required(self, key: str) -> str:
        """Get a required secret, raising an error if not found."""
        value = self.get(key)
        if value is None:
            raise KeyError(f"Required secret not found: {key}")
        return value

    def exists(self, key: str) -> bool:
        """Check if a secret exists in any provider."""
        return any(provider.exists(key) for provider in self.providers)


@dataclass
class Environment:
    """Represents a configured environment with its settings and secrets."""

    config: EnvironmentConfig
    secrets: EnvironmentSecrets = field(default_factory=EnvironmentSecrets)
    _active: bool = False

    @property
    def name(self) -> str:
        """Get environment name."""
        return self.config.name

    @property
    def base_url(self) -> str:
        """Get base URL."""
        return self.config.base_url

    @property
    def database(self) -> str | None:
        """Get database URL."""
        return self.config.database

    @property
    def is_read_only(self) -> bool:
        """Check if environment is read-only."""
        return self.config.read_only

    @property
    def is_active(self) -> bool:
        """Check if this environment is currently active."""
        return self._active

    def activate(self) -> None:
        """Activate this environment."""
        # Set environment variables
        for key, value in self.config.variables.items():
            os.environ[key] = value

        self._active = True
        logger.info(f"Activated environment: {self.name}")

    def deactivate(self) -> None:
        """Deactivate this environment."""
        # Clean up environment variables
        for key in self.config.variables:
            os.environ.pop(key, None)

        self._active = False
        logger.info(f"Deactivated environment: {self.name}")

    def get_secret(self, key: str, default: str | None = None) -> str | None:
        """Get a secret for this environment."""
        return self.secrets.get(key, default)

    def get_variable(self, key: str, default: str | None = None) -> str | None:
        """Get a variable for this environment."""
        return self.config.variables.get(key, default)

    def allows_operation(self, operation: str) -> bool:
        """Check if an operation is allowed in this environment.

        Args:
            operation: Operation type (read, write, delete, state_management)

        Returns:
            True if the operation is allowed
        """
        if operation == "state_management" and self.config.disable_state_management:
            return False

        if self.config.read_only and operation in ("write", "delete"):
            return False

        return True


@dataclass
class EnvironmentHealthResult:
    """Result of a single health check."""

    name: str
    healthy: bool
    message: str
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class EnvironmentHealthCheck:
    """Complete health check results for an environment."""

    environment: str
    overall_healthy: bool
    checks: list[EnvironmentHealthResult]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "environment": self.environment,
            "overall_healthy": self.overall_healthy,
            "checks": [
                {
                    "name": c.name,
                    "healthy": c.healthy,
                    "message": c.message,
                    "duration_ms": c.duration_ms,
                    "details": c.details,
                }
                for c in self.checks
            ],
            "timestamp": self.timestamp,
        }


@dataclass
class ResponseDifference:
    """Represents a difference in responses between environments."""

    path: str
    env1_value: Any
    env2_value: Any
    difference_type: str  # "missing", "added", "changed", "type_mismatch"


@dataclass
class EnvironmentComparison:
    """Result of comparing journey execution between environments."""

    journey_name: str
    env1: str
    env2: str
    env1_result: dict[str, Any]
    env2_result: dict[str, Any]
    differences: list[ResponseDifference]
    both_passed: bool
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def has_differences(self) -> bool:
        """Check if there are any differences."""
        return len(self.differences) > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "journey_name": self.journey_name,
            "env1": self.env1,
            "env2": self.env2,
            "env1_result": self.env1_result,
            "env2_result": self.env2_result,
            "differences": [
                {
                    "path": d.path,
                    "env1_value": d.env1_value,
                    "env2_value": d.env2_value,
                    "difference_type": d.difference_type,
                }
                for d in self.differences
            ],
            "both_passed": self.both_passed,
            "has_differences": self.has_differences,
            "timestamp": self.timestamp,
        }


class EnvironmentManager:
    """Manages multiple test environments.

    This class handles loading environment configurations, switching between
    environments, managing secrets, and comparing results across environments.

    Example:
        >>> manager = EnvironmentManager("venomqa.yaml")
        >>> env = manager.get_environment("staging")
        >>> health = manager.check_health("staging")
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        environments: dict[str, EnvironmentConfig] | None = None,
        default_environment: str | None = None,
    ) -> None:
        """Initialize the environment manager.

        Args:
            config_path: Path to venomqa.yaml configuration file
            environments: Pre-configured environments (overrides config file)
            default_environment: Name of the default environment
        """
        self._environments: dict[str, Environment] = {}
        self._active_environment: str | None = None
        self._default_environment: str | None = default_environment
        self._config_path = Path(config_path) if config_path else None

        if environments:
            for name, config in environments.items():
                self._environments[name] = self._create_environment(config)
        elif config_path:
            self._load_from_config(Path(config_path))

    def _load_from_config(self, config_path: Path) -> None:
        """Load environments from configuration file."""
        if not config_path.exists():
            logger.warning(f"Configuration file not found: {config_path}")
            return

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

            environments_config = config.get("environments", {})
            self._default_environment = config.get("default_environment")

            for name, env_data in environments_config.items():
                env_config = EnvironmentConfig.from_dict(name, env_data)
                self._environments[name] = self._create_environment(env_config)

            logger.info(f"Loaded {len(self._environments)} environments from {config_path}")

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse configuration: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    def _create_environment(self, config: EnvironmentConfig) -> Environment:
        """Create an Environment instance from config."""
        secrets = EnvironmentSecrets()

        # Add env file provider if specified
        if config.env_file:
            secrets.add_provider(EnvFileSecretProvider(config.env_file))

        # Add environment variable provider
        secrets.add_provider(EnvironmentVariableSecretProvider(f"VENOMQA_{config.name.upper()}_"))

        # Add secrets provider based on config
        if config.secrets_provider:
            provider = self._create_secrets_provider(config.secrets_provider, config.metadata)
            if provider:
                secrets.add_provider(provider)

        return Environment(config=config, secrets=secrets)

    def _create_secrets_provider(
        self, provider_type: str, metadata: dict[str, Any]
    ) -> SecretProvider | None:
        """Create a secrets provider based on type."""
        try:
            if provider_type == "aws_secrets_manager":
                return AWSSecretsManagerProvider(
                    region=metadata.get("aws_region"),
                    secret_name=metadata.get("secret_name"),
                    prefix=metadata.get("prefix", ""),
                )
            elif provider_type == "vault":
                return VaultSecretProvider(
                    url=metadata.get("vault_url"),
                    token=metadata.get("vault_token"),
                    mount_point=metadata.get("vault_mount", "secret"),
                    path=metadata.get("vault_path", ""),
                )
            elif provider_type == "env":
                return EnvironmentVariableSecretProvider(
                    prefix=metadata.get("prefix", "")
                )
            else:
                logger.warning(f"Unknown secrets provider type: {provider_type}")
                return None
        except Exception as e:
            logger.warning(f"Failed to create secrets provider {provider_type}: {e}")
            return None

    def add_environment(self, config: EnvironmentConfig) -> Environment:
        """Add a new environment.

        Args:
            config: Environment configuration

        Returns:
            The created Environment instance
        """
        env = self._create_environment(config)
        self._environments[config.name] = env
        return env

    def remove_environment(self, name: str) -> bool:
        """Remove an environment.

        Args:
            name: Environment name

        Returns:
            True if environment was removed
        """
        if name in self._environments:
            if self._active_environment == name:
                self._environments[name].deactivate()
                self._active_environment = None
            del self._environments[name]
            return True
        return False

    def get_environment(self, name: str | None = None) -> Environment:
        """Get an environment by name.

        Args:
            name: Environment name (uses default if None)

        Returns:
            Environment instance

        Raises:
            KeyError: If environment not found
        """
        if name is None:
            name = self._active_environment or self._default_environment

        if name is None:
            if self._environments:
                name = next(iter(self._environments))
            else:
                raise KeyError("No environments configured")

        if name not in self._environments:
            raise KeyError(f"Environment not found: {name}")

        return self._environments[name]

    def list_environments(self) -> list[str]:
        """List all environment names."""
        return list(self._environments.keys())

    def get_all_environments(self) -> dict[str, Environment]:
        """Get all environments."""
        return self._environments.copy()

    def activate(self, name: str) -> Environment:
        """Activate an environment.

        Args:
            name: Environment name

        Returns:
            The activated Environment
        """
        if self._active_environment and self._active_environment != name:
            self._environments[self._active_environment].deactivate()

        env = self.get_environment(name)
        env.activate()
        self._active_environment = name
        return env

    def deactivate(self) -> None:
        """Deactivate the current environment."""
        if self._active_environment:
            self._environments[self._active_environment].deactivate()
            self._active_environment = None

    @property
    def active_environment(self) -> Environment | None:
        """Get the currently active environment."""
        if self._active_environment:
            return self._environments.get(self._active_environment)
        return None

    @property
    def default_environment(self) -> str | None:
        """Get the default environment name."""
        return self._default_environment

    def check_health(self, name: str) -> EnvironmentHealthCheck:
        """Run health checks for an environment.

        Checks:
        - Connectivity (HTTP endpoint reachable)
        - Database connectivity (if configured)
        - Permissions (basic operations)

        Args:
            name: Environment name

        Returns:
            EnvironmentHealthCheck with results
        """
        env = self.get_environment(name)
        checks: list[EnvironmentHealthResult] = []

        # Check HTTP connectivity
        http_check = self._check_http_connectivity(env)
        checks.append(http_check)

        # Check database connectivity
        if env.database:
            db_check = self._check_database_connectivity(env)
            checks.append(db_check)

        # Check permissions
        permissions_check = self._check_permissions(env)
        checks.append(permissions_check)

        overall_healthy = all(c.healthy for c in checks)

        return EnvironmentHealthCheck(
            environment=name,
            overall_healthy=overall_healthy,
            checks=checks,
        )

    def _check_http_connectivity(self, env: Environment) -> EnvironmentHealthResult:
        """Check HTTP connectivity to the environment."""
        start_time = time.time()
        try:
            import httpx

            response = httpx.get(
                env.base_url,
                timeout=env.config.timeout,
                follow_redirects=True,
            )
            duration_ms = (time.time() - start_time) * 1000

            if response.status_code < 500:
                return EnvironmentHealthResult(
                    name="http_connectivity",
                    healthy=True,
                    message=f"HTTP {response.status_code}",
                    duration_ms=duration_ms,
                    details={"status_code": response.status_code, "url": env.base_url},
                )
            else:
                return EnvironmentHealthResult(
                    name="http_connectivity",
                    healthy=False,
                    message=f"Server error: HTTP {response.status_code}",
                    duration_ms=duration_ms,
                    details={"status_code": response.status_code, "url": env.base_url},
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return EnvironmentHealthResult(
                name="http_connectivity",
                healthy=False,
                message=f"Connection failed: {e}",
                duration_ms=duration_ms,
                details={"error": str(e), "url": env.base_url},
            )

    def _check_database_connectivity(self, env: Environment) -> EnvironmentHealthResult:
        """Check database connectivity."""
        if not env.database:
            return EnvironmentHealthResult(
                name="database_connectivity",
                healthy=True,
                message="No database configured (skipped)",
                duration_ms=0,
                details={"skipped": True},
            )

        start_time = time.time()
        try:
            # Try to connect based on database URL
            if env.database.startswith(("postgresql://", "postgres://")):
                return self._check_postgres_connectivity(env, start_time)
            elif env.database.startswith("mysql://"):
                return self._check_mysql_connectivity(env, start_time)
            elif env.database.startswith("sqlite://"):
                return self._check_sqlite_connectivity(env, start_time)
            else:
                duration_ms = (time.time() - start_time) * 1000
                return EnvironmentHealthResult(
                    name="database_connectivity",
                    healthy=False,
                    message="Unknown database type",
                    duration_ms=duration_ms,
                    details={"database_url": env.database[:20] + "..."},
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return EnvironmentHealthResult(
                name="database_connectivity",
                healthy=False,
                message=f"Connection failed: {e}",
                duration_ms=duration_ms,
                details={"error": str(e)},
            )

    def _check_postgres_connectivity(
        self, env: Environment, start_time: float
    ) -> EnvironmentHealthResult:
        """Check PostgreSQL connectivity."""
        try:
            import psycopg

            with psycopg.connect(env.database, connect_timeout=env.config.timeout) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()

            duration_ms = (time.time() - start_time) * 1000
            return EnvironmentHealthResult(
                name="database_connectivity",
                healthy=True,
                message="PostgreSQL connection successful",
                duration_ms=duration_ms,
                details={"database_type": "postgresql"},
            )

        except ImportError:
            duration_ms = (time.time() - start_time) * 1000
            return EnvironmentHealthResult(
                name="database_connectivity",
                healthy=False,
                message="psycopg package not installed",
                duration_ms=duration_ms,
                details={"error": "psycopg not installed"},
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return EnvironmentHealthResult(
                name="database_connectivity",
                healthy=False,
                message=f"PostgreSQL connection failed: {e}",
                duration_ms=duration_ms,
                details={"error": str(e)},
            )

    def _check_mysql_connectivity(
        self, env: Environment, start_time: float
    ) -> EnvironmentHealthResult:
        """Check MySQL connectivity."""
        try:
            import mysql.connector

            # Parse MySQL URL
            # mysql://user:pass@host:port/database
            pattern = r"mysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
            match = re.match(pattern, env.database or "")
            if not match:
                raise ValueError("Invalid MySQL connection string format")

            user, password, host, port, database = match.groups()

            conn = mysql.connector.connect(
                user=user,
                password=password,
                host=host,
                port=int(port),
                database=database,
                connect_timeout=env.config.timeout,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()

            duration_ms = (time.time() - start_time) * 1000
            return EnvironmentHealthResult(
                name="database_connectivity",
                healthy=True,
                message="MySQL connection successful",
                duration_ms=duration_ms,
                details={"database_type": "mysql"},
            )

        except ImportError:
            duration_ms = (time.time() - start_time) * 1000
            return EnvironmentHealthResult(
                name="database_connectivity",
                healthy=False,
                message="mysql-connector-python package not installed",
                duration_ms=duration_ms,
                details={"error": "mysql-connector-python not installed"},
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return EnvironmentHealthResult(
                name="database_connectivity",
                healthy=False,
                message=f"MySQL connection failed: {e}",
                duration_ms=duration_ms,
                details={"error": str(e)},
            )

    def _check_sqlite_connectivity(
        self, env: Environment, start_time: float
    ) -> EnvironmentHealthResult:
        """Check SQLite connectivity."""
        try:
            import sqlite3

            # Parse SQLite URL: sqlite:///path/to/db.sqlite
            db_path = (env.database or "").replace("sqlite:///", "")

            conn = sqlite3.connect(db_path, timeout=env.config.timeout)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()

            duration_ms = (time.time() - start_time) * 1000
            return EnvironmentHealthResult(
                name="database_connectivity",
                healthy=True,
                message="SQLite connection successful",
                duration_ms=duration_ms,
                details={"database_type": "sqlite"},
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return EnvironmentHealthResult(
                name="database_connectivity",
                healthy=False,
                message=f"SQLite connection failed: {e}",
                duration_ms=duration_ms,
                details={"error": str(e)},
            )

    def _check_permissions(self, env: Environment) -> EnvironmentHealthResult:
        """Check environment permissions."""
        start_time = time.time()

        allowed_ops = []
        denied_ops = []

        for op in ["read", "write", "delete", "state_management"]:
            if env.allows_operation(op):
                allowed_ops.append(op)
            else:
                denied_ops.append(op)

        duration_ms = (time.time() - start_time) * 1000

        return EnvironmentHealthResult(
            name="permissions",
            healthy=True,
            message=f"Allowed: {', '.join(allowed_ops)}; Denied: {', '.join(denied_ops) or 'none'}",
            duration_ms=duration_ms,
            details={
                "allowed": allowed_ops,
                "denied": denied_ops,
                "read_only": env.is_read_only,
            },
        )

    def compare_environments(
        self,
        journey: Journey,
        env1_name: str,
        env2_name: str,
        ignore_fields: list[str] | None = None,
    ) -> EnvironmentComparison:
        """Run a journey in two environments and compare results.

        Args:
            journey: Journey to run
            env1_name: First environment name
            env2_name: Second environment name
            ignore_fields: Fields to ignore in comparison (e.g., timestamps, IDs)

        Returns:
            EnvironmentComparison with differences
        """
        from venomqa import Client
        from venomqa.runner import JourneyRunner

        ignore_fields = ignore_fields or ["timestamp", "created_at", "updated_at", "id"]

        # Run in first environment
        env1 = self.activate(env1_name)
        client1 = Client(base_url=env1.base_url, timeout=env1.config.timeout)
        runner1 = JourneyRunner(client=client1, fail_fast=False)
        result1 = runner1.run(journey)

        # Run in second environment
        env2 = self.activate(env2_name)
        client2 = Client(base_url=env2.base_url, timeout=env2.config.timeout)
        runner2 = JourneyRunner(client=client2, fail_fast=False)
        result2 = runner2.run(journey)

        self.deactivate()

        # Compare results
        differences = self._compare_results(result1, result2, ignore_fields)

        return EnvironmentComparison(
            journey_name=journey.name,
            env1=env1_name,
            env2=env2_name,
            env1_result=self._result_to_dict(result1),
            env2_result=self._result_to_dict(result2),
            differences=differences,
            both_passed=result1.success and result2.success,
        )

    def _compare_results(
        self,
        result1: JourneyResult,
        result2: JourneyResult,
        ignore_fields: list[str],
    ) -> list[ResponseDifference]:
        """Compare two journey results."""
        differences: list[ResponseDifference] = []

        # Compare step results
        steps1 = {s.step_name: s for s in result1.step_results}
        steps2 = {s.step_name: s for s in result2.step_results}

        all_steps = set(steps1.keys()) | set(steps2.keys())

        for step_name in all_steps:
            step1 = steps1.get(step_name)
            step2 = steps2.get(step_name)

            if step1 is None:
                differences.append(
                    ResponseDifference(
                        path=f"steps.{step_name}",
                        env1_value=None,
                        env2_value="present",
                        difference_type="missing",
                    )
                )
                continue

            if step2 is None:
                differences.append(
                    ResponseDifference(
                        path=f"steps.{step_name}",
                        env1_value="present",
                        env2_value=None,
                        difference_type="added",
                    )
                )
                continue

            # Compare success status
            if step1.success != step2.success:
                differences.append(
                    ResponseDifference(
                        path=f"steps.{step_name}.success",
                        env1_value=step1.success,
                        env2_value=step2.success,
                        difference_type="changed",
                    )
                )

            # Compare responses
            if step1.response and step2.response:
                resp_diffs = self._compare_dicts(
                    step1.response,
                    step2.response,
                    f"steps.{step_name}.response",
                    ignore_fields,
                )
                differences.extend(resp_diffs)

        return differences

    def _compare_dicts(
        self,
        dict1: dict[str, Any],
        dict2: dict[str, Any],
        path: str,
        ignore_fields: list[str],
    ) -> list[ResponseDifference]:
        """Recursively compare two dictionaries."""
        differences: list[ResponseDifference] = []

        all_keys = set(dict1.keys()) | set(dict2.keys())

        for key in all_keys:
            if key in ignore_fields:
                continue

            current_path = f"{path}.{key}"
            val1 = dict1.get(key)
            val2 = dict2.get(key)

            if key not in dict1:
                differences.append(
                    ResponseDifference(
                        path=current_path,
                        env1_value=None,
                        env2_value=val2,
                        difference_type="missing",
                    )
                )
            elif key not in dict2:
                differences.append(
                    ResponseDifference(
                        path=current_path,
                        env1_value=val1,
                        env2_value=None,
                        difference_type="added",
                    )
                )
            elif type(val1) != type(val2):
                differences.append(
                    ResponseDifference(
                        path=current_path,
                        env1_value=val1,
                        env2_value=val2,
                        difference_type="type_mismatch",
                    )
                )
            elif isinstance(val1, dict) and isinstance(val2, dict):
                differences.extend(
                    self._compare_dicts(val1, val2, current_path, ignore_fields)
                )
            elif val1 != val2:
                differences.append(
                    ResponseDifference(
                        path=current_path,
                        env1_value=val1,
                        env2_value=val2,
                        difference_type="changed",
                    )
                )

        return differences

    def _result_to_dict(self, result: JourneyResult) -> dict[str, Any]:
        """Convert JourneyResult to dictionary."""
        return {
            "journey_name": result.journey_name,
            "success": result.success,
            "duration_ms": result.duration_ms,
            "step_count": len(result.step_results),
            "issues_count": len(result.issues),
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
        }

    def get_environment_config_for_runner(self, name: str | None = None) -> dict[str, Any]:
        """Get configuration suitable for JourneyRunner.

        Args:
            name: Environment name (uses active/default if None)

        Returns:
            Configuration dictionary
        """
        env = self.get_environment(name)

        return {
            "base_url": env.base_url,
            "timeout": env.config.timeout,
            "retry_count": env.config.retry_count,
            "db_url": env.database,
            "disable_state_management": env.config.disable_state_management,
            "read_only": env.is_read_only,
            "environment": env.name,
        }

    def filter_journeys_for_environment(
        self,
        journeys: list[Journey],
        environment_name: str | None = None,
    ) -> list[Journey]:
        """Filter journeys based on environment restrictions.

        In production/read-only environments, only journeys tagged as
        read-only or smoke tests will be returned.

        Args:
            journeys: List of journeys to filter
            environment_name: Environment name (uses active/default if None)

        Returns:
            Filtered list of journeys
        """
        env = self.get_environment(environment_name)

        if not env.is_read_only:
            return journeys

        # In read-only mode, filter to only read-only journeys
        filtered = []
        for journey in journeys:
            tags = getattr(journey, "tags", []) or []
            if "read_only" in tags or "smoke" in tags:
                filtered.append(journey)

        logger.info(
            f"Filtered {len(journeys)} journeys to {len(filtered)} for read-only environment"
        )
        return filtered
