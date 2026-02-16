"""VenomQA v1 Quick Start Example.

This example demonstrates the new v1 API with its simplified interface.
Run with: python -m examples.v1_quickstart.simple_test
"""

from venomqa.v1 import (
    Journey, Step, Checkpoint, Branch, Path,
    Invariant, Severity,
    action, invariant,
    explore,
)


# Define actions using the decorator
@action(name="login", description="Log in a test user")
def login(api):
    return api.post("/auth/login", json={
        "email": "test@example.com",
        "password": "password123",
    })


@action(name="create_order", description="Create a new order")
def create_order(api):
    return api.post("/orders", json={
        "product_id": 1,
        "quantity": 2,
    })


@action(name="cancel_order", description="Cancel the last order")
def cancel_order(api):
    return api.delete("/orders/latest")


@action(name="complete_order", description="Complete the checkout")
def complete_order(api):
    return api.post("/orders/latest/complete")


# Define invariants
@invariant(
    name="order_count_valid",
    message="Order count should never be negative",
    severity=Severity.CRITICAL,
)
def check_order_count(world):
    obs = world.systems.get("db")
    if obs is None:
        return True  # Skip if no DB
    count = obs.observe().data.get("orders_count", 0)
    return count >= 0


# Define the journey
journey = Journey(
    name="checkout_flow",
    description="Test the complete checkout process",
    steps=[
        # Login phase
        Step("login", login),
        Checkpoint("logged_in"),

        # Order creation
        Step("create_order", create_order),
        Checkpoint("order_created"),

        # Branch: either complete or cancel
        Branch(
            from_checkpoint="order_created",
            paths=[
                Path("complete", [
                    Step("complete", complete_order),
                ]),
                Path("cancel", [
                    Step("cancel", cancel_order),
                ]),
            ],
        ),
    ],
    invariants=[check_order_count],
)


if __name__ == "__main__":
    # Run the exploration
    result = explore(
        base_url="http://localhost:8000",
        journey=journey,
    )

    # Print results
    print(f"States visited: {result.states_visited}")
    print(f"Transitions: {result.transitions_taken}")
    print(f"Coverage: {result.coverage_percent:.1f}%")
    print(f"Violations: {len(result.violations)}")
    print(f"Success: {result.success}")
