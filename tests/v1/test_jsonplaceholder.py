"""Test VenomQA v1 against JSONPlaceholder API."""

import httpx

from venomqa.v1 import Agent, BFS
from venomqa.v1.core.action import Action, ActionResult, HTTPRequest, HTTPResponse
from venomqa.v1.core.invariant import Invariant, Severity
from venomqa.v1.core.state import Observation
from venomqa.v1.world import World
from venomqa.v1.world.rollbackable import Rollbackable, SystemCheckpoint


BASE_URL = "https://jsonplaceholder.typicode.com"


class HttpApiClient(Rollbackable):
    """Simple HTTP client that implements Rollbackable for VenomQA."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.Client(timeout=30.0)
        self._last_response: dict | None = None

    def get(self, path: str) -> ActionResult:
        """Make GET request."""
        import time

        url = f"{self.base_url}{path}"
        start = time.time()
        try:
            resp = self.client.get(url)
            duration_ms = int((time.time() - start) * 1000)
            return ActionResult.from_response(
                request=HTTPRequest(method="GET", url=url),
                response=HTTPResponse(
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    body=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
                ),
                duration_ms=duration_ms,
            )
        except Exception as e:
            return ActionResult.from_error(
                request=HTTPRequest(method="GET", url=url),
                error=str(e),
            )

    def post(self, path: str, json: dict) -> ActionResult:
        """Make POST request."""
        import time

        url = f"{self.base_url}{path}"
        start = time.time()
        try:
            resp = self.client.post(url, json=json)
            duration_ms = int((time.time() - start) * 1000)
            self._last_response = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None
            return ActionResult.from_response(
                request=HTTPRequest(method="POST", url=url, body=json),
                response=HTTPResponse(
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    body=self._last_response or resp.text,
                ),
                duration_ms=duration_ms,
            )
        except Exception as e:
            return ActionResult.from_error(
                request=HTTPRequest(method="POST", url=url, body=json),
                error=str(e),
            )

    def put(self, path: str, json: dict) -> ActionResult:
        """Make PUT request."""
        import time

        url = f"{self.base_url}{path}"
        start = time.time()
        try:
            resp = self.client.put(url, json=json)
            duration_ms = int((time.time() - start) * 1000)
            return ActionResult.from_response(
                request=HTTPRequest(method="PUT", url=url, body=json),
                response=HTTPResponse(
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    body=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
                ),
                duration_ms=duration_ms,
            )
        except Exception as e:
            return ActionResult.from_error(
                request=HTTPRequest(method="PUT", url=url, body=json),
                error=str(e),
            )

    def delete(self, path: str) -> ActionResult:
        """Make DELETE request."""
        import time

        url = f"{self.base_url}{path}"
        start = time.time()
        try:
            resp = self.client.delete(url)
            duration_ms = int((time.time() - start) * 1000)
            return ActionResult.from_response(
                request=HTTPRequest(method="DELETE", url=url),
                response=HTTPResponse(
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    body=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
                ),
                duration_ms=duration_ms,
            )
        except Exception as e:
            return ActionResult.from_error(
                request=HTTPRequest(method="DELETE", url=url),
                error=str(e),
            )

    # Rollbackable interface
    def checkpoint(self, name: str) -> SystemCheckpoint:
        """HTTP API is stateless from client perspective, just return empty checkpoint."""
        return {"name": name, "data": {}}

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """HTTP API is stateless, nothing to rollback."""
        pass

    def observe(self) -> Observation:
        """Return current observation - just metadata about last request."""
        return Observation(
            system="http_api",
            data={"last_response": self._last_response},
        )


def create_actions(api: HttpApiClient) -> list[Action]:
    """Create all API actions."""
    return [
        Action(
            name="list_posts",
            execute=lambda client: client.get("/posts"),
            description="GET /posts - list all posts",
            tags=["posts", "read"],
        ),
        Action(
            name="get_post",
            execute=lambda client: client.get("/posts/1"),
            description="GET /posts/1 - get single post",
            tags=["posts", "read"],
        ),
        Action(
            name="create_post",
            execute=lambda client: client.post("/posts", json={"title": "Test", "body": "Content", "userId": 1}),
            description="POST /posts - create new post",
            tags=["posts", "write"],
        ),
        Action(
            name="update_post",
            execute=lambda client: client.put("/posts/1", json={"title": "Updated"}),
            description="PUT /posts/1 - update post",
            tags=["posts", "write"],
        ),
        Action(
            name="delete_post",
            execute=lambda client: client.delete("/posts/1"),
            description="DELETE /posts/1 - delete post",
            tags=["posts", "write"],
        ),
        Action(
            name="list_comments",
            execute=lambda client: client.get("/posts/1/comments"),
            description="GET /posts/1/comments - list comments for post",
            tags=["comments", "read"],
        ),
        Action(
            name="list_users",
            execute=lambda client: client.get("/users"),
            description="GET /users - list all users",
            tags=["users", "read"],
        ),
    ]


def create_invariants(api: HttpApiClient) -> list[Invariant]:
    """Create all invariants to check."""

    def posts_exist(world: World) -> bool:
        """Check that /posts returns non-empty array."""
        result = api.get("/posts")
        if not result.success:
            return False
        body = result.response.body
        return isinstance(body, list) and len(body) > 0

    def valid_post_structure(world: World) -> bool:
        """Check that posts have required fields."""
        result = api.get("/posts")
        if not result.success:
            return False
        body = result.response.body
        if not isinstance(body, list) or len(body) == 0:
            return False
        # Check first post has required fields
        post = body[0]
        required_fields = {"id", "title", "body", "userId"}
        return all(field in post for field in required_fields)

    def user_exists(world: World) -> bool:
        """Check that GET /users/1 returns 200."""
        result = api.get("/users/1")
        return result.success and result.response.status_code == 200

    return [
        Invariant(
            name="posts_exist",
            check=posts_exist,
            message="GET /posts should return non-empty array",
            severity=Severity.HIGH,
        ),
        Invariant(
            name="valid_post_structure",
            check=valid_post_structure,
            message="Posts should have id, title, body, userId fields",
            severity=Severity.CRITICAL,
        ),
        Invariant(
            name="user_exists",
            check=user_exists,
            message="GET /users/1 should return 200",
            severity=Severity.MEDIUM,
        ),
    ]


def generate_mermaid(result) -> str:
    """Generate Mermaid diagram of exploration graph."""
    lines = ["graph TD"]

    # Add states as nodes
    state_labels = {}
    for i, state in enumerate(result.graph.iter_states()):
        label = f"S{i}"
        state_labels[state.id] = label
        lines.append(f"    {label}[State {i}]")

    # Add transitions as edges
    for transition in result.graph.iter_transitions():
        from_label = state_labels.get(transition.from_state_id, "?")
        to_label = state_labels.get(transition.to_state_id, "?")
        action = transition.action_name
        status = "ok" if transition.result.success else "err"
        lines.append(f"    {from_label} -->|{action} [{status}]| {to_label}")

    return "\n".join(lines)


def main():
    """Run the exploration."""
    print("=" * 60)
    print("VenomQA v1 - JSONPlaceholder API Exploration")
    print("=" * 60)
    print(f"\nTarget: {BASE_URL}")
    print()

    # Create API client
    api = HttpApiClient(BASE_URL)

    # Create world with HTTP client as system
    world = World(api=api, systems={"http_api": api})

    # Create actions and invariants
    actions = create_actions(api)
    invariants = create_invariants(api)

    print(f"Actions defined: {len(actions)}")
    for action in actions:
        print(f"  - {action.name}: {action.description}")

    print(f"\nInvariants defined: {len(invariants)}")
    for inv in invariants:
        print(f"  - {inv.name} ({inv.severity.name}): {inv.message}")

    print("\n" + "-" * 60)
    print("Starting exploration with BFS strategy (max_steps=20)")
    print("-" * 60 + "\n")

    # Create agent with BFS strategy
    agent = Agent(
        world=world,
        actions=actions,
        invariants=invariants,
        strategy=BFS(),
        max_steps=20,
    )

    # Run exploration
    result = agent.explore()

    # Print results
    print("\n" + "=" * 60)
    print("EXPLORATION RESULTS")
    print("=" * 60)

    print(f"\nStates visited: {result.states_visited}")
    print(f"Transitions taken: {result.transitions_taken}")
    print(f"Coverage: {result.coverage_percent:.1f}%")
    print(f"Duration: {result.duration_ms}ms")
    print(f"Success: {result.success}")

    print(f"\nViolations found: {len(result.violations)}")
    if result.violations:
        for v in result.violations:
            print(f"  - [{v.severity.name}] {v.invariant_name}: {v.message}")
            if v.action:
                print(f"    Triggered by action: {v.action}")
    else:
        print("  (no violations - all invariants passed)")

    # Print summary
    print("\n" + "-" * 60)
    print("Summary:")
    summary = result.summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")

    # Print Mermaid diagram
    print("\n" + "=" * 60)
    print("EXPLORATION GRAPH (Mermaid)")
    print("=" * 60)
    print()
    print("```mermaid")
    print(generate_mermaid(result))
    print("```")

    return result


if __name__ == "__main__":
    main()
