# Core Concepts

This document explains the fundamental concepts in VenomQA. Understanding these concepts is essential for using the framework effectively.

## The Five Concepts

VenomQA is built on five core concepts that work together:

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│                        AGENT                                        │
│                   (The Explorer)                                    │
│                                                                     │
│    The Agent traverses the state graph by executing Actions,       │
│    observing States, and checking Invariants.                      │
│                                                                     │
│    ┌─────────────────────────────────────────────────────────┐     │
│    │                                                         │     │
│    │                       WORLD                             │     │
│    │                  (The Sandbox)                          │     │
│    │                                                         │     │
│    │    The World contains all systems the Agent can         │     │
│    │    observe and rollback. It coordinates checkpoints     │     │
│    │    across all systems atomically.                       │     │
│    │                                                         │     │
│    │    ┌─────────┐  ┌─────────┐  ┌─────────┐              │     │
│    │    │   DB    │  │  Cache  │  │  Queue  │  ...         │     │
│    │    └─────────┘  └─────────┘  └─────────┘              │     │
│    │                                                         │     │
│    └─────────────────────────────────────────────────────────┘     │
│                          │                                          │
│                          │ executes                                 │
│                          ▼                                          │
│    ┌─────────────────────────────────────────────────────────┐     │
│    │                      ACTION                             │     │
│    │               (Changes the World)                       │     │
│    │                                                         │     │
│    │    POST /orders ──────────────────────────────────▶    │     │
│    │                                                         │     │
│    └─────────────────────────────────────────────────────────┘     │
│                          │                                          │
│                          │ produces                                 │
│                          ▼                                          │
│    ┌─────────────────────────────────────────────────────────┐     │
│    │                      STATE                              │     │
│    │              (Snapshot of World)                        │     │
│    │                                                         │     │
│    │    { db: {users: 5, orders: 3},                        │     │
│    │      cache: {sessions: 2},                             │     │
│    │      queue: {pending: 1} }                             │     │
│    │                                                         │     │
│    └─────────────────────────────────────────────────────────┘     │
│                          │                                          │
│                          │ checked by                               │
│                          ▼                                          │
│    ┌─────────────────────────────────────────────────────────┐     │
│    │                    INVARIANT                            │     │
│    │              (Rule That Must Hold)                      │     │
│    │                                                         │     │
│    │    "DB order count == API order count"                 │     │
│    │    "No user has negative balance"                      │     │
│    │    "Deleted items don't appear in search"              │     │
│    │                                                         │     │
│    └─────────────────────────────────────────────────────────┘     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 1. State

A **State** is a snapshot of the entire world at a moment in time.

### What's in a State?

A State contains **observations** from every system in the World:

```python
State(
    id="s_abc123",
    observations={
        "db": Observation(
            data={"users_count": 5, "orders_count": 3, "last_order_id": 42}
        ),
        "cache": Observation(
            data={"active_sessions": ["sess_1", "sess_2"]}
        ),
        "queue": Observation(
            data={"pending_jobs": 2, "failed_jobs": 0}
        ),
    },
    checkpoint_id="cp_xyz789",  # Can we rollback here?
    created_at=datetime(2024, 1, 15, 10, 30, 0),
)
```

### Why States Matter

States are **nodes in the exploration graph**. The Agent:
- Observes the current State after each Action
- Records State transitions in the Graph
- Rolls back to previous States to explore alternate paths
- Checks Invariants against the current State

### States vs Checkpoints

Not every State has a checkpoint. A **checkpoint** is an explicit save that enables rollback. States record what we observed; checkpoints enable us to return.

```
State observed ──────────────► Always happens after an Action
Checkpoint created ──────────► Only when we want to explore branches from here
```

## 2. Action

An **Action** is something that changes the World. Usually an API call.

### What's in an Action?

```python
Action(
    name="create_order",
    execute=lambda api, context: api.post("/orders", json={"product_id": 1, "quantity": 2}),
    preconditions=[
        lambda ctx: ctx.get("logged_in", False),
        lambda ctx: ctx.get("cart_items", 0) > 0,
    ],
    description="Create a new order from the current cart",
)
```

### Preconditions

