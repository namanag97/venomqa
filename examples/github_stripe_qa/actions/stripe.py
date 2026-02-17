"""VenomQA v1 actions for the mock Stripe API.

The Stripe client is passed through context["stripe"] rather than being
the primary World api (which is reserved for GitHub). Each function pulls
the Stripe HttpClient from context before making requests.

Context keys written by these actions:
    customer_id     — id of the most recently created Stripe customer
    pi_id           — id of the most recently created PaymentIntent
    pi_amount       — amount (in cents) of the current PaymentIntent
    refund_id       — id of the most recently created Refund
    pi_data         — full PaymentIntent dict from the last get_payment_intent call
"""

from __future__ import annotations

from venomqa.v1.core.action import ActionResult


def create_customer(api, context) -> ActionResult:  # type: ignore[no-untyped-def]
    """POST /customers — create a Stripe customer."""
    stripe = context.get("stripe")
    result = stripe.post(
        "/customers",
        json={"email": "buyer@qa.test", "name": "QA Test User"},
    )
    if result.success and result.response.status_code == 201:
        context.set("customer_id", result.response.body.get("id"))
    return result


def create_payment_intent(api, context) -> ActionResult:  # type: ignore[no-untyped-def]
    """POST /payment_intents — create a PaymentIntent for 1000 cents ($10.00)."""
    stripe = context.get("stripe")
    customer_id = context.get("customer_id", "")
    amount = 1000  # $10.00 in cents
    result = stripe.post(
        "/payment_intents",
        json={
            "amount": amount,
            "currency": "usd",
            "customer_id": customer_id,
        },
    )
    if result.success and result.response.status_code == 201:
        pi = result.response.body
        context.set("pi_id", pi.get("id"))
        context.set("pi_amount", pi.get("amount", amount))
    return result


def confirm_payment(api, context) -> ActionResult:  # type: ignore[no-untyped-def]
    """POST /payment_intents/{id}/confirm — confirm the current PaymentIntent."""
    stripe = context.get("stripe")
    pi_id = context.get("pi_id", "")
    result = stripe.post(f"/payment_intents/{pi_id}/confirm")
    return result


def create_refund(api, context) -> ActionResult:  # type: ignore[no-untyped-def]
    """POST /refunds — issue a refund that EXCEEDS the original payment amount.

    This action deliberately sends a refund_amount > pi_amount to probe
    whether the mock API enforces the over-refund guard. A correctly
    implemented server should return HTTP 400. The buggy mock accepts it,
    which the invariant `refund_cannot_exceed_payment` will catch.
    """
    stripe = context.get("stripe")
    pi_id = context.get("pi_id", "")
    pi_amount = context.get("pi_amount", 1000)
    # Over-refund: send 2× the original amount
    over_refund_amount = pi_amount * 2
    result = stripe.post(
        "/refunds",
        json={"payment_intent_id": pi_id, "amount": over_refund_amount},
    )
    if result.success and result.response.status_code == 201:
        context.set("refund_id", result.response.body.get("id"))
        context.set("refund_amount_sent", over_refund_amount)
    return result


def get_payment_intent(api, context) -> ActionResult:  # type: ignore[no-untyped-def]
    """GET /payment_intents/{id} — retrieve and cache the current PaymentIntent."""
    stripe = context.get("stripe")
    pi_id = context.get("pi_id", "")
    result = stripe.get(f"/payment_intents/{pi_id}")
    if result.success:
        context.set("pi_data", result.response.body)
    return result
