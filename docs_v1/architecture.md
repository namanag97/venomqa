# Architecture

This document describes the complete VenomQA architecture, including the implementation structure, object relationships, and design decisions.

## Design Principles

1. **Rollback is central**. Everything follows from the ability to checkpoint and restore state.

2. **World is the sandbox**. All systems the Agent interacts with are contained in the World.

3. **Graph-first exploration**. The Agent explores a state graph, not a linear sequence.

4. **Invariants are the oracle**. We know something is wrong when an invariant fails.

5. **DSL is sugar**. The Journey DSL compiles to core primitives; it's not special.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              VENOMQA                                        │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                          USER INTERFACE                               │  │
│  │                                                                       │  │
│  │   CLI                      DSL                      Core API          │  │
│  │   venomqa run ...          Journey, Step, ...       World, Agent, ... │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    │ compiles to / uses                     │
│                                    ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                            CORE                                       │  │
│  │                                                                       │  │
│  │   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │  │
│  │   │  Agent  │  │  World  │  │  Graph  │  │ Action  │  │Invariant│   │  │
│  │   └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘   │  │
│  │        │            │            │            │            │         │  │
│  │        │            │            │            │            │         │  │
│  │   ┌────▼────┐  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐   │  │
│  │   │Strategy │  │Rollback-│  │  State  │  │ Action  │  │Violation│   │  │
│  │   │         │  │  able   │  │         │  │ Result  │  │         │   │  │
│  │   └─────────┘  └────┬────┘  └─────────┘  └─────────┘  └─────────┘   │  │
│  │                     │                                                │  │
│  └─────────────────────┼────────────────────────────────────────────────┘  │
│                        │                                                    │
│                        │ implemented by                                     │
│                        ▼                                                    │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                          ADAPTERS                                     │  │
│  │                                                                       │  │
│  │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │  │
│  │   │ Postgres │  │  Redis   │  │MockQueue │  │ MockMail │  ...       │  │
│  │   └──────────┘  └──────────┘  └──────────┘  └──────────┘            │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
venomqa/
│
├── __init__.py                 # Public API exports
│
├── core/                       # Core domain objects
│   ├── __init__.py
│   ├── state.py                # State, Observation
│   ├── action.py               # Action, ActionResult
│   ├── transition.py           # Transition
│   ├── graph.py                # Graph
│   ├── invariant.py            # Invariant, Violation, Severity
│   └── result.py               # ExplorationResult
│
├── world/                      # World and rollback
│   ├── __init__.py             # World class
│   ├── rollbackable.py         # Rollbackable protocol
│   └── checkpoint.py           # Checkpoint, SystemCheckpoint
│
├── agent/                      # Exploration
│   ├── __init__.py             # Agent class
│   ├── strategies.py           # BFS, DFS, Random, CoverageGuided
│   └── scheduler.py            # Background/CI running
│
├── adapters/                   # System implementations
│   ├── __init__.py
│   ├── http.py                 # HTTPClient (httpx-based)
│   ├── postgres.py             # PostgresAdapter
│   ├── mysql.py                # MySQLAdapter
│   ├── sqlite.py               # SQLiteAdapter
│   ├── redis.py                # RedisAdapter
│   ├── mock_queue.py           # MockQueue
│   ├── mock_mail.py            # MockMail
│   ├── mock_storage.py         # MockStorage
│   └── wiremock.py             # WireMockAdapter
│
├── dsl/                        # Journey DSL
│   ├── __init__.py             # Journey, Step, Checkpoint, Branch, Path
│   ├── compiler.py             # compile(Journey) → (Graph, Actions, Invariants)
│   └── decorators.py           # @action, @invariant
│
├── reporters/                  # Output formats
│   ├── __init__.py
│   ├── console.py              # Terminal output
│   ├── markdown.py             # Markdown report
│   ├── json.py                 # JSON export
│   └── junit.py                # JUnit XML for CI
│
└── cli/                        # Command-line interface
    ├── __init__.py
    └── main.py                 # venomqa command
