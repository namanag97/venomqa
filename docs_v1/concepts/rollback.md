# How Rollback Works

Rollback is the core mechanism that enables state graph exploration. Without rollback, we could only test one path through the application. With rollback, we can explore every path.

This document explains how rollback works at every level: conceptually, in the World, and in each system adapter.

## Why Rollback Matters

Consider an e-commerce checkout flow:

```
[Cart with items]
       │
       ├── checkout ──► [Order Created]
       │                      │
       │                      ├── pay ──► [Order Paid]
       │                      │
       │                      └── cancel ──► [Order Cancelled]
       │
       └── empty_cart ──► [Empty Cart]
```

To test all paths, we need to:

1. Start with items in cart
2. Do checkout → Order Created
3. **Go back to "Cart with items"**
4. Do empty_cart → Empty Cart
5. **Go back to "Order Created"**
6. Do pay → Order Paid
7. **Go back to "Order Created"**
8. Do cancel → Order Cancelled

Steps 3, 5, and 7 require **rollback**. We need to restore the database, cache, and all other state to exactly what it was at that earlier point.

## The Rollback Guarantee

VenomQA guarantees that after `world.rollback(checkpoint)`:

> Every system in the World is indistinguishable from its state at the time `world.checkpoint()` was called.

This means:
- Database rows are exactly as they were
- Cache keys are exactly as they were
- Queue messages are exactly as they were
- Any observation you could make returns the same result

## World-Level Rollback

The World coordinates rollback across all systems atomically.

### Checkpoint

```python
def checkpoint(self, name: str) -> CheckpointID:
    """Save state of ALL systems atomically."""

    # Generate unique checkpoint ID
    checkpoint_id = f"cp_{uuid4().hex[:8]}"

    # Checkpoint each system
    system_checkpoints = {}
    for system_name, system in self.systems.items():
        system_checkpoints[system_name] = system.checkpoint(name)

    # Store the composite checkpoint
    self.checkpoints[checkpoint_id] = Checkpoint(
        id=checkpoint_id,
        name=name,
        system_checkpoints=system_checkpoints,
        created_at=datetime.now(),
    )

    return checkpoint_id
```

### Rollback

```python
def rollback(self, checkpoint_id: CheckpointID) -> None:
    """Restore ALL systems to checkpoint atomically."""

    # Get the checkpoint
    checkpoint = self.checkpoints[checkpoint_id]

    # Rollback each system
    for system_name, system_checkpoint in checkpoint.system_checkpoints.items():
        self.systems[system_name].rollback(system_checkpoint)
```

### Atomicity

The World ensures that either:
- All systems checkpoint successfully, OR
- No checkpoint is created (and an error is raised)

Similarly for rollback:
- All systems rollback successfully, OR
- An error is raised (and the World is in an inconsistent state — this is a fatal error)

## System-Level Rollback

Each system implements the `Rollbackable` protocol differently based on its capabilities.

### PostgreSQL

PostgreSQL supports transactional savepoints natively.

**Strategy**: Run the entire exploration within a single transaction. Use `SAVEPOINT` and `ROLLBACK TO SAVEPOINT` for checkpoints.

```python
class PostgresAdapter(Rollbackable):
    def __init__(self, connection_url: str):
        self.conn = psycopg.connect(connection_url)
        self.conn.autocommit = False  # CRITICAL: Stay in transaction
        self._transaction_started = False

    def begin(self):
        """Start the enclosing transaction. Call once at exploration start."""
        if not self._transaction_started:
            self.conn.execute("BEGIN")
            self._transaction_started = True

    def checkpoint(self, name: str) -> str:
        """Create a savepoint."""
        savepoint_name = f"sp_{name}_{uuid4().hex[:8]}"
        self.conn.execute(f"SAVEPOINT {savepoint_name}")
        return savepoint_name

    def rollback(self, savepoint_name: str) -> None:
        """Rollback to savepoint."""
        self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")

    def end(self):
        """End exploration. Rollback everything — don't commit."""
        if self._transaction_started:
            self.conn.execute("ROLLBACK")
            self._transaction_started = False

    def observe(self) -> Observation:
        """Query database state."""
        # Example: count rows in key tables
        data = {}
        for table in ["users", "orders", "products"]:
            result = self.conn.execute(f"SELECT COUNT(*) FROM {table}")
            data[f"{table}_count"] = result.fetchone()[0]
        return Observation(system="db", data=data, observed_at=datetime.now())
```

**Key insight**: The entire exploration is one transaction that is never committed. At the end, we `ROLLBACK` the whole thing. The database is pristine.

**Limitations**:
- All operations must be within one transaction
- Cannot test actual commit behavior
- Long transactions may cause lock contention

### MySQL

