# Journey DSL

The Journey DSL provides a user-friendly way to define exploration scenarios. Journeys compile to the core primitives (Graph, Actions, Invariants).

## When to Use the DSL

Use the **DSL** when:
- You have a specific flow in mind
- You want to define checkpoints explicitly
- You prefer declarative syntax

Use the **Core API** when:
- You want to generate actions programmatically
- You need full control over the graph
- You're integrating with OpenAPI/GraphQL schemas

## DSL Objects

### Journey

A Journey is the top-level container:

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path

journey = Journey(
    name="checkout_flow",
    steps=[
        Step("login", login_action),
        Checkpoint("logged_in"),
        Step("add_to_cart", add_to_cart_action),
        Checkpoint("cart_filled"),
        Branch(
            from_checkpoint="cart_filled",
            paths=[
                Path("checkout", [
                    Step("checkout", checkout_action),
                    Step("pay", pay_action),
                ]),
                Path("abandon", [
                    Step("clear_cart", clear_cart_action),
                ]),
            ],
        ),
    ],
    invariants=[
        order_count_invariant,
        cart_total_invariant,
    ],
    description="Test the checkout flow with multiple paths",
)
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Unique journey identifier |
| `steps` | `list[Step \| Checkpoint \| Branch]` | Yes | Ordered sequence of elements |
| `invariants` | `list[Invariant]` | No | Invariants to check |
| `description` | `str` | No | Human-readable description |

### Step

A Step wraps an Action:

```python
Step(
    name="create_order",
    action=lambda api: api.post("/orders", json={"product_id": 1}),
    description="Create a new order",
)
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Step identifier (becomes Action name) |
| `action` | `Callable[[APIClient], ActionResult]` | Yes | The action to execute |
| `description` | `str` | No | Human-readable description |

### Checkpoint

A Checkpoint marks a point where state can be saved:

```python
Checkpoint("after_login")
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Checkpoint identifier |

Checkpoints serve two purposes:
1. Enable rollback to this point
2. Serve as targets for Branch `from_checkpoint`

### Branch

A Branch forks exploration from a checkpoint:

```python
Branch(
    from_checkpoint="logged_in",
    paths=[
        Path("path_a", [...]),
        Path("path_b", [...]),
    ],
)
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `from_checkpoint` | `str` | Yes | Name of checkpoint to branch from |
| `paths` | `list[Path]` | Yes | Paths to explore |

When the Agent reaches a Branch, it:
1. Rolls back to `from_checkpoint`
2. Explores each Path
3. Rolls back between paths

### Path

A Path is a sequence of steps within a Branch:

```python
Path(
    name="checkout_path",
    steps=[
        Step("checkout", checkout_action),
        Step("pay", pay_action),
        Checkpoint("paid"),
        Step("get_receipt", get_receipt_action),
    ],
)
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Path identifier |
| `steps` | `list[Step \| Checkpoint]` | Yes | Steps in this path |

Paths can contain Steps and Checkpoints, but not nested Branches.

## Compilation

Journeys compile to core primitives:

```python
from venomqa import compile

graph, actions, invariants = compile(journey)

# graph: Graph with states and transitions
# actions: list[Action] derived from Steps
# invariants: list[Invariant] from journey
```

### What Compilation Produces

```
Journey                          Compiles To
───────                          ───────────

Step("login", fn)         →      Action(name="login", execute=fn)

Checkpoint("cp1")         →      Marker for checkpoint creation

Branch(                   →      Graph structure:
  from="cp1",                    - Rollback to cp1 between paths
  paths=[A, B]                   - Explore path A
)                                - Rollback to cp1
                                 - Explore path B
```

### Example Compilation

```python
journey = Journey(
    name="simple",
    steps=[
        Step("a", action_a),
        Checkpoint("cp1"),
        Step("b", action_b),
        Branch(
            from_checkpoint="cp1",
            paths=[
                Path("p1", [Step("c", action_c)]),
                Path("p2", [Step("d", action_d)]),
            ],
        ),
    ],
)
```

Produces this exploration graph:

