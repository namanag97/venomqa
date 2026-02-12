"""Cart actions for e-commerce journeys.

Reusable cart management actions.
"""


from venomqa.clients import HTTPClient


class CartActions:
    def __init__(self, base_url: str):
        self.client = HTTPClient(base_url=base_url)

    def create_cart(self, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post("/api/cart", json={}, headers=headers)

    def get_cart(self, cart_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(f"/api/cart/{cart_id}", headers=headers)

    def add_item(
        self, cart_id: str, product_id: str, quantity: int = 1, token: str | None = None
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(
            f"/api/cart/{cart_id}/items",
            json={"product_id": product_id, "quantity": quantity},
            headers=headers,
        )

    def update_item(self, cart_id: str, item_id: str, quantity: int, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.patch(
            f"/api/cart/{cart_id}/items/{item_id}",
            json={"quantity": quantity},
            headers=headers,
        )

    def remove_item(self, cart_id: str, item_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.delete(f"/api/cart/{cart_id}/items/{item_id}", headers=headers)

    def clear_cart(self, cart_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.delete(f"/api/cart/{cart_id}/items", headers=headers)

    def apply_coupon(self, cart_id: str, code: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(f"/api/cart/{cart_id}/coupon", json={"code": code}, headers=headers)

    def remove_coupon(self, cart_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.delete(f"/api/cart/{cart_id}/coupon", headers=headers)

    def set_shipping(self, cart_id: str, address: dict, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(f"/api/cart/{cart_id}/shipping", json=address, headers=headers)


def create_cart(client, context):
    actions = CartActions(base_url=context.get("base_url", "http://localhost:8000"))
    response = actions.create_cart(token=context.get("token"))
    if response.status_code in [200, 201]:
        context["cart_id"] = response.json().get("id")
    return response


def get_cart(client, context):
    actions = CartActions(base_url=context.get("base_url", "http://localhost:8000"))
    return actions.get_cart(cart_id=context["cart_id"], token=context.get("token"))


def add_to_cart(client, context):
    actions = CartActions(base_url=context.get("base_url", "http://localhost:8000"))
    return actions.add_item(
        cart_id=context["cart_id"],
        product_id=context["product_id"],
        quantity=context.get("quantity", 1),
        token=context.get("token"),
    )


def update_cart_item(client, context):
    actions = CartActions(base_url=context.get("base_url", "http://localhost:8000"))
    return actions.update_item(
        cart_id=context["cart_id"],
        item_id=context["item_id"],
        quantity=context.get("new_quantity", 1),
        token=context.get("token"),
    )


def remove_cart_item(client, context):
    actions = CartActions(base_url=context.get("base_url", "http://localhost:8000"))
    return actions.remove_item(
        cart_id=context["cart_id"],
        item_id=context["item_id"],
        token=context.get("token"),
    )


def clear_cart(client, context):
    actions = CartActions(base_url=context.get("base_url", "http://localhost:8000"))
    return actions.clear_cart(cart_id=context["cart_id"], token=context.get("token"))


def apply_coupon(client, context):
    actions = CartActions(base_url=context.get("base_url", "http://localhost:8000"))
    return actions.apply_coupon(
        cart_id=context["cart_id"],
        code=context["coupon_code"],
        token=context.get("token"),
    )


def remove_coupon(client, context):
    actions = CartActions(base_url=context.get("base_url", "http://localhost:8000"))
    return actions.remove_coupon(cart_id=context["cart_id"], token=context.get("token"))


def set_shipping(client, context):
    actions = CartActions(base_url=context.get("base_url", "http://localhost:8000"))
    return actions.set_shipping(
        cart_id=context["cart_id"],
        address=context.get(
            "shipping_address", {"street": "123 Main St", "city": "City", "zip": "12345"}
        ),
        token=context.get("token"),
    )
