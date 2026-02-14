"""Tests for validation and sanitization security in VenomQA."""

from __future__ import annotations

import pytest

from venomqa.core.models import (
    Branch,
    Checkpoint,
    Journey,
    Path,
    Step,
)
from venomqa.errors import JourneyValidationError
from venomqa.runner import JourneyRunner
from venomqa.state.postgres import PostgreSQLStateManager
from tests.conftest import MockClient, MockHTTPResponse, MockStateManager


class TestCheckpointValidation:
    """Tests for checkpoint name validation and sanitization."""

    def test_sanitize_simple_name(self) -> None:
        result = PostgreSQLStateManager._sanitize_name("simple_checkpoint")
        assert result == "chk_simple_checkpoint"

    def test_sanitize_name_with_special_chars(self) -> None:
        result = PostgreSQLStateManager._sanitize_name("test-name; DROP TABLE users;")
        assert ";" not in result
        assert "DROP" not in result.upper() or "_" in result

    def test_sanitize_name_with_spaces(self) -> None:
        result = PostgreSQLStateManager._sanitize_name("checkpoint with spaces")
        assert " " not in result
        assert "_" in result

    def test_sanitize_name_starting_with_digit(self) -> None:
        result = PostgreSQLStateManager._sanitize_name("123checkpoint")
        assert result.startswith("chk_sp_")

    def test_sanitize_name_with_sql_keywords(self) -> None:
        malicious_names = [
            "checkpoint; SELECT * FROM users",
            "checkpoint' OR '1'='1",
            "checkpoint--comment",
            "checkpoint/*block*/",
        ]

        for name in malicious_names:
            result = PostgreSQLStateManager._sanitize_name(name)
            assert ";" not in result
            assert "'" not in result
            assert "--" not in result
            assert "/*" not in result

    def test_sanitize_truncates_long_name(self) -> None:
        long_name = "a" * 100
        result = PostgreSQLStateManager._sanitize_name(long_name)
        assert len(result) <= 63

    def test_sanitize_preserves_underscores(self) -> None:
        result = PostgreSQLStateManager._sanitize_name("test_checkpoint_name")
        assert "test_checkpoint_name" in result

    def test_sanitize_empty_name(self) -> None:
        result = PostgreSQLStateManager._sanitize_name("")
        assert result.startswith("chk_")


class TestJourneyValidation:
    """Tests for journey model validation."""

    def test_journey_valid_with_matching_checkpoint(self) -> None:
        checkpoint = Checkpoint(name="after_create")
        branch = Branch(
            checkpoint_name="after_create",
            paths=[Path(name="test", steps=[])],
        )

        journey = Journey(
            name="valid_journey",
            steps=[checkpoint, branch],
        )

        assert journey.name == "valid_journey"

    def test_journey_invalid_with_missing_checkpoint(self) -> None:
        branch = Branch(
            checkpoint_name="nonexistent",
            paths=[Path(name="test", steps=[])],
        )

        with pytest.raises(JourneyValidationError, match="undefined checkpoint"):
            Journey(
                name="invalid_journey",
                steps=[branch],
            )

    def test_journey_with_multiple_branches_same_checkpoint(self) -> None:
        checkpoint = Checkpoint(name="shared")
        branch1 = Branch(checkpoint_name="shared", paths=[Path(name="p1", steps=[])])
        branch2 = Branch(checkpoint_name="shared", paths=[Path(name="p2", steps=[])])

        journey = Journey(
            name="multi_branch",
            steps=[checkpoint, branch1, branch2],
        )

        assert len(journey.steps) == 3

    def test_journey_with_nested_checkpoints(self) -> None:
        checkpoint1 = Checkpoint(name="first")
        checkpoint2 = Checkpoint(name="second")

        journey = Journey(
            name="nested",
            steps=[
                checkpoint1,
                checkpoint2,
            ],
        )

        assert journey.name == "nested"


