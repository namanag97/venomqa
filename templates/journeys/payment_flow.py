from typing import Optional
from venomqa import Journey, Step, Checkpoint, Branch
from venomqa.clients import HTTPClient


class PaymentActions:
    def __init__(self, base_url: str):
        self.client = HTTPClient(base_url=base_url)

    def create_cart(self, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.post("/api/cart", json={}, headers=headers)

    def add_to_cart(
        self,
        cart_id: str,
        product_id: str,
        quantity: int = 1,
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.post(
            f"/api/cart/{cart_id}/items",
            json={"product_id": product_id, "quantity": quantity},
            headers=headers,
        )

    def get_cart(self, cart_id: str, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.get(f"/api/cart/{cart_id}", headers=headers)

    def apply_coupon(
        self,
        cart_id: str,
        coupon_code: str,
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.post(
            f"/api/cart/{cart_id}/coupon",
            json={"code": coupon_code},
            headers=headers,
        )

    def create_payment_method(
        self,
        method_type: str,
        details: dict,
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.post(
            "/api/payment-methods",
            json={"type": method_type, "details": details},
            headers=headers,
        )

    def process_checkout(
        self,
        cart_id: str,
        payment_method_id: str,
        shipping_address: dict,
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.post(
            "/api/checkout",
            json={
                "cart_id": cart_id,
                "payment_method_id": payment_method_id,
                "shipping_address": shipping_address,
            },
            headers=headers,
        )

    def get_payment_status(self, payment_id: str, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.get(f"/api/payments/{payment_id}", headers=headers)

    def refund_payment(
        self,
        payment_id: str,
        amount: Optional[float] = None,
        reason: Optional[str] = None,
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = {}
        if amount:
            data["amount"] = amount
        if reason:
            data["reason"] = reason
        return self.client.post(f"/api/payments/{payment_id}/refund", json=data, headers=headers)

    def get_order(self, order_id: str, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.get(f"/api/orders/{order_id}", headers=headers)

    def cancel_order(self, order_id: str, reason: str, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.post(
            f"/api/orders/{order_id}/cancel",
            json={"reason": reason},
            headers=headers,
        )


def login_shopper(client, context):
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "shopper@example.com"),
            "password": context.get("password", "password123"),
        },
    )
    if response.status_code == 200:
        context["token"] = response.json().get("access_token")
        context["user_id"] = response.json().get("user", {}).get("id")
    return response


def setup_products(client, context):
    token = context.get("token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    product1 = client.post(
        "/api/products",
        json={"name": "Widget A", "price": 29.99, "stock": 100},
        headers=headers,
    )
    product2 = client.post(
        "/api/products",
        json={"name": "Widget B", "price": 49.99, "stock": 50},
        headers=headers,
    )

    if product1.status_code in [200, 201]:
        context["product1_id"] = product1.json().get("id")
    if product2.status_code in [200, 201]:
        context["product2_id"] = product2.json().get("id")

    return {"status": "products_created"}


def create_shopping_cart(client, context):
    actions = PaymentActions(context.get("base_url", "http://localhost:8000"))
    response = actions.create_cart(token=context.get("token"))
    if response.status_code in [200, 201]:
        context["cart_id"] = response.json().get("id")
    return response


def add_items_to_cart(client, context):
    actions = PaymentActions(context.get("base_url", "http://localhost:8000"))
    return actions.add_to_cart(
        cart_id=context["cart_id"],
        product_id=context["product1_id"],
        quantity=context.get("quantity", 2),
        token=context.get("token"),
    )


def add_second_item(client, context):
    actions = PaymentActions(context.get("base_url", "http://localhost:8000"))
    return actions.add_to_cart(
        cart_id=context["cart_id"],
        product_id=context["product2_id"],
        quantity=1,
        token=context.get("token"),
    )


def apply_discount_code(client, context):
    actions = PaymentActions(context.get("base_url", "http://localhost:8000"))
    return actions.apply_coupon(
        cart_id=context["cart_id"],
        coupon_code=context.get("coupon_code", "SAVE10"),
        token=context.get("token"),
    )


def verify_cart_totals(client, context):
    actions = PaymentActions(context.get("base_url", "http://localhost:8000"))
    return actions.get_cart(cart_id=context["cart_id"], token=context.get("token"))


def setup_payment_method(client, context):
    actions = PaymentActions(context.get("base_url", "http://localhost:8000"))
    response = actions.create_payment_method(
        method_type=context.get("payment_type", "credit_card"),
        details={
            "card_number": "4111111111111111",
            "expiry_month": 12,
            "expiry_year": 2025,
            "cvv": "123",
            "cardholder_name": "Test Shopper",
        },
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        context["payment_method_id"] = response.json().get("id")
    return response


def process_payment(client, context):
    actions = PaymentActions(context.get("base_url", "http://localhost:8000"))
    response = actions.process_checkout(
        cart_id=context["cart_id"],
        payment_method_id=context["payment_method_id"],
        shipping_address={
            "street": "123 Test St",
            "city": "Test City",
            "state": "TS",
            "zip": "12345",
            "country": "US",
        },
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["payment_id"] = data.get("payment_id")
        context["order_id"] = data.get("order_id")
        context["payment_status"] = data.get("status")
    return response


def check_payment_status(client, context):
    actions = PaymentActions(context.get("base_url", "http://localhost:8000"))
    return actions.get_payment_status(payment_id=context["payment_id"], token=context.get("token"))


def get_order_details(client, context):
    actions = PaymentActions(context.get("base_url", "http://localhost:8000"))
    return actions.get_order(order_id=context["order_id"], token=context.get("token"))


def refund_order(client, context):
    actions = PaymentActions(context.get("base_url", "http://localhost:8000"))
    return actions.refund_payment(
        payment_id=context["payment_id"],
        reason="Customer request - test refund",
        token=context.get("token"),
    )


def cancel_unpaid_order(client, context):
    actions = PaymentActions(context.get("base_url", "http://localhost:8000"))
    return actions.cancel_order(
        order_id=context["order_id"],
        reason="Customer cancelled",
        token=context.get("token"),
    )


shopping_cart_flow = Journey(
    name="shopping_cart",
    description="Add items to cart and verify totals",
    steps=[
        Step(name="login", action=login_shopper),
        Checkpoint(name="authenticated"),
        Step(name="setup_products", action=setup_products),
        Step(name="create_cart", action=create_shopping_cart),
        Step(name="add_item_1", action=add_items_to_cart),
        Step(name="add_item_2", action=add_second_item),
        Step(name="apply_coupon", action=apply_discount_code),
        Step(name="verify_totals", action=verify_cart_totals),
    ],
)


checkout_success_flow = Journey(
    name="checkout_success",
    description="Complete checkout with successful payment",
    steps=[
        Step(name="login", action=login_shopper),
        Checkpoint(name="authenticated"),
        Step(name="setup_products", action=setup_products),
        Step(name="create_cart", action=create_shopping_cart),
        Step(name="add_items", action=add_items_to_cart),
        Step(name="setup_payment", action=setup_payment_method),
        Step(name="process_checkout", action=process_payment),
        Checkpoint(name="payment_processed"),
        Step(name="check_payment_status", action=check_payment_status),
        Step(name="get_order", action=get_order_details),
    ],
)


refund_flow = Journey(
    name="payment_refund",
    description="Process payment and then refund it",
    steps=[
        Step(name="login", action=login_shopper),
        Checkpoint(name="authenticated"),
        Step(name="setup_products", action=setup_products),
        Step(name="create_cart", action=create_shopping_cart),
        Step(name="add_items", action=add_items_to_cart),
        Step(name="setup_payment", action=setup_payment_method),
        Step(name="process_checkout", action=process_payment),
        Checkpoint(name="payment_complete"),
        Step(name="refund_payment", action=refund_order),
        Checkpoint(name="refund_complete"),
    ],
)


full_purchase_flow = Journey(
    name="full_purchase_lifecycle",
    description="Complete purchase flow from cart to delivery confirmation",
    steps=[
        Step(name="login", action=login_shopper),
        Checkpoint(name="authenticated"),
        Step(name="setup_products", action=setup_products),
        Step(name="create_cart", action=create_shopping_cart),
        Step(name="add_item_1", action=add_items_to_cart),
        Step(name="add_item_2", action=add_second_item),
        Step(name="apply_discount", action=apply_discount_code),
        Step(name="verify_cart", action=verify_cart_totals),
        Step(name="add_payment_method", action=setup_payment_method),
        Step(name="checkout", action=process_payment),
        Checkpoint(name="order_placed"),
        Step(name="check_payment", action=check_payment_status),
        Step(name="get_order_details", action=get_order_details),
    ],
)


partial_refund_flow = Journey(
    name="partial_refund",
    description="Process partial refund for an order",
    steps=[
        Step(name="login", action=login_shopper),
        Checkpoint(name="authenticated"),
        Step(name="setup_products", action=setup_products),
        Step(name="create_cart", action=create_shopping_cart),
        Step(name="add_items", action=add_items_to_cart),
        Step(name="setup_payment", action=setup_payment_method),
        Step(name="checkout", action=process_payment),
        Checkpoint(name="paid"),
        Step(
            name="partial_refund",
            action=lambda client, ctx: PaymentActions(
                ctx.get("base_url", "http://localhost:8000")
            ).refund_payment(
                payment_id=ctx["payment_id"],
                amount=29.99,
                reason="Partial refund for returned item",
                token=ctx.get("token"),
            ),
        ),
    ],
)