Actions can have **preconditions** — conditions that must be true for the Action to be valid. The Agent skips Actions whose preconditions fail.

This models reality: you can't checkout without items in your cart.

### Actions are Edges

In the state graph, Actions are **edges**. They connect States:

```
[State A] ──── Action ────► [State B]
```

The combination of (State, Action) is what we explore. The Agent systematically tries every Action from every reachable State.

## 3. World

The **World** is the sandbox environment containing all systems the Agent can interact with.

### What's in a World?

```python
World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db": PostgresAdapter("postgres://localhost/testdb"),
        "cache": RedisAdapter("redis://localhost:6379"),
        "queue": MockQueue(),
        "mail": MockMail(),
    },
)
```

### The World's Responsibilities

The World does four things:

| Method | Purpose |
|--------|---------|
| `act(action)` | Execute an Action via the API |
| `observe()` | Query all systems, return current State |
| `checkpoint(name)` | Save state of ALL systems atomically |
| `rollback(checkpoint)` | Restore ALL systems atomically |

### Atomic Operations

**Critical**: Checkpoint and rollback are **atomic across all systems**. When you checkpoint, every system saves its state at the same logical moment. When you rollback, every system restores together.

This is essential for consistency. If the database rolled back but the cache didn't, you'd have invalid state.

### The API Client is Special

The API client is how the Agent **acts** on the World. It's not rollbackable itself — it talks to the System Under Test, which mutates the rollbackable systems.

```
Agent ──► World.act(action) ──► API Client ──► System Under Test
                                                      │
                                    mutates           │
                                         ┌────────────┘
                                         ▼
                               ┌─────────────────┐
                               │  DB  │ Cache │ ...│
                               └─────────────────┘
                                         ▲
                                         │
World.observe() ◄────────────────────────┘
```

## 4. Invariant

An **Invariant** is a rule that must always be true. If an Invariant fails, we've found a bug.

### What's in an Invariant?

```python
Invariant(
    name="order_count_consistent",
    check=lambda world: (
        world.systems["db"].query("SELECT COUNT(*) FROM orders")[0][0]
        == len(world.api.get("/orders").json()["orders"])
    ),
    message="Database order count must equal API response count",
    severity=Severity.HIGH,
)
```

### The Check Function

The `check` function receives the entire World. It can:
- Query the database directly
- Call the API
- Check the cache
- Inspect the queue
- Compare values across systems

It returns `True` if the invariant holds, `False` if violated.

### Types of Invariants

| Type | Example |
|------|---------|
| **Consistency** | DB count == API count |
| **Business Rules** | No negative balances |
| **Security** | Can't access other users' data |
| **Integrity** | Foreign keys exist |
| **Performance** | Response time < 500ms |

### When Invariants are Checked

The Agent checks all Invariants **after every Action**. This catches bugs immediately when they occur, not later when symptoms appear.

## 5. Agent

The **Agent** is the explorer. It traverses the state graph by executing Actions and observing States.

### What's in an Agent?

```python
Agent(
    world=world,
    actions=[login, logout, create_order, cancel_order, ...],
    invariants=[order_count_consistent, no_negative_balance, ...],
    strategy=BFS(),  # How to pick next (state, action)
)
```

### The Exploration Loop

The Agent runs this loop until the graph is fully explored:

```
1. Pick an unexplored (state, action) pair
2. Rollback to that state (if not already there)
3. Checkpoint before executing
4. Execute the action
5. Observe the new state
6. Check all invariants
7. Record the transition in the graph
8. Repeat
```

### Exploration Strategies

The **strategy** determines how the Agent picks the next (state, action) to explore:

| Strategy | Behavior |
|----------|----------|
| **BFS** | Explore all actions from each state before going deeper |
| **DFS** | Follow one path deeply before backtracking |
| **Random** | Pick randomly (good for fuzzing) |
| **CoverageGuided** | Prioritize actions that increase code coverage |

### Graph Building

As the Agent explores, it builds a **Graph** of all States and Transitions it has seen. This Graph is the output — a complete map of your application's state space.

## How They Work Together

