---
title: "Modeling APIs as State Machines for Exhaustive Testing"
date: 2024-01-25
description: "Learn how to model your APIs as finite state machines to find bugs that traditional tests miss. Covers state machine testing patterns, Python examples, and real-world order lifecycle scenarios."
authors:
  - name: VenomQA Team
keywords:
  - state machine testing
  - model-based testing
  - API state
  - finite automata
  - API testing
  - property-based testing
  - formal methods
---

# Modeling APIs as State Machines for Exhaustive Testing

Every API is a state machine. Most teams just don't realize it—and their tests suffer because of it.

When you test an API endpoint in isolation, you're testing a single transition. But bugs often hide in the *sequences*: what happens when you refund a refunded order? Ship before payment? Pay twice?

This post shows how to model APIs as explicit state machines for testing, finding bugs that only appear in specific orderings of operations.

## What is a State Machine?

A **finite state machine** (or finite automata) is a mathematical model of computation consisting of:

- **States**: Discrete conditions the system can be in
- **Transitions**: Rules for moving between states
- **Events**: Triggers that cause transitions
- **Initial state**: Where the machine starts
- **Final states**: Terminal conditions (optional)

Formally, a state machine is a 5-tuple `(Q, Σ, δ, q₀, F)` where:

- `Q` = finite set of states
- `Σ` = alphabet (input symbols/events)
- `δ` = transition function `Q × Σ → Q`
- `q₀` = initial state
- `F` = set of accepting states

### Why APIs Are Implicit State Machines

Consider a typical order API:

```
                    ┌─────────────────────────────────────────────┐
                    │                                             │
                    ▼                                             │
┌────────┐  create  ┌─────────┐  pay   ┌───────┐  ship  ┌──────────┤
│ [empty]│ ───────► │[pending]│───────►│[paid] │───────►│[shipped] │
└────────┘          └─────────┘        └───────┘        └──────────┘
                         │                  │
                         │ cancel           │ refund
                         ▼                  ▼
                    ┌──────────┐      ┌───────────┐
                    │[canceled]│      │[refunded] │
                    └──────────┘      └───────────┘
```

Every order exists in exactly one state. Operations like `pay`, `ship`, and `refund` are transitions. The API *is* a state machine, but the state machine is implicit—encoded in scattered `if` statements across your codebase:

```python
def refund_order(order_id):
    order = db.get_order(order_id)
    if order.status != "paid":
        raise BadRequestError("Can only refund paid orders")
    # ... refund logic
```

This `if` statement is enforcing a state transition rule. There are probably dozens more like it, each encoding a tiny piece of the state machine.

## Explicit vs Implicit State

### The Problem with Implicit State

Most APIs don't document their state machine. Instead:

1. **State is scattered**: Status fields, boolean flags, timestamps
2. **Rules are hidden**: Validation logic buried in controllers
3. **Edge cases are missed**: What *should* happen in impossible scenarios?
4. **Testing is incomplete**: Each endpoint tested in isolation

You end up reverse-engineering the state machine from behavior:

```python
# What states exist?
GET /orders/{id}  # Look at the status field

# What transitions are valid?
# Try every operation in every state and see what fails
```

### Why Explicit is Better

When you model the state machine explicitly:

```python
from enum import Enum

class OrderState(str, Enum):
    EMPTY = "empty"
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    CANCELED = "canceled"
    REFUNDED = "refunded"

VALID_TRANSITIONS = {
    OrderState.EMPTY: {"create": OrderState.PENDING},
    OrderState.PENDING: {"pay": OrderState.PAID, "cancel": OrderState.CANCELED},
    OrderState.PAID: {"ship": OrderState.SHIPPED, "refund": OrderState.REFUNDED},
    OrderState.SHIPPED: set(),  # Terminal
    OrderState.CANCELED: set(), # Terminal
    OrderState.REFUNDED: set(), # Terminal
}
```

Now you can:

1. **Generate tests** from the state graph
2. **Validate** that implementation matches model
3. **Document** behavior automatically
4. **Find impossible states** that shouldn't exist

## State Machine Testing Patterns

State machine testing (a form of model-based testing) follows a simple pattern:

### 1. Model the States

Define all possible states your resource can be in:

```python
class OrderState(str, Enum):
    EMPTY = "empty"
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    CANCELED = "canceled"
    REFUNDED = "refunded"
```

### 2. Define Valid Transitions

Map which operations are valid in which states:

```python
TRANSITIONS = {
    OrderState.EMPTY: {
        "create": OrderState.PENDING,
    },
    OrderState.PENDING: {
        "pay": OrderState.PAID,
        "cancel": OrderState.CANCELED,
    },
    OrderState.PAID: {
        "ship": OrderState.SHIPPED,
        "refund": OrderState.REFUNDED,
    },
    OrderState.SHIPPED: {},  # Terminal
    OrderState.CANCELED: {}, # Terminal
    OrderState.REFUNDED: {}, # Terminal
}
```

### 3. Check Invariants at Each State

Define properties that must hold in each state:

```python
INVARIANTS = {
    OrderState.PENDING: [
        lambda order: order.amount > 0,
        lambda order: order.created_at is not None,
    ],
    OrderState.PAID: [
        lambda order: order.paid_at is not None,
        lambda order: order.payment_id is not None,
    ],
    OrderState.SHIPPED: [
        lambda order: order.tracking_number is not None,
    ],
    OrderState.REFUNDED: [
        lambda order: order.refunded_at is not None,
        lambda order: order.refund_amount > 0,
    ],
}

# Universal invariants (always true)
UNIVERSAL_INVARIANTS = [
    lambda order: order.amount >= 0,
    lambda order: order.id is not None,
]
```

## Example: Order Lifecycle Testing

Let's build a complete state machine test for an order API using the VenomQA framework:

```python
from venomqa import Action, Agent, Invariant, World, BFS, Severity
from venomqa.adapters.http import HttpClient
from enum import Enum
from typing import Optional
import httpx

class OrderState(str, Enum):
    EMPTY = "empty"
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    CANCELED = "canceled"
    REFUNDED = "refunded"

class OrderContext:
    """Tracks current state and order data"""
    def __init__(self):
        self.state: OrderState = OrderState.EMPTY
        self.order_id: Optional[str] = None
        self.amount: Optional[int] = None
        self.payment_id: Optional[str] = None
        self.tracking_number: Optional[str] = None

# --- State Guards ---

def require_state(*allowed_states: OrderState):
    """Decorator that skips action if not in allowed state"""
    def decorator(func):
        def wrapper(api, context):
            if context.state not in allowed_states:
                return None  # Skip this action
            return func(api, context)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator

# --- Actions ---

@require_state(OrderState.EMPTY)
def create_order(api: HttpClient, context: OrderContext) -> Optional[httpx.Response]:
    """Create a new pending order"""
    response = api.post("/orders", json={"amount": 100})
    
    if response.status_code == 201:
        data = response.json()
        context.order_id = data["id"]
        context.amount = data["amount"]
        context.state = OrderState.PENDING
    
    return response

@require_state(OrderState.PENDING)
def pay_order(api: HttpClient, context: OrderContext) -> Optional[httpx.Response]:
    """Pay for a pending order"""
    response = api.post(
        f"/orders/{context.order_id}/pay",
        json={"payment_method": "card"}
    )
    
    if response.status_code == 200:
        data = response.json()
        context.payment_id = data.get("payment_id")
        context.state = OrderState.PAID
    
    return response

@require_state(OrderState.PENDING)
def cancel_order(api: HttpClient, context: OrderContext) -> Optional[httpx.Response]:
    """Cancel a pending order"""
    response = api.post(f"/orders/{context.order_id}/cancel")
    
    if response.status_code == 200:
        context.state = OrderState.CANCELED
    
    return response

@require_state(OrderState.PAID)
def ship_order(api: HttpClient, context: OrderContext) -> Optional[httpx.Response]:
    """Ship a paid order"""
    response = api.post(
        f"/orders/{context.order_id}/ship",
        json={"carrier": "fedex"}
    )
    
    if response.status_code == 200:
        data = response.json()
        context.tracking_number = data.get("tracking_number")
        context.state = OrderState.SHIPPED
    
    return response

@require_state(OrderState.PAID)
def refund_order(api: HttpClient, context: OrderContext) -> Optional[httpx.Response]:
    """Refund a paid order"""
    response = api.post(f"/orders/{context.order_id}/refund")
    
    if response.status_code == 200:
        context.state = OrderState.REFUNDED
    
    return response

# --- Invariants ---

def no_500_errors(world: World) -> bool:
    """Server should never return 5xx errors"""
    return world.context.get("last_status", 200) < 500

def amount_positive(world: World) -> bool:
    """Order amount must always be positive"""
    ctx = world.context
    if ctx.state == OrderState.EMPTY:
        return True  # No order yet
    return ctx.amount is not None and ctx.amount > 0

def paid_orders_have_payment_id(world: World) -> bool:
    """Paid/shipped orders must have a payment ID"""
    ctx = world.context
    if ctx.state in (OrderState.PAID, OrderState.SHIPPED, OrderState.REFUNDED):
        return ctx.payment_id is not None
    return True

def shipped_orders_have_tracking(world: World) -> bool:
    """Shipped orders must have a tracking number"""
    ctx = world.context
    if ctx.state == OrderState.SHIPPED:
        return ctx.tracking_number is not None
    return True

def terminal_states_are_final(world: World) -> bool:
    """Terminal states shouldn't allow further transitions"""
    ctx = world.context
    if ctx.state in (OrderState.CANCELED, OrderState.REFUNDED):
        # These states should have no valid outgoing transitions
        return ctx.state not in TRANSITIONS.get(ctx.state, {})
    return True

# --- Setup Agent ---

api = HttpClient(base_url="http://localhost:8000")
world = World(api=api, state_from_context=["state", "order_id"])

agent = Agent(
    world=world,
    actions=[
        Action(name="create_order", execute=create_order),
        Action(name="pay_order", execute=pay_order),
        Action(name="cancel_order", execute=cancel_order),
        Action(name="ship_order", execute=ship_order),
        Action(name="refund_order", execute=refund_order),
    ],
    invariants=[
        Invariant(name="no_500s", check=no_500_errors, severity=Severity.CRITICAL),
        Invariant(name="amount_positive", check=amount_positive, severity=Severity.ERROR),
        Invariant(name="paid_has_payment", check=paid_orders_have_payment_id),
        Invariant(name="shipped_has_tracking", check=shipped_orders_have_tracking),
        Invariant(name="terminal_final", check=terminal_states_are_final),
    ],
    strategy=BFS(),
    max_steps=100,
)

# Run exploration
result = agent.explore()
print(f"States visited: {result.states_visited}")
print(f"Violations found: {len(result.violations)}")

for violation in result.violations:
    print(f"  [{violation.severity}] {violation.name}: {violation.message}")
```

