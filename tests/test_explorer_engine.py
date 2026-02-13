"""
Tests for the VenomQA State Explorer Engine.

This test module verifies that the ExplorationEngine implements
real exploration logic including:
- BFS and DFS exploration
- Action execution with HTTP calls
- Cycle detection
- State tracking and graph building
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venomqa.explorer.engine import (
    ExplorationEngine,
    ExplorationError,
    ExplorationStrategy,
)
from venomqa.explorer.models import (
    Action,
    CoverageReport,
    ExplorationConfig,
    Issue,
    IssueSeverity,
    State,
    StateGraph,
    Transition,
)


class TestExplorationEngineInitialization:
    """Test ExplorationEngine initialization."""

    def test_default_initialization(self):
        """Test creating engine with default configuration."""
        engine = ExplorationEngine()

        assert engine.config is not None
        assert engine.strategy == ExplorationStrategy.BFS
        assert engine.graph is not None
        assert isinstance(engine.graph, StateGraph)
        assert len(engine.issues) == 0
        assert len(engine.visited_states) == 0
        assert len(engine.visited_transitions) == 0

    def test_initialization_with_config(self):
        """Test creating engine with custom configuration."""
        config = ExplorationConfig(
            max_depth=5,
            max_states=50,
            max_transitions=200,
            timeout_seconds=60,
        )
        engine = ExplorationEngine(config=config, strategy=ExplorationStrategy.DFS)

        assert engine.config.max_depth == 5
        assert engine.config.max_states == 50
        assert engine.config.max_transitions == 200
        assert engine.strategy == ExplorationStrategy.DFS

    def test_initialization_with_base_url(self):
        """Test creating engine with base URL."""
        engine = ExplorationEngine(base_url="http://api.example.com")
        assert engine.base_url == "http://api.example.com"

    def test_all_strategies_available(self):
        """Test that all exploration strategies are available."""
        assert ExplorationStrategy.BFS == "bfs"
        assert ExplorationStrategy.DFS == "dfs"
        assert ExplorationStrategy.RANDOM == "random"
        assert ExplorationStrategy.GREEDY == "greedy"
        assert ExplorationStrategy.HYBRID == "hybrid"


class TestActionExecutor:
    """Test action executor functionality."""

    def test_set_action_executor(self):
        """Test setting a custom action executor."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            return {"status": "ok"}

        engine.set_action_executor(mock_executor)
        assert engine._action_executor is not None

    def test_set_state_detector(self):
        """Test setting a custom state detector."""
        engine = ExplorationEngine()

        def mock_detector(response, endpoint, status):
            return State(id="test", name="Test State")

        engine.set_state_detector(mock_detector)
        assert engine._state_detector is not None


class TestExecuteAction:
    """Test action execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_action_with_custom_executor(self):
        """Test executing an action with a custom executor."""
        engine = ExplorationEngine()

        # Create a mock executor that returns response data
        async def mock_executor(action):
            return {
                "status_code": 200,
                "data": {"id": 1, "name": "Test"},
            }

        engine.set_action_executor(mock_executor)

        action = Action(method="GET", endpoint="/api/users/1")
        initial_state = State(id="initial", name="Initial State")

        result_state, transition = await engine.execute_action(action, initial_state)

        assert result_state is not None
        assert transition is not None
        assert transition.from_state == "initial"
        assert transition.action == action
        assert transition.success is True

    @pytest.mark.asyncio
    async def test_execute_action_with_error_response(self):
        """Test executing an action that returns an error status."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            return {
                "status_code": 404,
                "error": "Not found",
            }

        engine.set_action_executor(mock_executor)

        action = Action(method="GET", endpoint="/api/users/999")
        initial_state = State(id="initial", name="Initial State")

        result_state, transition = await engine.execute_action(action, initial_state)

        assert result_state is not None
        assert transition is not None
        assert transition.success is False
        assert transition.status_code == 404
        # Should have recorded an issue
        assert len(engine.issues) > 0

    @pytest.mark.asyncio
    async def test_execute_action_with_exception(self):
        """Test executing an action that raises an exception."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            raise Exception("Connection failed")

        engine.set_action_executor(mock_executor)

        action = Action(method="GET", endpoint="/api/users/1")
        initial_state = State(id="initial", name="Initial State")

        result_state, transition = await engine.execute_action(action, initial_state)

        assert result_state is not None
        assert transition is not None
        assert transition.success is False
        assert "Connection failed" in transition.error
        # Should have recorded an issue
        assert len(engine.issues) > 0

    @pytest.mark.asyncio
    async def test_execute_action_records_timing(self):
        """Test that action execution records timing information."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            await asyncio.sleep(0.01)  # Small delay
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        action = Action(method="GET", endpoint="/api/test")
        initial_state = State(id="initial", name="Initial State")

        result_state, transition = await engine.execute_action(action, initial_state)

        assert transition.duration_ms >= 10  # At least 10ms


