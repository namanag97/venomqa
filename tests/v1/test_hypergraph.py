"""Unit tests for Hyperedge, Hypergraph, constraints, and DimensionNoveltyStrategy."""

from __future__ import annotations

from venomqa.core.constraints import (
    AnonHasNoRole,
    AuthHasRole,
    FreeCannotExceedUsage,
    constraint,
)
from venomqa.core.dimensions import (
    AuthStatus,
    CountClass,
    EntityStatus,
    PlanType,
    UsageClass,
    UserRole,
)
from venomqa.core.hyperedge import Hyperedge
from venomqa.core.hypergraph import Hypergraph
from venomqa.core.state import Observation, State

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(system: str = "api", data: dict = None) -> State:
    obs = Observation(system=system, data=data or {})
    return State.create(observations={system: obs})


def edge(**dims) -> Hyperedge:
    return Hyperedge(dimensions=dims)


# ---------------------------------------------------------------------------
# Hyperedge
# ---------------------------------------------------------------------------

class TestHyperedge:
    def test_equality_same_dims(self):
        a = edge(auth=AuthStatus.AUTH, role=UserRole.USER)
        b = edge(auth=AuthStatus.AUTH, role=UserRole.USER)
        assert a == b

    def test_inequality_different_dims(self):
        a = edge(auth=AuthStatus.AUTH)
        b = edge(auth=AuthStatus.ANON)
        assert a != b

    def test_hash_is_stable(self):
        a = edge(auth=AuthStatus.AUTH, role=UserRole.USER)
        b = edge(auth=AuthStatus.AUTH, role=UserRole.USER)
        assert hash(a) == hash(b)

    def test_usable_as_dict_key(self):
        d = {edge(auth=AuthStatus.AUTH): "yes"}
        assert d[edge(auth=AuthStatus.AUTH)] == "yes"

    def test_hamming_distance_zero(self):
        a = edge(auth=AuthStatus.AUTH, role=UserRole.USER)
        assert a.hamming_distance(a) == 0

    def test_hamming_distance_one(self):
        a = edge(auth=AuthStatus.AUTH, role=UserRole.USER)
        b = edge(auth=AuthStatus.AUTH, role=UserRole.ADMIN)
        assert a.hamming_distance(b) == 1

    def test_hamming_distance_disjoint_keys(self):
        a = edge(auth=AuthStatus.AUTH)
        b = edge(role=UserRole.USER)
        # "auth" missing in b, "role" missing in a → 2 differences
        assert a.hamming_distance(b) == 2

    def test_get_missing_key_returns_default(self):
        e = edge(auth=AuthStatus.AUTH)
        assert e.get("role") is None
        assert e.get("role", UserRole.NONE) == UserRole.NONE

    def test_to_dict(self):
        e = edge(auth=AuthStatus.AUTH, role=UserRole.ADMIN)
        d = e.to_dict()
        assert d["auth"] == "auth"
        assert d["role"] == "admin"

    def test_partial_flag(self):
        e = Hyperedge(dimensions={}, partial=True)
        assert e.partial

    def test_repr(self):
        e = edge(auth=AuthStatus.AUTH)
        assert "Hyperedge" in repr(e)
        assert "auth" in repr(e)

    def test_from_observation_auth(self):
        obs = Observation(system="api", data={"authenticated": True})
        e = Hyperedge.from_observation(obs)
        assert e.get("auth") == AuthStatus.AUTH

    def test_from_observation_anon(self):
        obs = Observation(system="api", data={"authenticated": False})
        e = Hyperedge.from_observation(obs)
        assert e.get("auth") == AuthStatus.ANON

    def test_from_observation_role(self):
        obs = Observation(system="api", data={"role": "admin"})
        e = Hyperedge.from_observation(obs)
        assert e.get("role") == UserRole.ADMIN

    def test_from_observation_count_zero(self):
        obs = Observation(system="db", data={"count": 0})
        e = Hyperedge.from_observation(obs)
        assert e.get("count") == CountClass.ZERO

    def test_from_observation_count_few(self):
        obs = Observation(system="db", data={"count": 5})
        e = Hyperedge.from_observation(obs)
        assert e.get("count") == CountClass.FEW

    def test_from_observation_count_many(self):
        obs = Observation(system="db", data={"count": 100})
        e = Hyperedge.from_observation(obs)
        assert e.get("count") == CountClass.MANY

    def test_from_observation_usage_percent(self):
        obs = Observation(system="api", data={"usage_percent": 80.0})
        e = Hyperedge.from_observation(obs)
        assert e.get("usage") == UsageClass.HIGH

    def test_from_observation_usage_exceeded(self):
        obs = Observation(system="api", data={"usage_percent": 100.0})
        e = Hyperedge.from_observation(obs)
        assert e.get("usage") == UsageClass.EXCEEDED

    def test_from_observation_plan(self):
        obs = Observation(system="api", data={"plan": "pro"})
        e = Hyperedge.from_observation(obs)
        assert e.get("plan") == PlanType.PRO

    def test_from_observation_entity_status(self):
        obs = Observation(system="api", data={"status": "active"})
        e = Hyperedge.from_observation(obs)
        assert e.get("entity_status") == EntityStatus.ACTIVE

    def test_from_observation_unknown_fields_ignored(self):
        obs = Observation(system="api", data={"foo": "bar", "baz": 123})
        e = Hyperedge.from_observation(obs)
        assert e.dimensions == {} or e.partial

    def test_from_state_merges_observations(self):
        obs1 = Observation(system="api", data={"authenticated": True})
        obs2 = Observation(system="db", data={"count": 3})
        state = State.create(observations={"api": obs1, "db": obs2})
        e = Hyperedge.from_state(state)
        assert e.get("auth") == AuthStatus.AUTH
        assert e.get("count") == CountClass.FEW


