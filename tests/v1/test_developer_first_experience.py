"""TDD script: what a first-time developer SHOULD experience using VenomQA.

All tests here describe DESIRED behaviour. Some fail until the implementation
is fixed. They model a developer who:
  1. Has a simple Todo API with one planted bug
  2. Writes 3 actions + 1 invariant
  3. Runs VenomQA
  4. Expects clear, actionable output

Planted bug in the mock:
  DELETE /todos/{id} returns 200 even when the todo is already completed.
  It should return 403 (Forbidden).

Sequence that triggers it:
  POST /todos  →  PATCH /todos/{id} (mark done)  →  DELETE /todos/{id}
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

import pytest

from venomqa import Action, Agent, Invariant, Severity, World
from venomqa.adapters.http import HttpClient
from venomqa.adapters.mock_http_server import MockHTTPServer
from venomqa.core.action import precondition_has_context

# ─────────────────────────────────────────────────────────────────────────────
# Inline mock Todo API
# Module-level state so MockHTTPServer can snapshot/rollback it directly.
# ─────────────────────────────────────────────────────────────────────────────

_state: dict[str, Any] = {"todos": {}, "next_id": 1}
_lock = threading.Lock()


def _reset_state() -> None:
    with _lock:
        _state["todos"].clear()
        _state["next_id"] = 1


class _TodoHandler(BaseHTTPRequestHandler):
    """HTTP handler for the inline mock Todo API.

    Implements one planted bug:
      DELETE /todos/{id}  returns 200 even when the todo is completed.
      Correct behaviour would be 403 Forbidden.
    """

    def log_message(self, *_: Any) -> None:
        pass  # silence server logs in test output

    # ── helpers ──────────────────────────────────────────────────────────────

    def _send_json(self, status: int, body: Any) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw) if raw else {}

    def _todo_id_from_path(self) -> int | None:
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "todos":
            try:
                return int(parts[1])
            except ValueError:
                return None
        return None

    # ── routes ───────────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/todos":
            with _lock:
                todos = list(_state["todos"].values())
            self._send_json(200, todos)
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/todos":
            body = self._read_json()
            with _lock:
                tid = _state["next_id"]
                _state["next_id"] += 1
                todo = {"id": tid, "title": body.get("title", ""), "done": False}
                _state["todos"][str(tid)] = todo
            self._send_json(201, todo)
        else:
            self._send_json(404, {"error": "not found"})

    def do_PATCH(self) -> None:
        tid = self._todo_id_from_path()
        if tid is None:
            self._send_json(404, {"error": "not found"})
            return
        body = self._read_json()
        with _lock:
            todo = _state["todos"].get(str(tid))
            if todo is None:
                self._send_json(404, {"error": "not found"})
                return
            if "done" in body:
                todo["done"] = body["done"]
            self._send_json(200, todo)

    def do_DELETE(self) -> None:
        tid = self._todo_id_from_path()
        if tid is None:
            self._send_json(404, {"error": "not found"})
            return

        with _lock:
            todo = _state["todos"].get(str(tid))
            if todo is None:
                self._send_json(404, {"error": "not found"})
                return

            # ── PLANTED BUG ─────────────────────────────────────────────────
            # A completed todo should NOT be deletable (403 Forbidden).
            # This server incorrectly returns 200 for completed todos too.
            # Correct code would be:
            #   if todo["done"]:
            #       self._send_json(403, {"error": "cannot delete completed todo"})
            #       return
            del _state["todos"][str(tid)]
            self._send_json(200, {"deleted": tid})


class TodoObserver(MockHTTPServer):
    """VenomQA state observer for the inline Todo API.

    Implements MockHTTPServer so VenomQA can snapshot/rollback state directly
    without making HTTP calls — enabling true branching exploration.
    """

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

    def observe_from_state(self, state: dict[str, Any]) -> Any:
        from venomqa.v1.core.state import Observation

        todos = state["todos"]
        return Observation(
            system="todo",
            data={
                "count": len(todos),
                "done_count": sum(1 for t in todos.values() if t["done"]),
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# Server lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


_SERVER_PORT: int = _free_port()
_server: HTTPServer | None = None


def _start_server() -> None:
    global _server
    _server = HTTPServer(("127.0.0.1", _SERVER_PORT), _TodoHandler)
    t = threading.Thread(target=_server.serve_forever, daemon=True)
    t.start()


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _world() -> World:
    api = HttpClient(f"http://127.0.0.1:{_SERVER_PORT}")
    return World(api=api, systems={"todo": TodoObserver()})


def _actions() -> list[Action]:
    def create_todo(api: Any, context: Any) -> Any:
        resp = api.post("/todos", json={"title": "test task"})
        resp.expect_status(201)
        context.set("todo_id", resp.json()["id"])
        context.set("todo_was_done", False)  # reset completion flag on new todo
        return resp

    def complete_todo(api: Any, context: Any) -> Any:
        todo_id = context.get("todo_id")
        resp = api.patch(f"/todos/{todo_id}", json={"done": True})
        if resp.ok:
            # Record in context so invariants and subsequent actions can see it.
            # Context is checkpointed with state, so rollback to THIS state
            # restores todo_was_done=True — enabling the invariant check on
            # any later delete from this point in the exploration graph.
            context.set("todo_was_done", True)
        return resp

    def delete_todo(api: Any, context: Any) -> Any:
        todo_id = context.get("todo_id")
        return api.delete(f"/todos/{todo_id}")

    return [
        Action(name="create_todo", execute=create_todo, max_calls=2),
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


def _invariants() -> list[Invariant]:
    def completed_todo_not_deletable(world: Any) -> Any:
        """Invariants can return a string to give a dynamic failure message.

        Returns True  → no violation.
        Returns False → violation with the static invariant.message.
        Returns str   → violation with that string as the message (actual values).
        """
        last = world.last_action_result
        if last is None or last.request.method != "DELETE":
            return True
        if last.status_code == 404:
            return True  # todo didn't exist — not a violation

        todo_id = world.context.get("todo_id")
        if todo_id is None:
            return True

        # todo_was_done is set by complete_todo action and captured in the
        # checkpoint for that state. Rolling back to a post-complete state
        # restores this flag, so the invariant correctly detects the sequence:
        #   create_todo → complete_todo → delete_todo
        was_done = world.context.get("todo_was_done", False)
        if was_done and last.status_code == 200:
            return (
                f"DELETE /todos/{todo_id} returned {last.status_code} "
                f"but todo was marked as completed — expected 403 Forbidden. "
                f"Sequence: create → complete → delete triggered the planted bug."
            )
        return True

    return [
        Invariant(
            name="completed_todo_not_deletable",
            check=completed_todo_not_deletable,
            message="Completed todos must not be deletable (expected 403 Forbidden)",
            severity=Severity.CRITICAL,
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def todo_server() -> None:
    """Start the inline Todo server once for the whole module."""
    _start_server()


@pytest.fixture(autouse=True)
def fresh_state() -> None:
    """Reset server state between tests so tests are independent."""
    _reset_state()


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_bug_is_found() -> None:
    """VenomQA must find the planted bug: delete of completed todo returns 200.

    This is the foundational test — the full pipeline works.
    """
    from venomqa import BFS

    world = _world()
    agent = Agent(
        world=world,
        actions=_actions(),
        invariants=_invariants(),
        strategy=BFS(),
        max_steps=50,
    )
    result = agent.explore()

    critical = [v for v in result.violations if v.severity == Severity.CRITICAL]
    assert len(critical) >= 1, (
        f"Expected at least one CRITICAL violation but found none.\n"
        f"States visited: {result.states_visited}\n"
        f"Transitions taken: {result.transitions_taken}\n"
        f"All violations: {[v.invariant_name for v in result.violations]}"
    )
    assert any(
        "completed_todo_not_deletable" in v.invariant_name for v in critical
    ), f"Expected 'completed_todo_not_deletable' violation, got: {[v.invariant_name for v in critical]}"


def test_violation_message_is_dynamic() -> None:
    """When an invariant returns a string, that string becomes the violation message.

    This allows invariants to describe what actually went wrong (actual values,
    status codes, sequences) rather than showing a static pre-written description.

    CURRENTLY FAILS: Violation.create() ignores the return value and always uses
    invariant.message (the static field). Needs invariant check to support bool|str.
    """
    from venomqa import BFS

    world = _world()
    agent = Agent(
        world=world,
        actions=_actions(),
        invariants=_invariants(),
        strategy=BFS(),
        max_steps=50,
    )
    result = agent.explore()

    critical = [
        v for v in result.violations
        if v.invariant_name == "completed_todo_not_deletable"
    ]
    assert critical, "Expected at least one critical violation to be found"

    violation = critical[0]
    # The dynamic message must mention the actual status code (200) and the
    # expected behaviour (403). A static message like "Completed todos must not
    # be deletable (expected 403 Forbidden)" does NOT contain "200".
    assert "200" in violation.message, (
        f"Violation message should contain the actual status code '200' but got:\n"
        f"  '{violation.message}'\n"
        f"The invariant returned a dynamic string with the actual values. "
        f"The framework must capture that string as the violation message."
    )
    assert "403" in violation.message, (
        f"Violation message should mention the expected status '403'.\n"
        f"Got: '{violation.message}'"
    )


def test_precondition_actually_gates_action() -> None:
    """Actions guarded by precondition_has_context must not run before their
    required context key exists.

    Specifically: delete_todo requires 'todo_id'. From the initial state (no
    todo_id in context), delete_todo must never be executed.

    CURRENTLY FAILS: graph.get_unexplored() ignores context, so BFS fallback
    can return delete_todo from the initial state, and the agent never
    re-checks context before executing.
    """
    from venomqa import BFS

    calls: list[str] = []

    def create_todo(api: Any, context: Any) -> Any:
        resp = api.post("/todos", json={"title": "test"})
        resp.expect_status(201)
        context.set("todo_id", resp.json()["id"])
        return resp

    def delete_todo(api: Any, context: Any) -> Any:
        todo_id = context.get("todo_id")
        calls.append(f"delete called with todo_id={todo_id!r}")
        return api.delete(f"/todos/{todo_id}")

    actions = [
        Action(name="create_todo", execute=create_todo, max_calls=1),
        Action(
            name="delete_todo",
            execute=delete_todo,
            preconditions=[precondition_has_context("todo_id")],
        ),
    ]

    world = _world()
    agent = Agent(
        world=world,
        actions=actions,
        invariants=[],
        strategy=BFS(),
        max_steps=20,
    )
    agent.explore()

    # Every call to delete_todo must have had a real todo_id (not None).
    bad_calls = [c for c in calls if "None" in c]
    assert not bad_calls, (
        f"delete_todo was called WITHOUT a todo_id in context:\n"
        + "\n".join(f"  {c}" for c in bad_calls)
        + "\n\nThe precondition_has_context('todo_id') guard did not work. "
        "The agent executed delete_todo from a state where context had no 'todo_id'."
    )


def test_no_duplicate_violations() -> None:
    """The same bug at the same state must produce exactly one violation entry.

    If the same invariant fires in the same state via multiple paths, it
    should be deduplicated — the developer sees one clear bug, not noise.

    CURRENTLY FAILS: violations are appended without any deduplication check.
    """
    from venomqa import BFS

    world = _world()
    agent = Agent(
        world=world,
        actions=_actions(),
        invariants=_invariants(),
        strategy=BFS(),
        max_steps=50,
    )
    result = agent.explore()

    # Group violations by (invariant_name, state_id)
    seen: dict[tuple[str, str], int] = {}
    for v in result.violations:
        key = (v.invariant_name, v.state.id)
        seen[key] = seen.get(key, 0) + 1

    duplicates = {k: count for k, count in seen.items() if count > 1}
    assert not duplicates, (
        f"Duplicate violations found (same invariant, same state):\n"
        + "\n".join(
            f"  invariant={k[0]!r} state={k[1]!r} appeared {count}x"
            for k, count in duplicates.items()
        )
        + "\n\nVenomQA should deduplicate violations by (invariant_name, state_id)."
    )


def test_violation_has_human_readable_reproduction() -> None:
    """violation.reproduction_steps must be a list of human-readable strings.

    Each step should describe an HTTP request so the developer can reproduce
    the bug manually or in a script without reading Transition internals.

    Example expected output:
      ["POST /todos {\"title\": \"test task\"}", "PATCH /todos/1 {\"done\": true}",
       "DELETE /todos/1"]

    CURRENTLY FAILS: Violation has no reproduction_steps property; only the
    raw list[Transition] is available.
    """
    from venomqa import BFS

    world = _world()
    agent = Agent(
        world=world,
        actions=_actions(),
        invariants=_invariants(),
        strategy=BFS(),
        max_steps=50,
    )
    result = agent.explore()

    critical = [
        v for v in result.violations
        if v.invariant_name == "completed_todo_not_deletable"
    ]
    assert critical, "Expected at least one critical violation to be found"

    violation = critical[0]

    # Property must exist
    assert hasattr(violation, "reproduction_steps"), (
        "Violation must have a 'reproduction_steps' property.\n"
        "It should return list[str] with one human-readable step per transition."
    )

    steps = violation.reproduction_steps
    assert isinstance(steps, list), (
        f"reproduction_steps must be a list, got {type(steps).__name__}"
    )
    assert len(steps) >= 2, (
        f"Expected at least 2 reproduction steps (create + delete), "
        f"got {len(steps)}: {steps}"
    )

    # Each step must be a non-empty string
    for i, step in enumerate(steps):
        assert isinstance(step, str) and step.strip(), (
            f"Step {i} is not a non-empty string: {step!r}"
        )

    # At least one step should mention an HTTP method (POST, PATCH, DELETE)
    http_methods = {"POST", "PATCH", "DELETE", "GET", "PUT"}
    assert any(
        any(m in step for m in http_methods) for step in steps
    ), (
        f"None of the reproduction steps mention an HTTP method.\n"
        f"Steps: {steps}\n"
        f"Expected strings like 'POST /todos {{...}}' or 'DELETE /todos/1'"
    )
