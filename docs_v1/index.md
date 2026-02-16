# VenomQA

**Autonomous QA Agent for State Graph Exploration**

## What is VenomQA?

VenomQA is a testing framework that explores your API the way a human QA engineer would — by trying different actions, observing results, and systematically testing all possible paths through your application.

## The Problem

Traditional API testing is **linear**:

```
test_login()        → pass
test_create_order() → pass
test_checkout()     → pass
```

Each test runs independently. But real applications have **state**. After logging in, a user can:
- View their profile
- Create an order
- Update settings
- Log out

Each action leads to a new state with new possibilities. This forms a **graph**, not a line:

```
                         [Initial]
                             │
                           login
                             ▼
                        [LoggedIn]
                       /    │    \
            view_profile  create   logout
                 │        order      │
                 ▼          │        ▼
             [Profile]      ▼    [LoggedOut]
                       [HasOrder]
                       /        \
                   pay          cancel
                    │             │
                    ▼             ▼
                [Paid]      [Cancelled]
```

Traditional testing misses most of this graph. It tests one path and hopes the others work.

## The Solution

VenomQA explores the **entire graph** by:

1. **Executing an action** (e.g., POST /orders)
2. **Checkpointing** the system state (database, cache, queues)
3. **Observing** what changed
4. **Rolling back** to try alternate actions from the same state
5. **Checking invariants** (rules that must always hold)
6. **Recording violations** (bugs found)

This is exactly what a thorough human QA would do — but automatically and exhaustively.

## Key Insight: Rollback

The key innovation is **rollback**. To explore multiple paths from the same state, we must be able to return to that state.

VenomQA creates a **sandbox** where all stateful systems support checkpoint and rollback:

| System | Rollback Method |
|--------|-----------------|
| PostgreSQL | `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` |
| MySQL | `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` |
| Redis | `DUMP` keys / `RESTORE` keys |
| Queues | Mock with in-memory state |
| Email | Mock with in-memory capture |
| External APIs | Mock with WireMock |

Systems that cannot rollback (real Stripe, real email) are replaced with mocks that can.

## Core Concepts

VenomQA has five core concepts:

| Concept | What it is |
|---------|------------|
| **State** | A snapshot of the world at a moment |
| **Action** | Something that changes the world (usually an API call) |
| **World** | The sandbox containing all rollbackable systems |
| **Invariant** | A rule that must always be true |
| **Agent** | The explorer that traverses the state graph |

## Quick Example

```python
from venomqa import World, Agent, Action, Invariant
from venomqa.adapters import HttpClient, PostgresAdapter

# Create the sandbox world
world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db": PostgresAdapter("postgres://localhost/testdb"),
    }
)

# Define actions
login = Action(
    name="login",
    execute=lambda api: api.post("/auth/login", json={
        "email": "test@example.com",
        "password": "secret"
    }),
)

create_order = Action(
    name="create_order",
    execute=lambda api: api.post("/orders", json={"product_id": 1}),
    preconditions=[lambda state: state.get("logged_in", False)],
)

# Define invariants
order_count_consistent = Invariant(
    name="order_count_consistent",
    check=lambda world: (
        world.systems["db"].query("SELECT COUNT(*) FROM orders")[0][0]
        == len(world.api.get("/orders").json())
    ),
    message="Database order count must match API response",
)

# Explore
agent = Agent(
    world=world,
    actions=[login, create_order, logout, ...],
    invariants=[order_count_consistent],
)

result = agent.explore()

print(f"States explored: {result.states_visited}")
print(f"Violations found: {len(result.violations)}")

for violation in result.violations:
    print(f"  - {violation.invariant.name} after {violation.action.name}")
```

## Documentation

- [Core Concepts](concepts/overview.md) — The mental model
- [Data Model](data-model/index.md) — All objects and their relationships
- [How Rollback Works](concepts/rollback.md) — The key mechanism
- [Writing Actions](guides/writing-actions.md) — How to define actions
- [Writing Invariants](guides/writing-invariants.md) — How to define rules
- [Adapters](adapters/index.md) — Database, cache, queue implementations
- [DSL Reference](dsl/index.md) — Journey, Step, Branch syntax
- [CLI Reference](cli/index.md) — Command-line usage

## Installation

```bash
pip install venomqa
```

## License

MIT
