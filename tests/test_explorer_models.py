"""
Tests for the VenomQA State Explorer models.

This test script verifies that the models in venomqa/explorer/models.py
are actually working implementations, not placeholder slop.
"""

from datetime import datetime, timedelta

import pytest

from venomqa.explorer.models import (
    Action,
    CoverageReport,
    ExplorationResult,
    Issue,
    IssueSeverity,
    State,
    StateGraph,
    Transition,
)


class TestAction:
    """Test Action model."""

    def test_create_basic_action(self):
        """Test creating a basic Action."""
        action = Action(method="GET", endpoint="/api/users")
        assert action.method == "GET"
        assert action.endpoint == "/api/users"
        assert action.params is None
        assert action.body is None

    def test_method_uppercase_validation(self):
        """Test that HTTP methods are uppercased."""
        action = Action(method="post", endpoint="/api/items")
        assert action.method == "POST"

    def test_action_with_all_fields(self):
        """Test Action with all optional fields."""
        action = Action(
            method="POST",
            endpoint="/api/users",
            params={"page": 1},
            body={"name": "Test"},
            headers={"X-Custom": "value"},
            description="Create a user",
            requires_auth=True,
        )
        assert action.params == {"page": 1}
        assert action.body == {"name": "Test"}
        assert action.headers == {"X-Custom": "value"}
        assert action.description == "Create a user"
        assert action.requires_auth is True

    def test_action_equality(self):
        """Test Action equality comparison."""
        action1 = Action(method="GET", endpoint="/api/users", params={"id": 1})
        action2 = Action(method="GET", endpoint="/api/users", params={"id": 1})
        action3 = Action(method="GET", endpoint="/api/users", params={"id": 2})

        assert action1 == action2
        assert action1 != action3

    def test_action_hashable(self):
        """Test that Action can be used in sets."""
        action1 = Action(method="GET", endpoint="/api/users")
        action2 = Action(method="GET", endpoint="/api/users")
        action3 = Action(method="POST", endpoint="/api/users")

        action_set = {action1, action2, action3}
        assert len(action_set) == 2  # action1 and action2 are equal


class TestState:
    """Test State model."""

    def test_create_basic_state(self):
        """Test creating a basic State."""
        state = State(id="s1", name="Initial State")
        assert state.id == "s1"
        assert state.name == "Initial State"
        assert state.properties == {}
        assert state.available_actions == []

    def test_state_with_properties(self):
        """Test State with properties and actions."""
        action = Action(method="GET", endpoint="/api/data")
        state = State(
            id="s2",
            name="Logged In",
            properties={"user_id": 123, "role": "admin"},
            available_actions=[action],
            metadata={"source": "login"},
        )
        assert state.properties == {"user_id": 123, "role": "admin"}
        assert len(state.available_actions) == 1
        assert state.metadata == {"source": "login"}

    def test_state_equality(self):
        """Test State equality is based on ID."""
        state1 = State(id="s1", name="State One")
        state2 = State(id="s1", name="Different Name")
        state3 = State(id="s2", name="State One")

        assert state1 == state2  # Same ID
        assert state1 != state3  # Different ID

    def test_state_hashable(self):
        """Test that State can be used in sets."""
        state1 = State(id="s1", name="State One")
        state2 = State(id="s1", name="Different Name")
        state3 = State(id="s2", name="State Two")

        state_set = {state1, state2, state3}
        assert len(state_set) == 2  # state1 and state2 have same ID


class TestTransition:
    """Test Transition model."""

    def test_create_basic_transition(self):
        """Test creating a basic Transition."""
        action = Action(method="POST", endpoint="/api/login")
        transition = Transition(
            from_state="s1",
            action=action,
            to_state="s2",
        )
        assert transition.from_state == "s1"
        assert transition.to_state == "s2"
        assert transition.action == action
        assert transition.success is True

    def test_transition_with_response(self):
        """Test Transition with response data."""
        action = Action(method="GET", endpoint="/api/items")
        transition = Transition(
            from_state="s1",
            action=action,
            to_state="s2",
            response={"items": [1, 2, 3]},
            status_code=200,
            duration_ms=150.5,
            success=True,
        )
        assert transition.response == {"items": [1, 2, 3]}
        assert transition.status_code == 200
        assert transition.duration_ms == 150.5

    def test_failed_transition(self):
        """Test a failed Transition."""
        action = Action(method="DELETE", endpoint="/api/protected")
        transition = Transition(
            from_state="s1",
            action=action,
            to_state="s1",  # Stays in same state on failure
            success=False,
            error="Unauthorized",
            status_code=401,
        )
        assert transition.success is False
        assert transition.error == "Unauthorized"

    def test_transition_equality(self):
        """Test Transition equality."""
        action = Action(method="GET", endpoint="/api/data")
        t1 = Transition(from_state="s1", action=action, to_state="s2")
        t2 = Transition(from_state="s1", action=action, to_state="s2")
        t3 = Transition(from_state="s1", action=action, to_state="s3")

        assert t1 == t2
        assert t1 != t3