```

## Object Relationships

```
                                 Agent
                                   │
                  ┌────────────────┼────────────────┐
                  │                │                │
                  ▼                ▼                ▼
                World           Graph          Invariant[]
                  │                │                │
        ┌─────────┼─────────┐      │                │
        │         │         │      │                │
        ▼         ▼         ▼      ▼                │
    APIClient  Systems  Checkpoints Transition[]    │
                  │         │      │                │
                  │         │      │                │
                  ▼         ▼      ▼                ▼
            Rollbackable Checkpoint State[] ───► Violation[]
                  │                 │
                  ▼                 │
            Observation ◄───────────┘

LEGEND:
─────────────────────────────────────────────────
Agent         : Explores, owns World/Graph/Invariants
World         : Contains API + Systems + Checkpoints
Graph         : Contains States + Transitions
Rollbackable  : Protocol for checkpoint/rollback
State         : Contains Observations from systems
Invariant     : Checks World, produces Violations
```

## Execution Flow

### 1. Initialization

```
User creates:
  - World (with API client and systems)
  - Actions (what can be done)
  - Invariants (what must be true)
  - Agent (combines all)

OR

User creates:
  - Journey (DSL)

Which compiles to:
  - Graph + Actions + Invariants

Then creates:
  - World
  - Agent
```

### 2. Exploration Loop

```python
def explore(self) -> ExplorationResult:
    # 1. Observe initial state
    initial_state = self.world.observe()
    initial_cp = self.world.checkpoint("initial")
    initial_state = replace(initial_state, checkpoint_id=initial_cp)
    self.graph.add_state(initial_state)

    # 2. Exploration loop
    while True:
        # 2a. Get unexplored (state, action) pairs
        unexplored = self.graph.get_unexplored()
        if not unexplored:
            break

        # 2b. Pick next pair
        state, action = self.strategy.pick(unexplored)

        # 2c. Rollback to state
        if state.checkpoint_id:
            self.world.rollback(state.checkpoint_id)

        # 2d. Checkpoint before action
        cp = self.world.checkpoint(f"{state.id}_{action.name}")

        # 2e. Execute action
        result = self.world.act(action)

        # 2f. Observe new state
        new_state = self.world.observe()
        new_state = replace(new_state, checkpoint_id=cp)

        # 2g. Record transition
        transition = Transition(
            from_state_id=state.id,
            action_name=action.name,
            to_state_id=new_state.id,
            result=result,
        )
        self.graph.add_state(new_state)
        self.graph.add_transition(transition)

        # 2h. Check invariants
        for invariant in self.invariants:
            if not invariant.check(self.world):
                violation = Violation(
                    invariant_name=invariant.name,
                    state=new_state,
                    action=action,
                    reproduction_path=self.graph.get_path_to(new_state.id),
                )
                self.violations.append(violation)

    # 3. Return result
    return ExplorationResult(
        graph=self.graph,
        violations=self.violations,
        ...
    )
```

### 3. Rollback Coordination

```python
class World:
    def checkpoint(self, name: str) -> CheckpointID:
        """Atomically checkpoint all systems."""
        checkpoint_id = f"cp_{uuid4().hex[:8]}"

        system_checkpoints = {}
        for sys_name, system in self.systems.items():
            system_checkpoints[sys_name] = system.checkpoint(name)

        self.checkpoints[checkpoint_id] = Checkpoint(
            id=checkpoint_id,
            name=name,
            system_checkpoints=system_checkpoints,
        )

        return checkpoint_id

    def rollback(self, checkpoint_id: CheckpointID) -> None:
        """Atomically rollback all systems."""
        checkpoint = self.checkpoints[checkpoint_id]

        for sys_name, sys_cp in checkpoint.system_checkpoints.items():
            self.systems[sys_name].rollback(sys_cp)
```

## Key Design Decisions

### 1. Why World contains both API and Systems?

The API is how we **act**. Systems are what we **observe** and **rollback**. They're different roles:

```
Agent → World.act(action) → APIClient → System Under Test
                                              │
                                    mutates   │
                                              ▼
Agent ← World.observe() ←──────────── Systems (DB, Cache, etc.)
```

The API client talks to the SUT, which mutates the systems. We observe the systems directly for state comparison.

### 2. Why Rollbackable protocol?

Different systems have different rollback mechanisms:
- PostgreSQL: savepoints
- Redis: dump/restore
- Queues: must be mocked

The protocol provides a uniform interface:

```python
class Rollbackable(Protocol):
    def checkpoint(self, name: str) -> SystemCheckpoint: ...
    def rollback(self, checkpoint: SystemCheckpoint) -> None: ...
    def observe(self) -> Observation: ...