# ---------------------------------------------------------------------------
# Hypergraph
# ---------------------------------------------------------------------------

class TestHypergraph:
    def setup_method(self):
        self.hg = Hypergraph()

    def test_add_and_retrieve(self):
        e = edge(auth=AuthStatus.AUTH)
        self.hg.add("s1", e)
        assert self.hg.get_hyperedge("s1") == e

    def test_add_idempotent(self):
        e = edge(auth=AuthStatus.AUTH)
        self.hg.add("s1", e)
        self.hg.add("s1", e)  # Should not raise or duplicate
        assert self.hg.node_count == 1

    def test_node_count(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH))
        self.hg.add("s2", edge(auth=AuthStatus.ANON))
        assert self.hg.node_count == 2

    def test_query_by_dimension_single(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH))
        self.hg.add("s2", edge(auth=AuthStatus.ANON))
        result = self.hg.query_by_dimension(auth=AuthStatus.AUTH)
        assert result == ["s1"]

    def test_query_by_dimension_multiple_constraints(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH, role=UserRole.ADMIN))
        self.hg.add("s2", edge(auth=AuthStatus.AUTH, role=UserRole.USER))
        self.hg.add("s3", edge(auth=AuthStatus.ANON))
        result = self.hg.query_by_dimension(auth=AuthStatus.AUTH, role=UserRole.ADMIN)
        assert set(result) == {"s1"}

    def test_query_by_dimension_no_match(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH))
        result = self.hg.query_by_dimension(auth=AuthStatus.ANON)
        assert result == []

    def test_query_no_args_returns_all(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH))
        self.hg.add("s2", edge(auth=AuthStatus.ANON))
        assert len(self.hg.query_by_dimension()) == 2

    def test_all_values(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH))
        self.hg.add("s2", edge(auth=AuthStatus.ANON))
        vals = self.hg.all_values("auth")
        assert AuthStatus.AUTH in vals
        assert AuthStatus.ANON in vals

    def test_all_dimensions(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH, role=UserRole.ADMIN))
        dims = self.hg.all_dimensions()
        assert "auth" in dims
        assert "role" in dims

    def test_observed_combinations(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH, role=UserRole.ADMIN))
        self.hg.add("s2", edge(auth=AuthStatus.ANON, role=UserRole.NONE))
        combos = self.hg.observed_combinations("auth", "role")
        assert (AuthStatus.AUTH, UserRole.ADMIN) in combos
        assert (AuthStatus.ANON, UserRole.NONE) in combos

    def test_unexplored_combos(self):
        # Only AUTH+ADMIN observed → AUTH+USER, ANON+ADMIN, ANON+USER not yet seen
        self.hg.add("s1", edge(auth=AuthStatus.AUTH, role=UserRole.ADMIN))
        self.hg.add("s2", edge(auth=AuthStatus.ANON, role=UserRole.NONE))
        unexplored = self.hg.unexplored_combos("auth", "role")
        # AUTH+NONE, ANON+ADMIN, AUTH+USER etc. should appear
        assert (AuthStatus.AUTH, UserRole.ADMIN) not in unexplored
        assert len(unexplored) > 0

    def test_nearest_novel_state(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH, role=UserRole.ADMIN))
        target = edge(auth=AuthStatus.ANON, role=UserRole.NONE)
        # s1 differs in both dims → Hamming 2
        nearest = self.hg.nearest_novel_state(target)
        assert nearest == "s1"

    def test_nearest_novel_state_excludes(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH))
        result = self.hg.nearest_novel_state(edge(auth=AuthStatus.ANON), exclude={"s1"})
        assert result is None

    def test_coverage_per_dimension(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH))
        self.hg.add("s2", edge(auth=AuthStatus.ANON))
        cov = self.hg.coverage_per_dimension()
        assert cov["auth"] == 2

    def test_unknown_dimension_query_returns_empty(self):
        self.hg.add("s1", edge(auth=AuthStatus.AUTH))
        result = self.hg.query_by_dimension(plan=PlanType.FREE)
        assert result == []


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