Here's the complete flow:

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  1. SETUP                                                           │
│     Create World with API client and rollbackable systems          │
│     Define Actions (what can be done)                              │
│     Define Invariants (what must be true)                          │
│     Create Agent with World, Actions, Invariants                   │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  2. INITIAL STATE                                                   │
│     Agent observes initial state from World                        │
│     Agent checkpoints initial state                                │
│     Graph has one node (initial state)                             │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  3. EXPLORATION LOOP                                                │
│                                                                     │
│     while graph has unexplored (state, action) pairs:              │
│                                                                     │
│         a. PICK                                                     │
│            Strategy selects (state, action) to try                 │
│                                                                     │
│         b. ROLLBACK                                                 │
│            World.rollback(state.checkpoint)                        │
│            All systems restore to that state                       │
│                                                                     │
│         c. CHECKPOINT                                               │
│            World.checkpoint() before action                        │
│            Save point for this exploration branch                  │
│                                                                     │
│         d. ACT                                                      │
│            World.act(action)                                       │
│            API call executes, systems mutate                       │
│                                                                     │
│         e. OBSERVE                                                  │
│            new_state = World.observe()                             │
│            Query all systems for current state                     │
│                                                                     │
│         f. VERIFY                                                   │
│            For each invariant:                                     │
│                if not invariant.check(world):                      │
│                    Record violation                                │
│                                                                     │
│         g. RECORD                                                   │
│            Graph.add_transition(state, action, new_state)          │
│            Mark (state, action) as explored                        │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  4. RESULT                                                          │
│     Return ExplorationResult with:                                 │
│       - Complete Graph of states and transitions                   │
│       - List of Violations (bugs found)                            │
│       - Statistics (states visited, coverage, timing)              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Example: Exploring an E-commerce API

Let's trace through a concrete example:

### Setup

```python
# World
world = World(
    api=HttpClient("http://localhost:8000"),
    systems={"db": PostgresAdapter(...)},
)

# Actions
actions = [
    Action("login", lambda api, ctx: api.post("/login", json={...})),
    Action("add_to_cart", lambda api, ctx: api.post("/cart", json={...}),
           preconditions=[logged_in]),
    Action("checkout", lambda api, ctx: api.post("/checkout"),
           preconditions=[cart_not_empty]),
    Action("logout", lambda api, ctx: api.post("/logout"),
           preconditions=[logged_in]),
]

# Invariants
invariants = [
    Invariant("cart_total_correct", check=cart_matches_items),
    Invariant("order_has_items", check=orders_not_empty),
]

# Agent
agent = Agent(world, actions, invariants, strategy=BFS())
```

### Exploration Trace

```
Step 1: Initial
  State: {logged_in: false, cart: [], orders: []}
  Checkpoint: cp_0
  Valid actions: [login]  (others have failing preconditions)

Step 2: Execute login
  From: cp_0
  Action: login
  New State: {logged_in: true, cart: [], orders: []}
  Checkpoint: cp_1
  Invariants: all pass
  Graph: S0 --login--> S1

Step 3: Execute add_to_cart from S1
  From: cp_1
  Action: add_to_cart
  New State: {logged_in: true, cart: [item_1], orders: []}
  Checkpoint: cp_2
  Invariants: all pass
  Graph: S0 --login--> S1 --add_to_cart--> S2

Step 4: Execute checkout from S2
  From: cp_2
  Action: checkout
  New State: {logged_in: true, cart: [], orders: [order_1]}
  Invariants: all pass
  Graph: ... --checkout--> S3

Step 5: Rollback to S1, try logout
  Rollback to: cp_1
  State restored: {logged_in: true, cart: [], orders: []}
  Action: logout
  New State: {logged_in: false, cart: [], orders: []}
  Graph: S1 --logout--> S4

Step 6: Rollback to S2, try logout
  Rollback to: cp_2
  Action: logout
  ... and so on
```

The Agent systematically explores every path, rolling back to try alternates.

## Summary

| Concept | One-line Definition |
|---------|---------------------|
| **State** | Snapshot of all systems at a moment |
| **Action** | Something that changes the world |
| **World** | Sandbox with rollbackable systems |
| **Invariant** | Rule that must always be true |
| **Agent** | Explorer that traverses the state graph |

These five concepts are all you need to understand VenomQA. Everything else builds on them.