```

### 3. Why compile Journey to Graph?

The Journey DSL is for humans. The Graph is for machines. By compiling, we:
- Keep the DSL simple
- Keep the core implementation focused
- Enable programmatic graph construction

### 4. Why check invariants after every action?

Checking frequently catches bugs at their source:

```
Action A → Invariant OK
Action B → Invariant VIOLATED ← Bug is in action B
Action C → (wouldn't detect which action caused it)
```

### 5. Why immutable State and Transition?

States and Transitions are historical records. Once observed/taken, they don't change. This:
- Simplifies reasoning
- Enables safe parallelism
- Prevents accidental mutation

## Performance Considerations

### Checkpoint Frequency

More checkpoints = more exploration paths = slower
Fewer checkpoints = less coverage = faster

**Recommendation**: Checkpoint at meaningful state transitions, not every action.

### Database Rollback

Savepoints are fast. But:
- Very deep savepoint stacks may slow down
- Large transactions may cause lock contention

**Recommendation**: Keep test databases small. Use isolated test instances.

### Redis Rollback

Dumping all keys is O(n) where n = number of keys.

**Recommendation**: Use small datasets for exploration. Or checkpoint only relevant key prefixes.

### Parallel Exploration

The Agent is single-threaded by design because:
- Rollback affects shared state
- Action ordering matters

**For parallelism**: Run multiple Agents on isolated Worlds.

## Extension Points

### Custom Strategies

```python
class MyStrategy(Strategy):
    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        # Custom logic to pick next (state, action)
        unexplored = graph.get_unexplored()
        # ... prioritize somehow ...
        return (state, action)
```

### Custom Adapters

```python
class MyDatabaseAdapter(Rollbackable):
    def checkpoint(self, name: str) -> Any:
        # Save state somehow
        ...

    def rollback(self, checkpoint: Any) -> None:
        # Restore state
        ...

    def observe(self) -> Observation:
        # Return current state
        ...
```

### Custom Reporters

```python
class MyReporter:
    def report(self, result: ExplorationResult) -> None:
        # Output in custom format
        ...
```

## Error Handling

### Action Errors

If an action fails to execute (network error, timeout):
- `ActionResult.success = False`
- `ActionResult.error` contains the error message
- The transition is still recorded
- Invariants are still checked (on the unchanged state)

### Rollback Errors

If rollback fails:
- This is a **fatal error**
- The World is in an inconsistent state
- Exploration must stop

### Invariant Errors

If an invariant check raises an exception:
- Treat as a violation
- Log the exception
- Continue exploration

## Testing VenomQA Itself

### Unit Tests

```python
def test_state_immutability():
    state = State(id="s1", observations={}, ...)
    # State should be frozen
    with pytest.raises(FrozenInstanceError):
        state.id = "s2"

def test_graph_unexplored():
    graph = Graph()
    graph.add_state(state1)
    graph.add_action(action1)

    unexplored = graph.get_unexplored()
    assert (state1, action1) in unexplored

    graph.add_transition(transition1)
    unexplored = graph.get_unexplored()
    assert (state1, action1) not in unexplored
```

### Integration Tests

```python
def test_postgres_rollback():
    adapter = PostgresAdapter("postgres://...")
    adapter.begin()

    # Initial state
    initial = adapter.observe()
    cp = adapter.checkpoint("test")

    # Modify
    adapter.execute("INSERT INTO users ...")
    modified = adapter.observe()
    assert modified != initial

    # Rollback
    adapter.rollback(cp)
    restored = adapter.observe()
    assert restored == initial

    adapter.end()
```

### End-to-End Tests

```python
def test_full_exploration():
    world = World(
        api=HttpClient("http://localhost:8000"),
        systems={"db": PostgresAdapter("postgres://...")},
    )

    actions = [action1, action2, action3]
    invariants = [invariant1]

    agent = Agent(world, actions, invariants)
    result = agent.explore()

    assert result.states_visited > 0
    assert result.transitions_taken > 0
```
