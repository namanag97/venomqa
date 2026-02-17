"""Tests for user-feedback-driven features:
  - Violation deduplication (unique_violations)
  - World teardown hook
  - World state_from_context
  - scaffold URL support (mocked)
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from venomqa.v1.core.action import Action, ActionResult, HTTPRequest, HTTPResponse
from venomqa.v1.core.context import Context
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Invariant, Severity, Violation
from venomqa.v1.core.result import ExplorationResult
from venomqa.v1.core.state import Observation, State
from venomqa.v1.core.transition import Transition
from venomqa.v1.world import World


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_state(label: str = "s") -> State:
    return State.create(observations={label: Observation(system=label, data={"v": label})})


def _make_action(name: str = "act") -> Action:
    return Action(name=name, execute=lambda api: None)


def _make_ar() -> ActionResult:
    req = HTTPRequest(method="POST", url="/test")
    resp = HTTPResponse(status_code=409, body={"error": "conflict"})
    return ActionResult.from_response(req, resp)


def _make_transition(from_id: str, to_id: str, action_name: str) -> Transition:
    req = HTTPRequest(method="GET", url="/")
    resp = HTTPResponse(status_code=200, body={})
    return Transition.create(
        from_state_id=from_id,
        action_name=action_name,
        to_state_id=to_id,
        result=ActionResult.from_response(req, resp),
    )


def _make_violation(
    invariant_name: str = "inv",
    action_name: str = "act",
    path_len: int = 1,
) -> Violation:
    s = _make_state()
    a = _make_action(action_name)
    path = [_make_transition(f"s{i}", f"s{i+1}", action_name) for i in range(path_len)]
    return Violation(
        id=f"v_{invariant_name}_{path_len}",
        invariant_name=invariant_name,
        state=s,
        message="test violation",
        severity=Severity.HIGH,
        action=a,
        reproduction_path=path,
        timestamp=datetime.now(),
    )


def _make_result(violations: list[Violation]) -> ExplorationResult:
    graph = Graph([])
    r = ExplorationResult(graph=graph, violations=violations)
    r.finish()
    return r


def _make_mock_api() -> MagicMock:
    api = MagicMock()
    api.base_url = "http://test"
    api.timeout = 30.0
    api.default_headers = {}
    return api


def _make_mock_system(data: dict | None = None) -> MagicMock:
    s = MagicMock()
    s.checkpoint.return_value = "cp"
    s.observe.return_value = Observation(system="mock", data=data or {"v": 0})
    return s


# ─── Violation deduplication ─────────────────────────────────────────────────

class TestUniqueViolations:

    def test_no_violations_returns_empty(self):
        result = _make_result([])
        assert result.unique_violations == []

    def test_single_violation_returned_unchanged(self):
        v = _make_violation()
        result = _make_result([v])
        assert result.unique_violations == [v]

    def test_deduplicates_same_invariant_and_action(self):
        # Same root cause, different path lengths
        v_long = _make_violation("inv", "act", path_len=5)
        v_short = _make_violation("inv", "act", path_len=1)
        result = _make_result([v_long, v_short])
        unique = result.unique_violations
        assert len(unique) == 1
        assert unique[0] is v_short  # shortest path wins

    def test_different_invariants_both_kept(self):
        v1 = _make_violation("inv_a", "act", path_len=2)
        v2 = _make_violation("inv_b", "act", path_len=2)
        result = _make_result([v1, v2])
        assert len(result.unique_violations) == 2

    def test_different_actions_both_kept(self):
        v1 = _make_violation("inv", "act_a", path_len=2)
        v2 = _make_violation("inv", "act_b", path_len=2)
        result = _make_result([v1, v2])
        assert len(result.unique_violations) == 2

    def test_49_same_cause_returns_1(self):
        violations = [_make_violation("same_inv", "same_act", path_len=i + 1) for i in range(49)]
        result = _make_result(violations)
        unique = result.unique_violations
        assert len(unique) == 1
        assert len(unique[0].reproduction_path) == 1  # shortest

    def test_summary_includes_unique_violations_count(self):
        v_long = _make_violation("inv", "act", path_len=5)
        v_short = _make_violation("inv", "act", path_len=1)
        result = _make_result([v_long, v_short])
        s = result.summary()
        assert s["violations"] == 2
        assert s["unique_violations"] == 1

    def test_sorted_critical_before_high(self):
        high_v = _make_violation("high_inv", "act_h", path_len=1)
        critical_v = Violation(
            id="v_crit",
            invariant_name="crit_inv",
            state=_make_state(),
            message="critical",
            severity=Severity.CRITICAL,
            action=_make_action("act_c"),
            reproduction_path=[],
            timestamp=datetime.now(),
        )
        result = _make_result([high_v, critical_v])
        unique = result.unique_violations
        assert unique[0].severity == Severity.CRITICAL


# ─── Console reporter with dedup ─────────────────────────────────────────────

class TestConsoleReporterDedup:

    def _report(self, result: ExplorationResult) -> str:
        import io
        from venomqa.v1.reporters.console import ConsoleReporter
        buf = io.StringIO()
        ConsoleReporter(color=False, file=buf).report(result)
        return buf.getvalue()

    def test_shows_total_and_unique_count(self):
        violations = [_make_violation("inv", "act", path_len=i + 1) for i in range(5)]
        result = _make_result(violations)
        out = self._report(result)
        assert "5 total" in out
        assert "1 unique root cause" in out

    def test_shows_x_count_annotation(self):
        violations = [_make_violation("inv", "act", path_len=i + 1) for i in range(3)]
        result = _make_result(violations)
        out = self._report(result)
        assert "(x3 total)" in out

    def test_no_annotation_when_count_is_1(self):
        result = _make_result([_make_violation("inv", "act")])
        out = self._report(result)
        assert "(x1 total)" not in out


# ─── JSON reporter unique_violations ─────────────────────────────────────────

class TestJSONReporterUniqueViolations:

    def test_unique_violations_key_present(self):
        import json
        from venomqa.v1.reporters.json import JSONReporter
        violations = [_make_violation("inv", "act", path_len=i + 1) for i in range(5)]
        result = _make_result(violations)
        data = json.loads(JSONReporter().report(result))
        assert "unique_violations" in data
        assert len(data["violations"]) == 5
        assert len(data["unique_violations"]) == 1


# ─── Teardown hook ───────────────────────────────────────────────────────────

class TestWorldTeardown:

    def test_teardown_called_after_explore(self):
        from venomqa.v1 import Agent, BFS

        called: list[tuple] = []

        def cleanup(api, context):
            called.append((api, context))

        api = _make_mock_api()
        world = World(api=api, teardown=cleanup, state_from_context=[])

        def noop_action(api, context):
            req = HTTPRequest(method="GET", url="/")
            resp = HTTPResponse(status_code=200, body={})
            return ActionResult.from_response(req, resp)

        agent = Agent(
            world=world,
            actions=[Action(name="noop", execute=noop_action)],
            strategy=BFS(),
            max_steps=2,
        )
        agent.explore()
        assert len(called) == 1, "teardown must be called exactly once"

    def test_teardown_receives_api_and_context(self):
        from venomqa.v1 import Agent, BFS

        received: list[dict] = []

        def cleanup(api, context):
            received.append({"api": api, "context": context})

        api = _make_mock_api()
        world = World(api=api, teardown=cleanup, state_from_context=[])

        def set_key(a, ctx):
            ctx.set("x", 42)
            req = HTTPRequest(method="GET", url="/")
            resp = HTTPResponse(status_code=200, body={})
            return ActionResult.from_response(req, resp)

        agent = Agent(
            world=world,
            actions=[Action(name="set", execute=set_key)],
            strategy=BFS(),
            max_steps=3,
        )
        agent.explore()
        assert received[0]["api"] is api

    def test_teardown_none_by_default(self):
        api = _make_mock_api()
        world = World(api=api, state_from_context=[])
        world.run_teardown()  # must not raise

    def test_teardown_errors_do_not_crash_explore(self):
        from venomqa.v1 import Agent, BFS

        def bad_cleanup(api, context):
            raise RuntimeError("cleanup error")

        api = _make_mock_api()
        world = World(api=api, teardown=bad_cleanup)

        def noop(api, ctx):
            req = HTTPRequest(method="GET", url="/")
            resp = HTTPResponse(status_code=200, body={})
            return ActionResult.from_response(req, resp)

        agent = Agent(
            world=world,
            actions=[Action(name="noop", execute=noop)],
            strategy=BFS(),
            max_steps=2,
        )
        # Must not raise despite teardown failure
        result = agent.explore()
        assert result is not None


# ─── state_from_context ───────────────────────────────────────────────────────

class TestStateFromContext:

    def _make_world_with_context_state(self, keys: list[str]) -> World:
        api = _make_mock_api()
        return World(api=api, state_from_context=keys)

    def test_observe_includes_ctx_observation(self):
        world = self._make_world_with_context_state(["user_id"])
        world.context.set("user_id", 123)
        state = world.observe()
        assert "_ctx" in state.observations
        assert state.observations["_ctx"].data["user_id"] == 123

    def test_different_context_values_produce_different_states(self):
        world = self._make_world_with_context_state(["user_id"])
        world.context.set("user_id", 1)
        s1 = world.observe()
        world.context.set("user_id", 2)
        s2 = world.observe()
        assert s1.id != s2.id

    def test_same_context_values_same_state_id(self):
        world = self._make_world_with_context_state(["user_id"])
        world.context.set("user_id", 42)
        s1 = world.observe()
        s2 = world.observe()
        assert s1.id == s2.id

    def test_none_key_included_in_hash(self):
        world = self._make_world_with_context_state(["missing_key"])
        state = world.observe()
        assert "_ctx" in state.observations
        assert state.observations["_ctx"].data["missing_key"] is None

    def test_no_ctx_observation_when_not_configured(self):
        api = _make_mock_api()
        world = World(api=api, state_from_context=[])
        state = world.observe()
        assert "_ctx" not in state.observations

    def test_states_visited_gt_1_without_db_adapter(self):
        """Core use case: get states_visited > 1 from pure HTTP responses."""
        from venomqa.v1 import Agent, BFS

        api = _make_mock_api()
        world = World(api=api, state_from_context=["item_id"])

        _counter = [0]

        def create_item(a, ctx):
            _counter[0] += 1
            ctx.set("item_id", _counter[0])
            req = HTTPRequest(method="POST", url="/items")
            resp = HTTPResponse(status_code=201, body={"id": _counter[0]})
            return ActionResult.from_response(req, resp)

        def list_items(a, ctx):
            req = HTTPRequest(method="GET", url="/items")
            resp = HTTPResponse(status_code=200, body=[])
            return ActionResult.from_response(req, resp)

        agent = Agent(
            world=world,
            actions=[
                Action(name="create_item", execute=create_item),
                Action(name="list_items", execute=list_items),
            ],
            strategy=BFS(),
            max_steps=10,
        )
        result = agent.explore()
        assert result.states_visited > 1, (
            "state_from_context must cause states_visited > 1 when context keys change"
        )

    def test_no_systems_warning_suppressed_with_state_from_context(self):
        """state_from_context suppresses the 'no systems registered' warning."""
        import warnings
        from venomqa.v1 import Agent, BFS

        api = _make_mock_api()
        world = World(api=api, state_from_context=["x"])

        def noop(a, ctx):
            req = HTTPRequest(method="GET", url="/")
            resp = HTTPResponse(status_code=200, body={})
            return ActionResult.from_response(req, resp)

        agent = Agent(
            world=world,
            actions=[Action(name="noop", execute=noop)],
            strategy=BFS(),
            max_steps=2,
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agent.explore()

        no_sys_warnings = [w for w in caught if "No systems registered" in str(w.message)]
        assert no_sys_warnings == [], "warning should be suppressed when state_from_context is set"


# ─── scaffold URL support ────────────────────────────────────────────────────

class TestScaffoldURLSupport:

    def test_raises_value_error_on_connection_failure(self):
        from venomqa.v1.cli.scaffold import load_spec
        with pytest.raises(ValueError, match="Could not fetch spec"):
            load_spec("http://localhost:19999/openapi.json")  # nothing listening here

    def test_loads_json_from_url(self):
        from venomqa.v1.cli.scaffold import load_spec

        fake_spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {"/x": {"get": {"responses": {"200": {"description": "OK"}}}}},
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_spec
        mock_resp.raise_for_status.return_value = None

        with patch("httpx.get", return_value=mock_resp):
            spec = load_spec("http://localhost:8000/openapi.json")

        assert spec["openapi"] == "3.0.0"
        assert "/x" in spec["paths"]
