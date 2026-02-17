"""Tests for VenomQA Preflight Configuration.

Tests cover:
- PreflightConfig construction and defaults
- YAML loading
- Environment variable substitution (including special vars)
- from_dict() parsing with all check types
- from_config() SmokeTest creation
- Invalid config handling
- Config serialization round-trip
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from venomqa.preflight.config import (
    AuthCheckConfig,
    CRUDCheckConfig,
    CustomCheckConfig,
    HealthCheckConfig,
    ListCheckConfig,
    PreflightConfig,
    _substitute_recursive,
    generate_example_config,
    substitute_env_vars,
)

# =========================================================================
# substitute_env_vars
# =========================================================================

class TestSubstituteEnvVars:
    """Tests for the substitute_env_vars function."""

    def test_no_placeholders(self):
        """Strings without ${} are returned unchanged."""
        assert substitute_env_vars("hello world") == "hello world"

    def test_simple_env_var(self, monkeypatch):
        """${VAR} is replaced by the env var value."""
        monkeypatch.setenv("TEST_VAR_1", "replaced")
        assert substitute_env_vars("prefix-${TEST_VAR_1}-suffix") == "prefix-replaced-suffix"

    def test_env_var_with_default(self, monkeypatch):
        """${VAR:default} uses the env var when set."""
        monkeypatch.setenv("TEST_VAR_2", "fromenv")
        assert substitute_env_vars("${TEST_VAR_2:fallback}") == "fromenv"

    def test_env_var_default_used(self, monkeypatch):
        """${VAR:default} uses the default when the var is not set."""
        monkeypatch.delenv("TEST_VAR_MISSING_99", raising=False)
        assert substitute_env_vars("${TEST_VAR_MISSING_99:fallback}") == "fallback"

    def test_env_var_missing_no_default_left_as_is(self, monkeypatch):
        """${VAR} without a default is left as-is (template placeholder)."""
        monkeypatch.delenv("DEFINITELY_NOT_SET_XYZ", raising=False)
        result = substitute_env_vars("${DEFINITELY_NOT_SET_XYZ}")
        assert result == "${DEFINITELY_NOT_SET_XYZ}"

    def test_random_special_var(self):
        """${RANDOM} produces an 8-char hex string."""
        result = substitute_env_vars("id-${RANDOM}")
        # id- prefix + 8 hex chars
        assert result.startswith("id-")
        assert len(result) == 3 + 8
        assert re.match(r"^id-[0-9a-f]{8}$", result)

    def test_random_is_unique(self):
        """Two ${RANDOM} in the same string produce different values."""
        result = substitute_env_vars("${RANDOM}-${RANDOM}")
        parts = result.split("-")
        assert len(parts) == 2
        # They should (almost certainly) be different
        assert parts[0] != parts[1]

    def test_uuid_special_var(self):
        """${UUID} produces a valid UUID4 string."""
        import uuid
        result = substitute_env_vars("${UUID}")
        # Should not raise
        parsed = uuid.UUID(result)
        assert parsed.version == 4

    def test_timestamp_special_var(self):
        """${TIMESTAMP} produces a numeric timestamp."""
        result = substitute_env_vars("${TIMESTAMP}")
        ts = int(result)
        assert ts > 1_700_000_000  # After 2023

    def test_multiple_vars_in_one_string(self, monkeypatch):
        """Multiple placeholders in a single string are all resolved."""
        monkeypatch.setenv("HOST", "example.com")
        monkeypatch.setenv("PORT", "3000")
        result = substitute_env_vars("http://${HOST}:${PORT}/api")
        assert result == "http://example.com:3000/api"

    def test_empty_default(self, monkeypatch):
        """${VAR:} uses an empty string as default."""
        monkeypatch.delenv("NOT_SET_ABC", raising=False)
        assert substitute_env_vars("pre${NOT_SET_ABC:}post") == "prepost"


class TestSubstituteRecursive:
    """Tests for the _substitute_recursive helper."""

    def test_dict_substitution(self, monkeypatch):
        monkeypatch.setenv("MY_URL", "http://test.com")
        data = {"url": "${MY_URL}", "port": 8080}
        result = _substitute_recursive(data)
        assert result == {"url": "http://test.com", "port": 8080}

    def test_list_substitution(self, monkeypatch):
        monkeypatch.setenv("MY_PATH", "/health")
        data = ["${MY_PATH}", "/readyz"]
        result = _substitute_recursive(data)
        assert result == ["/health", "/readyz"]

    def test_nested_substitution(self, monkeypatch):
        monkeypatch.setenv("DEEP_VAL", "found")
        data = {"outer": {"inner": "${DEEP_VAL}"}}
        result = _substitute_recursive(data)
        assert result == {"outer": {"inner": "found"}}

    def test_non_string_passthrough(self):
        """Non-string, non-dict, non-list values are returned as-is."""
        assert _substitute_recursive(42) == 42
        assert _substitute_recursive(True) is True
        assert _substitute_recursive(None) is None


# =========================================================================
# HealthCheckConfig
# =========================================================================

class TestHealthCheckConfig:
    def test_defaults(self):
        hc = HealthCheckConfig()
        assert hc.path == "/health"
        assert hc.expected_status == [200]
        assert hc.expected_json is None
        assert hc.timeout is None

    def test_custom(self):
        hc = HealthCheckConfig(
            path="/healthz",
            expected_status=[200, 204],
            expected_json={"status": "ok"},
            timeout=5.0,
        )
        assert hc.path == "/healthz"
        assert hc.expected_status == [200, 204]
        assert hc.expected_json == {"status": "ok"}
        assert hc.timeout == 5.0


# =========================================================================
# AuthCheckConfig
# =========================================================================

class TestAuthCheckConfig:
    def test_defaults(self):
        ac = AuthCheckConfig()
        assert ac.path == "/api/v1/me"
        assert ac.method == "GET"
        assert ac.expected_status == [200]


# =========================================================================
# CRUDCheckConfig
# =========================================================================

class TestCRUDCheckConfig:
    def test_defaults(self):
        cc = CRUDCheckConfig()
        assert cc.path == "/api/v1/resources"
        assert cc.payload == {}
        assert cc.name is None
        assert cc.method == "POST"
        assert cc.expected_status == [200, 201, 409]
        assert cc.cleanup_path is None


# =========================================================================
# ListCheckConfig
# =========================================================================

class TestListCheckConfig:
    def test_defaults(self):
        lc = ListCheckConfig()
        assert lc.path == "/api/v1/resources"
        assert lc.expected_status == [200]
        assert lc.expected_type == "array"


# =========================================================================
# CustomCheckConfig
# =========================================================================

class TestCustomCheckConfig:
    def test_defaults(self):
        xc = CustomCheckConfig()
        assert xc.name == "Custom check"
        assert xc.method == "GET"
        assert xc.path == "/"
        assert xc.payload is None
        assert xc.headers is None
        assert xc.expected_status == [200]
        assert xc.expected_json is None


# =========================================================================
# PreflightConfig
# =========================================================================

class TestPreflightConfig:
    """Tests for PreflightConfig construction and methods."""

    def test_defaults(self):
        config = PreflightConfig()
        assert config.base_url == "http://localhost:8000"
        assert config.timeout == 10.0
        assert config.token is None
        assert config.token_env_var is None
        assert config.auth_header == "Authorization"
        assert config.auth_prefix == "Bearer"
        assert config.health_checks == []
        assert config.auth_checks == []
        assert config.crud_checks == []
        assert config.list_checks == []
        assert config.custom_checks == []

    def test_resolve_token_explicit(self):
        config = PreflightConfig(token="my-token")
        assert config.resolve_token() == "my-token"

    def test_resolve_token_env_var(self, monkeypatch):
        monkeypatch.setenv("TEST_TOKEN", "env-token")
        config = PreflightConfig(token_env_var="TEST_TOKEN")
        assert config.resolve_token() == "env-token"

    def test_resolve_token_explicit_over_env(self, monkeypatch):
        monkeypatch.setenv("TEST_TOKEN", "env-token")
        config = PreflightConfig(token="explicit", token_env_var="TEST_TOKEN")
        assert config.resolve_token() == "explicit"

    def test_resolve_token_none(self):
        config = PreflightConfig()
        assert config.resolve_token() is None

    def test_resolve_token_env_not_set(self, monkeypatch):
        monkeypatch.delenv("NOT_SET_TOKEN_VAR", raising=False)
        config = PreflightConfig(token_env_var="NOT_SET_TOKEN_VAR")
        assert config.resolve_token() is None


# =========================================================================
# PreflightConfig.from_dict
# =========================================================================

class TestPreflightConfigFromDict:
    """Tests for PreflightConfig.from_dict()."""

    def test_minimal(self):
        config = PreflightConfig.from_dict({})
        assert config.base_url == "http://localhost:8000"
        assert config.timeout == 10.0

    def test_base_settings(self):
        config = PreflightConfig.from_dict({
            "base_url": "http://example.com:3000",
            "timeout": 30.0,
        })
        assert config.base_url == "http://example.com:3000"
        assert config.timeout == 30.0

    def test_auth_settings(self):
        config = PreflightConfig.from_dict({
            "auth": {
                "token": "my-token",
                "token_env_var": "MY_TOKEN",
                "header": "X-API-Key",
                "prefix": "Key",
            }
        })
        assert config.token == "my-token"
        assert config.token_env_var == "MY_TOKEN"
        assert config.auth_header == "X-API-Key"
        assert config.auth_prefix == "Key"

    def test_health_checks_from_dict(self):
        config = PreflightConfig.from_dict({
            "health_checks": [
                {"path": "/healthz", "expected_status": [200, 204]},
                {"path": "/ready", "expected_json": {"ready": True}, "timeout": 5.0},
            ]
        })
        assert len(config.health_checks) == 2
        assert config.health_checks[0].path == "/healthz"
        assert config.health_checks[0].expected_status == [200, 204]
        assert config.health_checks[1].expected_json == {"ready": True}
        assert config.health_checks[1].timeout == 5.0

    def test_health_checks_from_string(self):
        config = PreflightConfig.from_dict({
            "health_checks": ["/health", "/healthz"]
        })
        assert len(config.health_checks) == 2
        assert config.health_checks[0].path == "/health"
        assert config.health_checks[1].path == "/healthz"

    def test_auth_checks_from_dict(self):
        config = PreflightConfig.from_dict({
            "auth_checks": [
                {"path": "/api/me", "method": "POST", "expected_status": [200, 201]},
            ]
        })
        assert len(config.auth_checks) == 1
        assert config.auth_checks[0].method == "POST"

    def test_auth_checks_from_string(self):
        config = PreflightConfig.from_dict({
            "auth_checks": ["/api/me"]
        })
        assert len(config.auth_checks) == 1
        assert config.auth_checks[0].path == "/api/me"

    def test_crud_checks(self):
        config = PreflightConfig.from_dict({
            "crud_checks": [
                {
                    "name": "Create item",
                    "path": "/items",
                    "payload": {"name": "test"},
                    "method": "PUT",
                    "expected_status": [201],
                    "cleanup_path": "/items/${id}",
                }
            ]
        })
        assert len(config.crud_checks) == 1
        cc = config.crud_checks[0]
        assert cc.name == "Create item"
        assert cc.path == "/items"
        assert cc.payload == {"name": "test"}
        assert cc.method == "PUT"
        assert cc.expected_status == [201]
        assert cc.cleanup_path == "/items/${id}"

    def test_list_checks(self):
        config = PreflightConfig.from_dict({
            "list_checks": [
                {"path": "/items", "expected_type": "paginated"},
            ]
        })
        assert len(config.list_checks) == 1
        assert config.list_checks[0].expected_type == "paginated"

    def test_list_checks_from_string(self):
        config = PreflightConfig.from_dict({
            "list_checks": ["/api/items"]
        })
        assert config.list_checks[0].path == "/api/items"

    def test_custom_checks(self):
        config = PreflightConfig.from_dict({
            "custom_checks": [
                {
                    "name": "Docs",
                    "method": "GET",
                    "path": "/docs",
                    "payload": {"key": "value"},
                    "headers": {"X-Test": "yes"},
                    "expected_status": [200, 301],
                    "expected_json": {"version": "3.0"},
                }
            ]
        })
        assert len(config.custom_checks) == 1
        xc = config.custom_checks[0]
        assert xc.name == "Docs"
        assert xc.headers == {"X-Test": "yes"}
        assert xc.expected_json == {"version": "3.0"}

    def test_env_var_substitution(self, monkeypatch):
        monkeypatch.setenv("MY_BASE_URL", "http://staging:9000")
        config = PreflightConfig.from_dict({
            "base_url": "${MY_BASE_URL}",
        })
        assert config.base_url == "http://staging:9000"

    def test_env_var_default_substitution(self, monkeypatch):
        monkeypatch.delenv("PROBABLY_NOT_SET_1234", raising=False)
        config = PreflightConfig.from_dict({
            "base_url": "${PROBABLY_NOT_SET_1234:http://fallback:8000}",
        })
        assert config.base_url == "http://fallback:8000"

    def test_invalid_health_check_type(self):
        with pytest.raises(ValueError, match="Invalid health check config"):
            PreflightConfig.from_dict({"health_checks": [42]})

    def test_invalid_crud_check_type(self):
        with pytest.raises(ValueError, match="CRUD check config must be a dict"):
            PreflightConfig.from_dict({"crud_checks": ["not a dict"]})

    def test_invalid_custom_check_type(self):
        with pytest.raises(ValueError, match="Custom check config must be a dict"):
            PreflightConfig.from_dict({"custom_checks": [123]})

    def test_invalid_list_check_type(self):
        with pytest.raises(ValueError, match="Invalid list check config"):
            PreflightConfig.from_dict({"list_checks": [123]})

    def test_invalid_auth_check_type(self):
        with pytest.raises(ValueError, match="Invalid auth check config"):
            PreflightConfig.from_dict({"auth_checks": [123]})


# =========================================================================
# PreflightConfig.from_yaml
# =========================================================================

class TestPreflightConfigFromYaml:
    """Tests for PreflightConfig.from_yaml()."""

    def test_load_from_yaml(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            base_url: "http://test:9000"
            timeout: 15.0
            health_checks:
              - path: /healthz
                expected_status: [200]
            auth_checks:
              - path: /me
            crud_checks:
              - path: /items
                payload:
                  name: "test"
            list_checks:
              - path: /items
            custom_checks:
              - name: "Docs"
                method: GET
                path: /docs
        """)
        yaml_file = tmp_path / "preflight.yaml"
        yaml_file.write_text(yaml_content)

        config = PreflightConfig.from_yaml(str(yaml_file))
        assert config.base_url == "http://test:9000"
        assert config.timeout == 15.0
        assert len(config.health_checks) == 1
        assert len(config.auth_checks) == 1
        assert len(config.crud_checks) == 1
        assert len(config.list_checks) == 1
        assert len(config.custom_checks) == 1

    def test_load_with_env_vars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YAML_TEST_URL", "http://from-env:4000")
        yaml_content = textwrap.dedent("""\
            base_url: "${YAML_TEST_URL}"
            health_checks:
              - path: /health
        """)
        yaml_file = tmp_path / "preflight.yaml"
        yaml_file.write_text(yaml_content)

        config = PreflightConfig.from_yaml(str(yaml_file))
        assert config.base_url == "http://from-env:4000"

    def test_load_with_defaults(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YAML_MISSING_VAR_99", raising=False)
        yaml_content = textwrap.dedent("""\
            base_url: "${YAML_MISSING_VAR_99:http://default:5000}"
        """)
        yaml_file = tmp_path / "preflight.yaml"
        yaml_file.write_text(yaml_content)

        config = PreflightConfig.from_yaml(str(yaml_file))
        assert config.base_url == "http://default:5000"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            PreflightConfig.from_yaml("/nonexistent/path/config.yaml")

    def test_invalid_yaml_top_level(self, tmp_path):
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("- just a list")

        with pytest.raises(ValueError, match="Expected a YAML mapping"):
            PreflightConfig.from_yaml(str(yaml_file))


# =========================================================================
# PreflightConfig.to_dict
# =========================================================================

class TestPreflightConfigToDict:
    """Tests for to_dict serialization."""

    def test_minimal_to_dict(self):
        config = PreflightConfig()
        d = config.to_dict()
        assert d["base_url"] == "http://localhost:8000"
        assert d["timeout"] == 10.0
        assert "auth" not in d
        assert "health_checks" not in d

    def test_full_to_dict(self):
        config = PreflightConfig(
            base_url="http://test:8000",
            timeout=5.0,
            token="tok",
            auth_header="X-Auth",
            auth_prefix="Token",
            health_checks=[HealthCheckConfig(path="/hp")],
            auth_checks=[AuthCheckConfig(path="/auth")],
            crud_checks=[CRUDCheckConfig(path="/crud", payload={"a": 1})],
            list_checks=[ListCheckConfig(path="/list")],
            custom_checks=[CustomCheckConfig(name="Custom", path="/custom")],
        )
        d = config.to_dict()
        assert d["auth"]["token"] == "tok"
        assert d["auth"]["header"] == "X-Auth"
        assert d["auth"]["prefix"] == "Token"
        assert len(d["health_checks"]) == 1
        assert len(d["auth_checks"]) == 1
        assert len(d["crud_checks"]) == 1
        assert len(d["list_checks"]) == 1
        assert len(d["custom_checks"]) == 1

    def test_round_trip(self):
        """Config -> to_dict -> from_dict should produce equivalent config."""
        config = PreflightConfig(
            base_url="http://round:1234",
            timeout=7.5,
            health_checks=[HealthCheckConfig(path="/hp", expected_status=[200, 204])],
            list_checks=[ListCheckConfig(path="/things", expected_type="paginated")],
        )
        d = config.to_dict()
        config2 = PreflightConfig.from_dict(d)
        assert config2.base_url == config.base_url
        assert config2.timeout == config.timeout
        assert len(config2.health_checks) == 1
        assert config2.health_checks[0].path == "/hp"
        assert config2.health_checks[0].expected_status == [200, 204]
        assert config2.list_checks[0].expected_type == "paginated"


# =========================================================================
# generate_example_config
# =========================================================================

class TestGenerateExampleConfig:
    """Tests for the example config generator."""

    def test_is_valid_yaml(self):
        import yaml
        content = generate_example_config()
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)
        assert "base_url" in parsed
        assert "health_checks" in parsed

    def test_can_load_as_preflight_config(self, monkeypatch):
        """The example config should be loadable (with env defaults)."""
        monkeypatch.delenv("API_URL", raising=False)
        monkeypatch.delenv("API_TOKEN", raising=False)
        import yaml
        content = generate_example_config()
        data = yaml.safe_load(content)
        # token_env_var references API_TOKEN which is not set, but that's OK
        # because it's resolved lazily via resolve_token()
        config = PreflightConfig.from_dict(data)
        assert "localhost" in config.base_url