### What This Tests

This exploration will discover:

1. **All valid paths**: `create → pay → ship`, `create → pay → refund`, `create → cancel`
2. **Invalid transitions**: Trying to ship a pending order, refund a shipped order
3. **Edge cases**: Double payment, refund after refund, cancel after payment
4. **Invariant violations**: Missing payment IDs, negative amounts, server errors

The state graph explored:

```
                    ┌─────────┐
                    │ [empty] │
                    └────┬────┘
                         │ create
                         ▼
                    ┌─────────┐
         ┌─────────►│[pending]│◄────────┐
         │          └────┬────┘         │
         │               │              │
         │         ┌─────┴─────┐        │
         │         │           │        │
         │      pay│        cancel      │
         │         ▼           ▼        │
         │    ┌───────┐   ┌──────────┐  │
         │    │[paid] │   │[canceled]│  │
         │    └───┬───┘   └──────────┘  │
         │        │                     │
         │   ┌────┴────┐                │
         │   │         │                │
         │ship      refund              │
         │   ▼         ▼                │
         │┌──────────┐┌───────────┐     │
         ││[shipped] ││[refunded] │     │
         │└──────────┘└───────────┘     │
         │                               │
         └───────────────────────────────┘
              (no valid transitions)
```

## Handling Complex States

Real-world APIs often have more complex state machines than a simple linear flow.

### Composite States

Sometimes a resource has multiple independent state dimensions:

```python
class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    CANCELED = "canceled"

class FulfillmentStatus(str, Enum):
    UNFULFILLED = "unfulfilled"
    PROCESSING = "processing"
    FULFILLED = "fulfilled"
    RETURNED = "returned"

class Order:
    status: OrderStatus
    fulfillment: FulfillmentStatus
    
    # Composite state = (status, fulfillment)
    # Valid: (PAID, UNFULFILLED), (PAID, PROCESSING), (SHIPPED, FULFILLED)
    # Invalid: (PENDING, FULFILLED), (CANCELED, PROCESSING)
```

Model these as tuples:

```python
COMPOSITE_TRANSITIONS = {
    (OrderStatus.PENDING, FulfillmentStatus.UNFULFILLED): {
        "pay": (OrderStatus.PAID, FulfillmentStatus.UNFULFILLED),
        "cancel": (OrderStatus.CANCELED, FulfillmentStatus.UNFULFILLED),
    },
    (OrderStatus.PAID, FulfillmentStatus.UNFULFILLED): {
        "start_fulfillment": (OrderStatus.PAID, FulfillmentStatus.PROCESSING),
        "ship": (OrderStatus.SHIPPED, FulfillmentStatus.FULFILLED),
        "refund": (OrderStatus.CANCELED, FulfillmentStatus.UNFULFILLED),
    },
    # ... etc
}
```

### Parallel State Machines

When resources have independent lifecycles:

```
Order: [created] → [paid] → [fulfilled] → [delivered]
                 ↘ [canceled]

Payment: [pending] → [processing] → [completed]
                          ↘ [failed]
                          
Invoice: [draft] → [sent] → [paid] → [archived]
```

