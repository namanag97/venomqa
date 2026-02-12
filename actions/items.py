def create_item(client, context, name=None, price=None, description=None):
    return client.post(
        "/api/items",
        json={
            "name": name or context.get("item_name", "Default Item"),
            "price": price or context.get("item_price", 0.0),
            "description": description or context.get("item_description", ""),
        },
    )


def get_item(client, context, item_id=None):
    item_id = item_id or context.get("item_id")
    return client.get(f"/api/items/{item_id}")


def update_item(client, context, item_id=None, name=None, price=None, description=None):
    item_id = item_id or context.get("item_id")
    data = {}
    if name is not None:
        data["name"] = name
    if price is not None:
        data["price"] = price
    if description is not None:
        data["description"] = description
    return client.patch(f"/api/items/{item_id}", json=data)


def delete_item(client, context, item_id=None):
    item_id = item_id or context.get("item_id")
    return client.delete(f"/api/items/{item_id}")


def list_items(client, context, page=1, limit=10, search=None):
    params = {"page": page, "limit": limit}
    if search:
        params["search"] = search
    return client.get("/api/items", params=params)
