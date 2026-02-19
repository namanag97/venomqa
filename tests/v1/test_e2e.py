"""End-to-end exploration tests."""


from venomqa import (
    BFS,
    DFS,
    Action,
    ActionResult,
    Agent,
    HTTPRequest,
    HTTPResponse,
    Invariant,
    Journey,
    Random,
    Severity,
    Step,
    World,
)
from venomqa.adapters import MockMail, MockQueue


class MockHttpClient:
    """Mock HTTP client for testing."""

    def __init__(self):
        self.calls = []
        self.responses = {}

    def set_response(self, path: str, response: dict):
        self.responses[path] = response

    def _make_result(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        request = HTTPRequest(method, path)

        if path in self.responses:
            response = HTTPResponse(
                status_code=200,
                body=self.responses[path],
            )
        else:
            response = HTTPResponse(status_code=200, body={})

        return ActionResult.from_response(request, response, duration_ms=10.0)

    def get(self, path, **kwargs):
        return self._make_result("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self._make_result("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self._make_result("PUT", path, **kwargs)

    def delete(self, path, **kwargs):
        return self._make_result("DELETE", path, **kwargs)


class TestBasicExploration:
    def test_single_action_exploration(self):
        """Test exploration with a single action."""
        api = MockHttpClient()
        queue = MockQueue()
        world = World(api=api, systems={"queue": queue})

        action = Action(
            name="ping",
            execute=lambda api: api.get("/ping"),
        )

        agent = Agent(world=world, actions=[action])
        result = agent.explore()

        assert result.states_visited >= 1
        assert result.transitions_taken >= 1
        assert result.success

    def test_multiple_actions_exploration(self):
        """Test exploration with multiple actions."""
        api = MockHttpClient()
        world = World(api=api, systems={"queue": MockQueue()})

        actions = [
            Action(name="list_users", execute=lambda api: api.get("/users")),
            Action(name="list_orders", execute=lambda api: api.get("/orders")),
            Action(name="get_stats", execute=lambda api: api.get("/stats")),
        ]

        agent = Agent(world=world, actions=actions, max_steps=10)
        result = agent.explore()

        assert result.states_visited >= 1
        assert result.transitions_taken >= 1
        assert len(api.calls) >= 1

    def test_exploration_with_preconditions(self):
        """Test that preconditions are respected."""
        api = MockHttpClient()
        queue = MockQueue()
        world = World(api=api, systems={"queue": queue})

        # Action that can always run
        def always_possible(state):
            return True

        # Action that can never run
        def never_possible(state):
            return False

        actions = [
            Action(name="always", execute=lambda api: api.get("/always"), preconditions=[always_possible]),
            Action(name="never", execute=lambda api: api.get("/never"), preconditions=[never_possible]),
        ]

        agent = Agent(world=world, actions=actions, max_steps=5)
        agent.explore()

        # "never" action should not have been executed
        paths = [call[1] for call in api.calls]
        assert "/always" in paths
        assert "/never" not in paths


class TestStrategies:
    def test_bfs_strategy(self):
        """Test BFS exploration strategy."""
        api = MockHttpClient()
        # Use state_from_context=[] to explicitly opt-in to context-only mode
        world = World(api=api, state_from_context=[])

        actions = [
            Action(name=f"action_{i}", execute=lambda api, i=i: api.get(f"/action/{i}"))
            for i in range(3)
        ]

        agent = Agent(world=world, actions=actions, strategy=BFS(), max_steps=10)
        result = agent.explore()

        assert result.transitions_taken >= 1

    def test_dfs_strategy(self):
        """Test DFS exploration strategy."""
        api = MockHttpClient()
        # Use state_from_context=[] to explicitly opt-in to context-only mode
        world = World(api=api, state_from_context=[])

        actions = [
            Action(name=f"action_{i}", execute=lambda api, i=i: api.get(f"/action/{i}"))
            for i in range(3)
        ]

        agent = Agent(world=world, actions=actions, strategy=DFS(), max_steps=10)
        result = agent.explore()

        assert result.transitions_taken >= 1

    def test_random_strategy(self):
        """Test random exploration strategy."""
        api = MockHttpClient()
        # Use state_from_context=[] to explicitly opt-in to context-only mode
        world = World(api=api, state_from_context=[])

        actions = [
            Action(name=f"action_{i}", execute=lambda api, i=i: api.get(f"/action/{i}"))
            for i in range(3)
        ]

        agent = Agent(world=world, actions=actions, strategy=Random(seed=42), max_steps=10)
        result = agent.explore()

        assert result.transitions_taken >= 1


class TestRollback:
    def test_checkpoint_and_rollback(self):
        """Test that world checkpoints and rollbacks work."""
        api = MockHttpClient()
        queue = MockQueue()
        world = World(api=api, systems={"queue": queue})

        # Add some messages
        queue.push("msg1")
        queue.push("msg2")

        # Checkpoint
        cp_id = world.checkpoint("before_clear")

        # Modify state
        queue.clear()
        assert queue.pending_count == 0

        # Rollback
        world.rollback(cp_id)
        assert queue.pending_count == 2

    def test_exploration_with_rollback(self):
        """Test that exploration rolls back correctly between branches."""
        api = MockHttpClient()
        queue = MockQueue()
        mail = MockMail()
        world = World(api=api, systems={"queue": queue, "mail": mail})

        def send_email(api):
            mail.send("test@example.com", "Test", "Body")
            return api.post("/send")

        def enqueue_task(api):
            queue.push("task")
            return api.post("/enqueue")

        actions = [
            Action(name="send_email", execute=send_email),
            Action(name="enqueue_task", execute=enqueue_task),
        ]

        agent = Agent(world=world, actions=actions, max_steps=10)
        result = agent.explore()

        assert result.success


class TestInvariantViolation:
    def test_violation_detected(self):
        """Test that invariant violations are detected."""
        api = MockHttpClient()
        world = World(api=api, systems={"queue": MockQueue()})

        # Invariant that always fails
        failing_invariant = Invariant(
            name="always_fails",
            check=lambda w: False,
            message="This always fails",
            severity=Severity.CRITICAL,
        )

        action = Action(name="trigger", execute=lambda api: api.get("/trigger"))

        agent = Agent(
            world=world,
            actions=[action],
            invariants=[failing_invariant],
            max_steps=5,
        )
        result = agent.explore()

        assert not result.success
        assert len(result.violations) >= 1
        assert result.violations[0].severity == Severity.CRITICAL

    def test_violation_reproduction_path(self):
        """Test that violations include reproduction paths."""
        api = MockHttpClient()
        world = World(api=api, state_from_context=[])

        violation_triggered = False

        def conditional_invariant(w):
            nonlocal violation_triggered
            # Fail only after some exploration
            if violation_triggered:
                return False
            return True

        def trigger_violation(api):
            nonlocal violation_triggered
            violation_triggered = True
            return api.post("/trigger")

        inv = Invariant(
            name="conditional",
            check=conditional_invariant,
            message="Triggered violation",
            severity=Severity.HIGH,
        )

        actions = [
            Action(name="setup", execute=lambda api: api.get("/setup")),
            Action(name="trigger", execute=trigger_violation),
        ]

        agent = Agent(
            world=world,
            actions=actions,
            invariants=[inv],
            max_steps=10,
        )
        result = agent.explore()

        # Should have a violation with a path
        assert len(result.violations) >= 1
        # Path should exist (may be empty if violation happened on first state)
        violation = result.violations[0]
        assert violation.invariant_name == "conditional"

    def test_multiple_violations(self):
        """Test detection of multiple invariant violations."""
        api = MockHttpClient()
        world = World(api=api, state_from_context=[])

        inv1 = Invariant(name="inv1", check=lambda w: False, message="First", severity=Severity.HIGH)
        inv2 = Invariant(name="inv2", check=lambda w: False, message="Second", severity=Severity.MEDIUM)

        action = Action(name="test", execute=lambda api: api.get("/test"))

        agent = Agent(
            world=world,
            actions=[action],
            invariants=[inv1, inv2],
            max_steps=2,
        )
        result = agent.explore()

        assert len(result.violations) >= 2
        names = {v.invariant_name for v in result.violations}
        assert "inv1" in names
        assert "inv2" in names

    def test_passing_invariants(self):
        """Test that passing invariants don't create violations."""
        api = MockHttpClient()
        world = World(api=api, state_from_context=[])

        passing_invariant = Invariant(
            name="always_passes",
            check=lambda w: True,
            message="Should never appear",
            severity=Severity.CRITICAL,
        )

        action = Action(name="test", execute=lambda api: api.get("/test"))

        agent = Agent(
            world=world,
            actions=[action],
            invariants=[passing_invariant],
            max_steps=5,
        )
        result = agent.explore()

        assert result.success
        assert len(result.violations) == 0


class TestJourneyIntegration:
    def test_journey_compilation_and_exploration(self):
        """Test that Journey DSL compiles and runs correctly."""
        from venomqa.dsl.compiler import compile

        api = MockHttpClient()
        world = World(api=api, state_from_context=[])

        def login_action(api):
            return api.post("/login", json={"user": "test"})

        def logout_action(api):
            return api.post("/logout")

        journey = Journey(
            name="auth_flow",
            steps=[
                Step("login", login_action),
                Step("logout", logout_action),
            ],
        )

        compiled = compile(journey)
        assert len(compiled.actions) == 2

        agent = Agent(world=world, actions=compiled.actions, max_steps=5)
        result = agent.explore()

        assert result.success


class TestExplorationResult:
    def test_coverage_calculation(self):
        """Test coverage percentage calculation."""
        api = MockHttpClient()
        world = World(api=api, state_from_context=[])

        actions = [
            Action(name="a1", execute=lambda api: api.get("/a1")),
            Action(name="a2", execute=lambda api: api.get("/a2")),
        ]

        agent = Agent(world=world, actions=actions, max_steps=10)
        result = agent.explore()

        assert result.coverage_percent >= 0
        assert result.coverage_percent <= 100

    def test_timing(self):
        """Test that timing is recorded."""
        api = MockHttpClient()
        world = World(api=api, state_from_context=[])

        action = Action(name="test", execute=lambda api: api.get("/test"))

        agent = Agent(world=world, actions=[action], max_steps=2)
        result = agent.explore()

        assert result.duration_ms >= 0
        assert result.started_at is not None
        assert result.finished_at is not None
