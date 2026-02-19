"""Sample actions for your VenomQA tests (v1 API).

Each action has signature: (api, context)
  - api      : HttpClient -- .get() .post() .put() .patch() .delete()
  - context  : Context   -- .get(key) / .set(key, val)  <- NOT context[key]

CRITICAL: Actions MUST validate responses using expect_* helpers:
  - resp.expect_status(201)         # raises if not 201
  - resp.expect_json_field("id")    # raises if field missing
  - resp.expect_json_list()         # raises if not array

Modify these for your specific API, then register them in an Agent.
"""


def health_check(api, context):
    """Check API health status."""
    resp = api.get("/health")
    resp.expect_status(200)  # raises AssertionError if not 200
    return resp


def list_items(api, context):
    """List all items and store in context.

    Uses expect_json_list() to validate the response is an array.
    """
    resp = api.get("/api/items")
    resp.expect_status(200)
    items = resp.expect_json_list()  # raises if not a list

    context.set("items", items)
    context.set("item_count", len(items))
    return resp


def create_item(api, context):
    """Create a new item and store its ID in context.

    Uses expect_json_field() to validate required fields exist.
    """
    resp = api.post("/api/items", json={
        "name": "VenomQA Test Item",
        "description": "Created by VenomQA",
    })
    resp.expect_status(200, 201)                    # 200 or 201
    data = resp.expect_json_field("id")             # raises if "id" missing

    context.set("item_id", data["id"])
    return resp


def get_item(api, context):
    """Fetch a single item by ID.

    GOOD PATTERN: Use Action(preconditions=["create_item"]) instead of
    checking context.has() inside the action.
    """
    item_id = context.get("item_id")
    resp = api.get(f"/api/items/{item_id}")
    resp.expect_status(200)

    data = resp.expect_json()
    if data.get("id") != item_id:
        raise AssertionError(f"Wrong item returned: expected {item_id}, got {data}")

    return resp


def delete_item(api, context):
    """Delete the item created by create_item.

    GOOD PATTERN: This action should use preconditions=["create_item"]
    so VenomQA only runs it after create_item has succeeded.

    BAD PATTERN (DON'T DO THIS):
        if item_id is None:
            return api.get("/noop")   # Silent no-op - hides bugs!
    """
    item_id = context.get("item_id")
    resp = api.delete(f"/api/items/{item_id}")
    resp.expect_status(200, 204)  # raises if not 200 or 204

    # Clean up context so we know item is gone
    context.delete("item_id")
    return resp