# =========================================================================
# SmokeTest.from_config
# =========================================================================

class TestSmokeTestFromConfig:
    """Tests for SmokeTest.from_config() and from_yaml()."""

    def test_from_config_basic(self):
        from venomqa.preflight import SmokeTest

        config = PreflightConfig(
            base_url="http://test:8000",
            timeout=5.0,
            token="my-token",
        )
        smoke = SmokeTest.from_config(config)
        assert smoke.base_url == "http://test:8000"
        assert smoke.token == "my-token"
        assert smoke.timeout == 5.0
        assert smoke._config is config

    def test_from_config_registers_checks(self):
        from venomqa.preflight import SmokeTest

        config = PreflightConfig(
            base_url="http://test:8000",
            health_checks=[HealthCheckConfig(path="/health")],
            auth_checks=[AuthCheckConfig(path="/me")],
            crud_checks=[CRUDCheckConfig(path="/items", payload={"n": 1})],
            list_checks=[ListCheckConfig(path="/items")],
            custom_checks=[CustomCheckConfig(name="Docs", method="GET", path="/docs")],
        )
        smoke = SmokeTest.from_config(config)
        # 5 checks: health + auth + crud + list + custom
        assert len(smoke._custom_checks) == 5

    def test_from_config_resolves_token_from_env(self, monkeypatch):
        from venomqa.preflight import SmokeTest

        monkeypatch.setenv("SMOKE_TOKEN", "env-token-123")
        config = PreflightConfig(
            base_url="http://test:8000",
            token_env_var="SMOKE_TOKEN",
        )
        smoke = SmokeTest.from_config(config)
        assert smoke.token == "env-token-123"

    def test_from_config_auth_header_propagated(self):
        from venomqa.preflight import SmokeTest

        config = PreflightConfig(
            base_url="http://test:8000",
            token="tok",
            auth_header="X-API-Key",
            auth_prefix="Key",
            health_checks=[HealthCheckConfig(path="/health")],
        )
        smoke = SmokeTest.from_config(config)
        assert smoke.auth_header == "X-API-Key"
        assert smoke.auth_prefix == "Key"
        # The health check should also have the custom auth header
        assert smoke._custom_checks[0].auth_header == "X-API-Key"
        assert smoke._custom_checks[0].auth_prefix == "Key"

    def test_from_config_invalid_type(self):
        from venomqa.preflight import SmokeTest

        with pytest.raises(TypeError, match="Expected PreflightConfig"):
            SmokeTest.from_config({"base_url": "http://test"})

    def test_from_yaml(self, tmp_path):
        from venomqa.preflight import SmokeTest

        yaml_content = textwrap.dedent("""\
            base_url: "http://yaml-test:8000"
            health_checks:
              - path: /health
        """)
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content)

        smoke = SmokeTest.from_yaml(str(yaml_file))
        assert smoke.base_url == "http://yaml-test:8000"
        assert len(smoke._custom_checks) == 1

    def test_from_config_run_all_config_mode(self):
        """In config mode, run_all only runs config checks, not defaults."""
        from venomqa.preflight import SmokeTest
        from venomqa.preflight.checks import SmokeTestResult

        config = PreflightConfig(
            base_url="http://test:8000",
            health_checks=[HealthCheckConfig(path="/health")],
        )
        smoke = SmokeTest.from_config(config)

        # Mock the single health check to pass
        mock_check = MagicMock()
        mock_check.run.return_value = SmokeTestResult(
            name="Health check", passed=True, duration_ms=1.0
        )
        smoke._custom_checks = [mock_check]

        report = smoke.run_all()
        assert report.passed is True
        assert len(report.results) == 1
        mock_check.run.assert_called_once()

    def test_legacy_mode_still_works(self):
        """SmokeTest created directly (not from config) still uses legacy run_all."""
        from venomqa.preflight import SmokeTest

        smoke = SmokeTest("http://test:8000")
        assert smoke._config is None

        # Mock httpx for the health check
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("httpx.Client", return_value=mock_client):
            report = smoke.run_all()

        assert report.passed is True
        assert len(report.results) == 1  # health only (no token)


