"""Integration test: all 4 mock adapters used together in one exploration."""

from __future__ import annotations

import json

from venomqa.v1 import (
    Action,
    ActionResult,
    Agent,
    HTTPRequest,
    HTTPResponse,
    Invariant,
    Severity,
    World,
)
from venomqa.v1.adapters.mock_mail import MockMail
from venomqa.v1.adapters.mock_queue import MockQueue
from venomqa.v1.adapters.mock_storage import MockStorage
from venomqa.v1.adapters.mock_time import MockTime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(method: str, url: str, body: object = None) -> ActionResult:
    return ActionResult.from_response(
        request=HTTPRequest(method=method, url=url, body=body),
        response=HTTPResponse(status_code=200, body=body),
    )


def _fail(method: str, url: str, status: int = 400) -> ActionResult:
    return ActionResult.from_response(
        request=HTTPRequest(method=method, url=url),
        response=HTTPResponse(status_code=status),
    )


# ---------------------------------------------------------------------------
# A toy "order processing" system using all 4 adapters
# ---------------------------------------------------------------------------

def make_actions(queue: MockQueue, mail: MockMail, storage: MockStorage, clock: MockTime):
    """Return a list of actions that exercise every mock adapter."""

    def place_order(api):
        # clock.now is a property (not a method)
        order_id = f"order-{clock.now.isoformat()}"
        queue.push({"order_id": order_id, "status": "pending"})
        # MockStorage.put() requires str/bytes content — use JSON
        storage.put(
            f"orders/{order_id}.json",
            json.dumps({"id": order_id, "status": "pending"}),
            content_type="application/json",
        )
        mail.send(
            to="customer@example.com",
            subject="Order placed",
            body=f"Your order {order_id} has been placed.",
        )
        return _ok("POST", "/orders", {"id": order_id})

    def process_order(api):
        msg = queue.pop()
        if msg is None:
            return _fail("POST", "/orders/process", 422)
        order_id = msg.payload["order_id"]
        storage.put(
            f"orders/{order_id}.json",
            json.dumps({"id": order_id, "status": "processed"}),
            content_type="application/json",
        )
        mail.send(
            to="customer@example.com",
            subject="Order processed",
            body=f"Order {order_id} has been processed.",
        )
        return _ok("POST", f"/orders/{order_id}/process")

    def advance_time(api):
        # Must freeze before advancing
        if not clock._frozen:
            clock.freeze()
        clock.advance(hours=1)
        return _ok("POST", "/time/advance")

    def list_orders(api):
        paths = storage.list("orders/")
        return _ok("GET", "/orders", paths)

    return [
        Action(name="place_order", execute=place_order),
        Action(name="process_order", execute=process_order),
        Action(name="advance_time", execute=advance_time),
        Action(name="list_orders", execute=list_orders),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAllMockAdaptersTogether:
    """Verify that all 4 mock adapters work together in a single World."""

    def setup_method(self):
        self.queue = MockQueue(name="orders")
        self.mail = MockMail()
        self.storage = MockStorage()
        self.clock = MockTime()

        self.world = World(
            api=None,  # No real HTTP client needed
            systems={
                "queue": self.queue,
                "mail": self.mail,
                "storage": self.storage,
                "clock": self.clock,
            },
        )
        self.actions = make_actions(self.queue, self.mail, self.storage, self.clock)

    def test_initial_state_all_adapters_empty(self):
        """State observations are keyed by the system name in World.systems."""
        state = self.world.observe()
        # State.observations keys match World.systems keys
        assert state.get_observation("queue") is not None
        assert state.get_observation("mail") is not None
        assert state.get_observation("storage") is not None
        assert state.get_observation("clock") is not None

        q_obs = state.get_observation("queue")
        assert q_obs.get("pending") == 0
        assert q_obs.get("total") == 0

        m_obs = state.get_observation("mail")
        assert m_obs.get("sent_count") == 0

        s_obs = state.get_observation("storage")
        assert s_obs.get("file_count") == 0

    def test_place_order_updates_all_adapters(self):
        action = next(a for a in self.actions if a.name == "place_order")
        action.execute(None)

        assert self.queue.pending_count == 1
        assert self.mail.sent_count == 1
        assert self.mail.get_sent()[0].subject == "Order placed"
        assert self.storage.file_count == 1

    def test_process_order_consumes_queue_and_sends_email(self):
        place = next(a for a in self.actions if a.name == "place_order")
        process = next(a for a in self.actions if a.name == "process_order")

        place.execute(None)
        result = process.execute(None)

        assert result.response.ok
        assert self.queue.pending_count == 0
        assert self.queue.processed_count == 1
        assert self.mail.sent_count == 2  # placed + processed

    def test_rollback_restores_all_adapters(self):
        # Checkpoint before placing any order
        cp = self.world.checkpoint("before_order")

        place = next(a for a in self.actions if a.name == "place_order")
        place.execute(None)

        assert self.queue.pending_count == 1
        assert self.storage.file_count == 1
        assert self.mail.sent_count == 1

        # Rollback — everything should be restored
        self.world.rollback(cp)

        assert self.queue.pending_count == 0
        assert self.storage.file_count == 0
        assert self.mail.sent_count == 0

    def test_clock_advances_and_rolls_back(self):
        self.clock.freeze()
        t0 = self.clock.now
        cp = self.world.checkpoint("t0")

        adv = next(a for a in self.actions if a.name == "advance_time")
        adv.execute(None)

        assert self.clock.now > t0

        self.world.rollback(cp)
        assert self.clock.now == t0

    def test_full_exploration_no_violations(self):
        """Agent explores the combined system and finds no violations."""

        def queue_consistency(world):
            q_obs = world.observe().get_observation("queue")
            if q_obs is None:
                return True
            return q_obs.get("total", 0) >= q_obs.get("processed", 0)

        inv = Invariant(
            name="queue_total_gte_processed",
            check=queue_consistency,
            severity=Severity.HIGH,
        )

        agent = Agent(
            world=self.world,
            actions=self.actions,
            invariants=[inv],
            max_steps=20,
        )
        result = agent.explore()

        assert result.states_visited >= 1
        assert result.transitions_taken >= 1
        assert result.success, f"Violations: {[v.invariant_name for v in result.violations]}"

    def test_exploration_with_all_adapters_observes_each_system(self):
        """After exploration each state has observations from all 4 systems."""
        agent = Agent(world=self.world, actions=self.actions, max_steps=10)
        result = agent.explore()

        for state in result.graph.states.values():
            obs_systems = set(state.observations.keys())
            assert "queue" in obs_systems
            assert "mail" in obs_systems
            assert "storage" in obs_systems
            assert "clock" in obs_systems

    def test_process_without_placing_returns_failure(self):
        """process_order on empty queue returns 422."""
        process = next(a for a in self.actions if a.name == "process_order")
        result = process.execute(None)
        assert result.response.status_code == 422

    def test_multiple_rollback_restore_sequence(self):
        """Multiple checkpoint / rollback cycles remain consistent."""
        place = next(a for a in self.actions if a.name == "place_order")
        process = next(a for a in self.actions if a.name == "process_order")

        cp0 = self.world.checkpoint("empty")
        place.execute(None)  # 1 pending

        cp1 = self.world.checkpoint("one_pending")
        process.execute(None)  # 0 pending, 1 processed

        cp2 = self.world.checkpoint("processed")

        # Roll back to one_pending
        self.world.rollback(cp1)
        assert self.queue.pending_count == 1
        assert self.queue.processed_count == 0

        # Roll forward to empty
        self.world.rollback(cp0)
        assert self.queue.pending_count == 0
        assert self.queue.processed_count == 0

        # Roll to processed
        self.world.rollback(cp2)
        assert self.queue.pending_count == 0
        assert self.queue.processed_count == 1

    def test_storage_contents_rolled_back(self):
        place = next(a for a in self.actions if a.name == "place_order")
        process = next(a for a in self.actions if a.name == "process_order")

        cp0 = self.world.checkpoint("start")
        place.execute(None)
        process.execute(None)

        # After process, a file exists
        paths = self.storage.list("orders/")
        assert len(paths) == 1
        file_obj = self.storage.get(paths[0])
        content = json.loads(file_obj.content)
        assert content["status"] == "processed"

        self.world.rollback(cp0)
        assert self.storage.file_count == 0

    def test_mail_inbox_rolled_back(self):
        place = next(a for a in self.actions if a.name == "place_order")

        cp = self.world.checkpoint("no_mail")
        place.execute(None)
        assert self.mail.sent_count == 1

        self.world.rollback(cp)
        assert self.mail.sent_count == 0

    def test_invariant_detects_queue_inconsistency(self):
        """An invariant that intentionally fails is caught by the agent."""

        never_ok = Invariant(
            name="always_fails",
            check=lambda world: False,
            severity=Severity.CRITICAL,
            message="Forced violation for testing",
        )

        agent = Agent(
            world=self.world,
            actions=self.actions[:1],  # only place_order
            invariants=[never_ok],
            max_steps=5,
        )
        result = agent.explore()
        assert not result.success
        assert len(result.violations) > 0
        assert result.violations[0].invariant_name == "always_fails"
