"""UAT test — real HttpClient against an in-process FastAPI server.

This test proves the full stack end-to-end:
  - HttpClient makes real HTTP calls (not mocked)
  - ActionResult.json() / .status_code / .ok proxies work
  - Agent.explore() finds violations planted in the server
  - ExplorationResult fields (action_coverage_percent, truncated_by_max_steps) are correct
  - ConsoleReporter and JSONReporter produce valid output

Run with: pytest tests/v1/test_real_http_uat.py -v
"""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from venomqa.adapters.http import HttpClient
from venomqa.reporters.console import ConsoleReporter
from venomqa.reporters.json import JSONReporter

from venomqa import BFS, Action, Agent, Invariant, Severity, World

# ---------------------------------------------------------------------------
# Minimal FastAPI app — one planted bug (list items returns wrong type on error)
# ---------------------------------------------------------------------------

app = FastAPI()
_items: dict[int, dict[str, Any]] = {}
_next_id = 1


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/items", status_code=201)
def create_item(body: dict):
    global _next_id
    item = {"id": _next_id, "name": body.get("name", "unnamed")}
    _items[_next_id] = item
    _next_id += 1
    return item


@app.get("/items")
def list_items():
    return list(_items.values())


@app.delete("/items/{item_id}", status_code=200)
def delete_item(item_id: int):
    if item_id in _items:
        del _items[item_id]
        return {"deleted": item_id}
    return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/items/buggy")
def buggy_list():
    """Planted bug: sometimes returns a non-list (dict instead of list)."""
    return {"items": list(_items.values()), "bug": True}   # wrong shape!


# ---------------------------------------------------------------------------
# Server fixture — starts uvicorn in a background thread
# ---------------------------------------------------------------------------

class _UvicornThread(threading.Thread):
    def __init__(self, port: int = 18742) -> None:
        super().__init__(daemon=True)
        self.port = port
        self._started = threading.Event()
        self._config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        self._server = uvicorn.Server(self._config)

    def run(self) -> None:
        self._server.run()

    def start_and_wait(self) -> None:
        self.start()
        import time
        for _ in range(50):
            time.sleep(0.05)
            try:
                import httpx
                r = httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=1)
                if r.status_code == 200:
                    return
            except Exception:
                pass
        raise RuntimeError("Server did not start in time")

    def stop(self) -> None:
        self._server.should_exit = True


BASE_URL = "http://127.0.0.1:18742"


@pytest.fixture(scope="module")
def server():
    global _items, _next_id
    _items = {}
    _next_id = 1
    t = _UvicornThread()
    t.start_and_wait()
    yield BASE_URL
    t.stop()


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def create_item(api, context):
    resp = api.post("/items", json={"name": "widget"})
    context.set("item_id", resp.json()["id"])
    return resp


def list_items(api, context):
    resp = api.get("/items")
    context.set("items", resp.json())
    return resp


def delete_item(api, context):
    item_id = context.get("item_id")
    if item_id is None:
        return api.get("/items")   # safe no-op
    return api.delete(f"/items/{item_id}")


def get_buggy(api, context):
    """Action that hits the planted-bug endpoint."""
    return api.get("/items/buggy")


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

