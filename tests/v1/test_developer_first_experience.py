"""TDD: First-time developer experience for VenomQA.

Simulates a developer who finds a todo API, writes 4 actions and 1 invariant,
runs VenomQA, and expects a clear actionable result.

Planted bug: DELETE /todos/{id} returns 200 even when the todo is already
completed (should return 403). VenomQA should find this.

Five tests — four of them expose silent implementation bugs that were fixed
before this file was merged:
  1. test_bug_is_found                          ← baseline (should always pass)
  2. test_violation_message_is_dynamic         ← invariant returns str, not bool
  3. test_precondition_actually_gates_action   ← context guard actually guards
  4. test_no_duplicate_violations              ← dedup by (invariant, state)
  5. test_violation_has_human_readable_reproduction ← reproduction_steps list
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

import pytest

from venomqa import (
    Action,
    ActionResult,
    Agent,
    HTTPRequest,
    HTTPResponse,
    Invariant,
    Severity,
    World,
)
from venomqa.adapters.mock_http_server import MockHTTPServer
from venomqa.adapters.http import HttpClient
from venomqa.v1.core.action import precondition_has_context
from venomqa.v1.core.state import Observation

# ---------------------------------------------------------------------------
# Shared module-level state for the mock Todo server
# ---------------------------------------------------------------------------

_state: dict[str, Any] = {"todos": {}, "next_id": 1}
_lock = threading.Lock()

_PORT = 18199  # intentionally high to avoid conflicts


def _reset_state() -> None:
    with _lock:
        _state["todos"].clear()
        _state["next_id"] = 1


# ---------------------------------------------------------------------------
# HTTP handler — implements the planted bug
# ---------------------------------------------------------------------------

class _TodoHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for the todo API with a planted bug.

    Bug: DELETE /todos/{id} returns 200 even when todo["done"] is True.
    Correct behaviour: should return 403.
    """

    def log_message(self, fmt, *args):  # silence server logs in test output
        pass

    # ---- helpers -----------------------------------------------------------

    def _send_json(self, status: int, body: Any) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def _todo_id_from_path(self) -> str | None:
        parts = self.path.split("/")
        if len(parts) >= 3 and parts[1] == "todos" and parts[2]:
            return parts[2]
        return None

    # ---- GET ---------------------------------------------------------------

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/todos":
            with _lock:
                self._send_json(200, list(_state["todos"].values()))
        else:
            todo_id = self._todo_id_from_path()
            if todo_id:
                with _lock:
                    todo = _state["todos"].get(todo_id)
                if todo:
                    self._send_json(200, todo)
                else:
                    self._send_json(404, {"error": "not found"})
            else:
                self._send_json(404, {"error": "not found"})

    # ---- POST --------------------------------------------------------------

    def do_POST(self) -> None:
        if self.path == "/todos":
            body = self._read_body()
            with _lock:
                todo_id = str(_state["next_id"])
                _state["next_id"] += 1
                todo = {"id": todo_id, "title": body.get("title", ""), "done": False}
                _state["todos"][todo_id] = todo
            self._send_json(201, todo)
        else:
            self._send_json(404, {"error": "not found"})

    # ---- PATCH -------------------------------------------------------------

    def do_PATCH(self) -> None:
        todo_id = self._todo_id_from_path()
        if todo_id:
            with _lock:
                todo = _state["todos"].get(todo_id)
                if todo:
                    body = self._read_body()
                    if "done" in body:
                        todo["done"] = body["done"]
                    self._send_json(200, todo)
                else:
                    self._send_json(404, {"error": "not found"})
        else:
            self._send_json(404, {"error": "not found"})

    # ---- DELETE ------------------------------------------------------------

    def do_DELETE(self) -> None:
        todo_id = self._todo_id_from_path()
        if todo_id:
            with _lock:
                todo = _state["todos"].get(todo_id)
                if not todo:
                    self._send_json(404, {"error": "not found"})
                    return
                # BUG: should check if todo["done"] and return 403, but doesn't
                del _state["todos"][todo_id]
                self._send_json(200, {"deleted": todo_id})
        else:
            self._send_json(404, {"error": "not found"})


