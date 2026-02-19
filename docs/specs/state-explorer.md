# State Explorer Specification

Specification of the exploration algorithms (BFS, DFS, CoverageGuided, Random, MCTS), their guarantees and tradeoffs.

## Overview

The state explorer decides which (state, action) pairs to try next. Different strategies optimize for different goals: shortest bug reproduction, maximum coverage, or deep exploration.

## Exploration Strategy Protocol

All strategies implement the `ExplorationStrategy` protocol:

```python
class ExplorationStrategy(Protocol):
    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        """Pick next (state, action) to explore.
        
        Returns:
            Tuple to explore, or None if exploration is complete.
        """
        ...
    
    def notify(self, state: State, actions: list[Action]) -> None:
        """Notify strategy of a newly discovered state.
        
        Args:
            state: The newly discovered state.
            actions: Actions valid from this state.
        """
        ...
```

## Built-in Strategies

### BFS (Breadth-First Search)

Explores states in the order they were discovered.

```python
class BFS:
    """Breadth-first exploration.
    
    Guarantees shortest paths to each state.
    Uses a queue-based frontier.
    """
    
    def __init__(self):
        self._frontier = QueueFrontier()  # FIFO queue
```

**Characteristics:**

| Property | Value |
|----------|-------|
| Memory | O(states × actions) |
| Path length | Minimal to each state |
| Best for | Shortest bug reproduction |
| PostgreSQL | ❌ Incompatible |

**Algorithm:**

```
1. Initialize queue with (initial_state, action) for all valid actions
2. While queue not empty:
   a. Dequeue (state, action)
   b. If already explored, skip
   c. Execute action, observe new state
   d. Enqueue (new_state, action) for all valid actions
3. Return when queue empty
```

**Example trace:**

```
Queue: [(S0, a1), (S0, a2)]
→ Execute (S0, a1) → S1
Queue: [(S0, a2), (S1, a3), (S1, a4)]
→ Execute (S0, a2) → S2
Queue: [(S1, a3), (S1, a4), (S2, a5)]
```

### DFS (Depth-First Search)

Explores as deep as possible before backtracking.

```python
class DFS:
    """Depth-first exploration.
    
    Explores deeply before backtracking.
    Uses less memory than BFS.
    """
    
    def __init__(self):
        self._frontier = StackFrontier()  # LIFO stack
```

**Characteristics:**

| Property | Value |
|----------|-------|
| Memory | O(depth × actions) |
| Path length | May be long |
| Best for | PostgreSQL, deep bugs |
| PostgreSQL | ✅ Compatible |

**Algorithm:**

```
1. Initialize stack with (initial_state, action) for all valid actions
2. While stack not empty:
   a. Pop (state, action)
   b. If already explored, skip
   c. Execute action, observe new state
   d. Push (new_state, action) for all valid actions
3. Return when stack empty
```

**Example trace:**

```
Stack: [(S0, a1), (S0, a2)]
→ Execute (S0, a2) → S2  (LIFO: takes last added)
Stack: [(S0, a1), (S2, a5)]
→ Execute (S2, a5) → S3
Stack: [(S0, a1), (S3, a6)]
```

### Random

Picks randomly from unexplored pairs.

```python
class Random:
    """Random exploration.
    
    Picks uniformly from unexplored pairs.
    Reproducible with seed.
    """
    
    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
```

**Characteristics:**

| Property | Value |
|----------|-------|
| Memory | O(1) for selection |
| Path length | Unpredictable |
| Best for | Fuzzing, surprise bugs |
| PostgreSQL | ⚠️ Use with caution |

**Algorithm:**

```
1. Get all unexplored (state, action) pairs
2. Pick one uniformly at random
3. Return None if no unexplored pairs remain
```

### CoverageGuided

Prioritizes least-explored actions.

```python
class CoverageGuided:
    """Coverage-guided exploration.
    
    Maximizes action diversity by prioritizing
    actions that have been explored the fewest times.
    """
    
    def __init__(self):
        self._action_counts: Counter[str] = Counter()
```

**Characteristics:**

| Property | Value |
|----------|-------|
| Memory | O(actions) for counts |
| Coverage | Maximizes action diversity |
| Best for | Maximum coverage |
| PostgreSQL | ❌ Incompatible |

