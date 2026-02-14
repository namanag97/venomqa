# State Management

State management is what makes VenomQA unique. It enables checkpointing and rollback for testing multiple scenarios from the same database state.

## Overview

VenomQA manages two types of state:

1. **Execution Context**: In-memory variables shared between steps
2. **Database State**: Actual database records (requires a state backend)

## Execution Context

The execution context is an in-memory dictionary that persists across steps:

```python
def step_one(client, context):
    # Store data
    context["user_id"] = 123
    context["token"] = "abc123"
    return response

def step_two(client, context):
    # Access data from previous step
    user_id = context["user_id"]
    return client.get(f"/api/users/{user_id}")
```

### Context API

```python
# Store values
context["key"] = value
context.set("key", value)

# Retrieve values
value = context.get("key")                    # Returns None if missing
value = context.get("key", default="fallback")  # Custom default
value = context.get_required("key")           # Raises KeyError if missing

# Check existence
if "key" in context:
    pass

# Store/retrieve step results
context.store_step_result("step_name", result)
result = context.get_step_result("step_name")

# Snapshot/restore
snapshot = context.snapshot()
context.restore(snapshot)

# Export
data = context.to_dict()
```

## Database State

For database state management, VenomQA uses the **State Manager** pattern.

### How It Works

```mermaid
sequenceDiagram
    participant Journey
    participant StateManager
    participant Database

    Journey->>StateManager: checkpoint("order_created")
    StateManager->>Database: SAVEPOINT order_created
    Database-->>StateManager: OK

    Journey->>Journey: Execute path steps

    Journey->>StateManager: rollback("order_created")
    StateManager->>Database: ROLLBACK TO SAVEPOINT order_created
    Database-->>StateManager: OK
```

### StateManager Protocol

All state backends implement this protocol:

```python
from typing import Protocol

class StateManager(Protocol):
    def connect(self) -> None:
        """Establish connection to the database."""
        ...

    def disconnect(self) -> None:
        """Close connection to the database."""
        ...

    def checkpoint(self, name: str) -> None:
        """Create a savepoint with the given name."""
        ...

    def rollback(self, name: str) -> None:
        """Rollback to a previously created checkpoint."""
        ...

    def release(self, name: str) -> None:
        """Release a checkpoint (free resources)."""
        ...

    def reset(self) -> None:
        """Reset database to clean state (truncate tables)."""
        ...

    def is_connected(self) -> bool:
        """Check if connection is active."""
        ...
```

## PostgreSQL Backend

PostgreSQL is the recommended backend for state management.

### Installation

```bash
pip install "venomqa[postgres]"
```

### Configuration

```yaml
# venomqa.yaml
db_url: "postgresql://qa:secret@localhost:5432/qa_test"
db_backend: "postgresql"
```

### Usage

```python
from venomqa import JourneyRunner, Client
from venomqa.state import PostgreSQLStateManager

# Create state manager
state_manager = PostgreSQLStateManager(
    connection_url="postgresql://qa:secret@localhost:5432/qa_test",
    tables_to_reset=["users", "orders", "items"],  # Tables to truncate on reset
    exclude_tables=["migrations"],                  # Never truncate these
)

# Create runner with state manager
runner = JourneyRunner(
    client=Client(base_url="http://localhost:8000"),
    state_manager=state_manager,
)

# Run journey - checkpoints handled automatically
result = runner.run(journey)
```

### How PostgreSQL Checkpoints Work

VenomQA uses SQL `SAVEPOINT` for checkpoints:

```sql
-- Creating a checkpoint
SAVEPOINT chk_order_created;

-- Rolling back to checkpoint
ROLLBACK TO SAVEPOINT chk_order_created;

-- Releasing checkpoint (optional cleanup)
RELEASE SAVEPOINT chk_order_created;
```

This is why:

- Checkpoints are lightweight (just markers in the transaction log)
- Rollback is instant (no data copying)
- Multiple nested checkpoints are supported

### Table Reset Options

Control which tables are affected:

```python
# Only reset specific tables
state_manager = PostgreSQLStateManager(
    connection_url="...",
    tables_to_reset=["users", "orders", "items"],
)

# Reset all tables except some
state_manager = PostgreSQLStateManager(
    connection_url="...",
    exclude_tables=["migrations", "audit_log", "schema_versions"],
)

# Reset all public schema tables (default)
state_manager = PostgreSQLStateManager(connection_url="...")
```

## Context vs Database State

Understanding the difference is crucial:

| Aspect | Context State | Database State |
|--------|---------------|----------------|
| Storage | In-memory | Database |
| Persistence | Per journey run | Persists until rollback |
| Checkpoint | Always saved | Requires StateManager |
| Rollback | Always restored | Requires StateManager |
| Performance | Instant | Transaction overhead |