class TestStateGraph:
    """Test StateGraph model - the key test for functionality."""

    def test_create_empty_graph(self):
        """Test creating an empty StateGraph."""
        graph = StateGraph()
        assert graph.states == {}
        assert graph.transitions == []
        assert graph.initial_state is None

    def test_add_state(self):
        """Test adding states to the graph."""
        graph = StateGraph()
        state1 = State(id="s1", name="Initial")
        state2 = State(id="s2", name="Logged In")

        graph.add_state(state1)
        assert "s1" in graph.states
        assert graph.initial_state == "s1"  # First state becomes initial

        graph.add_state(state2)
        assert "s2" in graph.states
        assert graph.initial_state == "s1"  # Initial doesn't change

    def test_add_transition(self):
        """Test adding transitions to the graph."""
        graph = StateGraph()
        action = Action(method="POST", endpoint="/api/login")
        transition = Transition(from_state="s1", action=action, to_state="s2")

        graph.add_transition(transition)

        # Transitions should be added
        assert len(graph.transitions) == 1
        assert graph.transitions[0] == transition

        # States should be auto-created
        assert "s1" in graph.states
        assert "s2" in graph.states

    def test_add_duplicate_transition(self):
        """Test that duplicate transitions are not added."""
        graph = StateGraph()
        action = Action(method="GET", endpoint="/api/data")
        transition = Transition(from_state="s1", action=action, to_state="s2")

        graph.add_transition(transition)
        graph.add_transition(transition)  # Add same transition again

        assert len(graph.transitions) == 1

    def test_get_neighbors(self):
        """Test getting neighbors of a state."""
        graph = StateGraph()

        # Build a simple graph: s1 -> s2 -> s3, s1 -> s3
        action1 = Action(method="GET", endpoint="/api/step1")
        action2 = Action(method="GET", endpoint="/api/step2")
        action3 = Action(method="GET", endpoint="/api/shortcut")

        graph.add_transition(Transition(from_state="s1", action=action1, to_state="s2"))
        graph.add_transition(Transition(from_state="s2", action=action2, to_state="s3"))
        graph.add_transition(Transition(from_state="s1", action=action3, to_state="s3"))

        # s1 should have neighbors s2 and s3
        neighbors_s1 = graph.get_neighbors("s1")
        assert set(neighbors_s1) == {"s2", "s3"}

        # s2 should have neighbor s3
        neighbors_s2 = graph.get_neighbors("s2")
        assert neighbors_s2 == ["s3"]

        # s3 has no outgoing transitions
        neighbors_s3 = graph.get_neighbors("s3")
        assert neighbors_s3 == []

    def test_get_transitions_from(self):
        """Test getting transitions from a state."""
        graph = StateGraph()
        action1 = Action(method="GET", endpoint="/api/a")
        action2 = Action(method="GET", endpoint="/api/b")

        t1 = Transition(from_state="s1", action=action1, to_state="s2")
        t2 = Transition(from_state="s1", action=action2, to_state="s3")
        t3 = Transition(from_state="s2", action=action1, to_state="s3")

        graph.add_transition(t1)
        graph.add_transition(t2)
        graph.add_transition(t3)

        from_s1 = graph.get_transitions_from("s1")
        assert len(from_s1) == 2
        assert t1 in from_s1
        assert t2 in from_s1

    def test_get_transitions_to(self):
        """Test getting transitions to a state."""
        graph = StateGraph()
        action1 = Action(method="GET", endpoint="/api/a")
        action2 = Action(method="GET", endpoint="/api/b")

        t1 = Transition(from_state="s1", action=action1, to_state="s3")
        t2 = Transition(from_state="s2", action=action2, to_state="s3")

        graph.add_transition(t1)
        graph.add_transition(t2)

        to_s3 = graph.get_transitions_to("s3")
        assert len(to_s3) == 2

    def test_get_state(self):
        """Test getting a state by ID."""
        graph = StateGraph()
        state = State(id="s1", name="Test State")
        graph.add_state(state)

        result = graph.get_state("s1")
        assert result == state

        result_none = graph.get_state("nonexistent")
        assert result_none is None

    def test_has_path(self):
        """Test path finding between states."""
        graph = StateGraph()

        # Build: s1 -> s2 -> s3 -> s4
        action = Action(method="GET", endpoint="/api/next")
        graph.add_transition(Transition(from_state="s1", action=action, to_state="s2"))
        graph.add_transition(Transition(from_state="s2", action=action, to_state="s3"))
        graph.add_transition(Transition(from_state="s3", action=action, to_state="s4"))

        # Path exists from s1 to s4
        assert graph.has_path("s1", "s4") is True

        # Path exists from s1 to s3
        assert graph.has_path("s1", "s3") is True

        # No path from s4 to s1 (directed graph)
        assert graph.has_path("s4", "s1") is False

        # Same state always has a path to itself
        assert graph.has_path("s1", "s1") is True

    def test_get_all_actions(self):
        """Test getting all unique actions."""
        graph = StateGraph()
        action1 = Action(method="GET", endpoint="/api/a")
        action2 = Action(method="POST", endpoint="/api/b")

        graph.add_transition(Transition(from_state="s1", action=action1, to_state="s2"))
        graph.add_transition(Transition(from_state="s2", action=action2, to_state="s3"))
        graph.add_transition(Transition(from_state="s1", action=action1, to_state="s3"))  # Duplicate action

        all_actions = graph.get_all_actions()
        assert len(all_actions) == 2
        assert action1 in all_actions
        assert action2 in all_actions

    def test_to_dict(self):
        """Test converting graph to dictionary."""
        graph = StateGraph()
        state = State(id="s1", name="Initial")
        graph.add_state(state)

        action = Action(method="GET", endpoint="/api/data")
        transition = Transition(from_state="s1", action=action, to_state="s2")
        graph.add_transition(transition)

        result = graph.to_dict()

        assert "states" in result
        assert "transitions" in result
        assert "initial_state" in result
        assert "stats" in result
        assert result["stats"]["total_states"] == 2
        assert result["stats"]["total_transitions"] == 1


