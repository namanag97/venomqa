"""Reusable actions for VenomQA tests (v1 API).

Actions are plain functions with signature (api, context).
  - api      : HttpClient  — use .get() .post() .put() .patch() .delete()
  - context  : Context     — use .get(key) / .set(key, val) — NOT context[key]

Example:
    from venomqa.v1 import Action

    def add_to_cart(api, context):
        product_id = context.get("product_id")
        resp = api.post("/api/cart/items", json={"product_id": product_id, "quantity": 1})
        context.set("cart_id", resp.json()["id"])
        return resp

    action = Action(name="add_to_cart", execute=add_to_cart, expected_status=[201])
"""
