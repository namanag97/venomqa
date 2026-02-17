"""Pytest integration for VenomQA stress test scenarios.

This module provides pytest test functions for running the stress
test scenarios in a CI/CD environment.

Run with:
    pytest tests/scenarios/test_scenarios.py -v

Skip slow tests:
    pytest tests/scenarios/test_scenarios.py -v -m "not slow"

Run specific category:
    pytest tests/scenarios/test_scenarios.py -v -k "branching"
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests.scenarios.scenario_concurrent_users import (
    concurrent_checkout_journey,
    inventory_stress_journey,
)

# Import all scenarios
from tests.scenarios.scenario_deep_branching import (
    deep_branching_journey,
    triple_nested_journey,
)
from tests.scenarios.scenario_failure_recovery import (
    failure_recovery_journey,
    partial_save_journey,
)
from tests.scenarios.scenario_file_operations import (
    file_cleanup_journey,
    file_operations_journey,
)
from tests.scenarios.scenario_long_running import (
    long_running_journey,
    memory_intensive_journey,
)
from tests.scenarios.scenario_realtime import (
    notification_journey,
    websocket_recovery_journey,
)
from tests.scenarios.scenario_time_based import (
    cart_expiration_journey,
    session_timeout_journey,
)
from venomqa import Client, JourneyRunner
from venomqa.core.models import JourneyResult
from venomqa.state import InMemoryStateManager

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_client():
    """Create a mock client for unit testing scenarios."""
    client = MagicMock(spec=Client)

    # Default successful response
    response = MagicMock()
    response.status_code = 200
    response.is_error = False
    response.json.return_value = {"id": "test_id", "status": "success"}
    response.content = b"test content"
    response.headers = {}

    client.get.return_value = response
    client.post.return_value = response
    client.put.return_value = response
    client.patch.return_value = response
    client.delete.return_value = response
    client.history = []
    client.last_request.return_value = None
    client.clear_history.return_value = None

    return client


@pytest.fixture
def mock_runner(mock_client):
    """Create a runner with mock client."""
    state_manager = InMemoryStateManager()

    return JourneyRunner(
        client=mock_client,
        state_manager=state_manager,
        parallel_paths=1,
        fail_fast=False,
    )


@pytest.fixture
def real_client(request):
    """Create a real client for integration testing.

    Use with:
        @pytest.mark.integration
        def test_with_real_client(real_client):
            ...
    """
    base_url = request.config.getoption("--base-url", default="http://localhost:8000")
    return Client(base_url=base_url)


@pytest.fixture
def real_runner(real_client):
    """Create a runner with real client."""
    state_manager = InMemoryStateManager()

    return JourneyRunner(
        client=real_client,
        state_manager=state_manager,
        parallel_paths=1,
        fail_fast=False,
    )


# =============================================================================
# Deep Branching Tests
# =============================================================================


class TestDeepBranching:
    """Tests for deep branching scenarios."""

    def test_journey_structure_valid(self):
        """Verify deep branching journey has valid structure."""
        journey = deep_branching_journey

        assert journey.name == "deep_branching_scenario"
        assert len(journey.steps) > 0
        assert len(journey.get_checkpoints()) >= 1
        assert "stress-test" in journey.tags

    def test_triple_nested_structure_valid(self):
        """Verify triple nested journey has valid structure."""
        journey = triple_nested_journey

        assert journey.name == "triple_nested_branching"
        assert len(journey.get_branches()) >= 1
        assert len(journey.get_checkpoints()) >= 1

    @pytest.mark.slow
    def test_deep_branching_execution(self, mock_runner):
        """Test deep branching journey execution."""
        result = mock_runner.run(deep_branching_journey)

        assert isinstance(result, JourneyResult)
        assert result.journey_name == "deep_branching_scenario"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_deep_branching_integration(self, real_runner):
        """Integration test for deep branching scenario."""
        result = real_runner.run(deep_branching_journey)

        assert isinstance(result, JourneyResult)
        # Note: Success depends on application state


# =============================================================================
# Concurrent Users Tests
# =============================================================================


class TestConcurrentUsers:
    """Tests for concurrent user scenarios."""

    def test_concurrent_checkout_structure(self):
        """Verify concurrent checkout journey structure."""
        journey = concurrent_checkout_journey

        assert journey.name == "concurrent_checkout_stress"
        assert "concurrency" in journey.tags
        assert journey.timeout == 300.0

    def test_inventory_stress_structure(self):
        """Verify inventory stress journey structure."""
        journey = inventory_stress_journey

        assert journey.name == "inventory_stress_test"
        assert len(journey.get_checkpoints()) >= 1

    @pytest.mark.slow
    def test_concurrent_checkout_execution(self, mock_runner):
        """Test concurrent checkout execution."""
        result = mock_runner.run(concurrent_checkout_journey)

        assert isinstance(result, JourneyResult)


# =============================================================================
# Long Running Tests
# =============================================================================


class TestLongRunning:
    """Tests for long-running scenarios."""

    def test_long_running_structure(self):
        """Verify long running journey has 50+ steps."""
        journey = long_running_journey

        assert journey.name == "long_running_50_steps"
        assert len(journey.steps) >= 50
        assert "memory" in journey.tags

    def test_memory_intensive_structure(self):
        """Verify memory intensive journey structure."""
        journey = memory_intensive_journey

        assert journey.name == "memory_intensive_journey"
        assert len(journey.get_checkpoints()) >= 2

    @pytest.mark.slow
    @pytest.mark.timeout(600)  # 10 minute timeout
    def test_long_running_execution(self, mock_runner):
        """Test long running journey execution."""
        result = mock_runner.run(long_running_journey)

        assert isinstance(result, JourneyResult)
        assert result.total_steps >= 50


# =============================================================================
# Failure Recovery Tests
# =============================================================================


class TestFailureRecovery:
    """Tests for failure recovery scenarios."""

    def test_failure_recovery_structure(self):
        """Verify failure recovery journey structure."""
        journey = failure_recovery_journey

        assert journey.name == "failure_recovery_scenario"
        assert "retry" in journey.tags

    def test_partial_save_structure(self):
        """Verify partial save journey structure."""
        journey = partial_save_journey

        assert journey.name == "partial_save_scenario"
        assert len(journey.get_branches()) >= 1

    @pytest.mark.slow
    def test_failure_recovery_execution(self, mock_runner):
        """Test failure recovery execution."""
        result = mock_runner.run(failure_recovery_journey)

        assert isinstance(result, JourneyResult)


# =============================================================================
# Real-Time Tests
# =============================================================================


class TestRealTime:
    """Tests for real-time scenarios."""

    def test_websocket_recovery_structure(self):
        """Verify WebSocket recovery journey structure."""
        journey = websocket_recovery_journey

        assert journey.name == "websocket_recovery_scenario"
        assert "websocket" in journey.tags

    def test_notification_structure(self):
        """Verify notification journey structure."""
        journey = notification_journey

        assert journey.name == "notification_delivery_scenario"
        assert "notifications" in journey.tags

    @pytest.mark.slow
    @pytest.mark.skipif(
        True,  # Skip by default as WebSocket requires server
        reason="WebSocket tests require running server with WS support",
    )
    def test_websocket_recovery_execution(self, mock_runner):
        """Test WebSocket recovery execution."""
        result = mock_runner.run(websocket_recovery_journey)

        assert isinstance(result, JourneyResult)


# =============================================================================
# File Operations Tests
# =============================================================================


class TestFileOperations:
    """Tests for file operation scenarios."""

    def test_file_operations_structure(self):
        """Verify file operations journey structure."""
        journey = file_operations_journey

        assert journey.name == "file_operations_scenario"
        assert "files" in journey.tags

    def test_file_cleanup_structure(self):
        """Verify file cleanup journey structure."""
        journey = file_cleanup_journey

        assert journey.name == "file_cleanup_scenario"
        assert len(journey.get_checkpoints()) >= 2

    @pytest.mark.slow
    def test_file_operations_execution(self, mock_runner):
        """Test file operations execution."""
        # Set up mock for file operations
        mock_runner.client.post.return_value.json.return_value = {
            "id": "file_id",
            "filename": "test.txt",
        }

        result = mock_runner.run(file_operations_journey)

        assert isinstance(result, JourneyResult)


# =============================================================================
# Time-Based Tests
# =============================================================================


class TestTimeBased:
    """Tests for time-based scenarios."""

    def test_cart_expiration_structure(self):
        """Verify cart expiration journey structure."""
        journey = cart_expiration_journey

        assert journey.name == "cart_expiration_scenario"
        assert "time" in journey.tags

    def test_session_timeout_structure(self):
        """Verify session timeout journey structure."""
        journey = session_timeout_journey

        assert journey.name == "session_timeout_scenario"
        assert "session" in journey.tags

    @pytest.mark.slow
    def test_cart_expiration_execution(self, mock_runner):
        """Test cart expiration execution."""
        result = mock_runner.run(cart_expiration_journey)

        assert isinstance(result, JourneyResult)


# =============================================================================
# Scenario Validation Tests
# =============================================================================


class TestScenarioValidation:
    """Tests to validate scenario definitions."""

    @pytest.mark.parametrize(
        "journey",
        [
            deep_branching_journey,
            triple_nested_journey,
            concurrent_checkout_journey,
            inventory_stress_journey,
            long_running_journey,
            memory_intensive_journey,
            failure_recovery_journey,
            partial_save_journey,
            websocket_recovery_journey,
            notification_journey,
            file_operations_journey,
            file_cleanup_journey,
            cart_expiration_journey,
            session_timeout_journey,
        ],
    )
    def test_journey_has_required_fields(self, journey):
        """Verify all journeys have required fields."""
        assert journey.name, "Journey must have a name"
        assert journey.description, "Journey must have a description"
        assert len(journey.tags) > 0, "Journey must have at least one tag"
        assert len(journey.steps) > 0, "Journey must have at least one step"

    @pytest.mark.parametrize(
        "journey",
        [
            deep_branching_journey,
            triple_nested_journey,
            concurrent_checkout_journey,
            inventory_stress_journey,
            long_running_journey,
            memory_intensive_journey,
            failure_recovery_journey,
            partial_save_journey,
            websocket_recovery_journey,
            notification_journey,
            file_operations_journey,
            file_cleanup_journey,
            cart_expiration_journey,
            session_timeout_journey,
        ],
    )
    def test_journey_has_stress_test_tag(self, journey):
        """Verify all scenarios are tagged as stress tests."""
        assert "stress-test" in journey.tags, (
            f"Journey {journey.name} should have 'stress-test' tag"
        )

    @pytest.mark.parametrize(
        "journey",
        [
            deep_branching_journey,
            concurrent_checkout_journey,
            long_running_journey,
            failure_recovery_journey,
            websocket_recovery_journey,
            file_operations_journey,
            cart_expiration_journey,
        ],
    )
    def test_journey_has_checkpoints(self, journey):
        """Verify main journeys have checkpoints."""
        checkpoints = journey.get_checkpoints()
        assert len(checkpoints) >= 1, (
            f"Journey {journey.name} should have at least one checkpoint"
        )


# =============================================================================
# Pytest Configuration
# =============================================================================


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--base-url",
        action="store",
        default="http://localhost:8000",
        help="Base URL for integration tests",
    )


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