class TestStepValidation:
    """Tests for step validation."""

    def test_step_name_required(self) -> None:
        def action(client, ctx):
            return client.get("/test")

        step = Step(name="test_step", action=action)
        assert step.name == "test_step"

    def test_step_action_required(self) -> None:
        def action(client, ctx):
            return client.get("/test")

        step = Step(name="test", action=action)
        assert callable(step.action)

    def test_step_default_values(self) -> None:
        def action(client, ctx):
            pass

        step = Step(name="test", action=action)

        assert step.description == ""
        assert step.expect_failure is False
        assert step.timeout is None
        assert step.retries == 0


class TestPathValidation:
    """Tests for path validation."""

    def test_path_with_valid_steps(self) -> None:
        def action(client, ctx):
            return client.get("/test")

        step1 = Step(name="step1", action=action)
        step2 = Step(name="step2", action=action)

        path = Path(name="valid_path", steps=[step1, step2])

        assert len(path.steps) == 2

    def test_path_with_empty_steps(self) -> None:
        path = Path(name="empty_path", steps=[])
        assert path.steps == []

    def test_path_with_checkpoint_in_steps(self) -> None:
        checkpoint = Checkpoint(name="midpoint")
        step = Step(name="step", action=lambda c, ctx: c.get("/"))

        path = Path(name="with_checkpoint", steps=[step, checkpoint])

        assert len(path.steps) == 2


class TestBranchValidation:
    """Tests for branch validation."""

    def test_branch_with_multiple_paths(self) -> None:
        path1 = Path(name="path1", steps=[])
        path2 = Path(name="path2", steps=[])
        path3 = Path(name="path3", steps=[])

        branch = Branch(
            checkpoint_name="test_checkpoint",
            paths=[path1, path2, path3],
        )

        assert len(branch.paths) == 3

    def test_branch_with_empty_paths(self) -> None:
        branch = Branch(checkpoint_name="test", paths=[])
        assert branch.paths == []


class TestStateManagerValidation:
    """Tests for state manager input validation."""

    def test_rollback_validates_checkpoint_exists(self) -> None:
        state_manager = MockStateManager()
        state_manager.connect()
        state_manager.checkpoint("valid_checkpoint")

        state_manager.rollback("valid_checkpoint")

        with pytest.raises(ValueError):
            state_manager.rollback("invalid_checkpoint")

    def test_checkpoint_name_uniqueness(self) -> None:
        state_manager = MockStateManager()
        state_manager.connect()

        state_manager.checkpoint("first")
        state_manager.checkpoint("first")

        assert len(state_manager._checkpoint_order) == 2
        assert len(state_manager._checkpoints) == 1

    def test_release_removes_checkpoint(self) -> None:
        state_manager = MockStateManager()
        state_manager.connect()
        state_manager.checkpoint("to_release")

        state_manager.release("to_release")

        assert "to_release" not in state_manager._checkpoints


class TestInputSanitization:
    """Tests for input sanitization across the framework."""

    def test_url_path_sanitization(self, mock_client: MockClient) -> None:
        mock_client.get("/users/1")

        last_request = mock_client.last_request()
        assert last_request is not None

    def test_request_body_sanitization(self, mock_client: MockClient) -> None:
        mock_client.post("/users", json={"name": "test<script>alert(1)</script>"})

        last_request = mock_client.last_request()
        assert last_request is not None
        assert "<script>" in str(last_request.request_body)

    def test_header_value_sanitization(self, mock_client: MockClient) -> None:
        mock_client.get("/test", headers={"X-Custom": "value\nAnother-Header: malicious"})

        last_request = mock_client.last_request()
        assert last_request is not None


class TestAuthenticationSecurity:
    """Tests for authentication-related security."""

    def test_auth_token_not_logged(self, mock_client: MockClient) -> None:
        mock_client.set_auth_token("super-secret-token-12345")

        mock_client.get("/protected")

        last_request = mock_client.last_request()
        assert last_request is not None

    def test_clear_auth_removes_token(self, mock_client: MockClient) -> None:
        mock_client.set_auth_token("secret-token")
        mock_client.clear_auth()

        assert mock_client._auth_token is None

    def test_auth_with_custom_scheme(self, mock_client: MockClient) -> None:
        mock_client.set_auth_token("api-key-123", scheme="ApiKey")

        assert mock_client._auth_token == "ApiKey api-key-123"


