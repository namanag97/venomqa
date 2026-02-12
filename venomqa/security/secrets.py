"""Secrets management for VenomQA - environment variables and Vault integration."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SecretsError(Exception):
    """Base exception for secrets management errors."""

    pass


class SecretNotFoundError(SecretsError):
    """Raised when a secret cannot be found."""

    pass


class VaultConnectionError(SecretsError):
    """Raised when Vault connection fails."""

    pass


@dataclass
class CachedSecret:
    """A cached secret with expiration."""

    value: str
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now() >= self.expires_at


class SecretBackend(ABC):
    """Abstract base class for secret backends."""

    @abstractmethod
    def get(self, key: str) -> str:
        """Retrieve a secret by key."""
        pass

    @abstractmethod
    def get_with_metadata(self, key: str) -> tuple[str, dict[str, Any]]:
        """Retrieve a secret with metadata."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a secret exists."""
        pass

    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]:
        """List available secret keys."""
        pass


class EnvironmentBackend(SecretBackend):
    """Backend for loading secrets from environment variables."""

    def __init__(self, prefix: str = "", env_file: str | Path | None = None) -> None:
        self.prefix = prefix
        self._cache: dict[str, str] = {}
        self._loaded_env_file = False

        if env_file:
            self._load_env_file(env_file)

    def _load_env_file(self, env_file: str | Path) -> None:
        """Load secrets from a .env file."""
        env_path = Path(env_file)
        if not env_path.exists():
            logger.warning(f"Environment file not found: {env_path}")
            return

        try:
            with open(env_path) as f:
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

                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    if key not in os.environ:
                        os.environ[key] = value
                        self._cache[key] = value

            self._loaded_env_file = True
            logger.debug(f"Loaded environment file: {env_path}")

        except Exception as e:
            logger.error(f"Failed to load env file: {e}")

    def get(self, key: str) -> str:
        """Get a secret from environment variables."""
        full_key = f"{self.prefix}{key}" if self.prefix else key

        value = os.environ.get(full_key)
        if value is None:
            raise SecretNotFoundError(f"Secret not found: {full_key}")

        return value

    def get_with_metadata(self, key: str) -> tuple[str, dict[str, Any]]:
        """Get a secret with metadata."""
        value = self.get(key)
        full_key = f"{self.prefix}{key}" if self.prefix else key
        metadata = {
            "source": "environment",
            "key": full_key,
        }
        return value, metadata

    def exists(self, key: str) -> bool:
        """Check if a secret exists."""
        full_key = f"{self.prefix}{key}" if self.prefix else key
        return full_key in os.environ

    def list_keys(self, prefix: str = "") -> list[str]:
        """List available secret keys."""
        keys = []
        env_prefix = f"{self.prefix}{prefix}" if self.prefix else prefix

        for key in os.environ:
            if self.prefix and not key.startswith(self.prefix):
                continue
            if prefix and not key.startswith(env_prefix):
                continue

            if self.prefix:
                keys.append(key[len(self.prefix) :])
            else:
                keys.append(key)

        return sorted(keys)


