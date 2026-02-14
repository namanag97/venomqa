"""Checkout actions for e-commerce journeys.

Reusable checkout management actions.
"""

from venomqa.http import Client


class CheckoutActions:
    def __init__(self, base_url: str, checkout_url: str | None = None):
        self.client = Client(base_url=base_url)
        self.checkout_client = Client(base_url=checkout_url or base_url)

    def start_checkout(self, cart_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.checkout_client.post(
            "/api/checkout", json={"cart_id": cart_id}, headers=headers
        )

    def set_shipping_method(self, checkout_id: str, method: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.checkout_client.patch(
            f"/api/checkout/{checkout_id}/shipping-method",
            json={"method": method},
            headers=headers,
        )

    def set_payment_method(
        self, checkout_id: str, payment_type: str, payment_data: dict, token: str | None = None
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.checkout_client.patch(
            f"/api/checkout/{checkout_id}/payment-method",
            json={"type": payment_type, "data": payment_data},
            headers=headers,
        )

    def complete_checkout(self, checkout_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.checkout_client.post(
            f"/api/checkout/{checkout_id}/complete", json={}, headers=headers
        )

    def get_checkout(self, checkout_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.checkout_client.get(f"/api/checkout/{checkout_id}", headers=headers)

    def cancel_checkout(self, checkout_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.checkout_client.post(
            f"/api/checkout/{checkout_id}/cancel", json={}, headers=headers
        )


def start_checkout(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        checkout_url=context.get("checkout_url"),
    )
    response = actions.start_checkout(cart_id=context["cart_id"], token=context.get("token"))
    if response.status_code in [200, 201]:
        context["checkout_id"] = response.json().get("id")
    return response


def set_shipping_method(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        checkout_url=context.get("checkout_url"),
    )
    return actions.set_shipping_method(
        checkout_id=context["checkout_id"],
        method=context.get("shipping_method", "standard"),
        token=context.get("token"),
    )


def set_payment_method(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        checkout_url=context.get("checkout_url"),
    )
    return actions.set_payment_method(
        checkout_id=context["checkout_id"],
        payment_type=context.get("payment_type", "card"),
        payment_data=context.get("payment_data", {"token": "tok_visa"}),
        token=context.get("token"),
    )


def complete_checkout(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        checkout_url=context.get("checkout_url"),
    )
    response = actions.complete_checkout(
        checkout_id=context["checkout_id"], token=context.get("token")
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["order_id"] = data.get("order_id")
        assert data.get("status") == "completed", (
            f"Checkout should complete, got {data.get('status')}"
        )
    return response


def get_checkout(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        checkout_url=context.get("checkout_url"),
    )
    return actions.get_checkout(checkout_id=context["checkout_id"], token=context.get("token"))


def cancel_checkout(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        checkout_url=context.get("checkout_url"),
    )
    return actions.cancel_checkout(checkout_id=context["checkout_id"], token=context.get("token"))