class TestConstraints:
    def test_anon_has_no_role_valid(self):
        c = AnonHasNoRole()
        e = edge(auth=AuthStatus.ANON, role=UserRole.NONE)
        assert c.is_valid(e)

    def test_anon_has_no_role_invalid(self):
        c = AnonHasNoRole()
        e = edge(auth=AuthStatus.ANON, role=UserRole.ADMIN)
        assert not c.is_valid(e)

    def test_anon_has_no_role_no_role_key(self):
        c = AnonHasNoRole()
        e = edge(auth=AuthStatus.ANON)  # No role key at all
        assert c.is_valid(e)  # role is None → passes

    def test_auth_has_role_valid(self):
        c = AuthHasRole()
        e = edge(auth=AuthStatus.AUTH, role=UserRole.USER)
        assert c.is_valid(e)

    def test_auth_has_role_invalid(self):
        c = AuthHasRole()
        e = edge(auth=AuthStatus.AUTH, role=UserRole.NONE)
        assert not c.is_valid(e)

    def test_free_cannot_exceed_usage_valid(self):
        c = FreeCannotExceedUsage()
        e = edge(plan=PlanType.FREE, usage=UsageClass.LOW)
        assert c.is_valid(e)

    def test_free_cannot_exceed_usage_invalid(self):
        c = FreeCannotExceedUsage()
        e = edge(plan=PlanType.FREE, usage=UsageClass.EXCEEDED)
        assert not c.is_valid(e)

    def test_pro_can_exceed_usage(self):
        c = FreeCannotExceedUsage()
        e = edge(plan=PlanType.PRO, usage=UsageClass.EXCEEDED)
        assert c.is_valid(e)

    def test_lambda_constraint(self):
        c = constraint("no_admin_anon", lambda e: not (
            e.get("auth") == AuthStatus.ANON and e.get("role") == UserRole.ADMIN
        ))
        assert c.is_valid(edge(auth=AuthStatus.ANON, role=UserRole.USER))
        assert not c.is_valid(edge(auth=AuthStatus.ANON, role=UserRole.ADMIN))

    def test_constraint_name(self):
        c = AnonHasNoRole()
        assert c.name == "anon_has_no_role"


# ---------------------------------------------------------------------------
# DimensionNoveltyStrategy
# ---------------------------------------------------------------------------

class TestDimensionNoveltyStrategy:
    """Test the dimension-aware exploration strategy."""

    def test_picks_from_unexplored(self):
        from venomqa.agent.dimension_strategy import DimensionNoveltyStrategy
        from venomqa.core.action import Action, ActionResult, HTTPRequest, HTTPResponse

        from venomqa.core.graph import Graph

        def dummy(api):
            return ActionResult.from_response(
                HTTPRequest("GET", "/"), HTTPResponse(200)
            )

        action = Action(name="dummy", execute=dummy)
        graph = Graph([action])
        state = make_state()
        graph.add_state(state)

        hg = Hypergraph()
        hg.add(state.id, edge(auth=AuthStatus.AUTH))

        strategy = DimensionNoveltyStrategy(hypergraph=hg)
        result = strategy.pick(graph)
        assert result is not None
        s, a = result
        assert a.name == "dummy"

    def test_falls_back_to_bfs_when_no_hypergraph(self):
        from venomqa.agent.dimension_strategy import DimensionNoveltyStrategy
        from venomqa.core.action import Action, ActionResult, HTTPRequest, HTTPResponse

        from venomqa.core.graph import Graph

        def dummy(api):
            return ActionResult.from_response(
                HTTPRequest("GET", "/"), HTTPResponse(200)
            )

        action = Action(name="dummy", execute=dummy)
        graph = Graph([action])
        state = make_state()
        graph.add_state(state)

        strategy = DimensionNoveltyStrategy(hypergraph=None)
        result = strategy.pick(graph)
        assert result is not None

    def test_returns_none_when_all_explored(self):
        from venomqa.agent.dimension_strategy import DimensionNoveltyStrategy
        from venomqa.core.action import Action, ActionResult, HTTPRequest, HTTPResponse
        from venomqa.core.transition import Transition

        from venomqa.core.graph import Graph

        def dummy(api):
            return ActionResult.from_response(
                HTTPRequest("GET", "/"), HTTPResponse(200)
            )

        action = Action(name="dummy", execute=dummy)
        graph = Graph([action])
        state = make_state()
        graph.add_state(state)

        # Mark as explored by adding a transition
        ar = ActionResult.from_response(HTTPRequest("GET", "/"), HTTPResponse(200))
        transition = Transition.create(state.id, "dummy", state.id, result=ar)
        graph.add_transition(transition)

        strategy = DimensionNoveltyStrategy()
        result = strategy.pick(graph)
        assert result is None

    def test_enqueue_and_push_are_noops(self):
        from venomqa.agent.dimension_strategy import DimensionNoveltyStrategy
        from venomqa.core.action import Action, ActionResult, HTTPRequest, HTTPResponse

        def dummy(api):
            return ActionResult.from_response(
                HTTPRequest("GET", "/"), HTTPResponse(200)
            )

        action = Action(name="dummy", execute=dummy)
        state = make_state()
        strategy = DimensionNoveltyStrategy()
        # Should not raise
        strategy.enqueue(state, [action])
        strategy.push(state, [action])