MySQL also supports savepoints within InnoDB transactions.

```python
class MySQLAdapter(Rollbackable):
    def __init__(self, connection_url: str):
        self.conn = mysql.connector.connect(...)
        self.conn.autocommit = False

    def checkpoint(self, name: str) -> str:
        savepoint_name = f"sp_{name}"
        self.conn.execute(f"SAVEPOINT {savepoint_name}")
        return savepoint_name

    def rollback(self, savepoint_name: str) -> None:
        self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
```

**Same limitations as PostgreSQL.**

### SQLite

SQLite supports savepoints, but file-based rollback is sometimes easier.

```python
class SQLiteAdapter(Rollbackable):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.checkpoints_dir = Path(tempfile.mkdtemp())

    def checkpoint(self, name: str) -> Path:
        """Copy the database file."""
        checkpoint_path = self.checkpoints_dir / f"{name}.db"
        shutil.copy(self.db_path, checkpoint_path)
        return checkpoint_path

    def rollback(self, checkpoint_path: Path) -> None:
        """Restore the database file."""
        shutil.copy(checkpoint_path, self.db_path)
```

**Trade-off**: File copy is slower but simpler and allows testing commit behavior.

### Redis

Redis doesn't have native rollback. We implement it by dumping and restoring keys.

```python
class RedisAdapter(Rollbackable):
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)

    def checkpoint(self, name: str) -> dict[str, bytes]:
        """Dump all keys."""
        checkpoint_data = {}
        for key in self.redis.keys("*"):
            checkpoint_data[key] = self.redis.dump(key)
        return checkpoint_data

    def rollback(self, checkpoint_data: dict[str, bytes]) -> None:
        """Restore all keys."""
        # Delete all current keys
        self.redis.flushall()

        # Restore checkpointed keys
        for key, value in checkpoint_data.items():
            self.redis.restore(key, 0, value)

    def observe(self) -> Observation:
        keys = [k.decode() for k in self.redis.keys("*")]
        return Observation(
            system="cache",
            data={"keys": keys, "count": len(keys)},
            observed_at=datetime.now(),
        )
```

**Limitations**:
- Slow for large datasets
- `FLUSHALL` is destructive — must use isolated Redis instance
- Key expiration times are not perfectly preserved

### Mock Systems

For systems that cannot rollback (queues, email, external APIs), we use in-memory mocks.

#### MockQueue

```python
@dataclass
class QueueMessage:
    id: str
    body: dict
    published_at: datetime

class MockQueue(Rollbackable):
    def __init__(self):
        self.messages: list[QueueMessage] = []

    def publish(self, body: dict) -> str:
        """Publish a message."""
        msg = QueueMessage(
            id=f"msg_{uuid4().hex[:8]}",
            body=body,
            published_at=datetime.now(),
        )
        self.messages.append(msg)
        return msg.id

    def consume(self) -> QueueMessage | None:
        """Consume a message."""
        if self.messages:
            return self.messages.pop(0)
        return None

    def checkpoint(self, name: str) -> list[QueueMessage]:
        """Copy the message list."""
        return [copy.deepcopy(msg) for msg in self.messages]

    def rollback(self, checkpoint: list[QueueMessage]) -> None:
        """Restore the message list."""
        self.messages = [copy.deepcopy(msg) for msg in checkpoint]

    def observe(self) -> Observation:
        return Observation(
            system="queue",
            data={
                "pending": len(self.messages),
                "message_ids": [m.id for m in self.messages],
            },
            observed_at=datetime.now(),
        )
```

#### MockMail

```python
@dataclass
class CapturedEmail:
    to: str
    subject: str
    body: str
    sent_at: datetime

class MockMail(Rollbackable):
    def __init__(self):
        self.emails: list[CapturedEmail] = []

    def send(self, to: str, subject: str, body: str) -> None:
        """Capture an email."""
        self.emails.append(CapturedEmail(
            to=to,
            subject=subject,
            body=body,
            sent_at=datetime.now(),
        ))

    def checkpoint(self, name: str) -> int:
        """Save the email count."""
        return len(self.emails)

    def rollback(self, count: int) -> None:
        """Delete emails sent after checkpoint."""
        self.emails = self.emails[:count]

    def observe(self) -> Observation:
        return Observation(
            system="mail",
            data={
                "count": len(self.emails),
                "recipients": [e.to for e in self.emails],
            },
            observed_at=datetime.now(),
        )
```

#### MockStorage

```python
class MockStorage(Rollbackable):
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def put(self, path: str, data: bytes) -> None:
        self.files[path] = data

    def get(self, path: str) -> bytes | None:
        return self.files.get(path)

    def delete(self, path: str) -> None:
        self.files.pop(path, None)

    def checkpoint(self, name: str) -> dict[str, bytes]:
        return copy.deepcopy(self.files)

    def rollback(self, checkpoint: dict[str, bytes]) -> None:
        self.files = copy.deepcopy(checkpoint)
```