# =========================================================================
# CustomHTTPCheck
# =========================================================================

class TestCustomHTTPCheck:
    """Tests for the CustomHTTPCheck class."""

    def test_custom_check_pass(self):
        from venomqa.preflight.checks import CustomHTTPCheck

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"ok": true}'
        mock_resp.json.return_value = {"ok": True}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_resp

        with patch("httpx.Client", return_value=mock_client):
            check = CustomHTTPCheck(
                "http://test:8000",
                check_name="Test check",
                method="GET",
                path="/test",
                expected_status=[200],
            )
            result = check.run()

        assert result.passed is True
        assert result.name == "Test check"

    def test_custom_check_wrong_status(self):
        from venomqa.preflight.checks import CustomHTTPCheck

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not found"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_resp

        with patch("httpx.Client", return_value=mock_client):
            check = CustomHTTPCheck(
                "http://test:8000",
                check_name="Test",
                path="/missing",
                expected_status=[200],
            )
            result = check.run()

        assert result.passed is False
        assert "404" in result.error

    def test_custom_check_expected_json_pass(self):
        from venomqa.preflight.checks import CustomHTTPCheck

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "healthy", "version": "1.0"}'
        mock_resp.json.return_value = {"status": "healthy", "version": "1.0"}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_resp

        with patch("httpx.Client", return_value=mock_client):
            check = CustomHTTPCheck(
                "http://test:8000",
                check_name="JSON check",
                path="/health",
                expected_status=[200],
                expected_json={"status": "healthy"},
            )
            result = check.run()

        assert result.passed is True

    def test_custom_check_expected_json_fail(self):
        from venomqa.preflight.checks import CustomHTTPCheck

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "degraded"}'
        mock_resp.json.return_value = {"status": "degraded"}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_resp

        with patch("httpx.Client", return_value=mock_client):
            check = CustomHTTPCheck(
                "http://test:8000",
                check_name="JSON check",
                path="/health",
                expected_status=[200],
                expected_json={"status": "healthy"},
            )
            result = check.run()

        assert result.passed is False
        assert "does not match" in result.error

    def test_custom_check_with_payload(self):
        from venomqa.preflight.checks import CustomHTTPCheck

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.text = '{"id": 1}'

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_resp

        with patch("httpx.Client", return_value=mock_client):
            check = CustomHTTPCheck(
                "http://test:8000",
                check_name="Create",
                method="POST",
                path="/items",
                payload={"name": "test"},
                expected_status=[201],
            )
            result = check.run()

        assert result.passed is True
        # Verify json payload was passed
        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["json"] == {"name": "test"}

    def test_custom_check_connection_error(self):
        import httpx

        from venomqa.preflight.checks import CustomHTTPCheck

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.side_effect = httpx.ConnectError("Connection refused")

        with patch("httpx.Client", return_value=mock_client):
            check = CustomHTTPCheck(
                "http://test:8000",
                check_name="Conn test",
                path="/health",
            )
            result = check.run()

        assert result.passed is False
        assert result.suggestion is not None

    def test_custom_check_with_extra_headers(self):
        from venomqa.preflight.checks import CustomHTTPCheck

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ""

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_resp

        with patch("httpx.Client", return_value=mock_client):
            check = CustomHTTPCheck(
                "http://test:8000",
                check_name="Header test",
                path="/test",
                extra_headers={"X-Custom": "value"},
            )
            result = check.run()

        assert result.passed is True
        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["headers"]["X-Custom"] == "value"


