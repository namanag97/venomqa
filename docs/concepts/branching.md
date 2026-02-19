# Checkpoints & Branching

Database rollback enables true parallel exploration.

## The Problem

To explore all paths through your API, you need to test from the same starting point:

```
[empty] → create → [has order] → refund → [refunded]
                        ↓
                      cancel → [canceled]
                        ↓
                      update → [modified]
```

Without rollback, each path would leave the database polluted:

```
Path 1: create → refund → (order still exists)
Path 2: create → cancel → (order still exists, conflicts!)
```

## The Solution: Savepoint Rollback

VenomQA uses database savepoints to branch cleanly:

```python
# PostgreSQL
SAVEPOINT vq_checkpoint_1;
-- ... run actions ...
ROLLBACK TO SAVEPOINT vq_checkpoint_1;
-- Database is now back to original state
```

This enables true exploration:

```
Start: [empty database]
  │
  ├── create → [has order A]
  │     │
  │     ├── refund → [refunded A] ✓
  │     │
  │     ├── cancel → [canceled A] ✓
  │     │
  │     └── update → [modified A] ✓
  │
  └── (rollback to empty)
        │
        ├── create → [has order B]
        │     └── ...
```

Each branch starts from a clean state.

## How It Works

### 1. Checkpoint Before Branch

When the agent reaches a state with multiple possible actions:

```python
# Internal: VenomQA calls world.checkpoint()
checkpoint_id = world.checkpoint()
```

### 2. Try Each Action

```python
for action in possible_actions:
    result = action.execute(api, context)
    # ... check invariants ...
    world.rollback(checkpoint_id)  # Reset for next branch
```

### 3. Restore Clean State

The database is exactly as it was before the action.

## Database Support

### PostgreSQL (Recommended)

```python
from venomqa.adapters.postgres import PostgresAdapter

db = PostgresAdapter("postgresql://user:pass@localhost/testdb")
world = World(api=api, systems={"db": db})
```

**Implementation:**

- Entire exploration runs in one uncommitted transaction
- Uses `SAVEPOINT` / `ROLLBACK TO SAVEPOINT`
- Zero test pollution

**Requirements:**

- `pip install psycopg[binary]`
- PostgreSQL 12+

### MySQL

```python
from venomqa.adapters.mysql import MySQLAdapter

db = MySQLAdapter(host="localhost", user="root", database="testdb")
world = World(api=api, systems={"db": db})
```

**Implementation:**

- Uses `SAVEPOINT` / `ROLLBACK TO SAVEPOINT`
- Similar to PostgreSQL

### SQLite

```python
from venomqa.adapters.sqlite import SQLiteAdapter

db = SQLiteAdapter(path="/path/to/test.db")
world = World(api=api, systems={"db": db})
```

**Implementation:**

- Copies database file on checkpoint
- Restores file on rollback
- Good for local development

### Redis

```python
from venomqa.adapters.redis_adapter import RedisAdapter

redis = RedisAdapter(host="localhost", port=6379)
world = World(api=api, systems={"redis": redis})
```

**Implementation:**

- `DUMP` all keys → `FLUSHALL` + `RESTORE` on rollback

### In-Memory (Testing)

```python
from venomqa.adapters.mock import MockSystem

mock_db = MockSystem(initial_state={"users": []})
world = World(api=api, systems={"db": mock_db})
```

**Implementation:**

- Deep copy on checkpoint
- Assign copy on rollback

## When Rollback Matters

### Without Rollback

```python
# This won't work correctly
def test_refund_twice():
    create_order()  # Order #1 created
    refund_order()  # Order #1 refunded
    # Database now has a refunded order
    
    # Next test starts with polluted state
    test_cancel_order()  # Order #1 already refunded!
```

### With Rollback

```python
# VenomQA explores correctly
[empty]
  │
  └── create_order(#1) → [has #1]
        │
        ├── refund_order(#1) → [refunded #1] ✓
        │     └── (rollback to [has #1])
        │
        └── refund_order(#1) → [refunded #1 again] ← BUG
              └── (rollback to [has #1])
              
        └── cancel_order(#1) → [canceled #1] ✓
              └── (rollback to [has #1])
```

## Checkpoint Granularity

### Per-Action (Default)

```python
world = World(api=api, systems={"db": db})
# Checkpoint before every action
```

### Manual Checkpoints

```python
# Take manual control
cp1 = world.checkpoint()
action1.execute(api, context)
world.rollback(cp1)
```

## Performance Considerations

| Database | Checkpoint Cost | Rollback Cost | Best For |
|----------|-----------------|---------------|----------|
| PostgreSQL | ~1ms | ~1ms | Production CI |
| MySQL | ~2ms | ~2ms | MySQL shops |
| SQLite | ~50ms (file copy) | ~50ms | Local dev |
| Redis | ~5ms | ~10ms | Cache testing |
| Mock | ~0.1ms | ~0.1ms | Unit tests |

## Common Patterns

### Reset Between Tests

```python
import pytest

@pytest.fixture
def clean_world():
    world = World(api=api, systems={"db": db})
    yield world
    # Automatic cleanup via transaction rollback
```

### Nested Branching

```python
# VenomQA handles nested checkpoints automatically
cp1 = world.checkpoint()
    action_a.execute()
    cp2 = world.checkpoint()
        action_b.execute()
    world.rollback(cp2)
    action_c.execute()
world.rollback(cp1)
```

## Troubleshooting

### "Savepoint does not exist"

The transaction was committed or rolled back externally. Ensure no other code is managing transactions.

### "Database file locked" (SQLite)

SQLite doesn't handle concurrent writes well. Use PostgreSQL for parallel exploration.

### Slow Rollback

If checkpoints are slow:

1. Check database connection pooling
2. Reduce initial data volume
3. Use PostgreSQL over SQLite

## Next Steps

- [State Management](state.md) - Context and state extraction
- [Adapters Reference](../reference/adapters.md) - Full adapter docs
- [Examples](../examples/index.md) - Real-world patterns
