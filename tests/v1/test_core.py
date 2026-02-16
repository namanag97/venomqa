"""Unit tests for core data objects."""

import pytest
from datetime import datetime

from venomqa.v1.core.state import State, Observation
from venomqa.v1.core.action import Action, ActionResult, HTTPRequest, HTTPResponse
from venomqa.v1.core.transition import Transition
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Invariant, Violation, Severity
from venomqa.v1.core.result import ExplorationResult


class TestObservation:
    def test_create(self):
        obs = Observation(
            system="db",
            data={"users": 5, "orders": 3},
        )
        assert obs.system == "db"
        assert obs.data["users"] == 5

    def test_get(self):
        obs = Observation(system="db", data={"count": 10})
        assert obs.get("count") == 10
        assert obs.get("missing", "default") == "default"

    def test_getitem(self):
        obs = Observation(system="db", data={"key": "value"})
        assert obs["key"] == "value"

    def test_frozen(self):
        obs = Observation(system="db", data={})
        with pytest.raises(Exception):  # FrozenInstanceError
            obs.system = "cache"


class TestState:
    def test_create(self):
        obs = Observation(system="db", data={"count": 1})
        state = State.create(observations={"db": obs})
        assert state.id.startswith("s_")
        assert "db" in state.observations

    def test_get_observation(self):
        obs = Observation(system="db", data={})
        state = State.create(observations={"db": obs})
        assert state.get_observation("db") == obs
        assert state.get_observation("missing") is None

    def test_equality(self):
        state1 = State(id="s_123", observations={})
        state2 = State(id="s_123", observations={})
        state3 = State(id="s_456", observations={})
        assert state1 == state2
        assert state1 != state3

    def test_hashable(self):
        state = State(id="s_123", observations={})
        s = {state}
        assert state in s


class TestAction:
    def test_create(self):
        action = Action(
            name="login",
            execute=lambda api: ActionResult(success=True, request=HTTPRequest("POST", "/login")),
            description="Log in",
            tags=["auth"],
        )
        assert action.name == "login"
        assert action.description == "Log in"

    def test_can_execute_no_preconditions(self):
        action = Action(name="test", execute=lambda api: None)
        state = State.create(observations={})
        assert action.can_execute(state)

    def test_can_execute_with_preconditions(self):
        obs = Observation(system="db", data={"logged_in": True})
        state = State.create(observations={"db": obs})

        action = Action(
            name="checkout",
            execute=lambda api: None,
            preconditions=[
                lambda s: s.observations.get("db", Observation("", {})).data.get("logged_in", False)
            ],
        )
        assert action.can_execute(state)

    def test_equality(self):
        action1 = Action(name="login", execute=lambda api: None)
        action2 = Action(name="login", execute=lambda api: None)
        action3 = Action(name="logout", execute=lambda api: None)
        assert action1 == action2
        assert action1 != action3


class TestActionResult:
    def test_from_response(self):
        request = HTTPRequest("GET", "/users")
        response = HTTPResponse(status_code=200, body={"users": []})
        result = ActionResult.from_response(request, response, duration_ms=50.0)
        assert result.success
        assert result.duration_ms == 50.0

    def test_from_error(self):
        request = HTTPRequest("GET", "/users")
        result = ActionResult.from_error(request, "Connection refused")
        assert not result.success
        assert result.error == "Connection refused"


class TestTransition:
    def test_create(self):
        result = ActionResult(success=True, request=HTTPRequest("GET", "/"))
        transition = Transition.create(
            from_state_id="s_1",
            action_name="login",
            to_state_id="s_2",
            result=result,
        )
        assert transition.id.startswith("t_")
        assert transition.from_state_id == "s_1"
        assert transition.to_state_id == "s_2"


class TestGraph:
    def test_add_state(self):
        graph = Graph()
        state = State.create(observations={})
        graph.add_state(state)
        assert graph.state_count == 1
        assert graph.initial_state_id == state.id

    def test_add_action(self):
        action = Action(name="test", execute=lambda api: None)
        graph = Graph([action])
        assert graph.action_count == 1
        assert graph.get_action("test") == action

    def test_add_transition(self):
        graph = Graph()
        result = ActionResult(success=True, request=HTTPRequest("GET", "/"))
        transition = Transition.create("s_1", "action", "s_2", result)
        graph.add_transition(transition)
        assert graph.transition_count == 1
        assert graph.is_explored("s_1", "action")

    def test_get_valid_actions(self):
        action1 = Action(name="a1", execute=lambda api: None)
        action2 = Action(name="a2", execute=lambda api: None, preconditions=[lambda s: False])
        graph = Graph([action1, action2])

        state = State.create(observations={})
        valid = graph.get_valid_actions(state)
        assert len(valid) == 1
        assert valid[0].name == "a1"

    def test_get_unexplored(self):
        action = Action(name="test", execute=lambda api: None)
        graph = Graph([action])

        state = State.create(observations={})
        graph.add_state(state)

        unexplored = graph.get_unexplored()
        assert len(unexplored) == 1
        assert unexplored[0] == (state, action)

    def test_get_path_to(self):
        graph = Graph()
        s1 = State(id="s_1", observations={})
        s2 = State(id="s_2", observations={})
        s3 = State(id="s_3", observations={})
        graph.add_state(s1)
        graph.add_state(s2)
        graph.add_state(s3)

        result = ActionResult(success=True, request=HTTPRequest("GET", "/"))
        t1 = Transition(id="t_1", from_state_id="s_1", action_name="a", to_state_id="s_2", result=result)
        t2 = Transition(id="t_2", from_state_id="s_2", action_name="b", to_state_id="s_3", result=result)
        graph.add_transition(t1)
        graph.add_transition(t2)

        path = graph.get_path_to("s_3")
        assert len(path) == 2
        assert path[0].id == "t_1"
        assert path[1].id == "t_2"


class TestInvariant:
    def test_create(self):
        inv = Invariant(
            name="test_inv",
            check=lambda world: True,
            message="Test message",
            severity=Severity.HIGH,
        )
        assert inv.name == "test_inv"
        assert inv.severity == Severity.HIGH


class TestViolation:
    def test_create(self):
        inv = Invariant(name="test", check=lambda w: False, message="Failed", severity=Severity.CRITICAL)
        state = State.create(observations={})
        violation = Violation.create(inv, state)
        assert violation.id.startswith("v_")
        assert violation.is_critical


class TestExplorationResult:
    def test_empty(self):
        graph = Graph()
        result = ExplorationResult(graph=graph)
        assert result.success
        assert result.states_visited == 0

    def test_with_violations(self):
        graph = Graph()
        inv = Invariant(name="test", check=lambda w: False, severity=Severity.HIGH)
        state = State.create(observations={})
        violation = Violation.create(inv, state)

        result = ExplorationResult(graph=graph, violations=[violation])
        assert not result.success
        assert len(result.high_violations) == 1

    def test_summary(self):
        graph = Graph()
        result = ExplorationResult(graph=graph)
        result.finish()
        summary = result.summary()
        assert "states_visited" in summary
        assert "success" in summary