# ---------------------------------------------------------------------------
# Agent with hypergraph=True
# ---------------------------------------------------------------------------

class TestAgentWithHypergraph:
    """Integration: Agent populates the Hypergraph during exploration."""

    def _make_world(self):
        from venomqa.world import World
        return World(api=None, state_from_context=[])

    def _ok(self):
        from venomqa.core.action import ActionResult, HTTPRequest, HTTPResponse
        return ActionResult.from_response(HTTPRequest("GET", "/"), HTTPResponse(200))

    def test_hypergraph_populated_after_exploration(self):
        from venomqa import Agent

        def dummy(api):
            return self._ok()

        from venomqa.core.action import Action
        action = Action(name="dummy", execute=dummy)

        world = self._make_world()
        agent = Agent(world=world, actions=[action], max_steps=5, hypergraph=True)
        agent.explore()

        assert agent.hypergraph is not None
        assert agent.hypergraph.node_count >= 1

    def test_dimension_coverage_attached_to_result(self):
        from venomqa.core.action import Action

        from venomqa import Agent

        def dummy(api):
            return self._ok()

        action = Action(name="dummy", execute=dummy)
        world = self._make_world()
        agent = Agent(world=world, actions=[action], max_steps=3, hypergraph=True)
        result = agent.explore()

        assert result.dimension_coverage is not None
        # total_states should match graph state count
        assert result.dimension_coverage.total_states == agent.hypergraph.node_count

    def test_no_hypergraph_by_default(self):
        from venomqa.core.action import Action

        from venomqa import Agent

        def dummy(api):
            return self._ok()

        action = Action(name="dummy", execute=dummy)
        world = self._make_world()
        agent = Agent(world=world, actions=[action], max_steps=3)
        result = agent.explore()

        assert agent.hypergraph is None
        assert result.dimension_coverage is None

    def test_observation_dimensions_extracted(self):
        """When actions return states with known dimension keys, they appear in hg."""
        from venomqa.core.action import Action, ActionResult, HTTPRequest, HTTPResponse
        from venomqa.world import World

        from venomqa import Agent

        # Use a MockStorage that we can manually seed observations through
        # Actually, we just need the world to have observations with dimension keys.
        # The easiest way: use a custom Rollbackable that produces known observations.

        class DimObservable:
            def checkpoint(self, name):
                return {"authenticated": True, "role": "admin", "count": 5}

            def rollback(self, cp):
                pass

            def observe(self):
                return Observation(
                    system="api",
                    data={"authenticated": True, "role": "admin", "count": 5},
                )

        world = World(api=None, systems={"api": DimObservable()})

        def dummy(api):
            return ActionResult.from_response(HTTPRequest("GET", "/"), HTTPResponse(200))

        action = Action(name="dummy", execute=dummy)
        agent = Agent(world=world, actions=[action], max_steps=3, hypergraph=True)
        agent.explore()

        hg = agent.hypergraph
        assert hg is not None
        # At least auth and role should be present
        dims = hg.all_dimensions()
        assert "auth" in dims or "count" in dims  # At least one recognised dimension
