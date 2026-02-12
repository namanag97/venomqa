from venomqa import Journey, Step, Action, Branch
from actions.auth import login
from actions.items import create_item, delete_item


def process_payment(client, context):
    return client.post(
        "/api/payments",
        json={
            "item_id": context["created_item"]["id"],
            "amount": context["created_item"]["price"],
            "method": context.get("payment_method", "credit_card"),
        },
    )


def verify_payment(client, context):
    return client.get(f"/api/payments/{context['payment_response']['id']}")


def refund_payment(client, context):
    return client.post(
        f"/api/payments/{context['payment_response']['id']}/refund",
    )


def notify_user(client, context):
    return client.post(
        "/api/notifications",
        json={
            "user_id": context["user"]["id"],
            "type": "payment_success",
            "message": f"Payment of ${context['created_item']['price']} completed",
        },
    )


payment_journey = Journey(
    name="payment_flow",
    description="Payment processing journey with branching",
    steps=[
        Step(
            name="login",
            action=Action(func=login),
            save_to="user",
            checkpoint="authenticated",
        ),
        Step(
            name="create_item_for_purchase",
            action=Action(func=create_item, args={"name": "Premium Widget", "price": 299.99}),
            save_to="created_item",
        ),
        Step(
            name="process_payment",
            action=Action(func=process_payment),
            save_to="payment_response",
            assert_that=lambda ctx: ctx["payment_response"].status_code in [200, 201],
        ),
        Step(
            name="branch_on_payment_result",
            branches=[
                Branch(
                    condition=lambda ctx: ctx["payment_response"]["status"] == "success",
                    steps=[
                        Step(
                            name="verify_payment",
                            action=Action(func=verify_payment),
                            save_to="verification",
                        ),
                        Step(
                            name="notify_user_success",
                            action=Action(func=notify_user),
                        ),
                    ],
                ),
                Branch(
                    condition=lambda ctx: ctx["payment_response"]["status"] == "pending",
                    steps=[
                        Step(
                            name="wait_for_confirmation",
                            action=Action(
                                func=lambda client, ctx: client.get(
                                    f"/api/payments/{ctx['payment_response']['id']}/status"
                                )
                            ),
                            retry=3,
                            retry_delay=5,
                        ),
                    ],
                ),
                Branch(
                    condition=lambda ctx: ctx["payment_response"]["status"] == "failed",
                    steps=[
                        Step(
                            name="handle_payment_failure",
                            action=Action(
                                func=lambda client, ctx: client.post(
                                    "/api/payments/retry",
                                    json={"payment_id": ctx["payment_response"]["id"]},
                                )
                            ),
                            expect_failure=True,
                        ),
                    ],
                ),
            ],
        ),
        Step(
            name="cleanup_item",
            action=Action(func=delete_item, args={"item_id": "{created_item[id]}"}),
            checkpoint="cleanup_complete",
        ),
    ],
)
