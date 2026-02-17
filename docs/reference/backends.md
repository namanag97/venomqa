# Database Backend Configuration

VenomQA supports database state management for checkpoint and rollback functionality. This enables testing multiple execution paths from the same database state.

> **New to state branching?** See [Getting Started - Using State Branching](../getting-started/index.md) for an introduction.

## Table of Contents

- [Overview](#overview)
- [PostgreSQL Backend](#postgresql-backend)
- [Configuration](#configuration)
- [Custom Backends](#custom-backends)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Related Documentation

| Topic | Document |
|-------|----------|
| API Reference | [api.md#state-management](api.md#state-management) |
| Writing Journeys | [../concepts/journeys.md](../concepts/journeys.md) |
| Advanced Usage | [../advanced/custom-backends.md](../advanced/custom-backends.md) |
| FAQ | [FAQ.md#state-branching](../faq.md) |

---

## Overview

### Why State Management?

Without state management, each test must:
1. Set up fresh data before testing
2. Clean up data after testing
3. Deal with data conflicts when running tests in parallel

With VenomQA's state management:
1. Create a checkpoint at a known state
2. Test multiple scenarios from that checkpoint
3. Automatically rollback between scenarios
4. No cleanup needed - rollback handles it

### How It Works

```
Journey Start
     │
     ▼
┌─────────────────┐
│  Step 1: Login  │
│  Step 2: Create │
│  Order          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     SAVEPOINT order_created
│  Checkpoint     │──────────────────────────────►
│  "order_created"│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Branch       │
│  ┌─────┬─────┐  │
│  │Path │Path │  │
│  │  A  │  B  │  │
│  └──┬──┴──┬──┘  │
│     │     │     │
│     │ ROLLBACK  │
│     ▼     ▼     │
└─────────────────┘
```

---

## PostgreSQL Backend

### Installation

```bash
pip install "venomqa[postgres]"
```

Or install psycopg directly:

```bash
pip install psycopg[binary]
```

### Basic Configuration

```yaml
# venomqa.yaml
db_url: "postgresql://qa_user:secret@localhost:5432/qa_test"
db_backend: "postgresql"
```

### Connection String Format

```
postgresql://[user[:password]@][host][:port]/database[?options]
```

Examples:

```bash
# Local development
postgresql://postgres:postgres@localhost:5432/test_db

# With SSL
postgresql://user:pass@host:5432/db?sslmode=require

# Docker service
postgresql://qa:secret@postgres:5432/qa_test

# Cloud database
postgresql://user:pass@aws-0-us-east-1.pooler.supabase.com:5432/postgres
```

### Environment Variable

```bash
export VENOMQA_DB_URL="postgresql://qa:secret@localhost:5432/qa_test"
```

### Docker Compose Setup

```yaml
# docker-compose.qa.yml
version: "3.8"

services:
  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://qa:secret@db:5432/qa_test

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: qa_test
      POSTGRES_USER: qa
      POSTGRES_PASSWORD: secret
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U qa -d qa_test"]
      interval: 5s
      timeout: 5s
      retries: 5
    tmpfs:
      - /var/lib/postgresql/data  # Use tmpfs for faster tests
```

### Programmatic Usage

```python
from venomqa import Journey, JourneyRunner, Client
from venomqa.state import PostgreSQLStateManager

# Create state manager
state_manager = PostgreSQLStateManager(
    connection_url="postgresql://qa:secret@localhost:5432/qa_test",
    tables_to_reset=["users", "orders", "items"],
    exclude_tables=["migrations", "schema_versions"],
)

# Create runner with state manager
runner = JourneyRunner(
    client=Client(base_url="http://localhost:8000"),
    state_manager=state_manager,
)

# Run journey - checkpoints and rollbacks handled automatically
result = runner.run(journey)
```

### How PostgreSQL Checkpoints Work

VenomQA uses SQL `SAVEPOINT` for checkpoints:

```sql
-- Creating a checkpoint
SAVEPOINT chk_order_created;

-- Rolling back to checkpoint
ROLLBACK TO SAVEPOINT chk_order_created;

-- Releasing checkpoint (optional)
RELEASE SAVEPOINT chk_order_created;
```

### Table Reset Options

Control which tables are truncated when resetting:

```python
# Only reset specific tables
state_manager = PostgreSQLStateManager(
    connection_url="...",
    tables_to_reset=["users", "orders", "items"],
)

# Reset all tables except some
state_manager = PostgreSQLStateManager(
    connection_url="...",
    exclude_tables=["migrations", "audit_log"],
)

# Reset all public tables (default when tables_to_reset is empty)
state_manager = PostgreSQLStateManager(
    connection_url="...",
)
```

---

## Configuration

### Configuration File

```yaml
# venomqa.yaml
base_url: "http://localhost:8000"

# Database settings
db_url: "postgresql://qa:secret@localhost:5432/qa_test"
db_backend: "postgresql"

# Docker settings
docker_compose_file: "docker-compose.qa.yml"

# Execution settings
parallel_paths: 1
fail_fast: false

# Logging
capture_logs: true
log_lines: 50
verbose: false

# Reporting
report_dir: "reports"
report_formats:
  - markdown
  - junit
```

### Environment Variables

```bash
# Database
export VENOMQA_DB_URL="postgresql://user:pass@host:5432/db"

# Connection
export VENOMQA_BASE_URL="http://api.example.com"

# Execution
export VENOMQA_TIMEOUT=60
export VENOMQA_PARALLEL_PATHS=4
export VENOMQA_VERBOSE=true
```

### Python Configuration

```python
from venomqa import QAConfig

config = QAConfig(
    base_url="http://localhost:8000",
    db_url="postgresql://qa:secret@localhost:5432/qa_test",
    db_backend="postgresql",
    timeout=30,
    parallel_paths=2,
    capture_logs=True,
)
```

---

## Custom Backends

### StateManager Protocol

Implement the `StateManager` protocol to create custom backends:

```python
from typing import Protocol

class StateManager(Protocol):
    def connect(self) -> None:
        """Establish connection to the database/service."""
        ...
    
    def disconnect(self) -> None:
        """Close connection to the database/service."""
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

### MySQL Backend Example

```python
import mysql.connector
from venomqa.state.base import BaseStateManager

class MySQLStateManager(BaseStateManager):
    """MySQL state manager using SAVEPOINT."""
    
    def __init__(self, connection_url: str, tables_to_reset: list[str] | None = None):
        super().__init__(connection_url)
        self.tables_to_reset = tables_to_reset or []
        self._conn = None
    
    def connect(self) -> None:
        # Parse connection URL and connect
        self._conn = mysql.connector.connect(
            host="localhost",
            user="qa",
            password="secret",
            database="qa_test",
        )
        self._connected = True
    
    def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False
    
    def checkpoint(self, name: str) -> None:
        self._ensure_connected()
        cursor = self._conn.cursor()
        cursor.execute(f"SAVEPOINT {name}")
        self._checkpoints.append(name)
    
    def rollback(self, name: str) -> None:
        self._ensure_connected()
        cursor = self._conn.cursor()
        cursor.execute(f"ROLLBACK TO SAVEPOINT {name}")
    
    def release(self, name: str) -> None:
        self._ensure_connected()
        cursor = self._conn.cursor()
        cursor.execute(f"RELEASE SAVEPOINT {name}")
        if name in self._checkpoints:
            self._checkpoints.remove(name)
    
    def reset(self) -> None:
        self._ensure_connected()
        cursor = self._conn.cursor()
        for table in self.tables_to_reset:
            cursor.execute(f"TRUNCATE TABLE {table}")
        self._conn.commit()
        self._checkpoints.clear()
```

### Redis Backend Example

For stateless applications using Redis:

```python
import redis
from venomqa.state.base import BaseStateManager

class RedisStateManager(BaseStateManager):
    """Redis state manager for key-value state."""
    
    def __init__(self, redis_url: str, key_prefix: str = "qa:"):
        super().__init__(redis_url)
        self.key_prefix = key_prefix
        self._redis = None
        self._snapshots: dict[str, dict] = {}
    
    def connect(self) -> None:
        self._redis = redis.from_url(self.connection_url)
        self._connected = True
    
    def disconnect(self) -> None:
        if self._redis:
            self._redis.close()
            self._redis = None
        self._connected = False
    
    def checkpoint(self, name: str) -> None:
        self._ensure_connected()
        # Save all keys matching prefix
        keys = self._redis.keys(f"{self.key_prefix}*")
        snapshot = {}
        for key in keys:
            snapshot[key] = self._redis.get(key)
        self._snapshots[name] = snapshot
        self._checkpoints.append(name)
    
    def rollback(self, name: str) -> None:
        self._ensure_connected()
        if name not in self._snapshots:
            raise ValueError(f"Checkpoint '{name}' not found")
        
        # Clear current state
        keys = self._redis.keys(f"{self.key_prefix}*")
        if keys:
            self._redis.delete(*keys)
        
        # Restore snapshot
        for key, value in self._snapshots[name].items():
            self._redis.set(key, value)
    
    def release(self, name: str) -> None:
        if name in self._snapshots:
            del self._snapshots[name]
        if name in self._checkpoints:
            self._checkpoints.remove(name)
    
    def reset(self) -> None:
        self._ensure_connected()
        keys = self._redis.keys(f"{self.key_prefix}*")
        if keys:
            self._redis.delete(*keys)
        self._snapshots.clear()
        self._checkpoints.clear()
```

### Registering Custom Backends

Add to your `pyproject.toml`:

```toml
[project.entry-points."venomqa.state_backends"]
mysql = "my_package.state:MySQLStateManager"
redis = "my_package.state:RedisStateManager"
```

---

## Best Practices

### 1. Use Separate Test Database

Never run tests against production or development databases:

```python
# Good - dedicated test database
db_url: "postgresql://qa:secret@localhost:5432/qa_test"

# Bad - development database
db_url: "postgresql://dev:dev@localhost:5432/dev_db"
```

### 2. Reset State Between Journeys

Start each journey with a clean state:

```python
# In your journey setup
state_manager.reset()
state_manager.checkpoint("clean_state")
```

### 3. Use Checkpoints Strategically

Place checkpoints before state-modifying operations you want to test multiple ways:

```python
Journey(
    name="order_flow",
    steps=[
        Step(name="login", action=login),
        Step(name="create_order", action=create_order),
        Checkpoint(name="order_created"),  # Good placement
        Branch(
            checkpoint_name="order_created",
            paths=[...],
        ),
    ],
)
```

### 4. Exclude System Tables

Prevent accidental truncation of migration tables:

```python
state_manager = PostgreSQLStateManager(
    connection_url="...",
    exclude_tables=[
        "alembic_version",
        "django_migrations",
        "schema_migrations",
    ],
)
```

### 5. Use Docker for Isolation

Run tests in isolated Docker containers:

```yaml
# docker-compose.qa.yml
services:
  db:
    image: postgres:15
    tmpfs:
      - /var/lib/postgresql/data  # Fast, ephemeral storage
```

### 6. Connection Pooling

For parallel execution, consider connection pooling:

```python
# Use a connection pool for parallel paths
from psycopg_pool import ConnectionPool

pool = ConnectionPool(conninfo="postgresql://...")
```

---

## Troubleshooting

### Connection Refused

```
Error: Connection refused to postgresql://localhost:5432
```

**Solutions:**
1. Ensure PostgreSQL is running: `docker compose up -d db`
2. Check port is correct and exposed
3. Verify connection string credentials

### Checkpoint Not Found

```
ValueError: Checkpoint 'order_created' not found
```

**Causes:**
1. Checkpoint was never created
2. Checkpoint name is misspelled
3. Connection was reset

**Solution:** Ensure checkpoint is created before branch references it:

```python
# Correct order
Checkpoint(name="order_created"),  # Create first
Branch(checkpoint_name="order_created", ...)  # Reference later
```

### Transaction Issues

```
Error: SAVEPOINT can only be used in transaction blocks
```

**Solution:** Ensure autocommit is disabled:

```python
self._conn.autocommit = False
```

### Table Locks

```
Error: relation "users" is locked
```

**Solutions:**
1. Wait for locks to release
2. Kill blocking queries
3. Use shorter transactions

### Reset Taking Too Long

If `reset()` is slow with many tables:

```python
# Specify only tables you need to reset
state_manager = PostgreSQLStateManager(
    connection_url="...",
    tables_to_reset=["users", "orders", "items"],  # Only these
)
```

### Parallel Path Conflicts

When running parallel paths with database operations:

```python
# Limit parallelism if seeing conflicts
runner = JourneyRunner(
    client=client,
    state_manager=state_manager,
    parallel_paths=1,  # Run sequentially
)
```

### Debugging State Issues

Enable verbose logging:

```bash
venomqa run -v
```

Check logs for checkpoint operations:
```
DEBUG - Created checkpoint: chk_order_created
DEBUG - Rolled back to checkpoint: chk_order_created
```