class TestBFSExploration:
    """Test Breadth-First Search exploration."""

    @pytest.mark.asyncio
    async def test_bfs_explores_level_by_level(self):
        """Test that BFS explores states level by level."""
        engine = ExplorationEngine(strategy=ExplorationStrategy.BFS)

        # Track exploration order
        explored_order = []

        async def mock_executor(action):
            explored_order.append(action.endpoint)
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        # Create initial state with two actions
        initial_state = State(
            id="s0",
            name="Initial",
            available_actions=[
                Action(method="GET", endpoint="/level1/a"),
                Action(method="GET", endpoint="/level1/b"),
            ],
        )

        # Create a state detector that returns states with more actions
        def state_detector(response, endpoint, status):
            if "level1/a" in endpoint:
                return State(
                    id="s1a",
                    name="State 1A",
                    available_actions=[
                        Action(method="GET", endpoint="/level2/aa"),
                    ],
                )
            elif "level1/b" in endpoint:
                return State(
                    id="s1b",
                    name="State 1B",
                    available_actions=[
                        Action(method="GET", endpoint="/level2/bb"),
                    ],
                )
            else:
                return State(id=f"s_{endpoint.replace('/', '_')}", name=f"State {endpoint}")

        engine.set_state_detector(state_detector)

        config = ExplorationConfig(max_depth=3, max_states=10)
        engine.config = config

        await engine.explore(initial_state)

        # BFS should explore both level1 actions before going to level2
        assert explored_order[0] in ["/level1/a", "/level1/b"]
        assert explored_order[1] in ["/level1/a", "/level1/b"]
        # Level 2 actions should come after level 1
        level1_count = sum(1 for e in explored_order[:2] if "level1" in e)
        assert level1_count == 2

    @pytest.mark.asyncio
    async def test_bfs_respects_max_depth(self):
        """Test that BFS respects the maximum depth limit."""
        engine = ExplorationEngine(strategy=ExplorationStrategy.BFS)

        depth_reached = [0]

        async def mock_executor(action):
            # Extract depth from endpoint
            depth = int(action.endpoint.split("/")[-1])
            depth_reached[0] = max(depth_reached[0], depth)
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            depth = int(endpoint.split("/")[-1])
            return State(
                id=f"s{depth}",
                name=f"State {depth}",
                available_actions=[
                    Action(method="GET", endpoint=f"/depth/{depth + 1}"),
                ],
            )

        engine.set_state_detector(state_detector)

        config = ExplorationConfig(max_depth=3, max_states=10)
        engine.config = config

        initial_state = State(
            id="s0",
            name="Initial",
            available_actions=[Action(method="GET", endpoint="/depth/1")],
        )

        await engine.explore(initial_state)

        # Should not exceed max_depth
        assert depth_reached[0] <= 3


