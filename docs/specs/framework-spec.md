# Framework Specification

Technical specification of VenomQA's architecture, core abstractions, and extension points.

## Overview

VenomQA is a state exploration framework for testing APIs through sequences of operations. It uses database rollback to enable exhaustive exploration of state graphs.

## Core Abstractions

### Action

An `Action` represents a single API operation.

```python
@dataclass
class Action:
    name: str                              # Unique identifier
    execute: Callable[[Any, Context], Any] # (api, context) -> response
    preconditions: list[str] | None        # Required prior actions
    max_calls: int | None                  # Max calls per state
    requires: dict[str, str] | None        # Resource requirements
    
    def __call__(self, api, context) -> ActionResult:
        """Execute the action and return result."""
        ...
    
    def can_execute(self, state: State) -> bool:
        """Check if action is valid in this state."""
        ...
```

**Semantics:**

- `execute` receives the API client and shared context
- Returns `None` to skip execution (precondition not met)
- `preconditions` are action names that must have been executed
- `max_calls` limits repetitions to prevent infinite loops

### Invariant

An `Invariant` is a property that must always hold.

```python
@dataclass
class Invariant:
    name: str                              # Unique identifier
    check: Callable[[World], bool | str]   # (world) -> passed | error_message
    severity: Severity                     # CRITICAL, HIGH, MEDIUM, LOW
    timing: InvariantTiming                # PRE_ACTION, POST_ACTION, BOTH
    
    def __call__(self, world: World) -> bool | str:
        """Check the invariant. Return True, False, or error message."""
        ...
```

**Severities:**

| Level | Meaning |
|-------|---------|
| CRITICAL | System-breaking bugs, security issues |
| HIGH | Data corruption, business logic failures |
| MEDIUM | Minor inconsistencies, edge cases |
| LOW | Style issues, performance problems |

**Timings:**

| Timing | When Checked |
|--------|--------------|
| PRE_ACTION | Before action execution |
| POST_ACTION | After action + state observation |
| BOTH | Both times |

### World

The `World` is the sandbox containing all state and systems.

```python
@dataclass
class World:
    api: HttpClient                        # HTTP client
    context: Context                       # Key-value store
    systems: dict[str, Rollbackable]       # External systems
    resources: ResourceGraph | None        # Resource dependencies
    
    def checkpoint(self, name: str) -> Checkpoint:
        """Save state of all systems."""
        ...
    
    def rollback(self, checkpoint: Checkpoint) -> None:
        """Restore all systems to checkpoint state."""
        ...
    
    def observe(self) -> Observation:
        """Observe current state of all systems."""
        ...
    
    def act(self, action: Action) -> ActionResult:
        """Execute an action and observe new state."""
        ...
```

**Construction:**

```python
# With database adapter
world = World(
    api=HttpClient("http://localhost:8000"),
    systems={"db": PostgresAdapter("postgresql://...")},
)

# Without database (context-only state)
world = World(
    api=HttpClient("http://localhost:8000"),
    state_from_context=["user_id", "order_id"],
)
```

### Context

The `Context` is a key-value store for passing data between actions.

```python
class Context:
    def get(self, key: str, default: Any = None) -> Any:
        """Get value by key."""
        ...
    
    def set(self, key: str, value: Any) -> None:
        """Set a value."""
        ...
    
    def delete(self, key: str) -> None:
        """Delete a key."""
        ...
    
    def has(self, key: str) -> bool:
        """Check if key exists."""
        ...
    
    def keys(self) -> list[str]:
        """Get all keys."""
        ...
    
    def to_dict(self) -> dict[str, Any]:
        """Export as dictionary."""
        ...
```

**Checkpoint behavior:** Context is automatically checkpointed and rolled back with the World.

### State

A `State` represents a unique point in the exploration graph.

```python
@dataclass
class State:
    id: str                           # Hash of observations
    observations: list[Observation]   # System states
    checkpoint_id: str | None         # For rollback
    created_at: datetime              # When discovered
```

**State identity:** Two states are considered identical if their observations hash to the same value.

### Observation

An `Observation` captures a system's state at a point in time.

```python
@dataclass
class Observation:
    system: str              # System identifier
    data: dict[str, Any]     # State data (counts, flags, etc.)
    metadata: dict           # Non-hashed metadata
```

**Hashing:** Only `system` and `data` participate in state hashing. `metadata` is for debugging.

### Graph

The `Graph` stores the exploration state space.

```python
class Graph:
    states: dict[str, State]
    transitions: list[Transition]
    actions: dict[str, Action]
    initial_state_id: str | None
    
    def add_state(self, state: State) -> State:
        """Add state, return canonical (may be deduplicated)."""
        ...
    
    def add_transition(self, transition: Transition) -> None:
        """Record a state transition."""
        ...
    
    def get_valid_actions(self, state: State) -> list[Action]:
        """Get actions valid from this state."""
        ...
    
    def get_unexplored(self) -> list[tuple[State, Action]]:
        """Get unexplored (state, action) pairs."""
        ...
    
    def is_explored(self, state_id: str, action_name: str) -> bool:
        """Check if a pair has been explored."""
        ...
```

