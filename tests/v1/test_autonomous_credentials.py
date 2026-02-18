"""Tests for venomqa.autonomous.credentials module."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from venomqa.autonomous.credentials import (
    AuthType,
    CredentialLoader,
    Credentials,
)


class TestCredentials:
    """Tests for the Credentials dataclass."""

    def test_default_values(self):
        """Test default credential values."""
        creds = Credentials()
        assert creds.auth_type == AuthType.NONE
        assert creds.auth_token is None
        assert creds.api_key is None
        assert creds.db_user == "postgres"
        assert creds.db_password == "postgres"

    def test_has_api_auth_none(self):
        """Test has_api_auth returns False for no auth."""
        creds = Credentials()
        assert creds.has_api_auth() is False

    def test_has_api_auth_bearer(self):
        """Test has_api_auth returns True for bearer token."""
        creds = Credentials(auth_type=AuthType.BEARER_TOKEN, auth_token="test")
        assert creds.has_api_auth() is True

    def test_has_api_auth_api_key(self):
        """Test has_api_auth returns True for API key."""
        creds = Credentials(auth_type=AuthType.API_KEY, api_key="test")
        assert creds.has_api_auth() is True


class TestGetHttpHeaders:
    """Tests for Credentials.get_http_headers()."""

    def test_no_auth_returns_empty_headers(self):
        """Test no auth returns empty headers."""
        creds = Credentials()
        headers = creds.get_http_headers()
        assert headers == {}

    def test_bearer_token_header(self):
        """Test bearer token generates correct header."""
        creds = Credentials(
            auth_type=AuthType.BEARER_TOKEN,
            auth_token="my-secret-token",
        )
        headers = creds.get_http_headers()
        assert headers == {"Authorization": "Bearer my-secret-token"}

    def test_api_key_header_default(self):
        """Test API key with default header name."""
        creds = Credentials(
            auth_type=AuthType.API_KEY,
            api_key="my-api-key",
        )
        headers = creds.get_http_headers()
        assert headers == {"X-API-Key": "my-api-key"}

    def test_api_key_header_custom(self):
        """Test API key with custom header name."""
        creds = Credentials(
            auth_type=AuthType.API_KEY,
            api_key="my-api-key",
            api_key_header="Authorization",
        )
        headers = creds.get_http_headers()
        assert headers == {"Authorization": "my-api-key"}

    def test_basic_auth_header(self):
        """Test basic auth generates correct header."""
        import base64

        creds = Credentials(
            auth_type=AuthType.BASIC_AUTH,
            basic_auth_user="admin",
            basic_auth_password="secret123",
        )
        headers = creds.get_http_headers()

        expected = base64.b64encode(b"admin:secret123").decode()
        assert headers == {"Authorization": f"Basic {expected}"}


class TestGetDbDsn:
    """Tests for Credentials.get_db_dsn()."""

    def test_postgres_dsn(self):
        """Test PostgreSQL DSN generation."""
        creds = Credentials(
            db_user="myuser",
            db_password="mypass",
            db_host="dbhost",
            db_port=5433,
            db_name="mydb",
        )
        dsn = creds.get_db_dsn("postgres")
        assert dsn == "postgresql://myuser:mypass@dbhost:5433/mydb"

    def test_mysql_dsn(self):
        """Test MySQL DSN generation."""
        creds = Credentials(
            db_user="myuser",
            db_password="mypass",
            db_host="dbhost",
            db_port=3306,
            db_name="mydb",
        )
        dsn = creds.get_db_dsn("mysql")
        assert dsn == "mysql://myuser:mypass@dbhost:3306/mydb"

    def test_unknown_db_type(self):
        """Test unknown database type returns empty string."""
        creds = Credentials()
        dsn = creds.get_db_dsn("unknown")
        assert dsn == ""


class TestCredentialLoader:
    """Tests for the CredentialLoader class."""

    def test_cli_overrides_env(self):
        """Test CLI arguments override environment variables."""
        with patch.dict(os.environ, {"VENOMQA_AUTH_TOKEN": "env-token"}):
            loader = CredentialLoader(
                auth_token="cli-token",
                interactive=False,
            )
            creds = loader.load()
            assert creds.auth_token == "cli-token"
            assert creds.sources.get("auth_token") == "cli"

    def test_env_variable_loading(self):
        """Test loading from environment variables."""
        with patch.dict(os.environ, {
            "VENOMQA_AUTH_TOKEN": "env-token",
            "VENOMQA_API_KEY": "env-api-key",
        }, clear=False):
            loader = CredentialLoader(interactive=False)
            creds = loader.load()
            # API key takes precedence over token if both present
            # Actually, token is set last so it should be used
            assert creds.auth_token == "env-token"

    def test_api_key_from_env(self):
        """Test API key loading from environment."""
        with patch.dict(os.environ, {"VENOMQA_API_KEY": "test-key"}, clear=False):
            loader = CredentialLoader(interactive=False)
            creds = loader.load()
            assert creds.api_key == "test-key"
            assert creds.auth_type == AuthType.API_KEY

    def test_basic_auth_from_env(self):
        """Test basic auth parsing from environment."""
        with patch.dict(os.environ, {"VENOMQA_BASIC_AUTH": "user:pass"}, clear=False):
            loader = CredentialLoader(interactive=False)
            creds = loader.load()
            assert creds.basic_auth_user == "user"
            assert creds.basic_auth_password == "pass"
            assert creds.auth_type == AuthType.BASIC_AUTH

    def test_env_file_loading(self):
        """Test loading from .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text('VENOMQA_API_KEY="file-api-key"\n')

            loader = CredentialLoader(
                project_dir=tmpdir,
                env_file=".env",
                interactive=False,
            )
            creds = loader.load()
            assert creds.api_key == "file-api-key"
            assert creds.sources.get("api_key") == ".env"

    def test_yaml_config_loading(self):
        """Test loading from venomqa.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_file = Path(tmpdir) / "venomqa.yaml"
            yaml_file.write_text("""
