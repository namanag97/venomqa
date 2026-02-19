# Custom Backends

Implement custom state management backends for different databases or storage systems.

## StateManager Protocol

All state backends must implement this protocol:

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

## BaseStateManager Class

Use `BaseStateManager` as a starting point:

```python
from venomqa.state.base import BaseStateManager


class MyStateManager(BaseStateManager):
    def __init__(self, connection_url: str, **kwargs):
        super().__init__(connection_url)
        self._conn = None

    def connect(self) -> None:
        self._conn = my_db.connect(self.connection_url)
        self._connected = True

    def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False

    def checkpoint(self, name: str) -> None:
        self._ensure_connected()
        # Implementation
        self._checkpoints.append(name)

    def rollback(self, name: str) -> None:
        self._ensure_connected()
        # Implementation

    def release(self, name: str) -> None:
        self._ensure_connected()
        # Implementation
        if name in self._checkpoints:
            self._checkpoints.remove(name)

    def reset(self) -> None:
        self._ensure_connected()
        # Implementation
        self._checkpoints.clear()
```

## Example: MySQL Backend

```python
import mysql.connector
from venomqa.state.base import BaseStateManager


class MySQLStateManager(BaseStateManager):
    """MySQL state manager using SAVEPOINT."""

    def __init__(
        self,
        connection_url: str,
        tables_to_reset: list[str] | None = None,
        exclude_tables: list[str] | None = None,
    ):
        super().__init__(connection_url)
        self.tables_to_reset = tables_to_reset or []
        self.exclude_tables = exclude_tables or []
        self._conn = None

    def connect(self) -> None:
        # Parse connection URL
        # mysql://user:pass@host:port/database
        from urllib.parse import urlparse
        parsed = urlparse(self.connection_url)

        self._conn = mysql.connector.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip('/'),
            autocommit=False,
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
        if name not in self._checkpoints:
            raise ValueError(f"Checkpoint '{name}' not found")
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

        # Get tables to reset
        tables = self.tables_to_reset
        if not tables:
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            tables = [t for t in tables if t not in self.exclude_tables]

        # Disable foreign key checks temporarily
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        for table in tables:
            cursor.execute(f"TRUNCATE TABLE {table}")

        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        self._conn.commit()
        self._checkpoints.clear()

    def commit(self) -> None:
        self._ensure_connected()
        self._conn.commit()
```

## Example: Redis Backend

For applications using Redis as primary storage:

```python
import redis
import json
from venomqa.state.base import BaseStateManager


class RedisStateManager(BaseStateManager):
    """Redis state manager using key snapshots."""

    def __init__(
        self,
        redis_url: str,
        key_prefix: str = "qa:",
        snapshot_prefix: str = "_snapshot:",
    ):
        super().__init__(redis_url)
        self.key_prefix = key_prefix
        self.snapshot_prefix = snapshot_prefix
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

        # Get all keys matching prefix
        keys = self._redis.keys(f"{self.key_prefix}*")
        snapshot = {}

        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            value = self._redis.get(key)
            ttl = self._redis.ttl(key)
            snapshot[key_str] = {
                "value": value.decode() if isinstance(value, bytes) else value,
                "ttl": ttl if ttl > 0 else None,
            }

        self._snapshots[name] = snapshot
        self._checkpoints.append(name)

    def rollback(self, name: str) -> None:
        self._ensure_connected()

        if name not in self._snapshots:
            raise ValueError(f"Checkpoint '{name}' not found")

        snapshot = self._snapshots[name]

        # Clear current keys
        keys = self._redis.keys(f"{self.key_prefix}*")
        if keys:
            self._redis.delete(*keys)

        # Restore snapshot
        for key, data in snapshot.items():
            if data["ttl"]:
                self._redis.setex(key, data["ttl"], data["value"])
            else:
                self._redis.set(key, data["value"])

    def release(self, name: str) -> None:
        if name in self._snapshots:
            del self._snapshots[name]
        if name in self._checkpoints:
            self._checkpoints.remove(name)

    def reset(self) -> None:
        self._ensure_connected()

        # Delete all keys matching prefix
        keys = self._redis.keys(f"{self.key_prefix}*")
        if keys:
            self._redis.delete(*keys)

        self._snapshots.clear()
        self._checkpoints.clear()
```

## Example: MongoDB Backend

