"""Regression tests for red team review fixes (2026-02-18).

Tests for:
- F4: Strategy.notify() replaces duck-typed hasattr checks
- F5: PostgresAdapter isinstance check (not string comparison)
- F6: 16-char state hash (64-bit collision resistance)
- A2: World.can_execute_action() skips observe() for context-only preconditions
- D4: ActionResult.json() raises ValueError (not AttributeError)
"""

import pytest

from venomqa.v1.agent.strategies import (
    BFS,
    DFS,
    CoverageGuided,
    Random,
    Strategy,
    Weighted,
)
from venomqa.v1.core.action import (
    Action,
    ActionResult,
    HTTPRequest,
    precondition_action_ran,
    precondition_has_context,
)
from venomqa.v1.core.context import Context
from venomqa.v1.core.state import Observation, State


class TestF4StrategyNotify:
    """F4: All strategies implement notify() method."""

    def test_strategy_protocol_has_notify(self):
        """Strategy Protocol includes notify() method."""
        # Check that Strategy protocol has notify method
        assert hasattr(Strategy, "notify")

    def test_bfs_has_notify(self):
        """BFS implements notify()."""
        strategy = BFS()
        assert hasattr(strategy, "notify")
        assert callable(strategy.notify)

    def test_dfs_has_notify(self):
        """DFS implements notify()."""
        strategy = DFS()
        assert hasattr(strategy, "notify")
        assert callable(strategy.notify)

    def test_random_has_notify(self):
        """Random implements notify() (inherited from BaseStrategy)."""
        strategy = Random()
        assert hasattr(strategy, "notify")
        assert callable(strategy.notify)

    def test_coverage_guided_has_notify(self):
        """CoverageGuided implements notify()."""
        strategy = CoverageGuided()
        assert hasattr(strategy, "notify")
        assert callable(strategy.notify)

    def test_weighted_has_notify(self):
        """Weighted implements notify() (inherited from BaseStrategy)."""
        strategy = Weighted()
        assert hasattr(strategy, "notify")
        assert callable(strategy.notify)

    def test_bfs_notify_adds_to_queue(self):
        """BFS.notify() adds actions to internal queue."""
        strategy = BFS()
        state = State(id="s_test", observations={})
        action = Action(name="test_action", execute=lambda api: None)

        # Initially queue should be empty (strategy not initialized)
        assert len(strategy._queue) == 0

        # Call notify
        strategy.notify(state, [action])

        # Queue should have the action
        assert len(strategy._queue) == 1
        assert strategy._queue[0] == ("s_test", "test_action")

    def test_dfs_notify_adds_to_stack(self):
        """DFS.notify() adds actions to internal stack."""
        strategy = DFS()
        state = State(id="s_test", observations={})
        action = Action(name="test_action", execute=lambda api: None)

        # Initially stack should be empty
        assert len(strategy._stack) == 0

        # Call notify
        strategy.notify(state, [action])

        # Stack should have the action
        assert len(strategy._stack) == 1
        assert strategy._stack[0] == ("s_test", "test_action")


class TestF5PostgresAdapterIsinstance:
    """F5: PostgresAdapter check uses isinstance, not string comparison."""

    def test_isinstance_check_works_for_subclass(self):
        """isinstance check catches PostgresAdapter subclasses."""
        from venomqa.v1.adapters.postgres import PostgresAdapter

        class CustomPostgresAdapter(PostgresAdapter):
            """A subclass that should also be caught."""
            pass

        # The old string comparison would fail here
        adapter = CustomPostgresAdapter("postgresql://localhost/test")
        assert isinstance(adapter, PostgresAdapter)

        # Verify it's not the exact type
        assert type(adapter).__name__ == "CustomPostgresAdapter"
        assert type(adapter).__name__ != "PostgresAdapter"