```
[Initial]
    │
    │ action_a
    ▼
[After A] ←── checkpoint "cp1"
    │
    │ action_b
    ▼
[After B]
    │
    │ rollback to cp1
    ▼
[After A] (restored)
    │
    ├── action_c ──► [After C] (path p1)
    │
    │ rollback to cp1
    │
    └── action_d ──► [After D] (path p2)
```

## Patterns

### Linear Flow

```python
Journey(
    name="linear",
    steps=[
        Step("step1", action1),
        Step("step2", action2),
        Step("step3", action3),
    ],
)

# Explores: step1 → step2 → step3
```

### Single Branch Point

```python
Journey(
    name="single_branch",
    steps=[
        Step("setup", setup_action),
        Checkpoint("ready"),
        Branch(
            from_checkpoint="ready",
            paths=[
                Path("option_a", [Step("a", action_a)]),
                Path("option_b", [Step("b", action_b)]),
                Path("option_c", [Step("c", action_c)]),
            ],
        ),
    ],
)

# Explores:
#   setup → a
#   setup → b (after rollback)
#   setup → c (after rollback)
```

### Multiple Branch Points

```python
Journey(
    name="multi_branch",
    steps=[
        Step("login", login_action),
        Checkpoint("logged_in"),
        Branch(
            from_checkpoint="logged_in",
            paths=[
                Path("buyer", [
                    Step("add_to_cart", add_action),
                    Checkpoint("has_cart"),
                    Branch(
                        from_checkpoint="has_cart",
                        paths=[
                            Path("checkout", [Step("checkout", checkout_action)]),
                            Path("abandon", [Step("clear", clear_action)]),
                        ],
                    ),
                ]),
                Path("browser", [
                    Step("browse", browse_action),
                ]),
            ],
        ),
    ],
)

# Explores:
#   login → add_to_cart → checkout
#   login → add_to_cart → clear (after rollback to has_cart)
#   login → browse (after rollback to logged_in)
```

### With Invariants

```python
Journey(
    name="with_checks",
    steps=[
        Step("create_order", create_order_action),
        Step("pay", pay_action),
    ],
    invariants=[
        Invariant(
            name="order_total_correct",
            check=lambda world: ...,
            message="Order total must match items",
        ),
        Invariant(
            name="payment_recorded",
            check=lambda world: ...,
            message="Payment must be recorded in database",
        ),
    ],
)
```

## Running Journeys

### Using explore()

The simplest way:

```python
from venomqa import explore

result = explore(
    "http://localhost:8000",  # API URL
    journey,                   # Journey object
    db_url="postgres://...",   # Database URL
)
```

### Using compile() + Agent

For more control:

```python
from venomqa import World, Agent, compile
from venomqa.adapters import HttpClient, PostgresAdapter

# Create world
world = World(
    api=HttpClient("http://localhost:8000"),
    systems={"db": PostgresAdapter("postgres://...")},
)

# Compile journey
graph, actions, invariants = compile(journey)

# Create agent with additional actions/invariants
all_actions = actions + [extra_action1, extra_action2]
all_invariants = invariants + [extra_invariant]

agent = Agent(
    world=world,
    actions=all_actions,
    invariants=all_invariants,
)

result = agent.explore()
```

## Decorators

For cleaner action definition:

```python
from venomqa.dsl import action, invariant

@action("create_user")
def create_user(api):
    return api.post("/users", json={"name": "Test"})

@action("delete_user", preconditions=[has_users])
def delete_user(api):
    return api.delete("/users/1")

@invariant("user_count_positive")
def user_count_positive(world):
    return world.systems["db"].query("SELECT COUNT(*) FROM users")[0][0] >= 0

# Use in journey
journey = Journey(
    name="user_crud",
    steps=[
        Step("create", create_user),
        Step("delete", delete_user),
    ],
    invariants=[user_count_positive],
)
```

## Limitations

The DSL is intentionally simple. For advanced scenarios, use the Core API:

| DSL Limitation | Core API Solution |
|----------------|-------------------|
| Static actions | Generate actions programmatically |
| No conditional branches | Use preconditions on actions |
| No loops | Agent naturally loops via exploration |
| No parameterization | Create multiple actions with factory |
