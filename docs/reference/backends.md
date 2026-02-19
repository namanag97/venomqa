# Database Backends

Configure database rollback for true parallel exploration.

## Overview

Database backends enable VenomQA to checkpoint and restore database state between exploration branches. This ensures each path starts from a clean, consistent state.

```
[empty database]
  │
  ├── create → [has data A]
  │     ├── refund → [refunded A]
  │     └── cancel → [canceled A]
  │
  └── (rollback) → [empty database]
        │
        └── create → [has data B]
```

## Supported Backends

| Backend | Implementation | Best For | Rollback Speed |
|---------|----------------|----------|----------------|
| PostgreSQL | SAVEPOINT | Production CI | ~1ms |
| MySQL | SAVEPOINT | MySQL shops | ~2ms |
| SQLite | File copy | Local dev | ~50ms |
| Redis | DUMP/RESTORE | Cache testing | ~10ms |
| Mock | Deep copy | Unit tests | ~0.1ms |

## PostgreSQL (Recommended)

### Installation

```bash
pip install "venomqa[postgres]"
# or
pip install psycopg[binary]
```

### Configuration

```python
from venomqa.adapters.postgres import PostgresAdapter

db = PostgresAdapter(
    connection_string="postgresql://user:pass@host:5432/dbname",
    schema="public",
)
```

### How It Works

```sql
-- Entire exploration runs in one transaction
BEGIN;

-- VenomQA creates savepoints
SAVEPOINT vq_checkpoint_1;
-- ... actions execute ...
ROLLBACK TO SAVEPOINT vq_checkpoint_1;
-- State is restored

-- Transaction never commits
ROLLBACK;
```

### Full Example

```python
from venomqa import World, Agent, Action, BFS
from venomqa.adapters.http import HttpClient
from venomqa.adapters.postgres import PostgresAdapter

api = HttpClient("http://localhost:8000")
db = PostgresAdapter("postgresql://localhost/testdb")

world = World(
    api=api,
    systems={"db": db},
    state_from_context=["order_id"],
)

def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    context.set("order_id", resp.json()["id"])
    return resp

def check_db(api, context):
    order_id = context.get("order_id")
    rows = db.query("SELECT * FROM orders WHERE id = %s", [order_id])
    print(f"DB has {len(rows)} orders")
    return None

agent = Agent(
    world=world,
    actions=[
        Action("create", create_order),
        Action("check", check_db),
    ],
    strategy=BFS(),
).explore()
```

### Connection String Format

```
postgresql://[user[:password]@][host][:port][/dbname][?param1=val1&...]
```

Examples:

```python
# Local with defaults
"postgresql://localhost/mydb"

# With credentials
"postgresql://user:pass@localhost/mydb"

# With options
"postgresql://user:pass@localhost/mydb?sslmode=require"

# From environment
import os
db = PostgresAdapter(os.getenv("DATABASE_URL"))
```

---

## MySQL

### Installation

```bash
pip install "venomqa[mysql]"
# or
pip install mysql-connector-python
```

### Configuration

```python
from venomqa.adapters.mysql import MySQLAdapter

db = MySQLAdapter(
    host="localhost",
    port=3306,
    user="root",
    password="secret",
    database="testdb",
)
```

Or with connection string:

```python
db = MySQLAdapter("mysql://user:pass@localhost:3306/testdb")
```

### Full Example

```python
from venomqa import World
from venomqa.adapters.http import HttpClient
from venomqa.adapters.mysql import MySQLAdapter

api = HttpClient("http://localhost:8000")
db = MySQLAdapter(host="localhost", user="root", database="testdb")

world = World(api=api, systems={"db": db})
```

---

## SQLite

### Installation

Built-in. No additional installation required.

### Configuration

```python
from venomqa.adapters.sqlite import SQLiteAdapter

db = SQLiteAdapter(
    path="/path/to/database.db",
    copy_on_checkpoint=True,
)
```

### How It Works

SQLite uses file copying instead of transactions:

1. **Checkpoint**: Copy database file to temp location
2. **Rollback**: Restore from temp copy

This is slower than PostgreSQL but works without special setup.

### Best Practices

- Use in-memory mode for fastest tests:
  ```python
  db = SQLiteAdapter(path=":memory:")
  ```

- Keep database small (< 100MB) for reasonable rollback times

---

## Redis

### Installation

```bash
pip install redis
```

### Configuration

```python
from venomqa.adapters.redis_adapter import RedisAdapter

redis = RedisAdapter(
    host="localhost",
    port=6379,
    db=0,
    password=None,
)
```

### How It Works

1. **Checkpoint**: `DUMP` all keys
2. **Rollback**: `FLUSHALL` + `RESTORE` all keys

### Full Example

```python
from venomqa import World
from venomqa.adapters.http import HttpClient
from venomqa.adapters.redis_adapter import RedisAdapter

api = HttpClient("http://localhost:8000")
redis = RedisAdapter(host="localhost")

world = World(
    api=api,
    systems={"cache": redis},
)

def clear_cache(api, context):
    redis.flush()
    return None
```

---

## Mock (Testing)

For unit tests without a real database.

### Configuration

```python
from venomqa.adapters.mock import MockSystem

# With initial state
mock = MockSystem(initial_state={
    "users": [],
    "orders": [],
})

world = World(api=api, systems={"db": mock})
```

### Methods

```python
# Query
rows = mock.query("users")  # Returns list

# Execute
mock.execute("INSERT INTO users VALUES (?)", [{"name": "Alice"}])

# Clear
mock.clear()
```

---

## Multiple Systems

You can configure multiple database systems:

```python
from venomqa import World
from venomqa.adapters.postgres import PostgresAdapter
from venomqa.adapters.redis_adapter import RedisAdapter

world = World(
    api=api,
    systems={
        "db": PostgresAdapter("postgresql://localhost/app"),
        "cache": RedisAdapter(host="localhost"),
    },
)

# Access in actions
def check_consistency(api, context):
    db_count = world.systems["db"].query("SELECT COUNT(*) FROM orders")[0][0]
    cache_count = world.systems["cache"].get("order_count")
    return db_count == cache_count
```

---

## Troubleshooting

### PostgreSQL: "SAVEPOINT does not exist"

The transaction was committed externally. Ensure no other code commits:

```python
# Bad: External commit
db.execute("COMMIT")  # Breaks VenomQA

# Good: Let VenomQA manage transactions
# (no explicit COMMIT)
```

### SQLite: "Database is locked"

SQLite doesn't handle concurrent access well. Solutions:

1. Use PostgreSQL for parallel exploration
2. Reduce concurrent workers
3. Use WAL mode: `PRAGMA journal_mode=WAL;`

### MySQL: "Lock wait timeout exceeded"

Long-running transactions can timeout. Increase timeout:

```python
db = MySQLAdapter(
    ...,
    connection_timeout=60,
)
```

### Redis: "OOM command not allowed"

Redis is out of memory. Solutions:

1. Increase Redis memory
2. Use smaller test data
3. Enable eviction: `maxmemory-policy allkeys-lru`

## Next Steps

- [Adapters](adapters.md) - HTTP and other adapters
- [Checkpoints & Branching](../concepts/branching.md) - Deep dive
- [CI/CD Integration](../tutorials/ci-cd.md) - Use in pipelines