### Transition

A `Transition` records moving from one state to another via an action.

```python
@dataclass
class Transition:
    from_state_id: str
    action_name: str
    to_state_id: str
    result: ActionResult
    timestamp: datetime
```

### Agent

The `Agent` orchestrates exploration.

```python
class Agent:
    world: World
    graph: Graph
    strategy: Strategy
    invariants: list[Invariant]
    max_steps: int
    
    def explore(self) -> ExplorationResult:
        """Run exploration and return results."""
        ...
```

## Extension Points

### Custom Strategies

Implement the `ExplorationStrategy` protocol:

```python
class ExplorationStrategy(Protocol):
    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        """Pick next (state, action) to explore, or None if done."""
        ...
    
    def notify(self, state: State, actions: list[Action]) -> None:
        """Called when new state is discovered."""
        ...
```

### Custom System Adapters

Implement the `Rollbackable` protocol:

```python
class Rollbackable(Protocol):
    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Save current state."""
        ...
    
    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore to checkpoint."""
        ...
    
    def observe(self) -> Observation:
        """Get current state for hashing."""
        ...
```

### Custom Reporters

Implement a callable that accepts `ExplorationResult`:

```python
def my_reporter(result: ExplorationResult) -> str:
    return f"Found {len(result.violations)} violations"
```

## Exploration Algorithm

```
1. Initialize
   - Run user setup hook
   - Observe initial state with checkpoint
   
2. While unexplored pairs exist and max_steps not reached:
   a. Pick (state, action) via strategy
   b. Rollback to state
   c. Check PRE_ACTION invariants
   d. Execute action
   e. Observe new state with checkpoint
   f. Record transition
   g. Check POST_ACTION invariants
   h. Notify strategy of new state
   
3. Return results
   - All violations found
   - Graph of explored states
   - Coverage statistics
```

## State Hashing

States are hashed based on observations:

```python
def hash_state(observations: list[Observation]) -> str:
    """Generate deterministic hash for state identity."""
    data = sorted(
        (obs.system, json.dumps(obs.data, sort_keys=True))
        for obs in observations
    )
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()[:16]
```

**Implications:**

- Identical observations = identical state ID
- State deduplication happens automatically
- Order of observations doesn't matter

## Checkpoint/Rollback Semantics

### PostgreSQL

```sql
-- Checkpoint
SAVEPOINT venom_checkpoint_N;

-- Rollback
ROLLBACK TO SAVEPOINT venom_checkpoint_N;
```

**Constraints:**

- SAVEPOINTs are stack-based (LIFO)
- Rolling back to an earlier savepoint destroys later savepoints
- Must use DFS strategy with PostgresAdapter

### SQLite

```python
# Checkpoint
snapshot = shutil.copy(db_path, temp_path)

# Rollback  
shutil.copy(temp_path, db_path)
```

### In-Memory

```python
# Checkpoint
snapshot = copy.deepcopy(self._state)

# Rollback
self._state = snapshot
```

## Thread Safety

VenomQA is **not** thread-safe by default.

- Single-threaded exploration is guaranteed safe
- Parallel exploration requires separate `World` instances
- Database connections should not be shared between agents

## Memory Model

| Component | Lifetime | Memory |
|-----------|----------|--------|
| World | Per exploration | ~10-100MB |
| Context | Per exploration | ~1-10MB |
| Graph | Per exploration | ~10-500MB |
| State | Collected at end | ~1KB each |
| Transition | Collected at end | ~100 bytes each |

## Error Handling

### Action Errors

```python
try:
    result = action(api, context)
except Exception as e:
    result = ActionResult(error=e)
```

Actions that raise exceptions are recorded as failed transitions.

### Invariant Errors

```python
try:
    passed = invariant(world)
    if not passed:
        record_violation(invariant)
except Exception as e:
    # Invariant itself failed - treat as violation
    record_violation(invariant, error=e)
```

### System Errors

```python
try:
    checkpoint = system.checkpoint(name)
except Exception:
    # Can't checkpoint - exploration may be incomplete
    log_warning("Checkpoint failed, state rollback unavailable")
```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `VENOMQA_API_KEY` | X-API-Key header |
| `VENOMQA_AUTH_TOKEN` | Bearer token |
| `VENOMQA_LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING) |

### CLI Options

```bash
venomqa explore \
    --strategy dfs \
    --max-steps 500 \
    --coverage-target 0.8 \
    --output results.json \
    --format json
```

## Version Compatibility

| Version | Python | Key Changes |
|---------|--------|-------------|
| 0.6.x | 3.10+ | Current stable |
| 0.5.x | 3.9+ | Added MCTS strategy |
| 0.4.x | 3.9+ | Added SQLite adapter |
| 0.3.x | 3.8+ | Initial release |

## Deprecation Policy

- Features deprecated for 2 minor versions before removal
- Deprecation warnings via Python `warnings` module
- Breaking changes only in major versions