auth:
  api_key: yaml-api-key
  api_key_header: X-Custom-Key
database:
  user: dbuser
  password: dbpass
""")

            loader = CredentialLoader(
                project_dir=tmpdir,
                config_file="venomqa.yaml",
                env_file=None,
                interactive=False,
            )
            creds = loader.load()
            assert creds.api_key == "yaml-api-key"
            assert creds.api_key_header == "X-Custom-Key"
            assert creds.db_user == "dbuser"
            assert creds.db_password == "dbpass"

    def test_precedence_cli_over_env_over_file(self):
        """Test complete precedence chain: CLI > env > .env > yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create yaml config
            yaml_file = Path(tmpdir) / "venomqa.yaml"
            yaml_file.write_text("auth:\n  api_key: yaml-key\n")

            # Create .env file
            env_file = Path(tmpdir) / ".env"
            env_file.write_text('VENOMQA_API_KEY="dotenv-key"\n')

            # Set environment variable
            with patch.dict(os.environ, {"VENOMQA_API_KEY": "env-key"}):
                # Test CLI wins
                loader = CredentialLoader(
                    api_key="cli-key",
                    project_dir=tmpdir,
                    interactive=False,
                )
                creds = loader.load()
                assert creds.api_key == "cli-key"
                assert creds.sources["api_key"] == "cli"

            # Test env wins over file (no CLI)
            with patch.dict(os.environ, {"VENOMQA_API_KEY": "env-key"}):
                loader = CredentialLoader(
                    project_dir=tmpdir,
                    interactive=False,
                )
                creds = loader.load()
                assert creds.api_key == "env-key"
                assert creds.sources["api_key"] == "env"

    def test_db_password_override(self):
        """Test database password CLI override."""
        loader = CredentialLoader(
            db_password="cli-db-pass",
            interactive=False,
        )
        creds = loader.load()
        assert creds.db_password == "cli-db-pass"
        assert creds.sources.get("db_password") == "cli"

    def test_no_interactive_in_ci(self):
        """Test interactive prompt is disabled in CI environments."""
        with patch.dict(os.environ, {"CI": "true"}):
            loader = CredentialLoader(interactive=True)
            assert loader._should_prompt() is False

    def test_auth_type_determined_correctly(self):
        """Test auth type is correctly determined from credentials."""
        # Bearer token
        loader = CredentialLoader(auth_token="token", interactive=False)
        creds = loader.load()
        assert creds.auth_type == AuthType.BEARER_TOKEN

        # API key
        loader = CredentialLoader(api_key="key", interactive=False)
        creds = loader.load()
        assert creds.auth_type == AuthType.API_KEY

        # Basic auth
        loader = CredentialLoader(basic_auth="user:pass", interactive=False)
        creds = loader.load()
        assert creds.auth_type == AuthType.BASIC_AUTH

        # None
        loader = CredentialLoader(interactive=False)
        creds = loader.load()
        assert creds.auth_type == AuthType.NONE