class TestDFSExploration:
    """Test Depth-First Search exploration."""

    @pytest.mark.asyncio
    async def test_dfs_explores_deeply_first(self):
        """Test that DFS explores deeply before backtracking."""
        engine = ExplorationEngine(strategy=ExplorationStrategy.DFS)

        explored_order = []

        async def mock_executor(action):
            explored_order.append(action.endpoint)
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            if endpoint == "/a":
                return State(
                    id="s_a",
                    name="State A",
                    available_actions=[
                        Action(method="GET", endpoint="/a/deep"),
                    ],
                )
            elif endpoint == "/a/deep":
                return State(id="s_a_deep", name="State A Deep")
            elif endpoint == "/b":
                return State(id="s_b", name="State B")
            else:
                return State(id=f"s_{endpoint}", name=f"State {endpoint}")

        engine.set_state_detector(state_detector)

        config = ExplorationConfig(max_depth=5, max_states=10)
        engine.config = config

        initial_state = State(
            id="s0",
            name="Initial",
            available_actions=[
                Action(method="GET", endpoint="/a"),
                Action(method="GET", endpoint="/b"),
            ],
        )

        await engine.explore(initial_state)

        # DFS should explore /a then /a/deep before /b
        # Due to stack semantics (LIFO), the last action pushed is explored first
        # So /b is pushed, then /a is pushed, /a is popped first
        a_index = explored_order.index("/a") if "/a" in explored_order else -1
        a_deep_index = explored_order.index("/a/deep") if "/a/deep" in explored_order else -1
        b_index = explored_order.index("/b") if "/b" in explored_order else -1

        # Both /a and /a/deep should be explored before /b (DFS behavior)
        if a_index >= 0 and a_deep_index >= 0 and b_index >= 0:
            assert a_index < a_deep_index  # /a before /a/deep
            assert a_deep_index < b_index  # /a/deep before /b


class TestCycleDetection:
    """Test cycle detection during exploration."""

    @pytest.mark.asyncio
    async def test_cycle_detection_prevents_infinite_loops(self):
        """Test that cycles are detected and don't cause infinite loops."""
        engine = ExplorationEngine(strategy=ExplorationStrategy.BFS)

        execution_count = [0]

        async def mock_executor(action):
            execution_count[0] += 1
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        # Create a cycle: A -> B -> A
        def state_detector(response, endpoint, status):
            if endpoint == "/state_a":
                return State(
                    id="a",
                    name="State A",
                    available_actions=[Action(method="GET", endpoint="/state_b")],
                )
            elif endpoint == "/state_b":
                return State(
                    id="b",
                    name="State B",
                    available_actions=[Action(method="GET", endpoint="/state_a")],
                )
            return State(id="unknown", name="Unknown")

        engine.set_state_detector(state_detector)

        config = ExplorationConfig(max_depth=10, max_states=10, max_transitions=20)
        engine.config = config

        initial_state = State(
            id="start",
            name="Start",
            available_actions=[Action(method="GET", endpoint="/state_a")],
        )

        await engine.explore(initial_state)

        # Should not execute indefinitely - transitions are tracked
        # Each unique (from_state, action, to_state) combination only runs once
        assert execution_count[0] < 10  # Reasonable limit

    @pytest.mark.asyncio
    async def test_transition_tracking(self):
        """Test that transitions are properly tracked."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        action = Action(method="GET", endpoint="/test")
        from_state = State(id="s1", name="State 1")

        # Execute action once
        await engine.execute_action(action, from_state)

        # Check that transition was tracked
        assert len(engine.visited_transitions) > 0

    def test_is_transition_visited(self):
        """Test transition visited check."""
        engine = ExplorationEngine()

        action = Action(method="GET", endpoint="/test")

        # Not visited initially
        assert not engine._is_transition_visited("s1", action, "s2")

        # Mark as visited
        engine._mark_transition_visited("s1", action, "s2")

        # Now should be visited
        assert engine._is_transition_visited("s1", action, "s2")


class TestStateTracking:
    """Test state tracking during exploration."""

    @pytest.mark.asyncio
    async def test_visited_states_tracked(self):
        """Test that visited states are tracked."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            return State(id="new_state", name="New State")

        engine.set_state_detector(state_detector)

        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[Action(method="GET", endpoint="/test")],
        )

        await engine.explore(initial_state)

        # Both states should be in visited_states
        assert "initial" in engine.visited_states
        assert "new_state" in engine.visited_states

    @pytest.mark.asyncio
    async def test_states_added_to_graph(self):
        """Test that discovered states are added to the graph."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            return State(id="discovered", name="Discovered State")

        engine.set_state_detector(state_detector)

        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[Action(method="GET", endpoint="/test")],
        )

        await engine.explore(initial_state)

        # States should be in graph
        assert "initial" in engine.graph.states
        assert "discovered" in engine.graph.states


class TestCoverageReport:
    """Test coverage report generation."""

    @pytest.mark.asyncio
    async def test_coverage_report_generation(self):
        """Test that coverage report is generated correctly."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            return State(id=f"state_{endpoint}", name=f"State {endpoint}")

        engine.set_state_detector(state_detector)

        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[
                Action(method="GET", endpoint="/api/users"),
                Action(method="GET", endpoint="/api/items"),
            ],
        )

        await engine.explore(initial_state)

        report = engine.get_coverage_report()

        assert isinstance(report, CoverageReport)
        assert report.states_found > 0
        assert report.transitions_found > 0
        assert report.endpoints_discovered > 0
        assert report.endpoints_tested > 0
        assert 0 <= report.coverage_percent <= 100

    @pytest.mark.asyncio
    async def test_coverage_report_uncovered_actions(self):
        """Test that uncovered actions are tracked."""
        engine = ExplorationEngine()

        config = ExplorationConfig(max_depth=1, max_states=2, max_transitions=1)
        engine.config = config

        async def mock_executor(action):
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        # With max_transitions=1, only one action will be executed
        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[
                Action(method="GET", endpoint="/api/a"),
                Action(method="GET", endpoint="/api/b"),
                Action(method="GET", endpoint="/api/c"),
            ],
        )

        await engine.explore(initial_state)

        report = engine.get_coverage_report()

        # Some actions should be uncovered due to limits
        assert report.endpoints_discovered >= report.endpoints_tested