# =========================================================================
# _is_json_superset
# =========================================================================

class TestIsJsonSuperset:
    """Tests for the JSON superset check."""

    def test_dict_superset(self):
        from venomqa.preflight.checks import _is_json_superset

        assert _is_json_superset({"a": 1, "b": 2}, {"a": 1}) is True
        assert _is_json_superset({"a": 1}, {"a": 1, "b": 2}) is False

    def test_nested_dict(self):
        from venomqa.preflight.checks import _is_json_superset

        actual = {"data": {"status": "ok", "count": 5}}
        expected = {"data": {"status": "ok"}}
        assert _is_json_superset(actual, expected) is True

    def test_scalar_equality(self):
        from venomqa.preflight.checks import _is_json_superset

        assert _is_json_superset("hello", "hello") is True
        assert _is_json_superset("hello", "world") is False
        assert _is_json_superset(42, 42) is True

    def test_list_contains(self):
        from venomqa.preflight.checks import _is_json_superset

        assert _is_json_superset([1, 2, 3], [1, 3]) is True
        assert _is_json_superset([1, 2], [3]) is False

    def test_type_mismatch(self):
        from venomqa.preflight.checks import _is_json_superset

        assert _is_json_superset("string", {"key": "val"}) is False
        assert _is_json_superset(42, [42]) is False