class TestGraphTraversal:
    """Test complex graph traversal scenarios."""

    def test_complex_graph_traversal(self):
        """Test traversal on a more complex graph."""
        graph = StateGraph()

        # Build a diamond-shaped graph:
        #       s1
        #      /  \
        #     s2   s3
        #      \  /
        #       s4
        action = Action(method="GET", endpoint="/api/traverse")

        graph.add_transition(Transition(from_state="s1", action=action, to_state="s2"))
        graph.add_transition(Transition(from_state="s1", action=action, to_state="s3"))
        graph.add_transition(Transition(from_state="s2", action=action, to_state="s4"))
        graph.add_transition(Transition(from_state="s3", action=action, to_state="s4"))

        # Both s2 and s3 should be reachable from s1
        neighbors = graph.get_neighbors("s1")
        assert "s2" in neighbors
        assert "s3" in neighbors

        # s4 should be reachable from both s2 and s3
        assert graph.has_path("s2", "s4") is True
        assert graph.has_path("s3", "s4") is True

        # s4 should be reachable from s1
        assert graph.has_path("s1", "s4") is True

    def test_cyclic_graph(self):
        """Test graph with cycles doesn't cause infinite loops."""
        graph = StateGraph()
        action = Action(method="GET", endpoint="/api/cycle")

        # Create a cycle: s1 -> s2 -> s3 -> s1
        graph.add_transition(Transition(from_state="s1", action=action, to_state="s2"))
        graph.add_transition(Transition(from_state="s2", action=action, to_state="s3"))
        graph.add_transition(Transition(from_state="s3", action=action, to_state="s1"))

        # This should not infinite loop
        assert graph.has_path("s1", "s3") is True
        assert graph.has_path("s2", "s1") is True
        assert graph.has_path("s3", "s2") is True


class TestIssue:
    """Test Issue model."""

    def test_create_issue(self):
        """Test creating an Issue."""
        issue = Issue(
            severity=IssueSeverity.HIGH,
            state="s1",
            error="Authentication bypass detected",
            suggestion="Review access controls",
            category="security",
        )
        assert issue.severity == IssueSeverity.HIGH
        assert issue.state == "s1"
        assert issue.error == "Authentication bypass detected"


class TestCoverageReport:
    """Test CoverageReport model."""

    def test_create_coverage_report(self):
        """Test creating a CoverageReport."""
        report = CoverageReport(
            states_found=10,
            transitions_found=25,
            endpoints_discovered=15,
            endpoints_tested=12,
            coverage_percent=80.0,
        )
        assert report.states_found == 10
        assert report.coverage_percent == 80.0

        result = report.to_dict()
        assert result["states_found"] == 10


class TestExplorationResult:
    """Test ExplorationResult model."""

    def test_create_exploration_result(self):
        """Test creating a complete ExplorationResult."""
        graph = StateGraph()
        coverage = CoverageReport(states_found=5, transitions_found=10)
        now = datetime.now()

        result = ExplorationResult(
            graph=graph,
            coverage=coverage,
            duration=timedelta(seconds=30),
            started_at=now,
            finished_at=now + timedelta(seconds=30),
        )

        assert result.graph == graph
        assert result.coverage == coverage
        assert result.duration.total_seconds() == 30
        assert result.success is True

    def test_get_issues_by_severity(self):
        """Test filtering issues by severity."""
        graph = StateGraph()
        coverage = CoverageReport()
        now = datetime.now()

        issues = [
            Issue(severity=IssueSeverity.CRITICAL, error="Critical error 1"),
            Issue(severity=IssueSeverity.CRITICAL, error="Critical error 2"),
            Issue(severity=IssueSeverity.HIGH, error="High error"),
            Issue(severity=IssueSeverity.LOW, error="Low error"),
        ]

        result = ExplorationResult(
            graph=graph,
            issues=issues,
            coverage=coverage,
            duration=timedelta(seconds=10),
            started_at=now,
            finished_at=now + timedelta(seconds=10),
        )

        critical = result.get_critical_issues()
        assert len(critical) == 2

        high = result.get_issues_by_severity(IssueSeverity.HIGH)
        assert len(high) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