Test each machine independently, then test interactions:

```python
def test_payment_failure_cancels_order():
    """Payment state machine affects order state machine"""
    order = create_order()
    payment = create_payment(order.id)
    
    # Simulate payment failure
    payment.fail()
    
    # Order should be canceled
    order.refresh()
    assert order.status == OrderStatus.CANCELED
```

### Hierarchical States

Some states contain sub-states:

```
[active]
  ├── [trial]
  ├── [subscribed]
  │     ├── [monthly]
  │     └── [annual]
  └── [past_due]
  
[canceled]
  ├── [expired]
  └── [churned]
```

Model with nested state machines:

```python
from typing import Union

class ActiveSubstate(str, Enum):
    TRIAL = "trial"
    SUBSCRIBED = "subscribed"
    PAST_DUE = "past_due"

class CanceledSubstate(str, Enum):
    EXPIRED = "expired"
    CHURNED = "churned"

class AccountState:
    top_level: Union[Literal["active"], Literal["canceled"]]
    substate: Union[ActiveSubstate, CanceledSubstate, None]
    
    def can_upgrade(self) -> bool:
        return (
            self.top_level == "active" and 
            self.substate in (ActiveSubstate.TRIAL, ActiveSubstate.SUBSCRIBED)
        )
```

## Benefits of State Machine Testing

### 1. Finds Impossible States

Traditional tests check happy paths. State machine testing finds:

```python
# This shouldn't exist, but does it?
order = Order(status="pending", shipped_at="2024-01-25")

# Invariant catches it
assert not (order.status == "pending" and order.shipped_at is not None)
```

### 2. Catches Missing Transitions

When you enumerate all states and transitions, gaps become obvious:

```
State: REFUNDED
Valid transitions: {}  # Empty!

But what if the customer wants to re-order?
Maybe we need: REFUNDED → "reorder" → PENDING (with new order_id)
```

### 3. Documents Behavior

The state machine *is* the documentation:

```python
# This tells you everything about order lifecycle
ORDER_STATE_MACHINE = {
    OrderState.EMPTY: {"create": OrderState.PENDING},
    OrderState.PENDING: {"pay": OrderState.PAID, "cancel": OrderState.CANCELED},
    OrderState.PAID: {"ship": OrderState.SHIPPED, "refund": OrderState.REFUNDED},
    OrderState.SHIPPED: {},
    OrderState.CANCELED: {},
    OrderState.REFUNDED: {},
}
```

Generate diagrams from it:

```python
import graphviz

def render_state_machine(transitions, filename="state_machine"):
    dot = graphviz.Digraph()
    
    for from_state, edges in transitions.items():
        for event, to_state in edges.items():
            dot.edge(from_state.value, to_state.value, label=event)
    
    dot.render(filename, format="png")
```

### 4. Enables Property-Based Testing

With an explicit state model, you can generate arbitrary sequences:

```python
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule

class OrderStateMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.state = OrderState.EMPTY
        self.order_id = None
    
    @rule()
    def create(self):
        if self.state == OrderState.EMPTY:
            self.state = OrderState.PENDING
            self.order_id = "order_123"
    
    @rule()
    def pay(self):
        if self.state == OrderState.PENDING:
            self.state = OrderState.PAID
    
    @rule()
    def ship(self):
        if self.state == OrderState.PAID:
            self.state = OrderState.SHIPPED
    
    @rule()
    def refund(self):
        if self.state == OrderState.PAID:
            self.state = OrderState.REFUNDED
    
    @rule()
    def cancel(self):
        if self.state == OrderState.PENDING:
            self.state = OrderState.CANCELED

TestOrderStateMachine = OrderStateMachine.TestCase
```

Hypothesis will generate thousands of random sequences, finding edge cases you'd never think to test.

## Conclusion

Every API is a state machine. The question is whether you model it explicitly or let it emerge implicitly from scattered conditionals.

**Explicit state machine modeling gives you:**

- **Completeness**: Test all paths, not just the ones you thought of
- **Clarity**: The model *is* the documentation
- **Confidence**: Invariants checked at every state
- **Maintainability**: Changes to state logic are localized

The order lifecycle example in this post is simple, but the pattern scales. Payment systems with 20+ states, subscription lifecycles with parallel state machines, multi-tenant SaaS with hierarchical permissions—all can be modeled and exhaustively tested.

Your API is already a state machine. You might as well make it explicit.

---

*VenomQA automates state machine testing for APIs. Define actions and invariants, and it explores every path through your state graph. [Get started →](https://github.com/anomaly/venomqa)*