# ---------------------------------------------------------------------------
# MockHTTPServer subclass — checkpoint/rollback via module-level state dict
# ---------------------------------------------------------------------------

class TodoObserver(MockHTTPServer):
    def __init__(self) -> None:
        super().__init__("todo")

    @staticmethod
    def get_state_snapshot() -> dict[str, Any]:
        with _lock:
            return {
                "todos": {k: dict(v) for k, v in _state["todos"].items()},
                "next_id": _state["next_id"],
            }

    @staticmethod
    def rollback_from_snapshot(snapshot: dict[str, Any]) -> None:
        with _lock:
            _state["todos"].clear()
            _state["todos"].update(
                {k: dict(v) for k, v in snapshot["todos"].items()}
            )
            _state["next_id"] = snapshot["next_id"]

    def observe_from_state(self, state: dict[str, Any]) -> Observation:
        todos = state["todos"]
        return Observation(
            system="todo",
            data={
                "count": len(todos),
                "done_count": sum(1 for t in todos.values() if t["done"]),
                "next_id": state["next_id"],
            },
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def todo_server():
    """Start a daemon HTTP server for the todo API."""
    server = HTTPServer(("127.0.0.1", _PORT), _TodoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


@pytest.fixture(autouse=True)
def fresh_state():
    """Reset in-process state before each test."""
    _reset_state()
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_world() -> World:
    api = HttpClient(f"http://127.0.0.1:{_PORT}")
    return World(
        api=api,
        systems={"todo": TodoObserver()},
        state_from_context=["todo_id"],
    )


def _build_actions() -> list[Action]:
    def create_todo(api, context):
        resp = api.post("/todos", json={"title": "test task"})
        if resp.ok:
            context.set("todo_id", resp.json()["id"])
        return resp

    def list_todos(api, context):
        return api.get("/todos")

    def complete_todo(api, context):
        todo_id = context.get("todo_id")
        if not todo_id:
            # No todo yet — return a no-op success so exploration doesn't crash
            return ActionResult.from_response(
                request=HTTPRequest(method="PATCH", url=f"http://127.0.0.1:{_PORT}/todos/none"),
                response=HTTPResponse(status_code=404),
            )
        return api.patch(f"/todos/{todo_id}", json={"done": True})

    def delete_todo(api, context):
        todo_id = context.get("todo_id")
        if not todo_id:
            return ActionResult.from_response(
                request=HTTPRequest(method="DELETE", url=f"http://127.0.0.1:{_PORT}/todos/none"),
                response=HTTPResponse(status_code=404),
            )
        return api.delete(f"/todos/{todo_id}")

    return [
        Action(name="create_todo", execute=create_todo),
        Action(name="list_todos", execute=list_todos, max_calls=2),
        Action(
            name="complete_todo",
            execute=complete_todo,
            preconditions=[precondition_has_context("todo_id")],
        ),
        Action(
            name="delete_todo",
            execute=delete_todo,
            preconditions=[precondition_has_context("todo_id")],
        ),
    ]


def _build_invariants_dynamic() -> list[Invariant]:
    """Invariant that returns a descriptive string instead of False."""

    def completed_todo_not_deletable(world) -> bool | str:
        last = world.last_action_result
        if last is None:
            return True
        if not hasattr(last, "request") or last.request is None:
            return True
        if last.request.method != "DELETE":
            return True

        # Check if any completed todo was just deleted successfully
        snap = TodoObserver.get_state_snapshot()
        todo_id = world.context.get("todo_id")
        if todo_id is None:
            return True

        # The todo was just deleted — check if it WAS completed before deletion
        # We can't read it from state now (already gone), but we can check the
        # response: if status 200 and request was DELETE /todos/{id}, check if
        # the todo was done at the time (the server deleted it unconditionally).
        # Use status_code as proxy: if 200, bug may have fired.
        if last.status_code == 200:
            # We need to check if the todo was marked done before this DELETE.
            # Since it's already gone, we rely on context tracking done state.
            was_done = world.context.get("todo_was_done")
            if was_done:
                return (
                    f"DELETE /todos/{todo_id} returned 200 but todo was completed "
                    f"(expected 403). Sequence triggered the bug."
                )
        return True

    return [
        Invariant(
            name="completed_todo_not_deletable",
            check=completed_todo_not_deletable,
            message="completed todos can't be deleted",
            severity=Severity.HIGH,
        )
    ]


def _build_invariants_simple() -> list[Invariant]:
    """Invariant that tracks done state via context and returns bool."""

    def completed_todo_not_deletable(world) -> bool | str:
        last = world.last_action_result
        if last is None:
            return True
        if not hasattr(last, "request") or last.request is None:
            return True
        if last.request.method != "DELETE":
            return True
        if last.status_code != 200:
            return True

        todo_id = world.context.get("todo_id")
        was_done = world.context.get("todo_was_done")
        if was_done:
            return (
                f"DELETE /todos/{todo_id} returned 200 but todo was completed "
                f"(expected 403). Sequence triggered the bug."
            )
        return True

    return [
        Invariant(
            name="completed_todo_not_deletable",
            check=completed_todo_not_deletable,
            message="completed todos can't be deleted",
            severity=Severity.HIGH,
        )
    ]


def _build_actions_with_done_tracking() -> list[Action]:
    """Actions that track done state for invariant checking."""

    def create_todo(api, context):
        resp = api.post("/todos", json={"title": "test task"})
        if resp.ok:
            context.set("todo_id", resp.json()["id"])
            context.set("todo_was_done", False)
        return resp

    def list_todos(api, context):
        return api.get("/todos")

    def complete_todo(api, context):
        todo_id = context.get("todo_id")
        if not todo_id:
            return ActionResult.from_response(
                request=HTTPRequest(method="PATCH", url=f"http://127.0.0.1:{_PORT}/todos/none"),
                response=HTTPResponse(status_code=404),
            )
        resp = api.patch(f"/todos/{todo_id}", json={"done": True})
        if resp.ok:
            context.set("todo_was_done", True)
        return resp

    def delete_todo(api, context):
        todo_id = context.get("todo_id")
        if not todo_id:
            return ActionResult.from_response(
                request=HTTPRequest(method="DELETE", url=f"http://127.0.0.1:{_PORT}/todos/none"),
                response=HTTPResponse(status_code=404),
            )
        return api.delete(f"/todos/{todo_id}")

    return [
        Action(name="create_todo", execute=create_todo),
        Action(name="list_todos", execute=list_todos, max_calls=2),
        Action(
            name="complete_todo",
            execute=complete_todo,
            preconditions=[precondition_has_context("todo_id")],
        ),
        Action(
            name="delete_todo",
            execute=delete_todo,
            preconditions=[precondition_has_context("todo_id")],
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bug_is_found(todo_server):
    """Baseline: VenomQA finds the planted DELETE bug via exploration."""
    world = _build_world()
    actions = _build_actions_with_done_tracking()
    invariants = _build_invariants_simple()

    agent = Agent(world=world, actions=actions, invariants=invariants, max_steps=30)
    result = agent.explore()

    assert len(result.violations) > 0, (
        "VenomQA should have found the DELETE-on-completed-todo bug. "
        f"States visited: {len(result.graph.states)}, "
        f"Transitions: {len(result.graph.transitions)}"
    )
    violation = result.violations[0]
    assert violation.invariant_name == "completed_todo_not_deletable"


def test_violation_message_is_dynamic(todo_server):
    """Invariant returning a string should produce that string as violation.message.

    Previously Violation.create() always used invariant.message (static string),
    ignoring any diagnostic string returned by the check function.
    """
    world = _build_world()
    actions = _build_actions_with_done_tracking()
    invariants = _build_invariants_simple()

    agent = Agent(world=world, actions=actions, invariants=invariants, max_steps=30)
    result = agent.explore()

    assert len(result.violations) > 0, "No violations found — bug not triggered"
    violation = result.violations[0]

    # The dynamic message should contain diagnostic detail, not the static fallback
    assert "403" in violation.message or "completed" in violation.message, (
        f"Expected dynamic message with diagnostic detail, got: {violation.message!r}. "
        "Static fallback was: 'completed todos can\\'t be deleted'"
    )
    assert violation.message != "completed todos can't be deleted", (
        "violation.message is the static invariant.message — "
        "dynamic string returned by check() was not captured"
    )


def test_precondition_actually_gates_action(todo_server):
    """Actions with precondition_has_context() must not fire from initial state.

    Previously graph.get_unexplored() passed no context to preconditions, and the
    Agent never re-checked context before executing — so guarded actions ran
    before context was populated.
    """
    world = _build_world()

    executed_before_create = []

    def spy_complete_todo(api, context):
        todo_id = context.get("todo_id")
        executed_before_create.append(todo_id)  # record for assertion
        if not todo_id:
            return ActionResult.from_response(
                request=HTTPRequest(method="PATCH", url=f"http://127.0.0.1:{_PORT}/todos/none"),
                response=HTTPResponse(status_code=404),
            )
        return api.patch(f"/todos/{todo_id}", json={"done": True})

    def create_todo(api, context):
        resp = api.post("/todos", json={"title": "test"})
        if resp.ok:
            context.set("todo_id", resp.json()["id"])
        return resp

    def list_todos(api, context):
        return api.get("/todos")

    actions = [
        Action(name="create_todo", execute=create_todo),
        Action(name="list_todos", execute=list_todos, max_calls=2),
        Action(
            name="complete_todo",
            execute=spy_complete_todo,
            preconditions=[precondition_has_context("todo_id")],
        ),
    ]

    agent = Agent(world=world, actions=actions, max_steps=20)
    agent.explore()

    # complete_todo must NEVER have been called with todo_id=None
    assert all(tid is not None for tid in executed_before_create), (
        "complete_todo was executed before create_todo set todo_id in context. "
        "Precondition guard did not work. "
        f"Calls with todo_id=None: {[t for t in executed_before_create if t is None]}"
    )


def test_no_duplicate_violations(todo_server):
    """The same (invariant, state) pair should produce exactly one violation entry.

    Previously there was no dedup — the same bug could be reported dozens of
    times as BFS explored different paths to the same state.
    """
    world = _build_world()
    actions = _build_actions_with_done_tracking()
    invariants = _build_invariants_simple()

    agent = Agent(world=world, actions=actions, invariants=invariants, max_steps=50)
    result = agent.explore()

    assert len(result.violations) > 0, "Bug was not found — cannot test dedup"

    # Count violations by (invariant_name, state_id)
    seen = set()
    duplicates = []
    for v in result.violations:
        key = (v.invariant_name, v.state.id)
        if key in seen:
            duplicates.append(key)
        seen.add(key)

    assert len(duplicates) == 0, (
        f"Found {len(duplicates)} duplicate violation(s) for the same (invariant, state): "
        f"{duplicates[:3]}"
    )


def test_violation_has_human_readable_reproduction(todo_server):
    """violation.reproduction_steps should be a list of human-readable strings.

    Previously violation.reproduction_path was a list[Transition] with no
    human-readable form. reproduction_steps should look like:
      ['POST /todos {"title": "test task"}', 'PATCH /todos/1 {"done": true}', 'DELETE /todos/1']
    """
    world = _build_world()
    actions = _build_actions_with_done_tracking()
    invariants = _build_invariants_simple()

    agent = Agent(world=world, actions=actions, invariants=invariants, max_steps=30)
    result = agent.explore()

    assert len(result.violations) > 0, "Bug was not found — cannot test reproduction steps"
    violation = result.violations[0]

    steps = violation.reproduction_steps
    assert isinstance(steps, list), f"reproduction_steps should be a list, got {type(steps)}"
    assert len(steps) > 0, "reproduction_steps should not be empty"

    for step in steps:
        assert isinstance(step, str), f"Each step should be a string, got {type(step)}: {step!r}"

    # At least one step should start with an HTTP method
    http_methods = {"GET", "POST", "PATCH", "PUT", "DELETE"}
    has_http_step = any(
        any(step.startswith(m) for m in http_methods)
        for step in steps
    )
    assert has_http_step, (
        f"Expected at least one step starting with an HTTP method. "
        f"Steps: {steps}"
    )

    # The DELETE step should be present (it's the buggy action)
    has_delete = any("DELETE" in step for step in steps)
    assert has_delete, (
        f"Expected a DELETE step in reproduction path. Steps: {steps}"
    )