def list_is_a_list(world):
    items = world.context.get("items")
    if items is None:
        return True   # not yet observed
    return isinstance(items, list)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRealHttpUAT:

    def test_action_result_proxies(self, server):
        """ActionResult.json(), .status_code, .ok work without going through .response."""
        api = HttpClient(server)

        resp = api.get("/health")
        assert resp.status_code == 200
        assert resp.ok is True
        assert resp.json() == {"status": "ok"}
        assert "ok" in resp.text

        resp_create = api.post("/items", json={"name": "test"})
        assert resp_create.status_code == 201
        data = resp_create.json()
        assert "id" in data
        assert data["name"] == "test"

    def test_full_exploration_no_violations(self, server):
        """Agent explores the clean endpoints and finds no violations."""
        global _items, _next_id
        _items = {}
        _next_id = 1

        api = HttpClient(server)
        world = World(api=api, state_from_context=[])

        agent = Agent(
            world=world,
            actions=[
                Action(name="create_item", execute=create_item, expected_status=[201]),
                Action(name="list_items",  execute=list_items,  expected_status=[200]),
                Action(name="delete_item", execute=delete_item),
            ],
            invariants=[
                Invariant(
                    name="list_is_a_list",
                    check=list_is_a_list,
                    message="GET /items must always return a JSON array",
                    severity=Severity.CRITICAL,
                ),
            ],
            strategy=BFS(),
            max_steps=30,
        )

        result = agent.explore()

        assert result.states_visited >= 1
        assert result.transitions_taken >= 1
        assert result.action_coverage_percent > 0
        assert result.success, f"Unexpected violations: {[v.message for v in result.violations]}"

    def test_exploration_finds_violation(self, server):
        """Agent finds the planted bug in the buggy endpoint."""
        global _items, _next_id
        _items = {}
        _next_id = 1

        api = HttpClient(server)
        world = World(api=api, state_from_context=[])

        def list_from_buggy(api, context):
            resp = api.get("/items/buggy")
            # Store the items field (wrong shape — dict, not list)
            context.set("items", resp.json())   # plants the violation
            return resp

        agent = Agent(
            world=world,
            actions=[
                Action(name="create_item",     execute=create_item, expected_status=[201]),
                Action(name="list_buggy",      execute=list_from_buggy, expected_status=[200]),
            ],
            invariants=[
                Invariant(
                    name="list_is_a_list",
                    check=list_is_a_list,
                    message="GET /items must return a list, not a dict",
                    severity=Severity.CRITICAL,
                ),
            ],
            strategy=BFS(),
            max_steps=30,
        )

        result = agent.explore()
        assert not result.success, "Should have found the planted bug"
        assert len(result.violations) > 0
        assert result.violations[0].severity == Severity.CRITICAL

    def test_truncated_by_max_steps(self, server):
        """truncated_by_max_steps is True when max_steps limit is hit."""
        global _items, _next_id
        _items = {}
        _next_id = 1

        api = HttpClient(server)
        world = World(api=api, state_from_context=[])

        agent = Agent(
            world=world,
            actions=[
                Action(name="create_item", execute=create_item, expected_status=[201]),
                Action(name="list_items",  execute=list_items,  expected_status=[200]),
                Action(name="delete_item", execute=delete_item),
            ],
            strategy=BFS(),
            max_steps=2,   # intentionally tiny
        )

        result = agent.explore()
        assert result.truncated_by_max_steps is True
        assert result.transitions_taken == 2

    def test_action_coverage_percent(self, server):
        """action_coverage_percent reflects how many unique actions were used."""
        global _items, _next_id
        _items = {}
        _next_id = 1

        api = HttpClient(server)
        world = World(api=api, state_from_context=[])

        agent = Agent(
            world=world,
            actions=[
                Action(name="create_item", execute=create_item, expected_status=[201]),
                Action(name="list_items",  execute=list_items,  expected_status=[200]),
                Action(name="delete_item", execute=delete_item),
            ],
            strategy=BFS(),
            max_steps=50,
        )

        result = agent.explore()
        # After enough steps all 3 actions should have been used at least once
        assert result.action_coverage_percent > 0
        assert 0 <= result.action_coverage_percent <= 100

    def test_action_missing_return_raises_clear_error(self, server):
        """Action that returns None raises TypeError with helpful message."""
        api = HttpClient(server)
        world = World(api=api, state_from_context=[])

        def bad_action(api, context):
            api.get("/health")   # forgot return!

        agent = Agent(
            world=world,
            actions=[Action(name="bad", execute=bad_action)],
            strategy=BFS(),
            max_steps=5,
        )

        with pytest.raises(TypeError, match="returned None.*Did you forget"):
            agent.explore()

    def test_json_reporter_output(self, server):
        """JSONReporter produces valid JSON with all expected fields."""
        global _items, _next_id
        _items = {}
        _next_id = 1

        api = HttpClient(server)
        world = World(api=api, state_from_context=[])

        agent = Agent(
            world=world,
            actions=[
                Action(name="create_item", execute=create_item),
                Action(name="list_items",  execute=list_items),
            ],
            strategy=BFS(),
            max_steps=10,
        )

        result = agent.explore()
        output = JSONReporter().report(result)
        data = json.loads(output)

        summary = data["summary"]
        assert "states_visited" in summary
        assert "action_coverage_percent" in summary
        assert "truncated_by_max_steps" in summary
        assert "success" in summary

    def test_console_reporter_truncation_warning(self, server):
        """ConsoleReporter shows truncation warning when max_steps is hit."""
        import io

        global _items, _next_id
        _items = {}
        _next_id = 1

        api = HttpClient(server)
        world = World(api=api, state_from_context=[])

        agent = Agent(
            world=world,
            actions=[
                Action(name="create_item", execute=create_item),
                Action(name="list_items",  execute=list_items),
                Action(name="delete_item", execute=delete_item),
            ],
            strategy=BFS(),
            max_steps=2,
        )

        result = agent.explore()
        buf = io.StringIO()
        ConsoleReporter(file=buf, color=False).report(result)
        output = buf.getvalue()
        assert "truncated" in output.lower() or "max_steps" in output.lower(), (
            f"Expected truncation warning in output, got:\n{output}"
        )
