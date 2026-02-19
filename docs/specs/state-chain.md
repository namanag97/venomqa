# State Chain Specification

Specification of how state chains work, including checkpoint/rollback semantics.

## Overview

State chains are the core mechanism enabling VenomQA's exhaustive exploration. This document specifies how checkpoints are created, managed, and rolled back during exploration.

## Definitions

### State Chain

A **state chain** is a sequence of states connected by transitions:

```
S0 →[a1]→ S1 →[a2]→ S2 →[a3]→ S3
```

Each state has a unique ID derived from its observations, and each transition records the action that caused the state change.

### Checkpoint

A **checkpoint** is a snapshot of all system states at a point in time, enabling rollback to that exact state.

```python
@dataclass
class Checkpoint:
    id: str                          # Unique identifier
    system_checkpoints: dict[str, Any]  # Per-system checkpoint data
    context_snapshot: dict[str, Any]    # Context key-values
    created_at: datetime
```

### Rollback

A **rollback** restores all systems to a previous checkpoint's state.

## Checkpoint Lifecycle

### Creation

Checkpoints are created automatically by the Agent:

```python
# In Agent._step()
checkpoint_name = f"after_{action.name}_{step_count}"
to_state = world.observe_and_checkpoint(checkpoint_name)
```

The naming convention is:

- Initial: `"initial"`
- After action: `"after_{action_name}_{step_number}"`

### Storage

Checkpoints are stored in-memory by the World:

```python
class World:
    _checkpoints: dict[str, Checkpoint]
    
    def checkpoint(self, name: str) -> str:
        system_checkpoints = {}
        for system_name, system in self.systems.items():
            system_checkpoints[system_name] = system.checkpoint(name)
        
        checkpoint = Checkpoint(
            id=name,
            system_checkpoints=system_checkpoints,
            context_snapshot=self.context.to_dict(),
        )
        self._checkpoints[name] = checkpoint
        return name
```

### Cleanup

Checkpoints are kept for the entire exploration. After exploration completes, all checkpoints are discarded.

## Rollback Semantics

### Basic Rollback

```python
def rollback(self, checkpoint_id: str) -> None:
    checkpoint = self._checkpoints[checkpoint_id]
    
    # Restore each system
    for system_name, system_checkpoint in checkpoint.system_checkpoints.items():
        self.systems[system_name].rollback(system_checkpoint)
    
    # Restore context
    self.context.clear()
    for key, value in checkpoint.context_snapshot.items():
        self.context.set(key, value)
```

### Multi-System Rollback

When multiple systems are registered, rollback happens atomically:

```python
world = World(
    api=api,
    systems={
        "db": PostgresAdapter(...),
        "cache": RedisAdapter(...),
        "queue": MockQueue(),
    },
)

# All systems checkpoint together
checkpoint = world.checkpoint("point_a")

# All systems rollback together
world.rollback(checkpoint)
```

**Failure handling:** If any system fails to rollback, the operation fails. Some systems may be partially rolled back.

### Nested Checkpoints

Checkpoints can be nested (checkpoint, then checkpoint again):

```
S0 → S1 (cp1) → S2 (cp2) → S3 (cp3)
```

Rollback to cp2 restores state S2, but cp3 is still valid:

```
S0 → S1 (cp1) → S2 (cp2) → S4 (new)
                      ↑
                   rollback
```

!!! warning "PostgreSQL limitation"
    PostgreSQL SAVEPOINTs are destroyed when you ROLLBACK TO an earlier savepoint. After rolling back from S3 to S2, checkpoint cp3 is invalid.

## State Identity

### Hash Calculation

State identity is determined by hashing observations:

```python
def calculate_state_id(observations: list[Observation]) -> str:
    """Calculate deterministic state ID from observations."""
    components = []
    for obs in sorted(observations, key=lambda o: o.system):
        # Only hash system + data, not metadata
        components.append(f"{obs.system}:{json.dumps(obs.data, sort_keys=True)}")
    
    combined = "|".join(components)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]
```

### Deduplication

When a new state has the same ID as an existing state:

```python
def add_state(self, new_state: State) -> State:
    existing = self.states.get(new_state.id)
    if existing:
        # Return existing state, discard new
        return existing
    self.states[new_state.id] = new_state
    return new_state
```

