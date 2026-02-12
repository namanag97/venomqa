"""E-commerce checkout journeys.

Demonstrates:
- Multiple payment method branching
- Cart state management
- Multi-port testing (api:8000, payments:8001)
"""


from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.clients import HTTPClient


class CheckoutActions:
    def __init__(self, base_url: str, payment_url: str | None = None):
        self.client = HTTPClient(base_url=base_url)
        self.payment_client = HTTPClient(base_url=payment_url or base_url)

    def create_cart(self, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post("/api/cart", json={}, headers=headers)

    def add_to_cart(
        self, cart_id: str, product_id: str, quantity: int = 1, token: str | None = None
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(
            f"/api/cart/{cart_id}/items",
            json={"product_id": product_id, "quantity": quantity},
            headers=headers,
        )

    def apply_coupon(self, cart_id: str, code: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(
            f"/api/cart/{cart_id}/coupon",
            json={"code": code},
            headers=headers,
        )

    def get_cart(self, cart_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(f"/api/cart/{cart_id}", headers=headers)

    def checkout_card(self, cart_id: str, card_token: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.payment_client.post(
            "/api/checkout/card",
            json={"cart_id": cart_id, "card_token": card_token},
            headers=headers,
        )

    def checkout_paypal(self, cart_id: str, paypal_email: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.payment_client.post(
            "/api/checkout/paypal",
            json={"cart_id": cart_id, "paypal_email": paypal_email},
            headers=headers,
        )

    def checkout_wallet(self, cart_id: str, wallet_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.payment_client.post(
            "/api/checkout/wallet",
            json={"cart_id": cart_id, "wallet_id": wallet_id},
            headers=headers,
        )

    def get_order(self, order_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(f"/api/orders/{order_id}", headers=headers)


def login_shopper(client, context):
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "shopper@example.com"),
            "password": context.get("password", "pass123"),
        },
    )
    if response.status_code == 200:
        data = response.json()
        context["token"] = data.get("access_token")
        context["user_id"] = data.get("user", {}).get("id")
    return response


def setup_products(client, context):
    token = context.get("token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    product1 = client.post(
        "/api/products", json={"name": "Product A", "price": 29.99, "stock": 100}, headers=headers
    )
    product2 = client.post(
        "/api/products", json={"name": "Product B", "price": 49.99, "stock": 50}, headers=headers
    )
    if product1.status_code in [200, 201]:
        context["product1_id"] = product1.json().get("id")
    if product2.status_code in [200, 201]:
        context["product2_id"] = product2.json().get("id")
    return {"status": "products_created"}


def create_cart(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.create_cart(token=context.get("token"))
    if response.status_code in [200, 201]:
        context["cart_id"] = response.json().get("id")
    return response


def add_items_to_cart(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    return actions.add_to_cart(
        cart_id=context["cart_id"],
        product_id=context["product1_id"],
        quantity=context.get("quantity", 2),
        token=context.get("token"),
    )


def apply_coupon(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    return actions.apply_coupon(
        cart_id=context["cart_id"],
        code=context.get("coupon_code", "SAVE10"),
        token=context.get("token"),
    )


def verify_cart(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.get_cart(cart_id=context["cart_id"], token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        context["cart_total"] = data.get("total")
        assert data.get("items"), "Cart should have items"
        assert data.get("total") > 0, "Cart total should be positive"
    return response


def pay_with_card(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.checkout_card(
        cart_id=context["cart_id"],
        card_token=context.get("card_token", "tok_visa"),
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["order_id"] = data.get("order_id")
        context["payment_id"] = data.get("payment_id")
    return response


def pay_with_paypal(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.checkout_paypal(
        cart_id=context["cart_id"],
        paypal_email=context.get("paypal_email", "buyer@example.com"),
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["order_id"] = data.get("order_id")
        context["payment_id"] = data.get("payment_id")
    return response


def pay_with_wallet(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.checkout_wallet(
        cart_id=context["cart_id"],
        wallet_id=context.get("wallet_id", "wallet_123"),
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["order_id"] = data.get("order_id")
        context["payment_id"] = data.get("payment_id")
    return response


def get_order_details(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.get_order(order_id=context["order_id"], token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        assert data.get("status") in ["paid", "processing"], (
            f"Order status should be paid or processing, got {data.get('status')}"
        )
    return response


def create_guest_cart(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.create_cart(token=None)
    if response.status_code in [200, 201]:
        context["cart_id"] = response.json().get("id")
        context["guest_session"] = response.json().get("session_id")
    return response


def add_guest_item(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    return actions.add_to_cart(
        cart_id=context["cart_id"],
        product_id=context["product1_id"],
        quantity=1,
        token=None,
    )


def guest_checkout(client, context):
    actions = CheckoutActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.checkout_card(
        cart_id=context["cart_id"],
        card_token=context.get("card_token", "tok_visa"),
        token=None,
    )
    if response.status_code in [200, 201]:
        context["order_id"] = response.json().get("order_id")
    return response


checkout_flow = Journey(
    name="ecommerce_checkout",
    description="Full checkout flow with multiple payment methods",
    steps=[
        Step(name="login", action=login_shopper),
        Checkpoint(name="authenticated"),
        Step(name="setup_products", action=setup_products),
        Step(name="create_cart", action=create_cart),
        Step(name="add_items", action=add_items_to_cart),
        Step(name="apply_coupon", action=apply_coupon),
        Step(name="verify_cart", action=verify_cart),
        Checkpoint(name="cart_ready"),
        Branch(
            checkpoint_name="cart_ready",
            paths=[
                Path(
                    name="card_payment",
                    steps=[
                        Step(name="pay_card", action=pay_with_card),
                        Step(name="verify_card_order", action=get_order_details),
                    ],
                ),
                Path(
                    name="paypal_payment",
                    steps=[
                        Step(name="pay_paypal", action=pay_with_paypal),
                        Step(name="verify_paypal_order", action=get_order_details),
                    ],
                ),
                Path(
                    name="wallet_payment",
                    steps=[
                        Step(name="pay_wallet", action=pay_with_wallet),
                        Step(name="verify_wallet_order", action=get_order_details),
                    ],
                ),
            ],
        ),
    ],
)

guest_checkout_flow = Journey(
    name="ecommerce_guest_checkout",
    description="Checkout flow for guest users without authentication",
    steps=[
        Step(name="setup_products", action=setup_products),
        Step(name="create_guest_cart", action=create_guest_cart),
        Step(name="add_guest_item", action=add_guest_item),
        Checkpoint(name="guest_cart_ready"),
        Step(name="guest_checkout", action=guest_checkout),
        Checkpoint(name="guest_order_placed"),
    ],
)

express_checkout_flow = Journey(
    name="ecommerce_express_checkout",
    description="Express checkout with saved payment method",
    steps=[
        Step(name="login", action=login_shopper),
        Checkpoint(name="authenticated"),
        Step(name="setup_products", action=setup_products),
        Step(name="create_cart", action=create_cart),
        Step(name="add_items", action=add_items_to_cart),
        Checkpoint(name="cart_ready"),
        Step(name="express_pay", action=pay_with_card),
        Step(name="verify_order", action=get_order_details),
    ],
)
