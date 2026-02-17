"""Tests for environment management module."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from venomqa.environments import (
    Environment,
    EnvironmentComparison,
    EnvironmentConfig,
    EnvironmentHealthCheck,
    EnvironmentHealthResult,
    EnvironmentManager,
    EnvironmentSecrets,
    ResponseDifference,
    SecretProvider,
)
from venomqa.environments.manager import (
    EnvFileSecretProvider,
    EnvironmentMode,
    EnvironmentVariableSecretProvider,
)


class TestEnvironmentConfig:
    """Tests for EnvironmentConfig dataclass."""

    def test_basic_config(self) -> None:
        config = EnvironmentConfig(
            name="local",
            base_url="http://localhost:8000",
        )

        assert config.name == "local"
        assert config.base_url == "http://localhost:8000"
        assert config.database is None
        assert config.read_only is False
        assert config.mode == EnvironmentMode.FULL
        assert config.timeout == 30
        assert config.retry_count == 3
        assert config.disable_state_management is False

    def test_read_only_sets_mode(self) -> None:
        config = EnvironmentConfig(
            name="production",
            base_url="https://api.example.com",
            read_only=True,
        )

        assert config.read_only is True
        assert config.mode == EnvironmentMode.READ_ONLY
        assert config.disable_state_management is True

    def test_from_dict(self) -> None:
        data = {
            "base_url": "https://staging.example.com",
            "database": "postgresql://staging-db/test",
            "read_only": False,
            "timeout": 60,
            "tags": ["staging", "test"],
            "variables": {"API_KEY": "test-key"},
        }

        config = EnvironmentConfig.from_dict("staging", data)

        assert config.name == "staging"
        assert config.base_url == "https://staging.example.com"
        assert config.database == "postgresql://staging-db/test"
        assert config.timeout == 60
        assert config.tags == ["staging", "test"]
        assert config.variables == {"API_KEY": "test-key"}

    def test_to_dict(self) -> None:
        config = EnvironmentConfig(
            name="local",
            base_url="http://localhost:8000",
            timeout=30,
        )

        data = config.to_dict()

        assert data["name"] == "local"
        assert data["base_url"] == "http://localhost:8000"
        assert data["timeout"] == 30
        assert data["mode"] == "full"


class TestEnvFileSecretProvider:
    """Tests for EnvFileSecretProvider."""

    def test_load_env_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("API_KEY=secret123\n")
            f.write("DATABASE_URL=postgresql://localhost/test\n")
            f.write("# Comment line\n")
            f.write("QUOTED_VALUE=\"quoted value\"\n")
            f.write("SINGLE_QUOTED='single quoted'\n")
            f.flush()

            provider = EnvFileSecretProvider(f.name)

            assert provider.get("API_KEY") == "secret123"
            assert provider.get("DATABASE_URL") == "postgresql://localhost/test"
            assert provider.get("QUOTED_VALUE") == "quoted value"
            assert provider.get("SINGLE_QUOTED") == "single quoted"
            assert provider.get("NONEXISTENT") is None
            assert provider.get("NONEXISTENT", "default") == "default"

        os.unlink(f.name)

    def test_exists(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("API_KEY=secret\n")
            f.flush()

            provider = EnvFileSecretProvider(f.name)

            assert provider.exists("API_KEY") is True
            assert provider.exists("NONEXISTENT") is False

        os.unlink(f.name)

    def test_get_all(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("PREFIX_VAR1=value1\n")
            f.write("PREFIX_VAR2=value2\n")
            f.write("OTHER_VAR=value3\n")
            f.flush()

            provider = EnvFileSecretProvider(f.name)

            all_secrets = provider.get_all()
            assert len(all_secrets) == 3

            prefixed = provider.get_all("PREFIX_")
            assert len(prefixed) == 2
            assert "PREFIX_VAR1" in prefixed
            assert "PREFIX_VAR2" in prefixed

        os.unlink(f.name)

    def test_missing_file(self) -> None:
        provider = EnvFileSecretProvider("/nonexistent/path/.env")

        # Should not raise, just return None
        assert provider.get("ANY_KEY") is None


class TestEnvironmentVariableSecretProvider:
    """Tests for EnvironmentVariableSecretProvider."""

    def test_get_from_env(self) -> None:
        with patch.dict(os.environ, {"TEST_KEY": "test_value"}):
            provider = EnvironmentVariableSecretProvider()

            assert provider.get("TEST_KEY") == "test_value"
            assert provider.get("NONEXISTENT") is None

    def test_get_with_prefix(self) -> None:
        with patch.dict(os.environ, {"MYAPP_API_KEY": "secret123"}):
            provider = EnvironmentVariableSecretProvider(prefix="MYAPP_")

            assert provider.get("API_KEY") == "secret123"
            assert provider.get("MYAPP_API_KEY") is None  # Prefix is already applied

    def test_exists(self) -> None:
        with patch.dict(os.environ, {"EXISTS": "yes"}):
            provider = EnvironmentVariableSecretProvider()

            assert provider.exists("EXISTS") is True
            assert provider.exists("NOT_EXISTS") is False


class TestEnvironmentSecrets:
    """Tests for EnvironmentSecrets."""

    def test_multiple_providers(self) -> None:
        provider1 = Mock(spec=SecretProvider)
        provider1.get.return_value = None

        provider2 = Mock(spec=SecretProvider)
        provider2.get.return_value = "value_from_provider2"

        secrets = EnvironmentSecrets(providers=[provider1, provider2])

        assert secrets.get("KEY") == "value_from_provider2"
        provider1.get.assert_called_once_with("KEY")
        provider2.get.assert_called_once_with("KEY")

    def test_first_provider_wins(self) -> None:
        provider1 = Mock(spec=SecretProvider)
        provider1.get.return_value = "value_from_provider1"

        provider2 = Mock(spec=SecretProvider)

        secrets = EnvironmentSecrets(providers=[provider1, provider2])

        assert secrets.get("KEY") == "value_from_provider1"
        provider2.get.assert_not_called()

    def test_get_required(self) -> None:
        provider = Mock(spec=SecretProvider)
        provider.get.return_value = "required_value"

        secrets = EnvironmentSecrets(providers=[provider])

        assert secrets.get_required("KEY") == "required_value"

    def test_get_required_raises(self) -> None:
        provider = Mock(spec=SecretProvider)
        provider.get.return_value = None

        secrets = EnvironmentSecrets(providers=[provider])

        with pytest.raises(KeyError, match="Required secret not found"):
            secrets.get_required("MISSING_KEY")

    def test_exists(self) -> None:
        provider1 = Mock(spec=SecretProvider)
        provider1.exists.return_value = False

        provider2 = Mock(spec=SecretProvider)
        provider2.exists.return_value = True

        secrets = EnvironmentSecrets(providers=[provider1, provider2])

        assert secrets.exists("KEY") is True


class TestEnvironment:
    """Tests for Environment class."""

    def test_basic_properties(self) -> None:
        config = EnvironmentConfig(
            name="staging",
            base_url="https://staging.example.com",
            database="postgresql://staging-db/test",
        )
        env = Environment(config=config)

        assert env.name == "staging"
        assert env.base_url == "https://staging.example.com"
        assert env.database == "postgresql://staging-db/test"
        assert env.is_read_only is False
        assert env.is_active is False

    def test_activate_deactivate(self) -> None:
        config = EnvironmentConfig(
            name="test",
            base_url="http://localhost",
            variables={"TEST_VAR": "test_value"},
        )
        env = Environment(config=config)

        env.activate()

        assert env.is_active is True
        assert os.environ.get("TEST_VAR") == "test_value"

        env.deactivate()

        assert env.is_active is False
        assert os.environ.get("TEST_VAR") is None

    def test_allows_operation_full_mode(self) -> None:
        config = EnvironmentConfig(
            name="local",
            base_url="http://localhost",
        )
        env = Environment(config=config)

        assert env.allows_operation("read") is True
        assert env.allows_operation("write") is True
        assert env.allows_operation("delete") is True
        assert env.allows_operation("state_management") is True

    def test_allows_operation_read_only(self) -> None:
        config = EnvironmentConfig(
            name="production",
            base_url="https://api.example.com",
            read_only=True,
        )
        env = Environment(config=config)

        assert env.allows_operation("read") is True
        assert env.allows_operation("write") is False
        assert env.allows_operation("delete") is False
        assert env.allows_operation("state_management") is False


class TestEnvironmentHealthCheck:
    """Tests for EnvironmentHealthCheck and related classes."""

    def test_health_check_result(self) -> None:
        result = EnvironmentHealthResult(
            name="http_connectivity",
            healthy=True,
            message="HTTP 200",
            duration_ms=50.5,
            details={"status_code": 200},
        )

        assert result.name == "http_connectivity"
        assert result.healthy is True
        assert result.duration_ms == 50.5

    def test_environment_health_check(self) -> None:
        checks = [
            EnvironmentHealthResult(name="http", healthy=True, message="OK", duration_ms=10),
            EnvironmentHealthResult(name="db", healthy=True, message="OK", duration_ms=20),
        ]

        health = EnvironmentHealthCheck(
            environment="staging",
            overall_healthy=True,
            checks=checks,
        )

        assert health.environment == "staging"
        assert health.overall_healthy is True
        assert len(health.checks) == 2

    def test_to_dict(self) -> None:
        checks = [
            EnvironmentHealthResult(name="http", healthy=True, message="OK", duration_ms=10),
        ]

        health = EnvironmentHealthCheck(
            environment="staging",
            overall_healthy=True,
            checks=checks,
        )

        data = health.to_dict()

        assert data["environment"] == "staging"
        assert data["overall_healthy"] is True
        assert len(data["checks"]) == 1


class TestEnvironmentManager:
    """Tests for EnvironmentManager."""

    @pytest.fixture
    def config_file(self) -> str:
        config_content = """