**Algorithm:**

```
1. Get all unexplored (state, action) pairs
2. Count how many times each action has been executed
3. Sort pairs by action count (ascending)
4. Return pair with least-executed action
```

**Example:**

```
Action counts: {a1: 5, a2: 3, a3: 1, a4: 8}
Unexplored pairs: [(S1, a1), (S2, a2), (S3, a3)]
→ Sort by count: [(S3, a3), (S2, a2), (S1, a1)]
→ Return (S3, a3)  # a3 has count 1
```

### Weighted

Random selection with configurable weights.

```python
class Weighted:
    """Weighted random exploration.
    
    Actions with higher weights are more likely to be picked.
    """
    
    def __init__(
        self,
        weights: dict[str, float] | None = None,
        seed: int | None = None,
    ):
        self._weights = weights or {}
        self._rng = random.Random(seed)
```

**Characteristics:**

| Property | Value |
|----------|-------|
| Memory | O(actions) for weights |
| Control | Manual priority |
| Best for | Focused testing |
| PostgreSQL | ⚠️ Use with caution |

**Algorithm:**

```
1. Get all unexplored (state, action) pairs
2. For each pair, look up weight (default: 1.0)
3. Weighted random selection
4. Return selected pair
```

**Example:**

```python
strategy = Weighted(weights={
    "login": 1.0,
    "create_order": 3.0,  # 3x more likely
    "refund": 2.0,
})
```

### MCTS (Monte Carlo Tree Search)

Uses UCB1 to balance exploration and exploitation.

```python
class MCTS:
    """Monte Carlo Tree Search exploration.
    
    Balances exploring new areas vs exploiting
    paths that led to violations.
    """
    
    def __init__(
        self,
        exploration_weight: float = math.sqrt(2),
        violation_reward: float = 10.0,
        new_state_reward: float = 1.0,
        seed: int | None = None,
    ):
        ...
```

**Characteristics:**

| Property | Value |
|----------|-------|
| Memory | O(states × actions) for tree |
| Bug focus | Learns to find bugs |
| Best for | Bug-heavy state spaces |
| PostgreSQL | ⚠️ Use with caution |

**Algorithm:**

```
1. Selection:
   - Start from root
   - Use UCB1 to pick most promising child
   - Repeat until reaching unexplored node

2. Expansion:
   - Add unexplored children to tree

3. Simulation:
   - (Lightweight) Evaluate node's potential

4. Backpropagation:
   - Update visit counts and rewards up tree
   - Violations give high reward
```

**UCB1 Formula:**

```
UCB1 = (reward / visits) + C × sqrt(ln(total_visits) / visits)

Where:
- reward: Accumulated reward for this node
- visits: Number of times this node was visited
- total_visits: Total visits across all nodes
- C: exploration_weight (default: sqrt(2))
```

## Strategy Comparison

| Strategy | Memory | Coverage | Bug Speed | PostgreSQL |
|----------|--------|----------|-----------|------------|
| BFS | High | Full | Fast (short paths) | ❌ |
| DFS | Low | Full | Medium | ✅ |
| Random | Low | Partial | Variable | ⚠️ |
| CoverageGuided | Low | Maximum | Medium | ❌ |
| Weighted | Low | Focused | Variable | ⚠️ |
| MCTS | Medium | Smart | Fast (if bugs exist) | ⚠️ |

## Guarantees

### BFS Guarantees

1. **Completeness:** Explores all reachable states
2. **Optimality:** Shortest path to each state
3. **Termination:** Terminates if state space is finite

### DFS Guarantees

1. **Completeness:** Explores all reachable states
2. **PostgreSQL compatible:** Safe with savepoint semantics
3. **Low memory:** Only stores current path + siblings

### Random Guarantees

1. **Coverage:** Eventually covers all pairs (with enough steps)
2. **No bias:** Uniform exploration
3. **Reproducibility:** Same seed = same exploration

### CoverageGuided Guarantees

1. **Action coverage:** Prioritizes under-explored actions
2. **Fairness:** All actions get explored eventually
3. **Completeness:** Explores all reachable states

### MCTS Guarantees

