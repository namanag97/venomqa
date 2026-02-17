"""Unit tests for the World class."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from venomqa.v1.core.action import Action, ActionResult, HTTPRequest, HTTPResponse
from venomqa.v1.core.context import Context
from venomqa.v1.core.state import Observation
from venomqa.v1.world import World


def _make_http_result(status: int = 200) -> ActionResult:
    req = HTTPRequest(method="GET", url="/test")
    resp = HTTPResponse(status_code=status, body={})
    return ActionResult.from_response(req, resp)


def _make_mock_system(obs_data: dict | None = None) -> MagicMock:
    system = MagicMock()
    system.checkpoint.return_value = "cp_1"
    system.observe.return_value = Observation(
        system="mock", data=obs_data or {"count": 0}
    )
    return system


class TestWorldObserve:
    def test_observe_returns_state(self):
        api = MagicMock()
        sys1 = _make_mock_system({"users": 3})
        world = World(api=api, systems={"db": sys1})

        state = world.observe()

        assert "db" in state.observations
        assert state.observations["db"].data["users"] == 3

    def test_observe_multiple_systems(self):
        api = MagicMock()
        sys1 = _make_mock_system({"users": 1})
        sys2 = _make_mock_system({"messages": 5})
        sys2.observe.return_value = Observation(system="cache", data={"messages": 5})
        world = World(api=api, systems={"db": sys1, "cache": sys2})

        state = world.observe()

        assert "db" in state.observations
        assert "cache" in state.observations

    def test_observe_no_systems(self):
        api = MagicMock()
        world = World(api=api)
        state = world.observe()
        assert state.observations == {}


class TestWorldCheckpointRollback:
    def test_observe_and_checkpoint_returns_state_with_checkpoint_id(self):
        api = MagicMock()
        sys1 = _make_mock_system()
        world = World(api=api, systems={"db": sys1})

        state = world.observe_and_checkpoint("test_cp")

        assert state.checkpoint_id is not None
        sys1.checkpoint.assert_called_once_with("test_cp")

    def test_rollback_restores_system(self):
        api = MagicMock()
        sys1 = _make_mock_system()
        world = World(api=api, systems={"db": sys1})

        state = world.observe_and_checkpoint("cp1")
        world.rollback(state.checkpoint_id)

        sys1.rollback.assert_called_once_with("cp_1")

    def test_rollback_unknown_checkpoint_raises(self):
        api = MagicMock()
        world = World(api=api)

        with pytest.raises(ValueError, match="Unknown checkpoint"):
            world.rollback("nonexistent")

    def test_rollback_restores_context(self):
        api = MagicMock()
        world = World(api=api)

        # Set value, checkpoint, modify, rollback — value should be restored
        world.context.set("key", "original")
        state = world.observe_and_checkpoint("before_change")
        world.context.set("key", "modified")
        assert world.context.get("key") == "modified"

        world.rollback(state.checkpoint_id)
        assert world.context.get("key") == "original"

    def test_has_checkpoint(self):
        api = MagicMock()
        world = World(api=api)

        assert not world.has_checkpoint("x")
        state = world.observe_and_checkpoint("cp")
        assert world.has_checkpoint(state.checkpoint_id)


class TestWorldAct:
    def test_act_simple_action(self):
        def my_action(api):
            return _make_http_result(200)

        api = MagicMock()
        world = World(api=api)
        action = Action(name="my_action", execute=my_action)

        result = world.act(action)

        assert result.success is True

    def test_act_context_action(self):
        def my_action(api, context):
            context.set("done", True)
            return _make_http_result(201)

        api = MagicMock()
        world = World(api=api)
        action = Action(name="my_action", execute=my_action)

        result = world.act(action)

        assert result.status_code == 201
        assert world.context.get("done") is True

    def test_register_system(self):
        api = MagicMock()
        world = World(api=api)
        sys1 = _make_mock_system()

        world.register_system("new_sys", sys1)
        state = world.observe()

        assert "new_sys" in state.observations


# ─── Named multi-client tests ──────────────────────────────────────────────


class TestWorldMultiClient:
    """Tests for World(clients={...}) and context.get_client()."""

    def _make_fake_client(self, label: str) -> MagicMock:
        client = MagicMock()
        client.label = label
        return client

    def test_clients_stored_on_world(self) -> None:
        api = self._make_fake_client("default")
        viewer = self._make_fake_client("viewer")
        world = World(api=api, clients={"viewer": viewer})
        assert world.clients["viewer"] is viewer

    def test_clients_empty_by_default(self) -> None:
        api = self._make_fake_client("default")
        world = World(api=api)
        assert world.clients == {}

    def test_context_get_client_returns_registered_client(self) -> None:
        api = self._make_fake_client("default")
        viewer = self._make_fake_client("viewer")
        world = World(api=api, clients={"viewer": viewer})
        assert world.context.get_client("viewer") is viewer

    def test_context_get_client_raises_on_missing_name(self) -> None:
        api = self._make_fake_client("default")
        world = World(api=api, clients={})
        with pytest.raises(KeyError, match="No client registered as 'admin'"):
            world.context.get_client("admin")

    def test_context_get_client_error_lists_available(self) -> None:
        api = self._make_fake_client("default")
        viewer = self._make_fake_client("viewer")
        world = World(api=api, clients={"viewer": viewer})
        with pytest.raises(KeyError, match="viewer"):
            world.context.get_client("missing")

    def test_clients_survive_checkpoint_rollback(self) -> None:
        """Named clients must NOT be wiped on rollback."""
        api = self._make_fake_client("default")
        viewer = self._make_fake_client("viewer")
        sys1 = _make_mock_system()
        world = World(api=api, clients={"viewer": viewer}, systems={"s": sys1})

        cp_id = world.checkpoint("before")
        # Rollback should restore context._data but keep _clients
        world.rollback(cp_id)

        assert world.context.get_client("viewer") is viewer

    def test_multiple_named_clients(self) -> None:
        api = self._make_fake_client("default")
        admin = self._make_fake_client("admin")
        viewer = self._make_fake_client("viewer")
        anon = self._make_fake_client("anon")
        world = World(api=api, clients={"admin": admin, "viewer": viewer, "anon": anon})
        assert world.context.get_client("admin") is admin
        assert world.context.get_client("viewer") is viewer
        assert world.context.get_client("anon") is anon

    def test_clients_accessible_in_invariant_via_world(self) -> None:
        """Invariants receive world and can read world.clients directly."""
        from venomqa.v1.core.invariant import Invariant, Severity

        api = self._make_fake_client("default")
        viewer = self._make_fake_client("viewer")
        world = World(api=api, clients={"viewer": viewer})

        captured: list[MagicMock] = []

        def check_client(w: World) -> bool:  # type: ignore[override]
            captured.append(w.clients["viewer"])
            return True

        inv = Invariant(name="test", check=check_client, message="x", severity=Severity.LOW)
        inv.check(world)
        assert captured[0] is viewer