environments:
  local:
    base_url: http://localhost:8000
    database: postgresql://localhost/test
  staging:
    base_url: https://staging.example.com
    database: postgresql://staging-db/test
    timeout: 60
  production:
    base_url: https://api.example.com
    database: null
    read_only: true

default_environment: local
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            yield f.name

        os.unlink(f.name)

    def test_load_from_config(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        assert len(manager.list_environments()) == 3
        assert "local" in manager.list_environments()
        assert "staging" in manager.list_environments()
        assert "production" in manager.list_environments()

    def test_default_environment(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        assert manager.default_environment == "local"

    def test_get_environment(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        env = manager.get_environment("staging")

        assert env.name == "staging"
        assert env.base_url == "https://staging.example.com"
        assert env.config.timeout == 60

    def test_get_environment_not_found(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        with pytest.raises(KeyError, match="Environment not found"):
            manager.get_environment("nonexistent")

    def test_get_default_environment(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        env = manager.get_environment()

        assert env.name == "local"

    def test_activate_environment(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        env = manager.activate("staging")

        assert env.is_active is True
        assert manager.active_environment == env

    def test_activate_switches_environment(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        env1 = manager.activate("local")
        assert env1.is_active is True

        env2 = manager.activate("staging")
        assert env2.is_active is True
        assert env1.is_active is False

    def test_deactivate(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        manager.activate("staging")
        assert manager.active_environment is not None

        manager.deactivate()
        assert manager.active_environment is None

    def test_add_environment(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        new_config = EnvironmentConfig(
            name="development",
            base_url="http://dev.example.com",
        )

        env = manager.add_environment(new_config)

        assert env.name == "development"
        assert "development" in manager.list_environments()

    def test_remove_environment(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        result = manager.remove_environment("staging")

        assert result is True
        assert "staging" not in manager.list_environments()

    def test_remove_nonexistent_environment(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        result = manager.remove_environment("nonexistent")

        assert result is False

    def test_get_environment_config_for_runner(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        config = manager.get_environment_config_for_runner("staging")

        assert config["base_url"] == "https://staging.example.com"
        assert config["timeout"] == 60
        assert config["environment"] == "staging"

    def test_production_environment_restrictions(self, config_file: str) -> None:
        manager = EnvironmentManager(config_file)

        env = manager.get_environment("production")

        assert env.is_read_only is True
        assert env.config.disable_state_management is True
        assert env.allows_operation("write") is False
        assert env.allows_operation("state_management") is False

    @patch("httpx.get")
    def test_check_health_http_success(self, mock_get: Mock, config_file: str) -> None:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        manager = EnvironmentManager(config_file)

        health = manager.check_health("staging")

        assert health.environment == "staging"
        http_check = next(c for c in health.checks if c.name == "http_connectivity")
        assert http_check.healthy is True

    @patch("httpx.get")
    def test_check_health_http_failure(self, mock_get: Mock, config_file: str) -> None:
        mock_get.side_effect = Exception("Connection refused")

        manager = EnvironmentManager(config_file)

        health = manager.check_health("local")

        http_check = next(c for c in health.checks if c.name == "http_connectivity")
        assert http_check.healthy is False
        assert "Connection refused" in http_check.message


class TestEnvironmentComparison:
    """Tests for EnvironmentComparison."""

    def test_comparison_no_differences(self) -> None:
        comparison = EnvironmentComparison(
            journey_name="test_journey",
            env1="staging",
            env2="production",
            env1_result={"success": True},
            env2_result={"success": True},
            differences=[],
            both_passed=True,
        )

        assert comparison.has_differences is False
        assert comparison.both_passed is True

    def test_comparison_with_differences(self) -> None:
        differences = [
            ResponseDifference(
                path="steps.login.response.status_code",
                env1_value=200,
                env2_value=201,
                difference_type="changed",
            ),
        ]

        comparison = EnvironmentComparison(
            journey_name="test_journey",
            env1="staging",
            env2="production",
            env1_result={"success": True},
            env2_result={"success": True},
            differences=differences,
            both_passed=True,
        )

        assert comparison.has_differences is True
        assert len(comparison.differences) == 1

    def test_to_dict(self) -> None:
        differences = [
            ResponseDifference(
                path="steps.login.success",
                env1_value=True,
                env2_value=False,
                difference_type="changed",
            ),
        ]

        comparison = EnvironmentComparison(
            journey_name="test_journey",
            env1="staging",
            env2="production",
            env1_result={"success": True},
            env2_result={"success": False},
            differences=differences,
            both_passed=False,
        )

        data = comparison.to_dict()

        assert data["journey_name"] == "test_journey"
        assert data["env1"] == "staging"
        assert data["env2"] == "production"
        assert data["both_passed"] is False
        assert data["has_differences"] is True
        assert len(data["differences"]) == 1


class TestEnvironmentManagerWithPreconfig:
    """Tests for EnvironmentManager with pre-configured environments."""

    def test_init_with_environments(self) -> None:
        environments = {
            "dev": EnvironmentConfig(
                name="dev",
                base_url="http://localhost:3000",
            ),
            "test": EnvironmentConfig(
                name="test",
                base_url="http://test.example.com",
            ),
        }

        manager = EnvironmentManager(environments=environments)

        assert len(manager.list_environments()) == 2
        assert "dev" in manager.list_environments()
        assert "test" in manager.list_environments()

    def test_init_with_default_environment(self) -> None:
        environments = {
            "dev": EnvironmentConfig(
                name="dev",
                base_url="http://localhost:3000",
            ),
        }

        manager = EnvironmentManager(
            environments=environments,
            default_environment="dev",
        )

        assert manager.default_environment == "dev"
        assert manager.get_environment().name == "dev"


class TestFilterJourneysForEnvironment:
    """Tests for filtering journeys based on environment restrictions."""

    def test_filter_for_read_only_environment(self) -> None:
        config = EnvironmentConfig(
            name="production",
            base_url="https://api.example.com",
            read_only=True,
        )

        manager = EnvironmentManager(
            environments={"production": config},
            default_environment="production",
        )

        # Create mock journeys with different tags
        journey1 = Mock()
        journey1.tags = ["read_only"]

        journey2 = Mock()
        journey2.tags = ["smoke"]

        journey3 = Mock()
        journey3.tags = ["write", "integration"]

        journey4 = Mock()
        journey4.tags = None

        journeys = [journey1, journey2, journey3, journey4]

        filtered = manager.filter_journeys_for_environment(journeys, "production")

        assert len(filtered) == 2
        assert journey1 in filtered
        assert journey2 in filtered
        assert journey3 not in filtered
        assert journey4 not in filtered

    def test_filter_for_full_environment(self) -> None:
        config = EnvironmentConfig(
            name="staging",
            base_url="https://staging.example.com",
            read_only=False,
        )

        manager = EnvironmentManager(
            environments={"staging": config},
            default_environment="staging",
        )

        journey1 = Mock()
        journey1.tags = ["read_only"]

        journey2 = Mock()
        journey2.tags = ["write"]

        journeys = [journey1, journey2]

        # In full mode, all journeys should be returned
        filtered = manager.filter_journeys_for_environment(journeys, "staging")

        assert len(filtered) == 2