1. **Bug finding:** Learns to find violations
2. **No guarantees:** May miss bugs, may not terminate
3. **Convergence:** With enough iterations, converges to optimal

## Tradeoffs

### BFS vs DFS

| Aspect | BFS | DFS |
|--------|-----|-----|
| Memory | Higher | Lower |
| Path length | Minimal | May be long |
| PostgreSQL | Incompatible | Compatible |
| First bug | Found quickly | May take longer |
| Deep bugs | May miss | Good at finding |

### Systematic vs Random

| Aspect | Systematic (BFS/DFS) | Random |
|--------|---------------------|--------|
| Completeness | Complete | Probabilistic |
| Reproducibility | Exact | With seed |
| Bug variety | Structured | Surprising |
| Large spaces | May not finish | Samples evenly |

### Coverage vs Bug-Focused

| Aspect | CoverageGuided | MCTS |
|--------|---------------|------|
| Goal | Maximize diversity | Find violations |
| Learning | None | Learns from violations |
| Bug paths | May miss deep bugs | Focuses on bug paths |
| No bugs | Still useful | May wander |

## PostgreSQL Compatibility

!!! warning "Important constraint"
    PostgreSQL SAVEPOINTs are stack-based. BFS, CoverageGuided, and similar strategies that rollback to arbitrary checkpoints will fail.

**Safe strategies:**

- DFS (always rolls back to most recent savepoint)
- Random (with limited depth)

**Unsafe strategies:**

- BFS
- CoverageGuided
- Weighted (may rollback arbitrarily)

**Workaround:** Use SQLite for BFS/CoverageGuided testing:

```python
# Use SQLite for exhaustive BFS testing
db = SQLiteAdapter("/tmp/test.db")
world = World(api=api, systems={"db": db})

agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
    strategy=BFS(),  # Safe with SQLite
)
```

## Selecting a Strategy

### Decision Tree

```
Using PostgreSQL?
├── Yes → Use DFS
└── No → Need shortest bug paths?
           ├── Yes → Use BFS
           └── No → Need maximum coverage?
                      ├── Yes → Use CoverageGuided
                      └── No → Have known hotspots?
                                 ├── Yes → Use Weighted
                                 └── No → Use Random or MCTS
```

### By Use Case

| Use Case | Recommended Strategy |
|----------|---------------------|
| CI/CD with PostgreSQL | DFS |
| Local development | BFS |
| Finding maximum bugs | MCTS |
| Coverage reports | CoverageGuided |
| Fuzzing | Random |
| Known risky actions | Weighted |

## Implementation Details

### Frontier Abstraction

```python
class Frontier(Protocol):
    def add(self, state_id: str, action_name: str) -> None: ...
    def pop(self) -> tuple[str, str] | None: ...
    def is_empty(self) -> bool: ...

class QueueFrontier(Frontier):
    """FIFO queue for BFS."""
    def __init__(self):
        self._queue = deque()

class StackFrontier(Frontier):
    """LIFO stack for DFS."""
    def __init__(self):
        self._stack = []
```

### Valid Action Filtering

Strategies receive pre-filtered valid actions:

```python
valid_actions = graph.get_valid_actions(state, context, used_actions)
```

Filtering includes:

1. Context preconditions (`context.has("order_id")`)
2. Action dependencies (`preconditions=["create_order"]`)
3. Max call limits (`max_calls=2`)
4. Resource requirements (`requires={"order": "created"}`)

### Termination Conditions

Exploration terminates when:

1. No unexplored pairs remain
2. `max_steps` reached
3. `coverage_target` reached
4. Strategy returns `None` from `pick()`

## Custom Strategies

Implement the protocol for custom behavior:

```python
class PrioritizeCriticalActions:
    """Strategy that prioritizes actions with critical invariants."""
    
    def __init__(self, critical_actions: set[str]):
        self.critical_actions = critical_actions
    
    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        unexplored = graph.get_unexplored()
        if not unexplored:
            return None
        
        # Prioritize critical actions
        critical = [p for p in unexplored if p[1].name in self.critical_actions]
        if critical:
            return critical[0]
        
        return unexplored[0]
    
    def notify(self, state: State, actions: list[Action]) -> None:
        pass  # No internal state to update
```
