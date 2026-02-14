"""E-commerce payment processing journeys.

Demonstrates:
- Payment processing with multiple gateways
- Refund flows
- Payment failure handling
"""

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.http import Client


class PaymentActions:
    def __init__(self, base_url: str, payment_url: str | None = None):
        self.client = Client(base_url=base_url)
        self.payment_client = Client(base_url=payment_url or "http://localhost:8001")

    def create_payment_intent(self, amount: float, currency: str = "USD", token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.payment_client.post(
            "/api/payments/intent",
            json={"amount": amount, "currency": currency},
            headers=headers,
        )

    def confirm_payment(self, intent_id: str, payment_method: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.payment_client.post(
            f"/api/payments/intent/{intent_id}/confirm",
            json={"payment_method": payment_method},
            headers=headers,
        )

    def get_payment(self, payment_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.payment_client.get(f"/api/payments/{payment_id}", headers=headers)

    def refund_payment(
        self,
        payment_id: str,
        amount: float | None = None,
        reason: str = "",
        token: str | None = None,
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        data = {"reason": reason}
        if amount:
            data["amount"] = amount
        return self.payment_client.post(
            f"/api/payments/{payment_id}/refund", json=data, headers=headers
        )

    def capture_payment(
        self, payment_id: str, amount: float | None = None, token: str | None = None
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        data = {}
        if amount:
            data["amount"] = amount
        return self.payment_client.post(
            f"/api/payments/{payment_id}/capture", json=data, headers=headers
        )

    def void_payment(self, payment_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.payment_client.post(
            f"/api/payments/{payment_id}/void", json={}, headers=headers
        )

    def get_refund(self, refund_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.payment_client.get(f"/api/refunds/{refund_id}", headers=headers)


def login_shopper(client, context):
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "shopper@example.com"),
            "password": context.get("password", "pass123"),
        },
    )
    if response.status_code == 200:
        context["token"] = response.json().get("access_token")
    return response


def create_payment_intent(client, context):
    actions = PaymentActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    amount = context.get("payment_amount", 99.99)
    response = actions.create_payment_intent(
        amount=amount, currency=context.get("currency", "USD"), token=context.get("token")
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["intent_id"] = data.get("id")
        context["client_secret"] = data.get("client_secret")
        assert data.get("status") == "requires_payment_method", (
            f"Intent should require payment method, got {data.get('status')}"
        )
    return response


def confirm_with_card(client, context):
    actions = PaymentActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.confirm_payment(
        intent_id=context["intent_id"],
        payment_method=context.get("card_method", "pm_card_visa"),
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["payment_id"] = data.get("payment_id")
        context["payment_status"] = data.get("status")
    return response


def confirm_with_failed_card(client, context):
    actions = PaymentActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    return actions.confirm_payment(
        intent_id=context["intent_id"],
        payment_method=context.get("fail_card_method", "pm_card_fail"),
        token=context.get("token"),
    )


def get_payment_status(client, context):
    actions = PaymentActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.get_payment(payment_id=context["payment_id"], token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        assert data.get("status") in ["succeeded", "captured"], (
            f"Payment should be successful, got {data.get('status')}"
        )
    return response


def full_refund(client, context):
    actions = PaymentActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.refund_payment(
        payment_id=context["payment_id"],
        reason="Customer request",
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["refund_id"] = data.get("id")
        assert data.get("status") == "succeeded", f"Refund should succeed, got {data.get('status')}"
    return response


def partial_refund(client, context):
    actions = PaymentActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    refund_amount = context.get("refund_amount", 25.00)
    response = actions.refund_payment(
        payment_id=context["payment_id"],
        amount=refund_amount,
        reason="Partial refund for returned item",
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        context["refund_id"] = response.json().get("id")
    return response


def verify_refund(client, context):
    actions = PaymentActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.get_refund(refund_id=context["refund_id"], token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        assert data.get("status") == "succeeded", (
            f"Refund status should be succeeded, got {data.get('status')}"
        )
    return response


def capture_payment(client, context):
    actions = PaymentActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.capture_payment(payment_id=context["payment_id"], token=context.get("token"))
    if response.status_code in [200, 201]:
        context["payment_status"] = "captured"
    return response


def void_payment(client, context):
    actions = PaymentActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        payment_url=context.get("payment_url", "http://localhost:8001"),
    )
    response = actions.void_payment(payment_id=context["payment_id"], token=context.get("token"))
    if response.status_code in [200, 201]:
        context["payment_status"] = "voided"
    return response


payment_processing_flow = Journey(
    name="ecommerce_payment_processing",
    description="Complete payment processing with capture",
    steps=[
        Step(name="login", action=login_shopper),
        Checkpoint(name="authenticated"),
        Step(name="create_intent", action=create_payment_intent),
        Checkpoint(name="intent_created"),
        Step(name="confirm_card", action=confirm_with_card),
        Checkpoint(name="payment_confirmed"),
        Step(name="verify_payment", action=get_payment_status),
        Step(name="capture", action=capture_payment),
        Checkpoint(name="payment_captured"),
    ],
)

refund_flow = Journey(
    name="ecommerce_refund",
    description="Full and partial refund flows",
    steps=[
        Step(name="login", action=login_shopper),
        Checkpoint(name="authenticated"),
        Step(
            name="create_intent",
            action=create_payment_intent,
            args={"payment_amount": 100.00},
        ),
        Step(name="confirm", action=confirm_with_card),
        Step(name="capture", action=capture_payment),
        Checkpoint(name="payment_complete"),
        Branch(
            checkpoint_name="payment_complete",
            paths=[
                Path(
                    name="full_refund",
                    steps=[
                        Step(name="refund_full", action=full_refund),
                        Step(name="verify_full_refund", action=verify_refund),
                    ],
                ),
                Path(
                    name="partial_refund",
                    steps=[
                        Step(
                            name="refund_partial",
                            action=partial_refund,
                            args={"refund_amount": 30.00},
                        ),
                        Step(name="verify_partial_refund", action=verify_refund),
                    ],
                ),
            ],
        ),
    ],
)

payment_failure_flow = Journey(
    name="ecommerce_payment_failure",
    description="Handle payment failures gracefully",
    steps=[
        Step(name="login", action=login_shopper),
        Checkpoint(name="authenticated"),
        Step(name="create_intent", action=create_payment_intent),
        Checkpoint(name="intent_created"),
        Step(name="confirm_failed_card", action=confirm_with_failed_card, expect_failure=True),
        Step(name="verify_intent_failed", action=create_payment_intent),
    ],
)
