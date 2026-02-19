# Custom Backends

Add support for MongoDB, Elasticsearch, or custom data stores by implementing the `Rollbackable` protocol.

## Overview

VenomQA uses adapters to communicate with external systems (databases, caches, message queues). Each adapter implements checkpoint/rollback semantics so exploration can branch cleanly.

## The Rollbackable Protocol

All system adapters must implement the `Rollbackable` protocol:

```python
from typing import Protocol, runtime_checkable, Any
from venomqa.sandbox import Observation

SystemCheckpoint = Any

@runtime_checkable
class Rollbackable(Protocol):
    """Protocol for systems that can checkpoint and rollback."""
    
    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Save current state and return checkpoint data."""
        ...
    
    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore state to a previous checkpoint."""
        ...
    
    def observe(self) -> Observation:
        """Get current state as an Observation."""
        ...
```

## Minimal Implementation

A simple in-memory adapter:

```python
import copy
from venomqa.sandbox import Observation

class InMemoryAdapter:
    """Simple in-memory adapter for testing."""
    
    def __init__(self, initial_data: dict | None = None):
        self._data = initial_data or {}
        self._snapshots: dict[str, dict] = {}
    
    def checkpoint(self, name: str) -> str:
        snapshot = copy.deepcopy(self._data)
        self._snapshots[name] = snapshot
        return name
    
    def rollback(self, checkpoint: str) -> None:
        self._data = copy.deepcopy(self._snapshots[checkpoint])
    
    def observe(self) -> Observation:
        return Observation.create(
            system="memory",
            data={"keys": list(self._data.keys()), "count": len(self._data)},
        )
    
    # Custom methods for your application
    def get(self, key: str) -> Any:
        return self._data.get(key)
    
    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
    
    def delete(self, key: str) -> None:
        self._data.pop(key, None)
```

## Using Custom Adapters

Register your adapter with `World`:

```python
from venomqa import Agent, World, Action, Invariant, Severity
from myapp.adapters import InMemoryAdapter

adapter = InMemoryAdapter(initial_data={"users": []})

world = World(
    api=api,
    systems={"storage": adapter},
)

agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
)

result = agent.explore()
```

Access the adapter in actions:

```python
def create_user(api, context):
    storage = context.world.systems["storage"]
    user_id = str(uuid.uuid4())
    storage.set(f"user:{user_id}", {"id": user_id, "created": datetime.utcnow()})
    context.set("user_id", user_id)
    return api.post("/users", json={"id": user_id})
```

## Example: MongoDB Adapter

Full implementation for MongoDB:

```python
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from venomqa.sandbox import Observation

class MongoDBAdapter:
    """MongoDB adapter with checkpoint/rollback via collection snapshots.
    
    This adapter creates in-memory snapshots of collections for rollback.
    Suitable for small-to-medium datasets. For large datasets, consider
    using MongoDB transactions or database clones.
    
    Example:
        from pymongo import MongoClient
        
        client = MongoClient("mongodb://localhost:27017")
        db = client["testdb"]
        
        adapter = MongoDBAdapter(
            db=db,
            collections=["users", "orders", "products"],
        )
        
        world = World(api=api, systems={"mongo": adapter})
    """
    
    def __init__(
        self,
        db,
        collections: list[str],
        checkpoint_mode: str = "memory",
    ):
        """Initialize MongoDB adapter.
        
        Args:
            db: PyMongo database instance.
            collections: List of collection names to track.
            checkpoint_mode: "memory" for in-memory snapshots,
                           "drop_restore" for temp collections (slower, less memory).
        """
        self.db = db
        self.collections = collections
        self.checkpoint_mode = checkpoint_mode
        self._snapshots: dict[str, dict[str, list[dict]]] = {}
        self._counter = 0
    
    def checkpoint(self, name: str) -> str:
        """Create a snapshot of tracked collections."""
        self._counter += 1
        checkpoint_id = f"{name}_{self._counter}"
        
        if self.checkpoint_mode == "memory":
            snapshot = {}
            for coll_name in self.collections:
                snapshot[coll_name] = list(self.db[coll_name].find())
            self._snapshots[checkpoint_id] = snapshot
        
        else:  # drop_restore mode
            for coll_name in self.collections:
                temp_name = f"_temp_{checkpoint_id}_{coll_name}"
                self.db[coll_name].aggregate([{"$out": temp_name}])
            self._snapshots[checkpoint_id] = {"mode": "drop_restore"}
        
        return checkpoint_id
    
    def rollback(self, checkpoint: str) -> None:
        """Restore collections to checkpoint state."""
        snapshot = self._snapshots[checkpoint]
        
        if snapshot.get("mode") == "drop_restore":
            # Restore from temp collections
            for coll_name in self.collections:
                temp_name = f"_temp_{checkpoint}_{coll_name}"
                self.db[coll_name].drop()
                self.db[temp_name].aggregate([{"$out": coll_name}])
                self.db[temp_name].drop()
        else:
            # Restore from memory snapshot
            for coll_name in self.collections:
                self.db[coll_name].delete_many({})
                if coll_name in snapshot and snapshot[coll_name]:
                    self.db[coll_name].insert_many(snapshot[coll_name])
    
    def observe(self) -> Observation:
        """Get observation data for state hashing."""
        data = {}
        for coll_name in self.collections:
            data[f"{coll_name}_count"] = self.db[coll_name].count_documents({})
        
        # Add some document hashes for better state discrimination
        for coll_name in self.collections[:3]:  # Limit for performance
            sample = list(self.db[coll_name].find().limit(10))
            if sample:
                data[f"{coll_name}_sample_ids"] = [str(doc.get("_id", "")) for doc in sample]
        
        return Observation.create(
            system="mongodb",
            data=data,
            metadata={"checkpoint_mode": self.checkpoint_mode},
        )
    
    def query(self, collection: str, filter: dict | None = None) -> list[dict]:
        """Query a collection (helper method)."""
        return list(self.db[collection].find(filter or {}))
    
    def insert(self, collection: str, document: dict) -> str:
        """Insert a document and return its ID."""
        result = self.db[collection].insert_one(document)
        return str(result.inserted_id)
    
    def update(self, collection: str, filter: dict, update: dict) -> int:
        """Update documents and return count."""
        result = self.db[collection].update_many(filter, {"$set": update})
        return result.modified_count
    
    def delete(self, collection: str, filter: dict) -> int:
        """Delete documents and return count."""
        result = self.db[collection].delete_many(filter)
        return result.deleted_count
```

Usage:

```python
from pymongo import MongoClient
from venomqa import Agent, World, Action, Invariant, Severity
from myapp.adapters.mongodb import MongoDBAdapter

client = MongoClient("mongodb://localhost:27017")
db = client["testdb"]

adapter = MongoDBAdapter(
    db=db,
    collections=["users", "orders", "products"],
)

world = World(api=api, systems={"db": adapter})

def create_order(api, context):
    db = context.world.systems["db"]
    order_id = db.insert("orders", {
        "user_id": context.get("user_id"),
        "amount": 100,
        "status": "pending",
        "created_at": datetime.utcnow(),
    })
    context.set("order_id", order_id)
    return api.post("/orders", json={"id": order_id})

def fulfill_order(api, context):
    order_id = context.get("order_id")
    db = context.world.systems["db"]
    db.update("orders", {"_id": ObjectId(order_id)}, {"status": "fulfilled"})
    return api.post(f"/orders/{order_id}/fulfill")
```

## Example: Elasticsearch Adapter