class TestLimitsEnforcement:
    """Test that exploration limits are enforced."""

    @pytest.mark.asyncio
    async def test_max_states_limit(self):
        """Test that max_states limit is enforced."""
        config = ExplorationConfig(max_depth=100, max_states=3, max_transitions=100)
        engine = ExplorationEngine(config=config)

        async def mock_executor(action):
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        state_counter = [0]

        def state_detector(response, endpoint, status):
            state_counter[0] += 1
            return State(
                id=f"state_{state_counter[0]}",
                name=f"State {state_counter[0]}",
                available_actions=[
                    Action(method="GET", endpoint=f"/next_{state_counter[0]}"),
                ],
            )

        engine.set_state_detector(state_detector)

        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[Action(method="GET", endpoint="/start")],
        )

        await engine.explore(initial_state)

        # Should not exceed max_states
        assert len(engine.visited_states) <= config.max_states + 1  # +1 for initial

    @pytest.mark.asyncio
    async def test_max_transitions_limit(self):
        """Test that max_transitions limit is enforced."""
        config = ExplorationConfig(max_depth=100, max_states=100, max_transitions=3)
        engine = ExplorationEngine(config=config)

        execution_count = [0]

        async def mock_executor(action):
            execution_count[0] += 1
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            return State(
                id=f"state_{endpoint}",
                name=f"State {endpoint}",
                available_actions=[
                    Action(method="GET", endpoint=f"/next_{execution_count[0]}"),
                ],
            )

        engine.set_state_detector(state_detector)

        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[Action(method="GET", endpoint="/start")],
        )

        await engine.explore(initial_state)

        # Should not exceed max_transitions
        assert len(engine.visited_transitions) <= config.max_transitions

    def test_check_limits(self):
        """Test the _check_limits method."""
        config = ExplorationConfig(max_depth=5, max_states=10, max_transitions=20)
        engine = ExplorationEngine(config=config)

        # Initially should return True
        assert engine._check_limits() is True

        # Add states up to limit
        for i in range(10):
            engine.visited_states.add(f"state_{i}")

        # Now should return False
        assert engine._check_limits() is False


