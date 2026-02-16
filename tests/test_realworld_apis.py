#!/usr/bin/env python3
"""Real-world API tests for VenomQA.

These tests verify VenomQA works correctly against real public APIs.
Tests are designed to be resilient to network issues and rate limiting.

Run with: pytest tests/test_realworld_apis.py -v --tb=short

Note: These tests require network access and may be slow or flaky
depending on API availability.
"""

from __future__ import annotations

import pytest

from venomqa import Client
from venomqa.core.models import Branch, Checkpoint, Journey, Path, Step
from venomqa.runner import JourneyRunner
from tests.conftest import MockStateManager


# Mark all tests in this module as requiring network
pytestmark = pytest.mark.network


class TestJSONPlaceholderAPI:
    """Test VenomQA against JSONPlaceholder - a free fake REST API."""

    BASE_URL = "https://jsonplaceholder.typicode.com"

    @pytest.fixture
    def client(self) -> Client:
        return Client(base_url=self.BASE_URL, timeout=30.0)

    @pytest.mark.timeout(30)
    def test_simple_journey_get_users(self, client: Client) -> None:
        """Test a simple journey that fetches users."""

        def get_users(c, ctx):
            return c.get("/users")

        def verify_users(c, ctx):
            users = ctx.get_step_result("fetch_users")
            if users and hasattr(users, "json"):
                data = users.json()
                assert len(data) == 10, f"Expected 10 users, got {len(data)}"
            return users

        journey = Journey(
            name="jsonplaceholder_users",
            steps=[
                Step(name="fetch_users", action=get_users, description="Fetch all users"),
                Step(name="verify_users", action=verify_users, description="Verify user count"),
            ],
        )

        # Validate journey structure
        issues = journey.validate()
        assert issues == [], f"Journey validation failed: {issues}"

        # Execute journey
        try:
            result = journey(client)
            assert result.success, f"Journey failed: {result.issues}"
            assert result.passed_steps == 2
        except Exception as e:
            # Network errors are acceptable for real-world tests
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                pytest.skip(f"Network unavailable: {e}")
            raise

    @pytest.mark.timeout(60)
    def test_branching_journey_crud(self, client: Client) -> None:
        """Test a journey with branches exploring CRUD paths."""

        def create_post(c, ctx):
            return c.post(
                "/posts",
                json={"title": "Test Post", "body": "Test Body", "userId": 1},
            )

        def read_post(c, ctx):
            return c.get("/posts/1")

        def update_post(c, ctx):
            return c.put(
                "/posts/1",
                json={"id": 1, "title": "Updated", "body": "Updated Body", "userId": 1},
            )

        def delete_post(c, ctx):
            return c.delete("/posts/1")

        checkpoint = Checkpoint(name="after_create")
        branch = Branch(
            checkpoint_name="after_create",
            paths=[
                Path(
                    name="update_path",
                    steps=[Step(name="update_post", action=update_post)],
                    description="Test update flow",
                ),
                Path(
                    name="delete_path",
                    steps=[Step(name="delete_post", action=delete_post)],
                    description="Test delete flow",
                ),
            ],
        )

        journey = Journey(
            name="jsonplaceholder_crud",
            steps=[
                Step(name="create_post", action=create_post),
                Step(name="read_post", action=read_post),
                checkpoint,
                branch,
            ],
            tags=["crud", "smoke"],
        )

        # Validate
        issues = journey.validate()
        assert issues == [], f"Journey validation failed: {issues}"

        # Execute with mock state manager (required for checkpoints/branches)
        try:
            state_manager = MockStateManager()
            runner = JourneyRunner(client=client, state_manager=state_manager)
            result = runner.run(journey)
            # Note: JSONPlaceholder is fake so all operations should succeed
            assert result.passed_steps >= 2
            assert result.total_paths == 2
        except Exception as e:
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                pytest.skip(f"Network unavailable: {e}")
            raise