class VaultBackend(SecretBackend):
    """Backend for loading secrets from HashiCorp Vault."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        namespace: str | None = None,
        mount_point: str = "secret",
        verify_tls: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self.url = url or os.environ.get("VAULT_ADDR", "http://localhost:8200")
        self._token = token
        self.namespace = namespace
        self.mount_point = mount_point
        self.verify_tls = verify_tls
        self.timeout = timeout
        self._client: Any = None
        self._cache: dict[str, CachedSecret] = {}

    def _get_client(self) -> Any:
        """Get or create Vault client."""
        if self._client is not None:
            return self._client

        try:
            import hvac
        except ImportError:
            raise VaultConnectionError(
                "hvac package not installed. Install with: pip install hvac"
            ) from None

        token = self._token or os.environ.get("VAULT_TOKEN")
        if not token:
            raise VaultConnectionError("No Vault token provided")

        self._client = hvac.Client(
            url=self.url,
            token=token,
            namespace=self.namespace,
            verify=self.verify_tls,
            timeout=self.timeout,
        )

        if not self._client.is_authenticated():
            raise VaultConnectionError("Vault authentication failed")

        logger.info(f"Connected to Vault at {self.url}")
        return self._client

    def get(self, key: str, ttl_seconds: int | None = None) -> str:
        """Get a secret from Vault."""
        cached = self._cache.get(key)
        if cached and not cached.is_expired():
            return cached.value

        client = self._get_client()

        try:
            if client.secrets.kv.v2.enabled:
                response = client.secrets.kv.v2.read_secret_version(
                    path=key,
                    mount_point=self.mount_point,
                )
                secret_data = response.get("data", {}).get("data", {})
            else:
                response = client.secrets.kv.v1.read_secret(
                    path=key,
                    mount_point=self.mount_point,
                )
                secret_data = response.get("data", {})

            if "value" in secret_data:
                value = secret_data["value"]
            elif len(secret_data) == 1:
                value = list(secret_data.values())[0]
            else:
                raise SecretNotFoundError(
                    f"Ambiguous secret structure for '{key}'. "
                    "Specify which key within the secret to use."
                )

            expires_at = None
            if ttl_seconds:
                expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

            self._cache[key] = CachedSecret(
                value=str(value),
                expires_at=expires_at,
                metadata={"path": key, "mount_point": self.mount_point},
            )

            return str(value)

        except Exception as e:
            if "InvalidPath" in str(e) or "permission denied" in str(e).lower():
                raise SecretNotFoundError(f"Secret not found in Vault: {key}") from e
            raise VaultConnectionError(f"Vault error: {e}") from e

    def get_with_metadata(self, key: str) -> tuple[str, dict[str, Any]]:
        """Get a secret with metadata."""
        value = self.get(key)
        cached = self._cache.get(key)
        metadata = cached.metadata if cached else {"path": key}
        metadata["source"] = "vault"
        return value, metadata

    def exists(self, key: str) -> bool:
        """Check if a secret exists in Vault."""
        try:
            self.get(key)
            return True
        except SecretNotFoundError:
            return False

    def list_keys(self, prefix: str = "") -> list[str]:
        """List secrets in Vault."""
        client = self._get_client()
        keys = []

        try:
            if client.secrets.kv.v2.enabled:
                response = client.secrets.kv.v2.list_secrets(
                    path=prefix,
                    mount_point=self.mount_point,
                )
            else:
                response = client.secrets.kv.v1.list_secrets(
                    path=prefix,
                    mount_point=self.mount_point,
                )

            keys = response.get("data", {}).get("keys", [])
        except Exception as e:
            logger.warning(f"Failed to list Vault secrets: {e}")

        return keys

    def invalidate_cache(self, key: str | None = None) -> None:
        """Invalidate cached secrets."""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()


class SecretsManager:
    """Central manager for secrets with multiple backends."""

    DEFAULT_SENSITIVE_KEYS = frozenset(
        [
            "password",
            "passwd",
            "pwd",
            "secret",
            "token",
            "api_key",
            "apikey",
            "auth",
            "credential",
            "private_key",
            "access_key",
            "secret_key",
            "db_password",
            "database_password",
            "db_user",
            "database_user",
        ]
    )

    def __init__(
        self,
        backends: list[SecretBackend] | None = None,
        auto_load_env: bool = True,
        env_prefix: str = "VENOMQA_",
        env_file: str | Path | None = ".env",
        enable_vault: bool = False,
    ) -> None:
        self._backends: list[SecretBackend] = []
        self._cache: dict[str, CachedSecret] = {}
        self._sensitive_keys: set[str] = set(self.DEFAULT_SENSITIVE_KEYS)
        self._redaction_callback: Callable[[str], str] | None = None

        if backends:
            self._backends = list(backends)
        else:
            if auto_load_env:
                self._backends.append(EnvironmentBackend(prefix=env_prefix, env_file=env_file))

            if enable_vault:
                vault_url = os.environ.get("VAULT_ADDR")
                if vault_url:
                    try:
                        self._backends.append(VaultBackend(url=vault_url))
                        logger.info("Vault backend enabled")
                    except VaultConnectionError as e:
                        logger.warning(f"Failed to connect to Vault: {e}")

    def add_backend(self, backend: SecretBackend, priority: int = 0) -> None:
        """Add a secret backend with optional priority."""
        if priority <= 0:
            self._backends.append(backend)
        else:
            self._backends.insert(priority - 1, backend)

    def get(self, key: str, default: str | None = None, ttl_seconds: int | None = None) -> str:
        """Get a secret, trying all backends in order."""
        cached = self._cache.get(key)
        if cached and not cached.is_expired():
            return cached.value

        for backend in self._backends:
            try:
                value = backend.get(key)
                expires_at = None
                if ttl_seconds:
                    expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

                self._cache[key] = CachedSecret(
                    value=value,
                    expires_at=expires_at,
                )
                return value
            except SecretNotFoundError:
                continue

        if default is not None:
            return default

        raise SecretNotFoundError(f"Secret not found in any backend: {key}")

    def get_required(self, key: str) -> str:
        """Get a required secret, raising an error if not found."""
        value = self.get(key)
        if value is None:
            raise SecretNotFoundError(f"Required secret not found: {key}")
        return value

    def get_int(self, key: str, default: int | None = None) -> int:
        """Get a secret as an integer."""
        value = self.get(key, default=str(default) if default is not None else None)
        try:
            return int(value)
        except (TypeError, ValueError):
            raise SecretsError(f"Secret '{key}' is not a valid integer: {value}") from None

    def get_bool(self, key: str, default: bool | None = None) -> bool:
        """Get a secret as a boolean."""
        value = self.get(key, default=str(default) if default is not None else None)
        if value is None:
            raise SecretNotFoundError(f"Secret not found: {key}")

        true_values = {"true", "1", "yes", "on", "enabled"}
        false_values = {"false", "0", "no", "off", "disabled"}

        value_lower = value.lower().strip()
        if value_lower in true_values:
            return True
        if value_lower in false_values:
            return False

        raise SecretsError(f"Secret '{key}' is not a valid boolean: {value}")

    def get_json(self, key: str, default: Any = None) -> Any:
        """Get a secret as parsed JSON."""
        import json

        value = self.get(key, default=None)
        if value is None:
            return default

        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            raise SecretsError(f"Secret '{key}' is not valid JSON: {e}") from e

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        """Set a secret in the local cache (not persisted to backends)."""
        expires_at = None
        if ttl_seconds:
            expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

        self._cache[key] = CachedSecret(
            value=value,
            expires_at=expires_at,
        )

    def is_sensitive(self, key: str) -> bool:
        """Check if a key is considered sensitive."""
        key_lower = key.lower()
        return any(sensitive in key_lower for sensitive in self._sensitive_keys)

    def redact(self, key: str, value: str) -> str:
        """Redact a sensitive value for logging."""
        if not self.is_sensitive(key):
            return value

        if self._redaction_callback:
            return self._redaction_callback(value)

        if len(value) <= 4:
            return "*" * len(value)
        return value[:2] + "*" * (len(value) - 4) + value[-2:]

    def add_sensitive_key(self, key: str) -> None:
        """Add a key pattern to the sensitive keys set."""
        self._sensitive_keys.add(key.lower())

    def set_redaction_callback(self, callback: Callable[[str], str]) -> None:
        """Set a custom redaction callback."""
        self._redaction_callback = callback

    def invalidate_cache(self, key: str | None = None) -> None:
        """Invalidate cached secrets."""
        if key:
            self._cache.pop(key, None)
            for backend in self._backends:
                if isinstance(backend, VaultBackend):
                    backend.invalidate_cache(key)
        else:
            self._cache.clear()
            for backend in self._backends:
                if isinstance(backend, VaultBackend):
                    backend.invalidate_cache()

    def health_check(self) -> dict[str, bool]:
        """Check health of all backends."""
        health = {}
        for i, backend in enumerate(self._backends):
            backend_name = backend.__class__.__name__
            try:
                if isinstance(backend, EnvironmentBackend):
                    health[backend_name] = True
                elif isinstance(backend, VaultBackend):
                    health[backend_name] = backend._get_client().is_authenticated()
                else:
                    health[f"backend_{i}"] = True
            except Exception:
                health[backend_name] = False
        return health