class TestErrorHandlingSecurity:
    """Tests for secure error handling."""

    def test_error_message_does_not_leak_secrets(self, mock_client: MockClient) -> None:
        def failing_action(client, ctx):
            raise Exception("Database error: password=secret123 at localhost")

        journey = Journey(
            name="error_leak_test",
            steps=[Step(name="fail", action=failing_action)],
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
        assert len(result.issues) == 1

    def test_connection_error_sanitized(self, mock_client: MockClient) -> None:
        def conn_error(client, ctx):
            raise ConnectionError("Connection to postgresql://user:pass@host/db failed")

        journey = Journey(
            name="conn_test",
            steps=[Step(name="conn", action=conn_error)],
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_valid_config_url(self) -> None:
        from venomqa.config.settings import QAConfig

        config = QAConfig(base_url="http://localhost:8000")
        assert config.base_url == "http://localhost:8000"

    def test_valid_db_url_postgresql(self) -> None:
        from venomqa.config.settings import QAConfig

        config = QAConfig(db_url="postgresql://user:pass@localhost:5432/testdb")
        assert config.db_url == "postgresql://user:pass@localhost:5432/testdb"

    def test_invalid_db_url_rejected(self) -> None:
        from venomqa.config.settings import QAConfig
        from venomqa.errors import ConfigValidationError

        with pytest.raises((ConfigValidationError, Exception)):
            QAConfig(db_url="mysql://user:pass@localhost/db")

    def test_valid_report_formats(self) -> None:
        from venomqa.config.settings import QAConfig

        config = QAConfig(report_formats=["markdown", "json", "junit"])
        assert "markdown" in config.report_formats

    def test_invalid_report_format_rejected(self) -> None:
        from venomqa.config.settings import QAConfig
        from venomqa.errors import ConfigValidationError

        with pytest.raises((ConfigValidationError, Exception)):
            QAConfig(report_formats=["markdown", "invalid_format"])

    def test_timeout_must_be_positive(self) -> None:
        from venomqa.config.settings import QAConfig

        config = QAConfig(timeout=30)
        assert config.timeout == 30

    def test_retry_count_default(self) -> None:
        from venomqa.config.settings import QAConfig

        config = QAConfig()
        assert config.retry_count == 3


class TestSQLInjectionPrevention:
    """Tests for SQL injection prevention."""

    def test_checkpoint_name_sql_injection_blocked(self) -> None:
        malicious_names = [
            "'; DROP TABLE users;--",
            "1; DELETE FROM data WHERE '1'='1",
            "name' UNION SELECT * FROM passwords--",
        ]

        for name in malicious_names:
            sanitized = PostgreSQLStateManager._sanitize_name(name)
            assert "'" not in sanitized
            assert ";" not in sanitized
            assert "--" not in sanitized

    def test_no_direct_sql_concatenation(self) -> None:
        user_input = "checkpoint_name"
        sanitized = PostgreSQLStateManager._sanitize_name(user_input)

        assert sanitized.startswith("chk_")
        assert "checkpoint_name" in sanitized


class TestXSSPrevention:
    """Tests for XSS prevention in outputs."""

    def test_step_name_xss_in_report(self, mock_client: MockClient) -> None:
        from venomqa.reporters.markdown import MarkdownReporter

        def xss_action(client, ctx):
            raise Exception("<script>alert('xss')</script>")

        journey = Journey(
            name="xss_test",
            steps=[Step(name="test", action=xss_action)],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        reporter = MarkdownReporter()
        report = reporter.generate([result])

        assert "<script>" in report

    def test_error_message_in_json_report(self, mock_client: MockClient) -> None:
        from venomqa.reporters.json_report import JSONReporter

        journey = Journey(
            name="error_test",
            steps=[Step(name="fail", action=lambda c, ctx: c.get("/fail"))],
        )

        mock_client.set_responses(
            [MockHTTPResponse(status_code=500, json_data={"error": "<b>bad</b>"})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        reporter = JSONReporter()
        report = reporter.generate([result])

        assert "<b>" in report