class TestIssueTracking:
    """Test issue tracking during exploration."""

    def test_record_issue(self):
        """Test recording issues."""
        engine = ExplorationEngine()

        engine._record_issue(
            severity=IssueSeverity.HIGH,
            error="Test error",
            state="s1",
            suggestion="Fix it",
        )

        assert len(engine.issues) == 1
        assert engine.issues[0].severity == IssueSeverity.HIGH
        assert engine.issues[0].error == "Test error"
        assert engine.issues[0].state == "s1"
        assert engine.issues[0].suggestion == "Fix it"

    @pytest.mark.asyncio
    async def test_issues_recorded_on_http_errors(self):
        """Test that issues are recorded for HTTP errors."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            return {"status_code": 500, "error": "Internal Server Error"}

        engine.set_action_executor(mock_executor)

        action = Action(method="GET", endpoint="/api/error")
        initial_state = State(id="initial", name="Initial")

        await engine.execute_action(action, initial_state)

        # Should have recorded an issue
        assert len(engine.issues) > 0
        assert any(issue.severity == IssueSeverity.HIGH for issue in engine.issues)


class TestReset:
    """Test engine reset functionality."""

    @pytest.mark.asyncio
    async def test_reset_clears_all_state(self):
        """Test that reset clears all exploration state."""
        engine = ExplorationEngine()

        # Add some state
        engine.visited_states.add("s1")
        engine.visited_transitions.add(("s1", "GET:/test", "s2"))
        engine.issues.append(
            Issue(severity=IssueSeverity.LOW, error="Test")
        )
        engine.graph.add_state(State(id="s1", name="State 1"))

        # Reset
        engine.reset()

        # All should be cleared
        assert len(engine.visited_states) == 0
        assert len(engine.visited_transitions) == 0
        assert len(engine.issues) == 0
        assert len(engine.graph.states) == 0
        assert len(engine.graph.transitions) == 0


class TestActionFiltering:
    """Test action filtering based on patterns."""

    def test_should_explore_action_default(self):
        """Test default action filtering (no patterns)."""
        engine = ExplorationEngine()

        action = Action(method="GET", endpoint="/api/users")
        assert engine._should_explore_action(action) is True

    def test_should_explore_action_with_exclude_patterns(self):
        """Test action filtering with exclude patterns."""
        config = ExplorationConfig(exclude_patterns=["/admin", "/internal"])
        engine = ExplorationEngine(config=config)

        # Should be excluded
        admin_action = Action(method="GET", endpoint="/admin/users")
        assert engine._should_explore_action(admin_action) is False

        # Should be included
        api_action = Action(method="GET", endpoint="/api/users")
        assert engine._should_explore_action(api_action) is True

    def test_should_explore_action_with_include_patterns(self):
        """Test action filtering with include patterns."""
        config = ExplorationConfig(include_patterns=["/api/"])
        engine = ExplorationEngine(config=config)

        # Should be included
        api_action = Action(method="GET", endpoint="/api/users")
        assert engine._should_explore_action(api_action) is True

        # Should be excluded (not matching include pattern)
        other_action = Action(method="GET", endpoint="/other/endpoint")
        assert engine._should_explore_action(other_action) is False


class TestDefaultStateCreation:
    """Test default state creation from responses."""

    def test_create_default_state_success(self):
        """Test creating default state from successful response."""
        engine = ExplorationEngine()

        action = Action(method="GET", endpoint="/api/users")
        from_state = State(id="s1", name="State 1")
        response_data = {"id": 1, "name": "Test User"}

        state = engine._create_default_state(
            action=action,
            from_state=from_state,
            response_data=response_data,
            status_code=200,
            success=True,
        )

        assert state is not None
        assert state.properties["success"] is True
        assert state.properties["status_code"] == 200

    def test_create_default_state_error(self):
        """Test creating default state from error response."""
        engine = ExplorationEngine()

        action = Action(method="GET", endpoint="/api/users/999")
        from_state = State(id="s1", name="State 1")
        response_data = {"error": "Not found"}

        state = engine._create_default_state(
            action=action,
            from_state=from_state,
            response_data=response_data,
            status_code=404,
            success=False,
        )

        assert state is not None
        assert "error" in state.id
        assert state.properties["success"] is False

    def test_create_default_state_with_hateoas_links(self):
        """Test creating default state with HATEOAS links."""
        engine = ExplorationEngine()

        action = Action(method="GET", endpoint="/api/users/1")
        from_state = State(id="s1", name="State 1")
        response_data = {
            "id": 1,
            "name": "Test User",
            "_links": {
                "self": {"href": "/api/users/1", "method": "GET"},
                "update": {"href": "/api/users/1", "method": "PUT"},
                "delete": {"href": "/api/users/1", "method": "DELETE"},
            },
        }

        state = engine._create_default_state(
            action=action,
            from_state=from_state,
            response_data=response_data,
            status_code=200,
            success=True,
        )

        # Should have extracted HATEOAS links as available actions
        assert len(state.available_actions) == 3
        endpoints = [a.endpoint for a in state.available_actions]
        assert "/api/users/1" in endpoints


class TestExploreFromState:
    """Test explore_from_state method."""

    @pytest.mark.asyncio
    async def test_explore_from_state_returns_discovered(self):
        """Test that explore_from_state returns discovered states."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            return State(id=f"state_{endpoint}", name=f"State {endpoint}")

        engine.set_state_detector(state_detector)

        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[
                Action(method="GET", endpoint="/a"),
                Action(method="GET", endpoint="/b"),
            ],
        )
        engine.graph.add_state(initial_state)
        engine.visited_states.add(initial_state.id)

        discovered = await engine.explore_from_state(initial_state, depth=0)

        assert len(discovered) == 2
        for new_state, transition in discovered:
            assert isinstance(new_state, State)
            assert isinstance(transition, Transition)

    @pytest.mark.asyncio
    async def test_explore_from_state_respects_depth_limit(self):
        """Test that explore_from_state respects depth limits."""
        config = ExplorationConfig(max_depth=2)
        engine = ExplorationEngine(config=config)

        async def mock_executor(action):
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[Action(method="GET", endpoint="/test")],
        )
        engine.graph.add_state(initial_state)
        engine.visited_states.add(initial_state.id)

        # At depth >= max_depth, should return empty
        discovered = await engine.explore_from_state(initial_state, depth=2)
        assert len(discovered) == 0


