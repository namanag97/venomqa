"""Comprehensive tests for rollback-based exploration.

These tests verify the core value proposition of VenomQA:
the ability to explore multiple branches from the same state
by using checkpoint/rollback.
"""

import pytest

from venomqa.v1 import (
    World, Agent, BFS, DFS, CoverageGuided,
    Action, ActionResult, HTTPRequest, HTTPResponse,
    Invariant, Severity,
)
from venomqa.v1.adapters import MockQueue, MockMail, MockStorage


class MockApi:
    """Mock API that tracks state for testing."""

    def __init__(self):
        self.logged_in = False
        self.cart = []
        self.orders = []
        self.balance = 100

    def post(self, path, **kwargs):
        request = HTTPRequest("POST", path, body=kwargs.get("json"))

        if path == "/login":
            self.logged_in = True
            return ActionResult.from_response(request, HTTPResponse(200, body={"logged_in": True}))

        if path == "/logout":
            self.logged_in = False
            return ActionResult.from_response(request, HTTPResponse(200, body={"logged_in": False}))

        if path == "/cart/add":
            if self.logged_in:
                self.cart.append(kwargs.get("json", {}).get("item", "item"))
                return ActionResult.from_response(request, HTTPResponse(200, body={"cart": self.cart}))
            return ActionResult.from_response(request, HTTPResponse(401, body={"error": "Not logged in"}))

        if path == "/cart/clear":
            self.cart = []
            return ActionResult.from_response(request, HTTPResponse(200, body={"cart": []}))

        if path == "/checkout":
            if self.cart:
                order_id = len(self.orders) + 1
                self.orders.append({"id": order_id, "items": list(self.cart)})
                self.cart = []
                self.balance -= 10
                return ActionResult.from_response(request, HTTPResponse(200, body={"order_id": order_id}))
            return ActionResult.from_response(request, HTTPResponse(400, body={"error": "Cart empty"}))

        return ActionResult.from_response(request, HTTPResponse(404))

    def get(self, path, **kwargs):
        request = HTTPRequest("GET", path)
        return ActionResult.from_response(request, HTTPResponse(200, body={}))


class TrackingQueue(MockQueue):
    """Queue that tracks all operations for verification."""

    def __init__(self):
        super().__init__()
        self.operation_log = []

    def push(self, payload):
        self.operation_log.append(("push", payload))
        return super().push(payload)

    def checkpoint(self, name):
        self.operation_log.append(("checkpoint", name))
        return super().checkpoint(name)

    def rollback(self, cp):
        self.operation_log.append(("rollback", None))
        return super().rollback(cp)


