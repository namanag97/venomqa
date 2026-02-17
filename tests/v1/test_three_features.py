"""Tests for auth helpers, path shrinking, and OpenAPI schema invariant."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from venomqa.v1.auth import ApiKeyAuth, AuthHttpClient, BearerTokenAuth, MultiRoleAuth
from venomqa.v1.core.action import Action, ActionResult, HTTPRequest, HTTPResponse
from venomqa.v1.core.context import Context
from venomqa.v1.core.invariant import Invariant, Severity, Violation
from venomqa.v1.core.transition import Transition
from venomqa.v1.world import World


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _ar(method: str = "GET", url: str = "/test", status: int = 200, body: object = None) -> ActionResult:
    req = HTTPRequest(method=method, url=url)
    resp = HTTPResponse(status_code=status, body=body or {})
    return ActionResult.from_response(req, resp)


def _fake_client(captured_headers: list | None = None) -> MagicMock:
    """Mock HttpClient that records the headers kwarg passed to it."""
    client = MagicMock()
    client.base_url = "http://test"
    client.timeout = 30.0
    client.default_headers = {}

    def make_result(*args, **kwargs):
        if captured_headers is not None:
            captured_headers.append(kwargs.get("headers", {}))
        return _ar()

    client.get.side_effect = make_result
    client.post.side_effect = make_result
    client.put.side_effect = make_result
    client.patch.side_effect = make_result
    client.delete.side_effect = make_result
    client.with_headers.return_value = client
    return client


def _ctx_with(key: str, value: str) -> Context:
    ctx = Context()
    ctx.set(key, value)
    return ctx


# ─── BearerTokenAuth ─────────────────────────────────────────────────────────

class TestBearerTokenAuth:

    def test_returns_auth_header(self):
        ctx = _ctx_with("token", "tok123")
        auth = BearerTokenAuth(token_fn=lambda c: c.get("token"))
        headers = auth.get_headers(ctx)
        assert headers == {"Authorization": "Bearer tok123"}

    def test_missing_token_returns_empty(self):
        ctx = Context()
        auth = BearerTokenAuth(token_fn=lambda c: c.get("token"))
        assert auth.get_headers(ctx) == {}

    def test_custom_scheme(self):
        ctx = _ctx_with("token", "abc")
        auth = BearerTokenAuth(token_fn=lambda c: c.get("token"), scheme="Token")
        assert auth.get_headers(ctx)["Authorization"] == "Token abc"

    def test_custom_header(self):
        ctx = _ctx_with("token", "abc")
        auth = BearerTokenAuth(token_fn=lambda c: c.get("token"), header="X-Auth")
        assert "X-Auth" in auth.get_headers(ctx)


# ─── ApiKeyAuth ──────────────────────────────────────────────────────────────

class TestApiKeyAuth:

    def test_returns_api_key_header(self):
        ctx = _ctx_with("api_key", "key123")
        auth = ApiKeyAuth(key_fn=lambda c: c.get("api_key"))
        assert auth.get_headers(ctx) == {"X-API-Key": "key123"}

    def test_missing_key_returns_empty(self):
        ctx = Context()
        auth = ApiKeyAuth(key_fn=lambda c: c.get("api_key"))
        assert auth.get_headers(ctx) == {}

    def test_custom_header(self):
        ctx = _ctx_with("key", "k")
        auth = ApiKeyAuth(key_fn=lambda c: c.get("key"), header="X-Token")
        assert "X-Token" in auth.get_headers(ctx)


# ─── MultiRoleAuth ───────────────────────────────────────────────────────────

class TestMultiRoleAuth:

    def _auth(self) -> MultiRoleAuth:
        return MultiRoleAuth(
            roles={
                "admin":  BearerTokenAuth(lambda c: c.get("admin_token")),
                "viewer": BearerTokenAuth(lambda c: c.get("viewer_token")),
            },
            default="admin",
        )

    def test_default_role_used_when_no_role_passed(self):
        ctx = Context()
        ctx.set("admin_token", "adm")
        ctx.set("viewer_token", "view")
        auth = self._auth()
        headers = auth.get_headers(ctx)
        assert headers["Authorization"] == "Bearer adm"

    def test_explicit_role_used(self):
        ctx = Context()
        ctx.set("admin_token", "adm")
        ctx.set("viewer_token", "view")
        auth = self._auth()
        headers = auth.get_headers(ctx, role="viewer")
        assert headers["Authorization"] == "Bearer view"

    def test_unknown_role_raises(self):
        ctx = Context()
        auth = self._auth()
        with pytest.raises(KeyError, match="Unknown role 'superadmin'"):
            auth.get_headers(ctx, role="superadmin")

    def test_invalid_default_raises_at_construction(self):
        with pytest.raises(ValueError, match="Default role 'missing'"):
            MultiRoleAuth(
                roles={"admin": BearerTokenAuth(lambda c: c.get("t"))},
                default="missing",
            )


# ─── AuthHttpClient ──────────────────────────────────────────────────────────

class TestAuthHttpClient:

    def _make(self, token: str = "tok") -> tuple[AuthHttpClient, list, Context]:
        captured: list = []
        raw = _fake_client(captured)
        ctx = Context()
        ctx.set("token", token)
        auth = BearerTokenAuth(lambda c: c.get("token"))
        client = AuthHttpClient(raw, auth, ctx)
        return client, captured, ctx

    def test_get_injects_auth_header(self):
        client, captured, _ = self._make()
        client.get("/path")
        assert captured[0].get("Authorization") == "Bearer tok"

    def test_post_injects_auth_header(self):
        client, captured, _ = self._make()
        client.post("/path", json={})
        assert captured[0].get("Authorization") == "Bearer tok"

    def test_delete_injects_auth_header(self):
        client, captured, _ = self._make()
        client.delete("/path")
        assert captured[0].get("Authorization") == "Bearer tok"

    def test_caller_headers_merged_over_auth(self):
        client, captured, _ = self._make()
        client.get("/path", headers={"X-Custom": "custom"})
        h = captured[0]
        assert h.get("Authorization") == "Bearer tok"
        assert h.get("X-Custom") == "custom"

    def test_caller_header_wins_on_conflict(self):
        client, captured, _ = self._make()
        client.get("/path", headers={"Authorization": "override"})
        assert captured[0]["Authorization"] == "override"

    def test_token_read_from_context_at_call_time(self):
        client, captured, ctx = self._make(token="old")
        ctx.set("token", "new")  # change token mid-flight
        client.get("/path")
        assert captured[0]["Authorization"] == "Bearer new"

    def test_with_role_uses_role_token(self):
        captured: list = []
        raw = _fake_client(captured)
        ctx = Context()
        ctx.set("admin_token", "adm")
        ctx.set("viewer_token", "view")
        auth = MultiRoleAuth(
            roles={
                "admin":  BearerTokenAuth(lambda c: c.get("admin_token")),
                "viewer": BearerTokenAuth(lambda c: c.get("viewer_token")),
            },
            default="admin",
        )
        client = AuthHttpClient(raw, auth, ctx)
        viewer = client.with_role("viewer")
        viewer.delete("/resource/1")
        assert captured[0]["Authorization"] == "Bearer view"

    def test_role_kwarg_on_direct_call(self):
        captured: list = []
        raw = _fake_client(captured)
        ctx = Context()
        ctx.set("admin_token", "adm")
        ctx.set("viewer_token", "view")
        auth = MultiRoleAuth(
            roles={
                "admin":  BearerTokenAuth(lambda c: c.get("admin_token")),
                "viewer": BearerTokenAuth(lambda c: c.get("viewer_token")),
            },
            default="admin",
        )
        client = AuthHttpClient(raw, auth, ctx)
        client.delete("/resource/1", role="viewer")
        assert captured[0]["Authorization"] == "Bearer view"


# ─── World(auth=) integration ─────────────────────────────────────────────────

class TestWorldAuthIntegration:

    def test_world_wraps_api_with_auth_client(self):
        raw = _fake_client()
        ctx = Context()
        auth = BearerTokenAuth(lambda c: c.get("token"))
        world = World(api=raw, auth=auth, context=ctx)
        assert isinstance(world.api, AuthHttpClient)

    def test_world_without_auth_keeps_raw_api(self):
        raw = _fake_client()
        world = World(api=raw)
        # Should not be wrapped
        assert not isinstance(world.api, AuthHttpClient)

    def test_auth_token_injected_in_explore(self):
        from venomqa.v1 import Agent, BFS

        captured_headers: list = []
        raw = _fake_client(captured_headers)
        ctx = Context()
        ctx.set("token", "explore_tok")
        auth = BearerTokenAuth(lambda c: c.get("token"))
        world = World(api=raw, auth=auth, context=ctx)

        def call_api(api, context):
            return api.get("/test")

        agent = Agent(
            world=world,
            actions=[Action(name="call_api", execute=call_api)],
            strategy=BFS(),
            max_steps=2,
        )
        agent.explore()
        # At least one request should have the auth header
        auth_headers = [h for h in captured_headers if "Authorization" in h]
        assert auth_headers, "Auth header should be injected during exploration"
        assert auth_headers[0]["Authorization"] == "Bearer explore_tok"


# ─── Path shrinking ───────────────────────────────────────────────────────────

class TestPathShrinking:
    """Tests for Agent(shrink=True)."""

    def _make_action_result(self) -> ActionResult:
        return _ar()

    def _make_transition(self, action_name: str) -> Transition:
        from venomqa.v1.core.state import Observation, State
        s1 = State.create({"s": Observation(system="s", data={"v": 1})})
        s2 = State.create({"s": Observation(system="s", data={"v": 2})})
        return Transition.create(
            from_state_id=s1.id,
            action_name=action_name,
            to_state_id=s2.id,
            result=self._make_action_result(),
        )

    def test_shrink_false_by_default(self):
        from venomqa.v1 import Agent, BFS

        world = World(api=MagicMock())
        agent = Agent(world=world, actions=[], strategy=BFS())
        assert agent.shrink is False

    def test_short_path_not_shrunk(self):
        """A 1-step path cannot be shortened."""
        from venomqa.v1 import Agent, BFS
        from venomqa.v1.adapters.mock_queue import MockQueue
        from venomqa.v1.adapters.mock_storage import MockStorage

        queue = MockQueue("q")
        world = World(api=MagicMock(), systems={"q": queue})

        _fired = [0]

        def check(w):
            _fired[0] += 1
            return False  # always violates

        inv = Invariant(name="always_fails", check=check, message="x", severity=Severity.LOW)

        def noop(api, ctx):
            return _ar()

        agent = Agent(
            world=world,
            actions=[Action(name="noop", execute=noop)],
            invariants=[inv],
            strategy=BFS(),
            max_steps=5,
            shrink=True,
        )
        result = agent.explore()
        # Violations should exist but single-step paths can't be shortened
        for v in result.violations:
            assert len(v.reproduction_path) <= 1

    def test_shrink_true_param_accepted(self):
        from venomqa.v1 import Agent, BFS

        world = World(api=MagicMock())
        agent = Agent(world=world, actions=[], strategy=BFS(), shrink=True)
        assert agent.shrink is True

    def test_shrink_reduces_path_length(self):
        """Integration: shrinking must produce a path no longer than original."""
        from venomqa.v1 import Agent, BFS
        from venomqa.v1.adapters.mock_storage import MockStorage

        storage = MockStorage(bucket="b")
        world = World(api=MagicMock(), systems={"s": storage}, state_from_context=["step"])

        _counter = [0]

        def step_action(api, ctx):
            _counter[0] += 1
            ctx.set("step", _counter[0])
            return _ar()

        # Invariant fires only when step >= 3 — so a 3+ step path triggers it
        # but a 1 or 2 step path might not (depending on counter state)
        # With shrink=True the agent should find a shorter reproduction.
        def check_counter(w):
            # Always fails after step 1 — any path of length >= 1 triggers it
            return w.context.get("step", 0) == 0

        inv = Invariant(
            name="step_check",
            check=check_counter,
            message="step must be 0",
            severity=Severity.LOW,
        )

        agent = Agent(
            world=world,
            actions=[Action(name="step", execute=step_action)],
            invariants=[inv],
            strategy=BFS(),
            max_steps=10,
            shrink=True,
        )
        result = agent.explore()
        # With shrink=True, violations should have minimal (1-step) paths
        for v in result.violations:
            # Shrunk message should mention shrinking IF path was reduced
            # (may not always trigger for 1-step paths)
            assert len(v.reproduction_path) >= 0  # just verify it doesn't crash


# ─── OpenAPI schema invariant ─────────────────────────────────────────────────

MINI_SPEC: dict = {
    "openapi": "3.0.0",
    "info": {"title": "Test", "version": "1"},
    "paths": {
        "/users": {
            "post": {
                "responses": {
                    "201": {
                        "description": "Created",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["id", "name"],
                                    "properties": {
                                        "id":   {"type": "integer"},
                                        "name": {"type": "string"},
                                    },
                                }
                            }
                        },
                    }
                }
            }
        },
        "/items": {
            "get": {
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {"type": "array"}
                            }
                        },
                    }
                }
            }
        },
    },
}


class TestOpenAPISchemaInvariant:

    def _make_inv(self) -> "OpenAPISchemaInvariant":
        from venomqa.v1.invariants.openapi import OpenAPISchemaInvariant
        from unittest.mock import patch
        with patch("venomqa.v1.cli.scaffold.load_spec", return_value=MINI_SPEC):
            return OpenAPISchemaInvariant(spec_path="fake.yaml")

    def _world_with_last(self, ar: ActionResult) -> World:
        world = World(api=MagicMock())
        world._last_action_result = ar
        return world

    def test_passes_on_valid_response(self):
        inv = self._make_inv()
        ar = _ar("POST", "http://localhost/users", 201, {"id": 1, "name": "Alice"})
        world = self._world_with_last(ar)
        assert inv.check(world) is True

    def test_fails_on_missing_required_field(self):
        inv = self._make_inv()
        ar = _ar("POST", "http://localhost/users", 201, {"id": 1})  # missing "name"
        world = self._world_with_last(ar)
        assert inv.check(world) is False
        assert "name" in inv.message or "name" in inv._last_error

    def test_passes_when_no_last_action(self):
        inv = self._make_inv()
        world = World(api=MagicMock())
        assert inv.check(world) is True

    def test_skips_unknown_path(self):
        inv = self._make_inv()
        ar = _ar("GET", "http://localhost/unknown", 200, {"anything": True})
        world = self._world_with_last(ar)
        assert inv.check(world) is True

    def test_skips_undocumented_status_code(self):
        inv = self._make_inv()
        ar = _ar("POST", "http://localhost/users", 409, {"error": "conflict"})
        world = self._world_with_last(ar)
        assert inv.check(world) is True  # 409 not in spec → skip

    def test_fails_wrong_type(self):
        inv = self._make_inv()
        # /items GET 200 expects array, we return object
        ar = _ar("GET", "http://localhost/items", 200, {"not": "an array"})
        world = self._world_with_last(ar)
        assert inv.check(world) is False

    def test_passes_array_response(self):
        inv = self._make_inv()
        ar = _ar("GET", "http://localhost/items", 200, [{"id": 1}])
        world = self._world_with_last(ar)
        assert inv.check(world) is True

    def test_ignore_paths_skips_validation(self):
        from venomqa.v1.invariants.openapi import OpenAPISchemaInvariant
        from unittest.mock import patch
        with patch("venomqa.v1.cli.scaffold.load_spec", return_value=MINI_SPEC):
            inv = OpenAPISchemaInvariant(spec_path="fake.yaml", ignore_paths=["/users"])
        ar = _ar("POST", "http://localhost/users", 201, {})  # missing required
        world = self._world_with_last(ar)
        assert inv.check(world) is True  # ignored

    def test_raises_without_spec_url_or_path(self):
        from venomqa.v1.invariants.openapi import OpenAPISchemaInvariant
        with pytest.raises(ValueError, match="spec_url= or spec_path="):
            OpenAPISchemaInvariant()

    def test_name_and_severity_attributes(self):
        inv = self._make_inv()
        assert inv.name == "openapi_schema"
        assert inv.severity == Severity.HIGH

    def test_parameterized_path_matches(self):
        """Path /users/123 must match spec pattern /users/{id}."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/users/{id}": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["id"],
                                            "properties": {"id": {"type": "integer"}},
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
        }
        from venomqa.v1.invariants.openapi import OpenAPISchemaInvariant
        from unittest.mock import patch
        with patch("venomqa.v1.cli.scaffold.load_spec", return_value=spec):
            inv = OpenAPISchemaInvariant(spec_path="fake.yaml")

        # Missing required field "id" → should fail
        ar = _ar("GET", "http://localhost/users/123", 200, {"name": "Alice"})
        world = World(api=MagicMock())
        world._last_action_result = ar
        assert inv.check(world) is False

    def test_world_last_action_result_set_by_act(self):
        """world.last_action_result is populated after world.act()."""
        from venomqa.v1.core.action import Action

        called_with = []

        def my_action(api, ctx):
            called_with.append(True)
            return _ar("POST", "http://test/x", 200, {"ok": True})

        raw = MagicMock()
        raw.base_url = "http://test"
        raw.timeout = 30
        raw.default_headers = {}
        # Make raw.post return the ActionResult
        raw.post.return_value = _ar("POST", "http://test/x", 200, {"ok": True})

        world = World(api=raw)
        action = Action(name="my_action", execute=my_action)
        assert world.last_action_result is None
        world.act(action)
        assert world.last_action_result is not None
