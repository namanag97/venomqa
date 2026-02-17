"""VenomQA exploration definitions (v1 API).

Define actions and invariants, then run Agent.explore() to exhaustively
test every reachable state sequence — no linear test scripts needed.

Example:
    from venomqa.v1 import Action, Invariant, Agent, World, BFS, Severity
    from venomqa.v1.adapters.http import HttpClient

    def create_item(api, context):
        resp = api.post("/items", json={"name": "test"})
        context.set("item_id", resp.json()["id"])
        return resp

    def list_items(api, context):
        resp = api.get("/items")
        context.set("items", resp.json())
        return resp

    def list_is_valid(world):
        items = world.context.get("items") or []
        return isinstance(items, list)

    agent = Agent(
        world=World(api=HttpClient("http://localhost:8000")),
        actions=[
            Action(name="create_item", execute=create_item, expected_status=[201]),
            Action(name="list_items",  execute=list_items,  expected_status=[200]),
        ],
        invariants=[
            Invariant(name="list_valid", check=list_is_valid,
                      message="GET /items must return a list", severity=Severity.CRITICAL),
        ],
        strategy=BFS(),
        max_steps=200,
    )
    result = agent.explore()
"""