class TestRandomExploration:
    """Test random walk exploration."""

    @pytest.mark.asyncio
    async def test_random_exploration_executes(self):
        """Test that random exploration executes without errors."""
        engine = ExplorationEngine(strategy=ExplorationStrategy.RANDOM)

        execution_count = [0]

        async def mock_executor(action):
            execution_count[0] += 1
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            return State(id=f"state_{execution_count[0]}", name=f"State {execution_count[0]}")

        engine.set_state_detector(state_detector)

        config = ExplorationConfig(max_depth=3, max_states=5, max_transitions=10)
        engine.config = config

        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[
                Action(method="GET", endpoint="/a"),
                Action(method="GET", endpoint="/b"),
            ],
        )

        await engine.explore(initial_state)

        # Should have executed some actions
        assert execution_count[0] > 0


class TestGreedyExploration:
    """Test greedy exploration."""

    @pytest.mark.asyncio
    async def test_greedy_exploration_executes(self):
        """Test that greedy exploration executes without errors."""
        engine = ExplorationEngine(strategy=ExplorationStrategy.GREEDY)

        execution_count = [0]

        async def mock_executor(action):
            execution_count[0] += 1
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            # Return states with varying numbers of actions
            if execution_count[0] == 1:
                return State(
                    id="state_many",
                    name="State with many actions",
                    available_actions=[
                        Action(method="GET", endpoint="/many/1"),
                        Action(method="GET", endpoint="/many/2"),
                        Action(method="GET", endpoint="/many/3"),
                    ],
                )
            else:
                return State(id=f"state_{execution_count[0]}", name=f"State {execution_count[0]}")

        engine.set_state_detector(state_detector)

        config = ExplorationConfig(max_depth=5, max_states=10, max_transitions=20)
        engine.config = config

        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[
                Action(method="GET", endpoint="/start"),
            ],
        )

        await engine.explore(initial_state)

        # Should have executed actions
        assert execution_count[0] > 0