```python
from __future__ import annotations

import copy
from typing import Any

from venomqa.sandbox import Observation

class ElasticsearchAdapter:
    """Elasticsearch adapter with scroll-based snapshots.
    
    Uses scroll API to snapshot documents, restores via bulk delete/insert.
    
    Example:
        from elasticsearch import Elasticsearch
        
        client = Elasticsearch(["http://localhost:9200"])
        
        adapter = ElasticsearchAdapter(
            client=client,
            indices=["users", "orders"],
        )
        
        world = World(api=api, systems={"es": adapter})
    """
    
    def __init__(
        self,
        client,
        indices: list[str],
        batch_size: int = 1000,
    ):
        """Initialize Elasticsearch adapter.
        
        Args:
            client: Elasticsearch client instance.
            indices: List of index names to track.
            batch_size: Batch size for scroll operations.
        """
        self.client = client
        self.indices = indices
        self.batch_size = batch_size
        self._snapshots: dict[str, dict[str, list[dict]]] = {}
        self._counter = 0
    
    def checkpoint(self, name: str) -> str:
        """Create a snapshot of tracked indices."""
        self._counter += 1
        checkpoint_id = f"{name}_{self._counter}"
        
        snapshot = {}
        for index in self.indices:
            snapshot[index] = self._snapshot_index(index)
        
        self._snapshots[checkpoint_id] = snapshot
        return checkpoint_id
    
    def _snapshot_index(self, index: str) -> list[dict]:
        """Snapshot all documents from an index."""
        documents = []
        
        response = self.client.search(
            index=index,
            body={"query": {"match_all": {}}},
            size=self.batch_size,
            scroll="2m",
        )
        
        scroll_id = response.get("_scroll_id")
        hits = response["hits"]["hits"]
        
        while hits:
            documents.extend(hits)
            response = self.client.scroll(scroll_id=scroll_id, scroll="2m")
            scroll_id = response.get("_scroll_id")
            hits = response["hits"]["hits"]
        
        if scroll_id:
            try:
                self.client.clear_scroll(scroll_id=scroll_id)
            except Exception:
                pass
        
        return documents
    
    def rollback(self, checkpoint: str) -> None:
        """Restore indices to checkpoint state."""
        snapshot = self._snapshots[checkpoint]
        
        for index in self.indices:
            # Delete all documents
            self.client.delete_by_query(
                index=index,
                body={"query": {"match_all": {}}},
                conflicts="proceed",
            )
            
            # Restore documents
            if snapshot[index]:
                actions = []
                for doc in snapshot[index]:
                    actions.append({
                        "_index": index,
                        "_id": doc["_id"],
                        "_source": doc["_source"],
                    })
                
                from elasticsearch.helpers import bulk
                bulk(self.client, actions)
    
    def observe(self) -> Observation:
        """Get observation data for state hashing."""
        data = {}
        
        for index in self.indices:
            count = self.client.count(index=index)["count"]
            data[f"{index}_count"] = count
            
            # Sample some IDs
            if count > 0:
                sample = self.client.search(
                    index=index,
                    body={"query": {"match_all": {}}},
                    size=5,
                    _source=False,
                )
                data[f"{index}_sample_ids"] = [hit["_id"] for hit in sample["hits"]["hits"]]
        
        return Observation.create(
            system="elasticsearch",
            data=data,
        )
    
    def search(self, index: str, query: dict) -> list[dict]:
        """Search an index (helper method)."""
        response = self.client.search(index=index, body=query)
        return response["hits"]["hits"]
    
    def index_document(self, index: str, doc: dict, id: str | None = None) -> str:
        """Index a document and return its ID."""
        body = doc.copy()
        response = self.client.index(index=index, id=id, body=body)
        return response["_id"]
    
    def delete_document(self, index: str, id: str) -> bool:
        """Delete a document by ID."""
        try:
            self.client.delete(index=index, id=id)
            return True
        except Exception:
            return False
```

## Example: Redis Adapter (Advanced)

Redis adapter using Lua scripts for atomic snapshots:

```python
from __future__ import annotations

from typing import Any

from venomqa.sandbox import Observation

class RedisAdapter:
    """Redis adapter with atomic dump/restore.
    
    Uses Redis DUMP/RESTORE for atomic checkpoint/rollback.
    Handles strings, hashes, sets, and sorted sets.
    
    Example:
        import redis
        
        client = redis.Redis(host="localhost", port=6379, db=0)
        
        adapter = RedisAdapter(
            client=client,
            key_prefix="myapp:",
        )
        
        world = World(api=api, systems={"redis": adapter})
    """
    
    def __init__(
        self,
        client,
        key_prefix: str = "",
        scan_count: int = 1000,
    ):
        """Initialize Redis adapter.
        
        Args:
            client: Redis client instance.
            key_prefix: Only track keys with this prefix.
            scan_count: Batch size for SCAN operations.
        """
        self.client = client
        self.key_prefix = key_prefix
        self.scan_count = scan_count
        self._snapshots: dict[str, dict[str, bytes]] = {}
        self._counter = 0
    
    def _get_keys(self) -> list[str]:
        """Get all keys matching prefix."""
        keys = []
        cursor = 0
        pattern = f"{self.key_prefix}*" if self.key_prefix else "*"
        
        while True:
            cursor, batch = self.client.scan(cursor, match=pattern, count=self.scan_count)
            keys.extend(batch)
            if cursor == 0:
                break
        
        return keys
    
    def checkpoint(self, name: str) -> str:
        """Dump all keys atomically."""
        self._counter += 1
        checkpoint_id = f"{name}_{self._counter}"
        
        keys = self._get_keys()
        snapshot = {}
        
        for key in keys:
            dump = self.client.dump(key)
            if dump:
                snapshot[key] = dump
            ttl = self.client.ttl(key)
            snapshot[f"__ttl__{key}"] = ttl
        
        self._snapshots[checkpoint_id] = snapshot
        return checkpoint_id
    
    def rollback(self, checkpoint: str) -> None:
        """Restore all keys from dump."""
        snapshot = self._snapshots[checkpoint]
        
        # Delete current keys
        keys = self._get_keys()
        if keys:
            self.client.delete(*keys)
        
        # Restore from snapshot
        for key, dump in snapshot.items():
            if key.startswith("__ttl__"):
                continue
            
            ttl = snapshot.get(f"__ttl__{key}", -1)
            if ttl == -2:  # Key had no expiry
                ttl = 0
            
            try:
                self.client.restore(key, ttl, dump, replace=True)
            except Exception:
                pass
    
    def observe(self) -> Observation:
        """Get observation data for state hashing."""
        keys = self._get_keys()
        
        data = {
            "key_count": len(keys),
            "keys": sorted(keys)[:50],  # Sample for hashing
        }
        
        # Add type counts
        type_counts = {}
        for key in keys[:100]:
            key_type = self.client.type(key)
            type_counts[key_type] = type_counts.get(key_type, 0) + 1
        data["type_counts"] = type_counts
        
        return Observation.create(
            system="redis",
            data=data,
        )
    
    def get(self, key: str) -> Any:
        """Get a value (helper method)."""
        return self.client.get(self.key_prefix + key)
    
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value (helper method)."""
        full_key = self.key_prefix + key
        if ttl:
            self.client.setex(full_key, ttl, value)
        else:
            self.client.set(full_key, value)
    
    def delete(self, key: str) -> None:
        """Delete a key (helper method)."""
        self.client.delete(self.key_prefix + key)
```

## Best Practices

### 1. Minimize Snapshot Size

```python
def checkpoint(self, name: str) -> str:
    snapshot = {}
    for coll in self.collections:
        # Only snapshot essential fields
        snapshot[coll] = [
            {"_id": doc["_id"], "status": doc.get("status")}
            for doc in self.db[coll].find()
        ]
    return snapshot
```

### 2. Handle Large Datasets

```python
class LargeDatasetAdapter:
    def __init__(self, db, collections: list[str], max_docs: int = 10000):
        self.max_docs = max_docs
    
    def checkpoint(self, name: str) -> str:
        # Warn if dataset is too large
        total_docs = sum(self.db[c].count_documents({}) for c in self.collections)
        if total_docs > self.max_docs:
            warnings.warn(f"Large dataset ({total_docs} docs). Consider sharding.")
```

### 3. Use Efficient Queries

```python
def observe(self) -> Observation:
    # Use aggregation for counts instead of fetching all docs
    pipeline = [{"$count": "total"}]
    counts = {c: list(self.db[c].aggregate(pipeline))[0]["total"]
              for c in self.collections}
```

### 4. Clean Up Resources

```python
def close(self) -> None:
    """Close connections when exploration ends."""
    self.client.close()
```

### 5. Provide Useful Observations

```python
def observe(self) -> Observation:
    return Observation.create(
        system="mongodb",
        data={
            "users_count": 5,
            "users_statuses": {"active": 3, "pending": 2},  # Good for dedup
            "orders_count": 10,
        },
    )
```

## Troubleshooting

### "Rollback didn't restore state"

Ensure you're deep-copying data:

```python
import copy

def checkpoint(self, name: str) -> str:
    # Bad: shallow copy
    snapshot = self._data.copy()
    
    # Good: deep copy
    snapshot = copy.deepcopy(self._data)
```

### "State explosion with adapter"

Add meaningful fields to observations:

```python
def observe(self) -> Observation:
    return Observation.create(
        system="mydb",
        data={
            "order_count": self.count("orders"),
            "max_order_id": self.max_id("orders"),  # Helps distinguish states
        },
    )
```

### "Checkpoint too slow"

Consider lazy checkpointing:

```python
def checkpoint(self, name: str) -> str:
    # Just record the name, snapshot on first rollback
    self._pending_checkpoint = name
    return name
```