# =========================================================================
# BaseCheck auth header customization
# =========================================================================

class TestBaseCheckAuthHeaders:
    """Tests for configurable auth headers in BaseCheck."""

    def test_default_auth_header(self):
        from venomqa.preflight.checks import BaseCheck

        check = BaseCheck("http://test:8000", token="my-token")
        headers = check._headers()
        assert headers["Authorization"] == "Bearer my-token"

    def test_custom_auth_header(self):
        from venomqa.preflight.checks import BaseCheck

        check = BaseCheck(
            "http://test:8000",
            token="key-123",
            auth_header="X-API-Key",
            auth_prefix="Key",
        )
        headers = check._headers()
        assert "X-API-Key" in headers
        assert headers["X-API-Key"] == "Key key-123"
        assert "Authorization" not in headers

    def test_pre_formatted_token(self):
        from venomqa.preflight.checks import BaseCheck

        check = BaseCheck("http://test:8000", token="Bearer already-formatted")
        headers = check._headers()
        assert headers["Authorization"] == "Bearer already-formatted"

    def test_no_token(self):
        from venomqa.preflight.checks import BaseCheck

        check = BaseCheck("http://test:8000")
        headers = check._headers()
        assert "Authorization" not in headers
        assert "X-API-Key" not in headers


# =========================================================================
# Example YAML configs are valid
# =========================================================================

class TestExampleConfigs:
    """Verify that shipped example YAML configs are syntactically valid."""

    @pytest.fixture
    def examples_dir(self):
        base = Path(__file__).parent.parent / "examples"
        return base

    def test_main_example(self, examples_dir):
        import yaml
        path = examples_dir / "preflight_config.yaml"
        if not path.exists():
            pytest.skip("Example file not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)
        assert "base_url" in data

    def test_preflight_configs_dir(self, examples_dir):
        import yaml
        configs_dir = examples_dir / "preflight_configs"
        if not configs_dir.exists():
            pytest.skip("Preflight configs directory not found")
        yaml_files = list(configs_dir.glob("*.yaml"))
        assert len(yaml_files) >= 1, "Expected at least one example config"
        for yf in yaml_files:
            with open(yf) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, dict), f"{yf.name} is not a valid YAML mapping"
            assert "base_url" in data, f"{yf.name} missing base_url"