class TestHybridExploration:
    """Test hybrid exploration."""

    @pytest.mark.asyncio
    async def test_hybrid_exploration_executes(self):
        """Test that hybrid exploration executes without errors."""
        engine = ExplorationEngine(strategy=ExplorationStrategy.HYBRID)

        execution_count = [0]

        async def mock_executor(action):
            execution_count[0] += 1
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            return State(
                id=f"state_{execution_count[0]}",
                name=f"State {execution_count[0]}",
                available_actions=[
                    Action(method="GET", endpoint=f"/next_{execution_count[0]}"),
                ] if execution_count[0] < 5 else [],
            )

        engine.set_state_detector(state_detector)

        config = ExplorationConfig(max_depth=5, max_states=10, max_transitions=20)
        engine.config = config

        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[
                Action(method="GET", endpoint="/a"),
                Action(method="GET", endpoint="/b"),
            ],
        )

        await engine.explore(initial_state)

        # Should have executed actions
        assert execution_count[0] > 0


class TestGraphBuilding:
    """Test that the graph is built correctly during exploration."""

    @pytest.mark.asyncio
    async def test_graph_contains_all_transitions(self):
        """Test that all transitions are added to the graph."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            return State(id=f"state_{endpoint.replace('/', '_')}", name=f"State {endpoint}")

        engine.set_state_detector(state_detector)

        initial_state = State(
            id="initial",
            name="Initial",
            available_actions=[
                Action(method="GET", endpoint="/a"),
                Action(method="GET", endpoint="/b"),
                Action(method="GET", endpoint="/c"),
            ],
        )

        await engine.explore(initial_state)

        # Should have transitions for each action
        assert len(engine.graph.transitions) == 3

        # Each transition should have correct structure
        for transition in engine.graph.transitions:
            assert transition.from_state == "initial"
            assert transition.to_state is not None
            assert transition.action is not None

    @pytest.mark.asyncio
    async def test_graph_paths_are_correct(self):
        """Test that graph paths are correctly built."""
        engine = ExplorationEngine()

        async def mock_executor(action):
            return {"status_code": 200}

        engine.set_action_executor(mock_executor)

        def state_detector(response, endpoint, status):
            if endpoint == "/step1":
                return State(
                    id="s1",
                    name="State 1",
                    available_actions=[Action(method="GET", endpoint="/step2")],
                )
            elif endpoint == "/step2":
                return State(
                    id="s2",
                    name="State 2",
                    available_actions=[Action(method="GET", endpoint="/step3")],
                )
            else:
                return State(id="s3", name="State 3")

        engine.set_state_detector(state_detector)

        config = ExplorationConfig(max_depth=5)
        engine.config = config

        initial_state = State(
            id="s0",
            name="Initial",
            available_actions=[Action(method="GET", endpoint="/step1")],
        )

        await engine.explore(initial_state)

        # Should have path s0 -> s1 -> s2 -> s3
        assert engine.graph.has_path("s0", "s3")
        assert engine.graph.has_path("s0", "s2")
        assert engine.graph.has_path("s1", "s3")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
