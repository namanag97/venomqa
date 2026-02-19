# Ports & Adapters

Clean architecture for testable API clients.

## The Problem

Tightly coupled code is hard to test:

```python
# Bad: Hard to test
def create_order():
    import requests
    resp = requests.post("http://api.example.com/orders", json={...})
    return resp.json()
```

This code:

- Hard-codes the HTTP library (requests)
- Hard-codes the base URL
- Can't be mocked easily
- Can't be reused in different environments

## The Solution: Ports & Adapters

Separate **what** you do (port) from **how** you do it (adapter):

```
┌─────────────────┐      ┌─────────────────┐
│  Your Code      │      │  VenomQA Test   │
│  (Production)   │      │  (Exploration)  │
└────────┬────────┘      └────────┬────────┘
         │                        │
         ▼                        ▼
┌─────────────────────────────────────────┐
│              PORT (Interface)            │
│  create_order(), refund_order(), ...    │
└────────────────────┬────────────────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
┌─────────────────┐      ┌─────────────────┐
│  HTTP Adapter   │      │  Mock Adapter   │
│  (Production)   │      │  (Testing)      │
└─────────────────┘      └─────────────────┘
```

## Ports (Interfaces)

A port defines what operations are possible:

```python
# ports/order_port.py
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass

@dataclass
class Order:
    id: str
    amount: int
    status: str

class OrderPort(ABC):
    @abstractmethod
    def create(self, amount: int) -> Order:
        """Create a new order."""
        pass

    @abstractmethod
    def refund(self, order_id: str) -> Order:
        """Refund an order."""
        pass

    @abstractmethod
    def get(self, order_id: str) -> Optional[Order]:
        """Get an order by ID."""
        pass

    @abstractmethod
    def cancel(self, order_id: str) -> Order:
        """Cancel an order."""
        pass
```

## Adapters (Implementations)

### HTTP Adapter (Production)

```python
# adapters/http_order_adapter.py
from venomqa.adapters.http import HttpClient

class HTTPOrderAdapter(OrderPort):
    def __init__(self, base_url: str):
        self.client = HttpClient(base_url)

    def create(self, amount: int) -> Order:
        resp = self.client.post("/orders", json={"amount": amount})
        data = resp.json()
        return Order(id=data["id"], amount=amount, status="created")

    def refund(self, order_id: str) -> Order:
        resp = self.client.post(f"/orders/{order_id}/refund")
        data = resp.json()
        return Order(id=data["id"], amount=data["amount"], status="refunded")

    def get(self, order_id: str) -> Optional[Order]:
        resp = self.client.get(f"/orders/{order_id}")
        if resp.status_code == 404:
            return None
        data = resp.json()
        return Order(id=data["id"], amount=data["amount"], status=data["status"])

    def cancel(self, order_id: str) -> Order:
        resp = self.client.post(f"/orders/{order_id}/cancel")
        data = resp.json()
        return Order(id=data["id"], amount=data["amount"], status="canceled")
```

### Mock Adapter (Testing)

```python
# adapters/mock_order_adapter.py
class MockOrderAdapter(OrderPort):
    def __init__(self):
        self.orders = {}
        self.next_id = 1

    def create(self, amount: int) -> Order:
        order = Order(id=str(self.next_id), amount=amount, status="created")
        self.orders[order.id] = order
        self.next_id += 1
        return order

    def refund(self, order_id: str) -> Order:
        order = self.orders.get(order_id)
        if order:
            order.status = "refunded"
        return order

    def get(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)

    def cancel(self, order_id: str) -> Order:
        order = self.orders.get(order_id)
        if order:
            order.status = "canceled"
        return order
```

## Using in VenomQA

### With HTTP Adapter

```python
from venomqa import Action, Agent, BFS, World
from adapters.http_order_adapter import HTTPOrderAdapter

orders = HTTPOrderAdapter("http://localhost:8000")
api = HttpClient("http://localhost:8000")
world = World(api=api, state_from_context=["order_id"])

def create_order(api, context):
    order = orders.create(amount=100)
    context.set("order_id", order.id)
    return order

def refund_order(api, context):
    order_id = context.get("order_id")
    return orders.refund(order_id)

agent = Agent(
    world=world,
    actions=[
        Action("create_order", create_order),
        Action("refund_order", refund_order),
    ],
    invariants=[...],
    strategy=BFS(),
).explore()
```

### With Mock Adapter

```python
from adapters.mock_order_adapter import MockOrderAdapter

orders = MockOrderAdapter()

# Use without real server
def test_create_refund_flow():
    order = orders.create(100)
    assert order.status == "created"

    refunded = orders.refund(order.id)
    assert refunded.status == "refunded"
```

## VenomQA's Built-in Adapters

VenomQA provides ready-to-use adapters:

### HttpClient

```python
from venomqa.adapters.http import HttpClient

api = HttpClient(
    base_url="http://localhost:8000",
    headers={"X-API-Key": "secret"},
    timeout=30.0,
)

resp = api.get("/orders/123")
resp = api.post("/orders", json={"amount": 100})
resp = api.put("/orders/123", json={"amount": 200})
resp = api.delete("/orders/123")
```

### PostgresAdapter

```python
from venomqa.adapters.postgres import PostgresAdapter

db = PostgresAdapter("postgresql://localhost/testdb")

rows = db.query("SELECT * FROM orders WHERE status = $1", ["pending"])
db.execute("UPDATE orders SET status = $1 WHERE id = $2", ["shipped", "123"])
```

### SQLiteAdapter

```python
from venomqa.adapters.sqlite import SQLiteAdapter

db = SQLiteAdapter("/path/to/database.db")
```

## Benefits

| Aspect | Without Ports | With Ports |
|--------|---------------|------------|
| Test without server | ✗ | ✓ |
| Swap implementations | ✗ | ✓ |
| Mock in unit tests | Hard | Easy |
| VenomQA integration | Manual | Automatic |

## When to Use

### Use Ports & Adapters When:

- Your API has complex business logic
- You want to test without a running server
- You need multiple implementations (HTTP, gRPC, etc.)
- You're building a library, not just a client

### Skip When:

- You're testing a simple external API
- The overhead isn't worth it
- You only have one implementation

## Example: Full Stack

```python
# Application code uses ports
class OrderService:
    def __init__(self, orders: OrderPort):
        self.orders = orders

    def process_refund(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if not order or order.status != "created":
            return False
        self.orders.refund(order_id)
        return True

# Production wiring
service = OrderService(HTTPOrderAdapter("https://api.example.com"))

# Test wiring
service = OrderService(MockOrderAdapter())

# VenomQA wiring
world = World(api=api, state_from_context=["order_id"])
```

## Next Steps

- [Adapters Reference](../reference/adapters.md) - Full adapter docs
- [Examples](../examples/index.md) - Real-world patterns
- [State Management](state.md) - Context and state