### WireMock (External API Mocking)

For external APIs (Stripe, SendGrid, etc.), we use WireMock to mock responses and track requests.

```python
class WireMockAdapter(Rollbackable):
    def __init__(self, wiremock_url: str):
        self.base_url = wiremock_url

    def checkpoint(self, name: str) -> dict:
        """Save current stub mappings and request journal."""
        mappings = requests.get(f"{self.base_url}/__admin/mappings").json()
        requests_journal = requests.get(f"{self.base_url}/__admin/requests").json()
        return {
            "mappings": mappings,
            "requests": requests_journal,
        }

    def rollback(self, checkpoint: dict) -> None:
        """Restore stubs and clear requests since checkpoint."""
        # Reset to checkpoint mappings
        requests.post(f"{self.base_url}/__admin/mappings/reset")
        for mapping in checkpoint["mappings"]["mappings"]:
            requests.post(f"{self.base_url}/__admin/mappings", json=mapping)

        # Clear request journal
        requests.delete(f"{self.base_url}/__admin/requests")
```

## Rollback Strategies Comparison

| System | Checkpoint Method | Rollback Method | Speed | Fidelity |
|--------|-------------------|-----------------|-------|----------|
| PostgreSQL | SAVEPOINT | ROLLBACK TO SAVEPOINT | Fast | High |
| MySQL | SAVEPOINT | ROLLBACK TO SAVEPOINT | Fast | High |
| SQLite | File copy | File copy | Medium | Perfect |
| Redis | DUMP keys | FLUSHALL + RESTORE | Slow | High |
| MockQueue | Copy list | Replace list | Fast | Perfect |
| MockMail | Save count | Truncate list | Fast | Perfect |
| MockStorage | Copy dict | Replace dict | Fast | Perfect |
| WireMock | Save mappings | Reset + restore | Medium | High |

## Common Pitfalls

### 1. Autocommit Mode

**Problem**: Database commits each statement automatically.

```python
# WRONG: autocommit=True breaks savepoints
conn = psycopg.connect(url, autocommit=True)

# RIGHT: autocommit=False keeps transaction open
conn = psycopg.connect(url, autocommit=False)
```

### 2. Shared Database

**Problem**: Other processes modify the database during exploration.

**Solution**: Use an isolated test database. Run VenomQA in exclusive mode.

### 3. Non-Deterministic Actions

**Problem**: An action produces different results each time (timestamps, random IDs).

**Solution**: Control sources of non-determinism:
- Mock the clock (see TimeAdapter)
- Seed random number generators
- Use deterministic ID generation in tests

### 4. External Side Effects

**Problem**: An action sends a real email or charges a real credit card.

**Solution**: Always mock external services. Never point VenomQA at production APIs.

### 5. Large Data Sets

**Problem**: Checkpointing Redis with millions of keys is slow.

**Solution**:
- Use a smaller test dataset
- Checkpoint only specific key prefixes
- Accept slower exploration for thoroughness

## The Exploration Transaction Pattern

For database-backed systems, VenomQA uses this pattern:

```
BEGIN TRANSACTION
│
├── Initial setup (seed data)
│
├── SAVEPOINT initial
│   │
│   ├── Action 1
│   │   └── SAVEPOINT after_action_1
│   │       │
│   │       ├── Action 2a
│   │       │   └── observe, check invariants
│   │       │
│   │       └── ROLLBACK TO after_action_1
│   │           │
│   │           └── Action 2b
│   │               └── observe, check invariants
│   │
│   └── ROLLBACK TO initial
│       │
│       └── Action 1b
│           └── ...
│
└── ROLLBACK  (never COMMIT)
```

The entire exploration is one transaction. Nothing is ever committed. The database is unchanged after exploration.

## Testing Your Adapters

Before using an adapter in exploration, verify it works:

```python
def test_adapter_rollback():
    adapter = PostgresAdapter("postgres://localhost/testdb")
    adapter.begin()

    # Initial state
    initial_count = adapter.observe().data["users_count"]

    # Checkpoint
    cp = adapter.checkpoint("test")

    # Modify state
    adapter.conn.execute("INSERT INTO users (name) VALUES ('test')")
    modified_count = adapter.observe().data["users_count"]
    assert modified_count == initial_count + 1

    # Rollback
    adapter.rollback(cp)

    # Verify restoration
    restored_count = adapter.observe().data["users_count"]
    assert restored_count == initial_count  # MUST equal initial

    adapter.end()
```

This test should pass for every adapter before you use it in production.