```python
from pymongo import MongoClient
from bson import json_util
import json
from venomqa.state.base import BaseStateManager


class MongoDBStateManager(BaseStateManager):
    """MongoDB state manager using collection snapshots."""

    def __init__(
        self,
        connection_url: str,
        database: str,
        collections_to_reset: list[str] | None = None,
    ):
        super().__init__(connection_url)
        self.database_name = database
        self.collections_to_reset = collections_to_reset or []
        self._client = None
        self._db = None
        self._snapshots: dict[str, dict] = {}

    def connect(self) -> None:
        self._client = MongoClient(self.connection_url)
        self._db = self._client[self.database_name]
        self._connected = True

    def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
        self._connected = False

    def checkpoint(self, name: str) -> None:
        self._ensure_connected()

        collections = self.collections_to_reset or self._db.list_collection_names()
        snapshot = {}

        for coll_name in collections:
            coll = self._db[coll_name]
            docs = list(coll.find({}))
            snapshot[coll_name] = json.loads(json_util.dumps(docs))

        self._snapshots[name] = snapshot
        self._checkpoints.append(name)

    def rollback(self, name: str) -> None:
        self._ensure_connected()

        if name not in self._snapshots:
            raise ValueError(f"Checkpoint '{name}' not found")

        snapshot = self._snapshots[name]

        for coll_name, docs in snapshot.items():
            coll = self._db[coll_name]
            coll.delete_many({})
            if docs:
                restored_docs = json.loads(json_util.dumps(docs))
                coll.insert_many(restored_docs)

    def release(self, name: str) -> None:
        if name in self._snapshots:
            del self._snapshots[name]
        if name in self._checkpoints:
            self._checkpoints.remove(name)

    def reset(self) -> None:
        self._ensure_connected()

        collections = self.collections_to_reset or self._db.list_collection_names()

        for coll_name in collections:
            self._db[coll_name].delete_many({})

        self._snapshots.clear()
        self._checkpoints.clear()
```

## Registering Custom Backends

### Using Entry Points

Add to `pyproject.toml`:

```toml
[project.entry-points."venomqa.state_backends"]
mysql = "my_package.state:MySQLStateManager"
redis = "my_package.state:RedisStateManager"
mongodb = "my_package.state:MongoDBStateManager"
```

### Using Configuration

```yaml
# venomqa.yaml
db_backend: "mysql"  # Uses registered backend
db_url: "mysql://user:pass@localhost:3306/qa_test"
```

## Using Custom Backends

```python
from my_state import MySQLStateManager
from venomqa import JourneyRunner, Client

# Create state manager
state_manager = MySQLStateManager(
    connection_url="mysql://qa:secret@localhost:3306/qa_test",
    tables_to_reset=["users", "orders"],
)

# Create runner with state manager
runner = JourneyRunner(
    client=Client(base_url="http://localhost:8000"),
    state_manager=state_manager,
)

# Run journey
result = runner.run(journey)
```

## Best Practices

### 1. Handle Connection Errors

```python
def connect(self) -> None:
    try:
        self._conn = db.connect(self.connection_url)
        self._connected = True
    except Exception as e:
        self._connected = False
        raise ConnectionError(f"Failed to connect: {e}")
```

### 2. Use Context Managers

```python
class MyStateManager(BaseStateManager):
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

# Usage
with MyStateManager(url) as state_manager:
    state_manager.checkpoint("start")
    # ...
```

### 3. Implement Health Checks

```python
def health_check(self) -> bool:
    """Check if the database is healthy."""
    try:
        if not self._connected:
            return False
        self._conn.execute("SELECT 1")
        return True
    except Exception:
        return False
```

### 4. Support Async Operations

```python
import asyncio


class AsyncStateManager(BaseStateManager):
    async def connect_async(self) -> None:
        self._conn = await async_db.connect(self.connection_url)
        self._connected = True

    async def checkpoint_async(self, name: str) -> None:
        self._ensure_connected()
        await self._conn.execute(f"SAVEPOINT {name}")
        self._checkpoints.append(name)
```

### 5. Log Operations

```python
import logging

logger = logging.getLogger(__name__)


class LoggingStateManager(BaseStateManager):
    def checkpoint(self, name: str) -> None:
        logger.debug(f"Creating checkpoint: {name}")
        super().checkpoint(name)
        logger.info(f"Checkpoint created: {name}")

    def rollback(self, name: str) -> None:
        logger.debug(f"Rolling back to: {name}")
        super().rollback(name)
        logger.info(f"Rolled back to: {name}")
```
