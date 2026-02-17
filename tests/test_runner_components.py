"""Tests for extracted runner components: IssueFormatter, CacheManager, ResultsPersister, ActionResolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from venomqa.core.models import Severity
from venomqa.runner.cache import CacheManager
from venomqa.runner.formatter import IssueFormatter
from venomqa.runner.persistence import ResultsPersister
from venomqa.runner.resolver import (
    DictActionResolver,
    RegistryActionResolver,
)


class TestIssueFormatter:
    """Tests for IssueFormatter."""

    def test_initialization(self) -> None:
        formatter = IssueFormatter()
        assert formatter.get_issues() == []

    def test_add_issue(self) -> None:
        formatter = IssueFormatter()
        issue = formatter.add_issue(
            journey="test_journey",
            path="main",
            step="test_step",
            error="Test error",
            severity=Severity.HIGH,
        )

        assert issue.journey == "test_journey"
        assert issue.path == "main"
        assert issue.step == "test_step"
        assert issue.error == "Test error"
        assert issue.severity == Severity.HIGH

    def test_add_issue_with_request_response(self) -> None:
        formatter = IssueFormatter()
        request = {"method": "POST", "url": "/api/users", "body": {"name": "test"}}
        response = {"status_code": 422, "body": {"error": "Validation failed"}}

        issue = formatter.add_issue(
            journey="test",
            path="main",
            step="create_user",
            error="HTTP 422",
            request=request,
            response=response,
        )

        assert issue.request == request
        assert issue.response == response

    def test_get_issues_returns_copy(self) -> None:
        formatter = IssueFormatter()
        formatter.add_issue(
            journey="test",
            path="main",
            step="step1",
            error="Error 1",
        )

        issues1 = formatter.get_issues()
        issues2 = formatter.get_issues()

        assert issues1 == issues2
        assert issues1 is not issues2  # Different list objects

    def test_clear(self) -> None:
        formatter = IssueFormatter()
        formatter.add_issue(
            journey="test",
            path="main",
            step="step1",
            error="Error",
        )
        assert len(formatter.get_issues()) == 1

        formatter.clear()
        assert len(formatter.get_issues()) == 0

    def test_format_step_failure(self) -> None:
        formatter = IssueFormatter()
        output = formatter.format_step_failure(
            step_name="login",
            error="HTTP 401",
            request={"method": "POST", "url": "/auth/login", "body": {"user": "test"}},
            response={"status_code": 401, "body": {"error": "Invalid credentials"}},
        )

        assert "Step 'login' failed: HTTP 401" in output
        assert "POST /auth/login" in output
        assert "Response (401)" in output

    def test_format_step_failure_without_request_response(self) -> None:
        formatter = IssueFormatter()
        output = formatter.format_step_failure(
            step_name="broken_step",
            error="Connection refused",
        )

        assert "Step 'broken_step' failed: Connection refused" in output
        assert "Suggestion:" in output

    def test_format_body_for_display_dict(self) -> None:
        formatter = IssueFormatter()
        body = {"id": 1, "name": "test"}
        result = formatter.format_body_for_display(body)
        assert '"id": 1' in result
        assert '"name": "test"' in result

    def test_format_body_for_display_long_string(self) -> None:
        formatter = IssueFormatter()
        body = "x" * 600  # Long string
        result = formatter.format_body_for_display(body)
        assert "... [truncated]" in result
        assert len(result) < 600

    def test_format_body_for_display_none(self) -> None:
        formatter = IssueFormatter()
        assert formatter.format_body_for_display(None) == "(empty)"

    def test_get_error_suggestion_status_codes(self) -> None:
        formatter = IssueFormatter()

        assert "authentication" in formatter.get_error_suggestion(
            "HTTP 401", {"status_code": 401}
        ).lower()
        assert "permissions" in formatter.get_error_suggestion(
            "HTTP 403", {"status_code": 403}
        ).lower()
        assert "endpoint" in formatter.get_error_suggestion(
            "HTTP 404", {"status_code": 404}
        ).lower()

    def test_get_error_suggestion_patterns(self) -> None:
        formatter = IssueFormatter()

        assert "running" in formatter.get_error_suggestion(
            "connection refused", None
        ).lower()
        assert "timeout" in formatter.get_error_suggestion(
            "request timeout", None
        ).lower()


class TestCacheManager:
    """Tests for CacheManager."""

    def test_initialization_disabled(self) -> None:
        manager = CacheManager(cache=None, enabled=False)
        assert not manager.enabled

    def test_initialization_enabled(self) -> None:
        mock_cache = MagicMock()
        manager = CacheManager(cache=mock_cache, enabled=True)
        assert manager.enabled

    def test_try_get_cached_response_disabled(self) -> None:
        manager = CacheManager(cache=None, enabled=False)
        result = manager.try_get_cached_response("GET", "/api/users", None, None)
        assert result is None

    def test_try_get_cached_response_non_cacheable_method(self) -> None:
        mock_cache = MagicMock()
        manager = CacheManager(cache=mock_cache, enabled=True)

        result = manager.try_get_cached_response("POST", "/api/users", None, None)
        assert result is None

    def test_try_get_cached_response_cache_hit(self) -> None:
        mock_cache = MagicMock()
        mock_cache.compute_key.return_value = "test_key"
        mock_cache.get.return_value = {"status_code": 200, "body": {"id": 1}}

        manager = CacheManager(cache=mock_cache, enabled=True)
        result = manager.try_get_cached_response("GET", "/api/users/1", None, None)

        assert result is not None
        assert result.status_code == 200
        assert manager._hits == 1
        assert manager._misses == 0

    def test_try_get_cached_response_cache_miss(self) -> None:
        mock_cache = MagicMock()
        mock_cache.compute_key.return_value = "test_key"
        mock_cache.get.return_value = None

        manager = CacheManager(cache=mock_cache, enabled=True)
        result = manager.try_get_cached_response("GET", "/api/users/1", None, None)

        assert result is None
        assert manager._hits == 0
        assert manager._misses == 1

    def test_cache_response(self) -> None:
        mock_cache = MagicMock()
        mock_cache.compute_key.return_value = "test_key"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"id": 1}

        manager = CacheManager(cache=mock_cache, enabled=True, ttl=300.0)
        manager.cache_response("GET", "/api/users/1", None, None, mock_response)

        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args[1]["ttl"] == 300.0

    def test_cache_response_error_not_cached(self) -> None:
        mock_cache = MagicMock()

        mock_response = MagicMock()
        mock_response.status_code = 500  # Error response

        manager = CacheManager(cache=mock_cache, enabled=True)
        manager.cache_response("GET", "/api/users/1", None, None, mock_response)

        mock_cache.set.assert_not_called()

    def test_get_stats(self) -> None:
        mock_cache = MagicMock()
        mock_stats = MagicMock()
        mock_stats.to_dict.return_value = {"size": 10, "max_size": 100}
        mock_cache.get_stats.return_value = mock_stats

        manager = CacheManager(cache=mock_cache, enabled=True)
        manager._hits = 5
        manager._misses = 3

        stats = manager.get_stats()
        assert stats["enabled"] is True
        assert stats["hits"] == 5
        assert stats["misses"] == 3

    def test_get_stats_disabled(self) -> None:
        manager = CacheManager(cache=None, enabled=False)
        stats = manager.get_stats()
        assert stats["enabled"] is False

    def test_clear(self) -> None:
        mock_cache = MagicMock()
        manager = CacheManager(cache=mock_cache, enabled=True)
        manager._hits = 5
        manager._misses = 3

        manager.clear()

        mock_cache.clear.assert_called_once()
        assert manager._hits == 0
        assert manager._misses == 0


class TestResultsPersister:
    """Tests for ResultsPersister."""

    def test_initialization_disabled(self) -> None:
        persister = ResultsPersister(repository=None, enabled=False)
        assert not persister.enabled

    def test_initialization_with_repository(self) -> None:
        mock_repo = MagicMock()
        persister = ResultsPersister(repository=mock_repo, enabled=True)
        assert persister.enabled
        assert persister.repository is mock_repo

    def test_persist_disabled(self) -> None:
        persister = ResultsPersister(repository=None, enabled=False)

        mock_result = MagicMock()
        mock_journey = MagicMock()

        run_id = persister.persist(mock_result, mock_journey)
        assert run_id is None

    def test_persist_success(self) -> None:
        mock_repo = MagicMock()
        mock_repo.save_journey_result.return_value = "run-123"

        persister = ResultsPersister(
            repository=mock_repo,
            enabled=True,
            tags=["smoke", "integration"],
            metadata={"environment": "test"},
        )

        mock_result = MagicMock()
        mock_result.journey_name = "test_journey"
        mock_journey = MagicMock()
        mock_journey.tags = ["extra_tag"]
        mock_journey.description = "Test journey"

        run_id = persister.persist(mock_result, mock_journey)

        assert run_id == "run-123"
        mock_repo.save_journey_result.assert_called_once()

    def test_persist_with_extra_metadata(self) -> None:
        mock_repo = MagicMock()
        mock_repo.save_journey_result.return_value = "run-456"

        persister = ResultsPersister(repository=mock_repo, enabled=True)

        mock_result = MagicMock()
        mock_journey = MagicMock()
        mock_journey.tags = []
        mock_journey.description = ""

        run_id = persister.persist(
            mock_result, mock_journey, extra_metadata={"custom": "value"}
        )

        assert run_id == "run-456"
        call_args = mock_repo.save_journey_result.call_args
        assert "custom" in call_args[1]["metadata"]

    def test_persist_exception_handling(self) -> None:
        mock_repo = MagicMock()
        mock_repo.save_journey_result.side_effect = Exception("Database error")

        persister = ResultsPersister(repository=mock_repo, enabled=True)

        mock_result = MagicMock()
        mock_journey = MagicMock()
        mock_journey.tags = []
        mock_journey.description = ""

        # Should not raise, just return None
        run_id = persister.persist(mock_result, mock_journey)
        assert run_id is None

    def test_close(self) -> None:
        mock_repo = MagicMock()
        persister = ResultsPersister(repository=mock_repo, enabled=True)

        persister.close()
        mock_repo.close.assert_called_once()


class TestActionResolver:
    """Tests for ActionResolver implementations."""

    def test_dict_action_resolver_register_and_resolve(self) -> None:
        def my_action(client, ctx):
            return client.get("/test")

        resolver = DictActionResolver()
        resolver.register("test.action", my_action)

        resolved = resolver.resolve("test.action")
        assert resolved is my_action

    def test_dict_action_resolver_with_initial_actions(self) -> None:
        def action1(c, ctx):
            pass

        def action2(c, ctx):
            pass

        resolver = DictActionResolver({"action1": action1, "action2": action2})

        assert resolver.resolve("action1") is action1
        assert resolver.resolve("action2") is action2

    def test_dict_action_resolver_not_found(self) -> None:
        resolver = DictActionResolver()

        with pytest.raises(KeyError, match="Action 'missing' not found"):
            resolver.resolve("missing")

    def test_registry_action_resolver(self) -> None:
        with patch("venomqa.plugins.registry.get_registry") as mock_get_registry:
            mock_registry = MagicMock()
            def mock_action(c, ctx):
                return None
            mock_registry.resolve_action.return_value = mock_action
            mock_get_registry.return_value = mock_registry

            resolver = RegistryActionResolver()
            result = resolver.resolve("auth.login")

            mock_registry.resolve_action.assert_called_once_with("auth.login")
            assert result is mock_action


class TestActionResolverIntegration:
    """Integration tests for ActionResolver with Step."""

    def test_step_with_dict_resolver(self) -> None:
        from venomqa.core.models import Step

        def custom_action(client, ctx):
            return client.get("/custom")

        resolver = DictActionResolver({"custom.action": custom_action})

        step = Step(name="test", action="custom.action")
        resolved = step.get_action_callable(resolver)

        assert resolved is custom_action

    def test_step_with_callable_ignores_resolver(self) -> None:
        from venomqa.core.models import Step

        def inline_action(client, ctx):
            return client.get("/inline")

        resolver = DictActionResolver()

        step = Step(name="test", action=inline_action)
        resolved = step.get_action_callable(resolver)

        # Should return the callable directly, not use resolver
        assert resolved is inline_action
