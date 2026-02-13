"""Order management journey - test order lifecycle."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from venomqa import Journey, Step, Checkpoint, Branch, Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "actions"))
from auth_actions import admin_login
from product_actions import list_products
from cart_actions import (
    create_cart,
    add_to_cart,
    add_shipping_address,
)
from order_actions import (
    create_payment_session,
    select_payment_session,
    complete_cart,
    get_order,
    list_orders_admin,
    get_order_admin,
    create_fulfillment,
    cancel_order,
)


complete_order_journey = Journey(
    name="complete_order_flow",
    description="End-to-end order creation flow",
    steps=[
        Step(
            name="list_products",
            action=list_products,
            description="Browse products",
        ),
        Step(
            name="create_cart",
            action=create_cart,
            description="Create cart",
        ),
        Step(
            name="add_to_cart",
            action=add_to_cart,
            description="Add product to cart",
        ),
        Step(
            name="add_shipping_address",
            action=add_shipping_address,
            description="Add shipping info",
        ),
        Step(
            name="create_payment_session",
            action=create_payment_session,
            description="Initialize payment",
        ),
        Step(
            name="select_payment_session",
            action=select_payment_session,
            description="Select payment method",
        ),
        Step(
            name="complete_cart",
            action=complete_cart,
            description="Complete order",
        ),
        Checkpoint(name="order_created"),
        Step(
            name="get_order",
            action=get_order,
            description="Verify order created",
        ),
    ],
)


order_management_journey = Journey(
    name="order_management",
    description="Admin order management operations",
    steps=[
        Step(
            name="admin_login",
            action=admin_login,
            description="Login as admin",
        ),
        Step(
            name="list_orders",
            action=list_orders_admin,
            description="List all orders",
        ),
        Step(
            name="get_order",
            action=get_order_admin,
            description="Get order details",
        ),
        Checkpoint(name="order_viewed"),
        Branch(
            checkpoint_name="order_viewed",
            paths=[
                Path(
                    name="fulfill_order",
                    steps=[
                        Step(
                            name="create_fulfillment",
                            action=create_fulfillment,
                            description="Fulfill the order",
                        ),
                    ],
                ),
                Path(
                    name="cancel_order",
                    steps=[
                        Step(
                            name="cancel",
                            action=cancel_order,
                            description="Cancel the order",
                        ),
                    ],
                ),
            ],
        ),
    ],
)