### Example

```python
def create_user(client, context):
    # Database state: new row in users table
    response = client.post("/api/users", json={"name": "John"})

    # Context state: in-memory reference
    context["user_id"] = response.json()["id"]

    return response

# At checkpoint:
# - Context: {"user_id": 123} is snapshotted
# - Database: SAVEPOINT marks the transaction

# After rollback:
# - Context: {"user_id": 123} is restored
# - Database: User row is removed (ROLLBACK TO SAVEPOINT)
```

## Running Without State Backend

VenomQA works without a database backend, but with limitations:

```python
# No state manager - context only
runner = JourneyRunner(
    client=Client(base_url="http://localhost:8000"),
    # state_manager=None (default)
)
```

What works:

- Context checkpointing and restoration
- Branch execution (context is isolated)
- All step execution features

What doesn't work:

- Database rollback (changes persist)
- True state isolation between paths
- Deterministic test data

## Best Practices

### 1. Use Separate Test Database

Never test against production or development databases:

```yaml
# Good - dedicated test database
db_url: "postgresql://qa:secret@localhost:5432/qa_test"

# Bad - development database
db_url: "postgresql://dev:dev@localhost:5432/dev_db"
```

### 2. Reset State Between Journey Runs

Start each journey with a clean state:

```python
# In your test setup
state_manager.reset()  # Truncate tables
state_manager.checkpoint("clean_state")
```

### 3. Use Fast Storage for Tests

Use tmpfs for faster database operations:

```yaml
# docker-compose.qa.yml
services:
  db:
    image: postgres:15
    tmpfs:
      - /var/lib/postgresql/data  # RAM-based storage
```

### 4. Exclude Migration Tables

Never truncate schema migration tables:

```python
state_manager = PostgreSQLStateManager(
    connection_url="...",
    exclude_tables=[
        "alembic_version",      # Alembic
        "django_migrations",    # Django
        "schema_migrations",    # Rails/custom
        "_prisma_migrations",   # Prisma
    ],
)
```

### 5. Handle Connection Pooling

For parallel execution, consider connection limits:

```python
# PostgreSQL connection string with pool settings
db_url = "postgresql://qa:secret@localhost:5432/qa_test?pool_size=10"
```

## Troubleshooting

### Connection Refused

```
Error: Connection refused to postgresql://localhost:5432
```

**Solutions:**

1. Ensure PostgreSQL is running
2. Check port is correct
3. Verify credentials

```bash
# Test connection
psql "postgresql://qa:secret@localhost:5432/qa_test" -c "SELECT 1"
```

### Checkpoint Not Found

```
ValueError: Checkpoint 'order_created' not found
```

**Causes:**

1. Checkpoint never created
2. Typo in checkpoint name
3. Connection was reset

**Solution:** Ensure checkpoint is created before branch:

```python
Checkpoint(name="order_created"),  # Create first
Branch(checkpoint_name="order_created", ...)  # Then reference
```

### Transaction Issues

```
Error: SAVEPOINT can only be used in transaction blocks
```

**Solution:** Ensure autocommit is disabled:

```python
# This is handled automatically by PostgreSQLStateManager
# but if using custom backend, ensure:
connection.autocommit = False
```

### Slow Reset Operations

If `reset()` is slow:

```python
# Specify only needed tables
state_manager = PostgreSQLStateManager(
    connection_url="...",
    tables_to_reset=["users", "orders", "items"],  # Only these
)
```

## Custom State Backends

Implement the StateManager protocol for custom backends:

```python
from venomqa.state.base import BaseStateManager

class MyCustomStateManager(BaseStateManager):
    def connect(self) -> None:
        self._conn = my_database.connect()
        self._connected = True

    def disconnect(self) -> None:
        self._conn.close()
        self._connected = False

    def checkpoint(self, name: str) -> None:
        self._ensure_connected()
        self._conn.execute(f"SAVEPOINT {name}")
        self._checkpoints.append(name)

    def rollback(self, name: str) -> None:
        self._ensure_connected()
        self._conn.execute(f"ROLLBACK TO SAVEPOINT {name}")

    def release(self, name: str) -> None:
        self._ensure_connected()
        self._conn.execute(f"RELEASE SAVEPOINT {name}")
        self._checkpoints.remove(name)

    def reset(self) -> None:
        self._ensure_connected()
        for table in self.tables_to_reset:
            self._conn.execute(f"TRUNCATE TABLE {table} CASCADE")
        self._conn.commit()
```

See [Custom Backends](../advanced/custom-backends.md) for detailed implementation guides.

## Next Steps

- [Database Backends](../reference/backends.md) - Configure different backends
- [Custom Backends](../advanced/custom-backends.md) - Implement your own
- [Checkpoints & Branching](branching.md) - Use state management in journeys
