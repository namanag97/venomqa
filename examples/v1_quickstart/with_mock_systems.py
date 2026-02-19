"""VenomQA v1 Example with Mock Systems.

This example shows how to use mock adapters for testing
without external dependencies.
"""

from venomqa import (
    World, Agent, BFS,
    Action, ActionResult, HTTPRequest, HTTPResponse,
    Invariant, Severity,
)
from venomqa.adapters import MockQueue, MockMail, MockStorage


class MockApi:
    """A mock API for demonstration."""

    def __init__(self):
        self.users = {}
        self.orders = []

    def post(self, path, **kwargs):
        request = HTTPRequest("POST", path, body=kwargs.get("json"))

        if path == "/users":
            user_id = len(self.users) + 1
            self.users[user_id] = kwargs.get("json", {})
            return ActionResult.from_response(
                request,
                HTTPResponse(201, body={"id": user_id}),
            )

        if path == "/orders":
            order_id = len(self.orders) + 1
            self.orders.append({"id": order_id, **kwargs.get("json", {})})
            return ActionResult.from_response(
                request,
                HTTPResponse(201, body={"id": order_id}),
            )

        return ActionResult.from_response(
            request,
            HTTPResponse(404, body={"error": "Not found"}),
        )

    def get(self, path, **kwargs):
        request = HTTPRequest("GET", path)
        return ActionResult.from_response(
            request,
            HTTPResponse(200, body={"users": list(self.users.values())}),
        )


def main():
    # Create mock systems
    api = MockApi()
    queue = MockQueue(name="tasks")
    mail = MockMail()
    storage = MockStorage(bucket="uploads")

    # Create the world
    world = World(
        api=api,
        systems={
            "queue": queue,
            "mail": mail,
            "storage": storage,
        },
    )

    # Define actions
    def create_user(api):
        result = api.post("/users", json={"name": "Test User"})
        # Side effect: send welcome email
        mail.send("test@example.com", "Welcome!", "Hello!")
        return result

    def create_order(api):
        result = api.post("/orders", json={"product": "Widget"})
        # Side effect: enqueue processing job
        queue.push({"type": "process_order", "order_id": 1})
        return result

    def upload_file(api):
        storage.put("receipt.pdf", b"PDF content")
        return api.post("/files", json={"path": "receipt.pdf"})

    actions = [
        Action(name="create_user", execute=create_user),
        Action(name="create_order", execute=create_order),
        Action(name="upload_file", execute=upload_file),
    ]

    # Define invariants
    invariants = [
        Invariant(
            name="queue_not_overflowing",
            check=lambda w: w.systems["queue"].pending_count < 100,
            message="Task queue should not overflow",
            severity=Severity.HIGH,
        ),
        Invariant(
            name="storage_reasonable",
            check=lambda w: w.systems["storage"].file_count < 1000,
            message="Storage should not have too many files",
            severity=Severity.MEDIUM,
        ),
    ]

    # Create and run agent
    agent = Agent(
        world=world,
        actions=actions,
        invariants=invariants,
        strategy=BFS(),
        max_steps=20,
    )

    result = agent.explore()

    # Print results
    print("=" * 50)
    print("Exploration Results")
    print("=" * 50)
    print(f"States visited: {result.states_visited}")
    print(f"Transitions taken: {result.transitions_taken}")
    print(f"Duration: {result.duration_ms:.0f}ms")

    print("\nSystem states after exploration:")
    print(f"  Queue: {queue.pending_count} pending, {queue.processed_count} processed")
    print(f"  Mail: {mail.sent_count} emails sent")
    print(f"  Storage: {storage.file_count} files")

    if result.violations:
        print(f"\nViolations found: {len(result.violations)}")
        for v in result.violations:
            print(f"  - {v.severity.value}: {v.invariant_name}")
    else:
        print("\nNo violations found!")

    return result.success


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