**Implication:** The same logical state reached via different paths shares the same State object.

## Context Checkpoint Behavior

### What's Checkpointed

All context keys and values are checkpointed:

```python
context_snapshot = {
    "user_id": "abc123",
    "order_id": "xyz789",
    "logged_in": True,
}
```

### What's Not Checkpointed

- References to external objects
- File handles
- Database connections

### Rollback

Context is fully replaced on rollback:

```python
# Before rollback
context.set("new_key", "value")  # Added after checkpoint

# After rollback
context.get("new_key")  # None - key doesn't exist
```

## Database-Specific Semantics

### PostgreSQL

```sql
-- Checkpoint
SAVEPOINT venom_initial;

-- Later checkpoint  
SAVEPOINT venom_after_create_order_1;

-- Rollback to initial
ROLLBACK TO SAVEPOINT venom_initial;
-- Note: venom_after_create_order_1 is now destroyed!
```

**Constraint:** Only DFS strategy works with PostgresAdapter because DFS only rolls back to the most recent checkpoint.

### SQLite

```python
# Checkpoint
temp_path = f"{db_path}.checkpoint_{name}"
shutil.copy2(db_path, temp_path)

# Rollback
shutil.copy2(temp_path, db_path)
os.remove(temp_path)
```

**No ordering constraint:** Any checkpoint can be restored at any time.

### Redis

```python
# Checkpoint
snapshot = {}
for key in scan_all_keys():
    snapshot[key] = client.dump(key)
    snapshot[f"__ttl__{key}"] = client.ttl(key)

# Rollback
client.flushall()
for key, dump in snapshot.items():
    if not key.startswith("__ttl__"):
        ttl = snapshot.get(f"__ttl__{key}", 0)
        client.restore(key, ttl, dump, replace=True)
```

## Replay Semantics

When a state has no valid checkpoint (e.g., after crash), VenomQA can replay actions:

```python
def replay_to_state(self, target_state: State) -> None:
    """Replay actions to reach target state."""
    path = graph.get_path_to(target_state.id)
    
    # Find last valid checkpoint in path
    for i, transition in enumerate(path):
        state = graph.get_state(transition.to_state_id)
        if state.checkpoint_id:
            last_checkpoint = state.checkpoint_id
            replay_from = i + 1
    
    # Rollback to last checkpoint
    self.world.rollback(last_checkpoint)
    
    # Replay remaining actions
    for transition in path[replay_from:]:
        action = graph.get_action(transition.action_name)
        self.world.act(action)
```

## Invariants During Rollback

Invariants are **not** checked during rollback operations. They're only checked after action execution.

## Performance Characteristics

| Operation | PostgreSQL | SQLite | In-Memory |
|-----------|------------|--------|-----------|
| Checkpoint | ~1ms | ~50ms | ~0.1ms |
| Rollback | ~1ms | ~50ms | ~0.1ms |
| Memory per checkpoint | ~1KB | Full DB copy | ~State size |

## Error Scenarios

### Checkpoint Failure

```python
try:
    world.checkpoint("point_a")
except CheckpointError as e:
    # One or more systems failed to checkpoint
    # Exploration can continue but rollback may fail
    log.warning(f"Checkpoint failed: {e}")
```

### Rollback Failure

```python
try:
    world.rollback("point_a")
except RollbackError as e:
    # One or more systems failed to rollback
    # State may be inconsistent - abort exploration
    raise ExplorationAborted("Rollback failed")
```

### Invalid Checkpoint

```python
world.rollback("nonexistent_checkpoint")
# Raises: KeyError("Checkpoint not found: nonexistent_checkpoint")
```

## Guarantees

1. **Atomicity:** Multi-system checkpoints are all-or-nothing
2. **Isolation:** Each exploration has independent checkpoints
3. **Consistency:** After rollback, all systems are at the checkpoint state
4. **Durability:** N/A (checkpoints are in-memory only)

## Limitations

1. **PostgreSQL ordering:** Must use DFS strategy
2. **Memory usage:** All checkpoints kept in memory
3. **External systems:** Can't rollback external APIs
4. **File systems:** Can't rollback file system changes (use MockStorage)