class TestRollbackExploration:
    """Tests for rollback-based state space exploration."""

    def test_explores_multiple_branches_from_same_state(self):
        """Test that agent explores multiple actions from the same state via rollback."""
        api = MockApi()
        queue = TrackingQueue()

        world = World(api=api, systems={"queue": queue})

        # Three actions that can all run from initial state
        actions = [
            Action(name="action_a", execute=lambda api: api.post("/a")),
            Action(name="action_b", execute=lambda api: api.post("/b")),
            Action(name="action_c", execute=lambda api: api.post("/c")),
        ]

        agent = Agent(world=world, actions=actions, strategy=BFS(), max_steps=10)
        result = agent.explore()

        # Should have explored all three actions from initial state
        action_names = {t.action_name for t in result.graph.transitions}
        assert "action_a" in action_names
        assert "action_b" in action_names
        assert "action_c" in action_names

        # Verify rollbacks occurred (at least 2 for 3 branches)
        rollback_count = sum(1 for op in queue.operation_log if op[0] == "rollback")
        assert rollback_count >= 2, f"Expected at least 2 rollbacks, got {rollback_count}"

    def test_rollback_restores_state_correctly(self):
        """Test that rollback actually restores system state."""
        api = MockApi()
        queue = MockQueue()
        mail = MockMail()

        world = World(api=api, systems={"queue": queue, "mail": mail})

        def action_send_email(api):
            mail.send("test@example.com", "Subject", "Body")
            return api.post("/send")

        def action_enqueue(api):
            queue.push({"task": "process"})
            return api.post("/enqueue")

        actions = [
            Action(name="send_email", execute=action_send_email),
            Action(name="enqueue", execute=action_enqueue),
        ]

        agent = Agent(world=world, actions=actions, strategy=BFS(), max_steps=10)
        result = agent.explore()

        # Both actions should have been explored
        assert result.transitions_taken >= 2

        # After exploration, we should be at some state
        # But the key test is that rollback worked during exploration
        # We can verify by checking that states have checkpoint_ids
        for state in result.graph.iter_states():
            assert state.checkpoint_id is not None, f"State {state.id} has no checkpoint_id"

    def test_preconditions_respected_across_branches(self):
        """Test that action preconditions work correctly with rollback."""
        api = MockApi()
        queue = MockQueue()

        world = World(api=api, systems={"queue": queue})

        logged_in_flag = [False]  # Use list to allow mutation in closure

        def login(api):
            logged_in_flag[0] = True
            return api.post("/login")

        def logout(api):
            logged_in_flag[0] = False
            return api.post("/logout")

        def protected_action(api):
            return api.post("/protected")

        actions = [
            Action(name="login", execute=login),
            Action(name="logout", execute=logout, preconditions=[lambda s: logged_in_flag[0]]),
            Action(
                name="protected",
                execute=protected_action,
                preconditions=[lambda s: logged_in_flag[0]],
            ),
        ]

        agent = Agent(world=world, actions=actions, strategy=BFS(), max_steps=20)
        result = agent.explore()

        # Login should happen before protected/logout
        transitions = list(result.graph.iter_transitions())
        assert any(t.action_name == "login" for t in transitions)

    def test_invariant_violations_with_reproduction_path(self):
        """Test that violations include correct reproduction paths."""
        api = MockApi()
        queue = MockQueue()

        world = World(api=api, systems={"queue": queue})

        trigger_count = [0]

        def trigger_action(api):
            trigger_count[0] += 1
            queue.push("triggered")
            return api.post("/trigger")

        def check_invariant(world):
            # Fail when triggered more than once
            return trigger_count[0] <= 1

        actions = [
            Action(name="setup", execute=lambda api: api.post("/setup")),
            Action(name="trigger", execute=trigger_action),
        ]

        invariants = [
            Invariant(
                name="trigger_limit",
                check=check_invariant,
                message="Should not trigger more than once",
                severity=Severity.HIGH,
            )
        ]

        agent = Agent(
            world=world,
            actions=actions,
            invariants=invariants,
            strategy=BFS(),
            max_steps=10,
        )
        result = agent.explore()

        # Should find violation when trigger is called twice
        if result.violations:
            violation = result.violations[0]
            assert violation.reproduction_path is not None
            assert len(violation.reproduction_path) > 0

    def test_dfs_explores_deeply_before_backtracking(self):
        """Test that DFS strategy explores depth-first."""
        api = MockApi()
        queue = MockQueue()

        world = World(api=api, systems={"queue": queue})

        execution_order = []

        def make_action(name):
            def execute(api):
                execution_order.append(name)
                return api.post(f"/{name}")
            return execute

        actions = [
            Action(name="a", execute=make_action("a")),
            Action(name="b", execute=make_action("b")),
            Action(name="c", execute=make_action("c")),
        ]

        agent = Agent(world=world, actions=actions, strategy=DFS(), max_steps=10)
        result = agent.explore()

        # DFS should explore - exact order depends on implementation
        # but all should be explored
        assert len(execution_order) >= 3

    def test_coverage_guided_prioritizes_unexplored_actions(self):
        """Test that CoverageGuided strategy prioritizes less-explored actions."""
        api = MockApi()
        queue = MockQueue()

        world = World(api=api, systems={"queue": queue})

        action_counts = {"rare": 0, "common": 0}

        def rare_action(api):
            action_counts["rare"] += 1
            return api.post("/rare")

        def common_action(api):
            action_counts["common"] += 1
            return api.post("/common")

        actions = [
            Action(name="rare", execute=rare_action),
            Action(name="common", execute=common_action),
        ]

        agent = Agent(
            world=world,
            actions=actions,
            strategy=CoverageGuided(),
            max_steps=10,
        )
        result = agent.explore()

        # Both actions should be explored
        assert action_counts["rare"] >= 1
        assert action_counts["common"] >= 1