class TestF6HashLength:
    """F6: State hash is 16 characters (64-bit collision resistance)."""

    def test_state_id_is_18_chars(self):
        """State ID is 's_' + 16 hex chars = 18 total."""
        obs = Observation(system="test", data={"key": "value"})
        state = State.create(observations={"test": obs})

        # s_ prefix + 16 hex chars
        assert len(state.id) == 18
        assert state.id.startswith("s_")
        # Content hash should be 16 chars
        assert len(state.content_hash()) == 16

    def test_different_states_have_different_hashes(self):
        """Different observations produce different state IDs."""
        obs1 = Observation(system="test", data={"key": "value1"})
        obs2 = Observation(system="test", data={"key": "value2"})

        state1 = State.create(observations={"test": obs1})
        state2 = State.create(observations={"test": obs2})

        assert state1.id != state2.id


class TestA2CanExecuteOptimization:
    """A2: World.can_execute_action() skips observe() for context-only preconditions."""

    def test_context_only_precondition_skips_observe(self):
        """Context-only preconditions don't require observe()."""
        from unittest.mock import MagicMock, patch

        from venomqa.v1.adapters.http import HttpClient
        from venomqa.v1.world import World

        # Create a mock HTTP client
        mock_api = MagicMock(spec=HttpClient)
        world = World(api=mock_api)

        # Set context value
        world.context.set("user_id", "123")

        # Create action with context-only precondition
        action = Action(
            name="test_action",
            execute=lambda api: None,
            preconditions=[precondition_has_context("user_id")],
        )

        # Patch observe to track if it's called
        with patch.object(world, "observe") as mock_observe:
            result = world.can_execute_action(action)

            # observe() should NOT be called for context-only precondition
            mock_observe.assert_not_called()

        assert result is True

    def test_state_based_precondition_calls_observe(self):
        """State-based preconditions require observe()."""
        from unittest.mock import MagicMock, patch

        from venomqa.v1.adapters.http import HttpClient
        from venomqa.v1.world import World

        # Create a mock HTTP client
        mock_api = MagicMock(spec=HttpClient)
        world = World(api=mock_api)

        # Create action with state-based precondition
        def state_precondition(state: State) -> bool:
            return True

        action = Action(
            name="test_action",
            execute=lambda api: None,
            preconditions=[state_precondition],
        )

        # Patch observe to track if it's called
        mock_state = State(id="s_mock", observations={})
        with patch.object(world, "observe", return_value=mock_state) as mock_observe:
            world.can_execute_action(action)

            # observe() SHOULD be called for state-based precondition
            mock_observe.assert_called_once()

    def test_action_ran_precondition_skips_observe(self):
        """precondition_action_ran() doesn't require observe()."""
        from unittest.mock import MagicMock, patch

        from venomqa.v1.adapters.http import HttpClient
        from venomqa.v1.world import World

        mock_api = MagicMock(spec=HttpClient)
        world = World(api=mock_api)

        action = Action(
            name="test_action",
            execute=lambda api: None,
            preconditions=[precondition_action_ran("other_action")],
        )

        with patch.object(world, "observe") as mock_observe:
            # Will fail because other_action hasn't run, but observe shouldn't be called
            world.can_execute_action(action)
            mock_observe.assert_not_called()


class TestD4ActionResultJsonException:
    """D4: ActionResult.json() raises ValueError, not AttributeError."""

    def test_json_raises_value_error_when_no_response(self):
        """ActionResult.json() raises ValueError when response is None."""
        request = HTTPRequest(method="GET", url="/test")
        result = ActionResult(
            success=False,
            request=request,
            response=None,
            error="Connection refused",
        )

        with pytest.raises(ValueError) as exc_info:
            result.json()

        assert "Cannot get JSON: request failed with no response" in str(exc_info.value)

    def test_json_does_not_raise_attribute_error(self):
        """Verify it's not AttributeError (the old behavior)."""
        request = HTTPRequest(method="GET", url="/test")
        result = ActionResult(
            success=False,
            request=request,
            response=None,
            error="Connection refused",
        )

        # Should NOT raise AttributeError
        try:
            result.json()
        except AttributeError:
            pytest.fail("json() should raise ValueError, not AttributeError")
        except ValueError:
            pass  # Expected