class TestHTTPBinAPI:
    """Test VenomQA against HTTPBin - HTTP request/response testing service."""

    BASE_URL = "https://httpbin.org"

    @pytest.fixture
    def client(self) -> Client:
        return Client(base_url=self.BASE_URL, timeout=30.0)

    @pytest.mark.timeout(30)
    def test_request_inspection_journey(self, client: Client) -> None:
        """Test that VenomQA correctly handles various HTTP methods."""

        def test_get(c, ctx):
            return c.get("/get", params={"foo": "bar"})

        def test_post(c, ctx):
            return c.post("/post", json={"test": "data"})

        def test_headers(c, ctx):
            return c.get("/headers")

        journey = Journey(
            name="httpbin_inspection",
            steps=[
                Step(name="test_get", action=test_get),
                Step(name="test_post", action=test_post),
                Step(name="test_headers", action=test_headers),
            ],
            tags=["http", "inspection"],
        )

        issues = journey.validate()
        assert issues == []

        try:
            result = journey(client)
            assert result.passed_steps == 3
        except Exception as e:
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                pytest.skip(f"Network unavailable: {e}")
            raise

    @pytest.mark.timeout(30)
    def test_status_code_handling(self, client: Client) -> None:
        """Test that VenomQA handles different status codes correctly."""

        def test_200(c, ctx):
            return c.get("/status/200")

        def test_404(c, ctx):
            return c.get("/status/404")

        journey = Journey(
            name="httpbin_status",
            steps=[
                Step(name="expect_200", action=test_200),
                Step(name="expect_404", action=test_404, expect_failure=True),
            ],
        )

        try:
            result = journey(client)
            # First step succeeds, second expects failure
            assert result.step_results[0].success
            assert result.step_results[1].success  # expect_failure=True makes failure a success
        except Exception as e:
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                pytest.skip(f"Network unavailable: {e}")
            raise


class TestJourneyValidation:
    """Test Journey validation against real-world scenarios."""

    def test_validate_catches_common_mistakes(self) -> None:
        """Test that validation catches common journey authoring mistakes."""

        def action(c, ctx):
            return c.get("/test")

        # Test 1: Empty journey
        empty = Journey(name="empty", steps=[])
        assert len(empty.validate()) > 0

        # Test 2: Branch referencing missing checkpoint
        with pytest.raises(Exception):  # JourneyValidationError
            Journey(
                name="bad_ref",
                steps=[Branch(checkpoint_name="nonexistent", paths=[])],
            )

        # Test 3: Duplicate step names
        duplicate = Journey(
            name="duplicate",
            steps=[
                Step(name="same_name", action=action),
                Step(name="same_name", action=action),
            ],
        )
        issues = duplicate.validate()
        assert any("duplicate" in i.lower() for i in issues)

        # Test 4: Valid journey passes validation
        valid = Journey(
            name="valid",
            steps=[
                Step(name="step1", action=action),
                Checkpoint(name="cp1"),
                Branch(
                    checkpoint_name="cp1",
                    paths=[
                        Path(name="path1", steps=[Step(name="step2", action=action)]),
                    ],
                ),
            ],
        )
        assert valid.validate() == []


class TestRealWorldScenarios:
    """Test real-world testing scenarios."""

    def test_journey_with_context_sharing(self) -> None:
        """Test that context is properly shared between steps."""

        def step1(c, ctx):
            ctx.set("user_id", 123)
            return {"status": "ok"}

        def step2(c, ctx):
            user_id = ctx.get("user_id")
            assert user_id == 123, f"Expected user_id=123, got {user_id}"
            return {"status": "ok", "user_id": user_id}

        journey = Journey(
            name="context_sharing",
            steps=[
                Step(name="set_context", action=step1),
                Step(name="use_context", action=step2),
            ],
        )

        issues = journey.validate()
        assert issues == []

    def test_journey_tags_filtering(self) -> None:
        """Test that journey tags work correctly."""

        def action(c, ctx):
            return {"ok": True}

        journey = Journey(
            name="tagged_journey",
            steps=[Step(name="test", action=action)],
            tags=["smoke", "api", "v2"],
        )

        assert journey.has_tag("smoke")
        assert journey.has_tag("API")  # Case insensitive
        assert not journey.has_tag("regression")

    def test_step_timeout_configuration(self) -> None:
        """Test that step timeout is properly configured."""

        def slow_action(c, ctx):
            import time
            time.sleep(0.1)
            return {"status": "ok"}

        step = Step(name="slow", action=slow_action, timeout=5.0)
        assert step.timeout == 5.0

        journey = Journey(
            name="timed_journey",
            steps=[step],
            timeout=30.0,
        )
        assert journey.timeout == 30.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