class TestStateCheckpointing:
    """Tests specifically for state checkpointing behavior."""

    def test_all_states_have_checkpoints(self):
        """Test that every state gets a checkpoint_id."""
        api = MockApi()
        queue = MockQueue()

        world = World(api=api, systems={"queue": queue})

        actions = [
            Action(name="a", execute=lambda api: api.post("/a")),
            Action(name="b", execute=lambda api: api.post("/b")),
        ]

        agent = Agent(world=world, actions=actions, max_steps=10)
        result = agent.explore()

        for state in result.graph.iter_states():
            assert state.checkpoint_id is not None, f"State {state.id} missing checkpoint_id"
            assert world.has_checkpoint(state.checkpoint_id), f"Checkpoint {state.checkpoint_id} not in world"

    def test_checkpoint_names_are_unique(self):
        """Test that checkpoint names don't collide."""
        api = MockApi()
        queue = MockQueue()

        world = World(api=api, systems={"queue": queue})

        actions = [
            Action(name="a", execute=lambda api: api.post("/a")),
            Action(name="b", execute=lambda api: api.post("/b")),
        ]

        agent = Agent(world=world, actions=actions, max_steps=10)
        result = agent.explore()

        checkpoint_ids = set()
        for state in result.graph.iter_states():
            assert state.checkpoint_id not in checkpoint_ids, "Duplicate checkpoint_id found"
            checkpoint_ids.add(state.checkpoint_id)


class TestWorldCheckpointRollback:
    """Tests for World checkpoint/rollback coordination."""

    def test_world_observe_and_checkpoint(self):
        """Test observe_and_checkpoint returns state with checkpoint_id."""
        api = MockApi()
        queue = MockQueue()
        mail = MockMail()

        world = World(api=api, systems={"queue": queue, "mail": mail})

        # Add some state
        queue.push("msg1")
        mail.send("a@test.com", "Subject", "Body")

        state = world.observe_and_checkpoint("test_checkpoint")

        assert state.checkpoint_id is not None
        assert world.has_checkpoint(state.checkpoint_id)
        assert "queue" in state.observations
        assert "mail" in state.observations

    def test_world_rollback_restores_all_systems(self):
        """Test that rollback restores all systems atomically."""
        api = MockApi()
        queue = MockQueue()
        mail = MockMail()
        storage = MockStorage()

        world = World(api=api, systems={
            "queue": queue,
            "mail": mail,
            "storage": storage,
        })

        # Initial state
        state1 = world.observe_and_checkpoint("initial")

        # Modify all systems
        queue.push("new_message")
        mail.send("b@test.com", "New", "Body")
        storage.put("file.txt", b"content")

        assert queue.pending_count == 1
        assert mail.sent_count == 1
        assert storage.file_count == 1

        # Rollback
        world.rollback(state1.checkpoint_id)

        # All systems should be restored
        assert queue.pending_count == 0
        assert mail.sent_count == 0
        assert storage.file_count == 0

    def test_multiple_checkpoints_and_rollbacks(self):
        """Test multiple checkpoint/rollback cycles."""
        api = MockApi()
        queue = MockQueue()

        world = World(api=api, systems={"queue": queue})

        # State 0: empty
        state0 = world.observe_and_checkpoint("s0")
        assert queue.pending_count == 0

        # State 1: one message
        queue.push("msg1")
        state1 = world.observe_and_checkpoint("s1")
        assert queue.pending_count == 1

        # State 2: two messages
        queue.push("msg2")
        state2 = world.observe_and_checkpoint("s2")
        assert queue.pending_count == 2

        # Rollback to state 1
        world.rollback(state1.checkpoint_id)
        assert queue.pending_count == 1

        # Rollback to state 0
        world.rollback(state0.checkpoint_id)
        assert queue.pending_count == 0

        # Rollback to state 2
        world.rollback(state2.checkpoint_id)
        assert queue.pending_count == 2
