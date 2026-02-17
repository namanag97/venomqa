"""VenomQA v1 Quick Start Example.

Demonstrates the v1 API: define Actions and Invariants, let VenomQA
explore every reachable action sequence.

Run with: python3 examples/v1_quickstart/simple_test.py
"""

from venomqa.v1 import (
    Action,
    Agent,
    BFS,
    Invariant,
    Severity,
    World,
)
from venomqa.v1.adapters.http import HttpClient


# 1. Define actions — signature is always (api, context)

def login(api, context):
    resp = api.post("/auth/login", json={
        "email": "test@example.com",
        "password": "password123",
    })
    context.set("token", resp.json().get("token"))
    return resp


def create_order(api, context):
    resp = api.post("/orders", json={"product_id": 1, "quantity": 2})
    context.set("order_id", resp.json().get("id"))
    return resp


def cancel_order(api, context):
    order_id = context.get("order_id")
    return api.delete(f"/orders/{order_id}")


def complete_order(api, context):
    order_id = context.get("order_id")
    return api.post(f"/orders/{order_id}/complete")


def list_orders(api, context):
    resp = api.get("/orders")
    context.set("orders", resp.json())
    return resp


# 2. Define invariants — receive a single World argument

def order_count_valid(world):
    orders = world.context.get("orders")
    if orders is None:
        return True   # not observed yet
    return isinstance(orders, list) and len(orders) >= 0


# 3. Wire up Agent and explore

if __name__ == "__main__":
    api = HttpClient("http://localhost:8000")
    world = World(api=api)

    agent = Agent(
        world=world,
        actions=[
            Action(name="login",         execute=login),
            Action(name="create_order",  execute=create_order),
            Action(name="cancel_order",  execute=cancel_order),
            Action(name="complete_order", execute=complete_order),
            Action(name="list_orders",   execute=list_orders),
        ],
        invariants=[
            Invariant(
                name="order_count_valid",
                check=order_count_valid,
                message="Order list must always be a non-negative-length list",
                severity=Severity.CRITICAL,
            ),
        ],
        strategy=BFS(),
        max_steps=200,
    )

    result = agent.explore()

    print(f"States visited:      {result.states_visited}")
    print(f"Transitions taken:   {result.transitions_taken}")
    print(f"Action coverage:     {result.action_coverage_percent:.0f}%")
    print(f"Truncated:           {result.truncated_by_max_steps}")
    print(f"Violations:          {len(result.violations)}")
    for v in result.violations:
        print(f"  [{v.severity.value.upper()}] {v.invariant_name}: {v.message}")
    print(f"Success:             {result.success}")
