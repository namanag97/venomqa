"""Shopping cart journey - test cart operations."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from venomqa import Journey, Step, Checkpoint, Branch, Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "actions"))
from product_actions import list_products
from cart_actions import (
    create_cart,
    get_cart,
    add_to_cart,
    update_cart_item,
    remove_from_cart,
    add_shipping_address,
)


cart_operations_journey = Journey(
    name="cart_operations",
    description="Test shopping cart CRUD operations",
    steps=[
        Step(
            name="list_products",
            action=list_products,
            description="Get available products",
        ),
        Step(
            name="create_cart",
            action=create_cart,
            description="Create a new cart",
        ),
        Step(
            name="add_to_cart",
            action=add_to_cart,
            description="Add product to cart",
        ),
        Checkpoint(name="item_in_cart"),
        Branch(
            checkpoint_name="item_in_cart",
            paths=[
                Path(
                    name="update_quantity",
                    steps=[
                        Step(
                            name="update_cart_item",
                            action=update_cart_item,
                            description="Update item quantity",
                        ),
                        Step(
                            name="get_cart",
                            action=get_cart,
                            description="Verify cart update",
                        ),
                    ],
                ),
                Path(
                    name="remove_item",
                    steps=[
                        Step(
                            name="remove_from_cart",
                            action=remove_from_cart,
                            description="Remove item from cart",
                        ),
                        Step(
                            name="get_cart",
                            action=get_cart,
                            description="Verify item removed",
                        ),
                    ],
                ),
                Path(
                    name="add_shipping",
                    steps=[
                        Step(
                            name="add_shipping_address",
                            action=add_shipping_address,
                            description="Add shipping address",
                        ),
                    ],
                ),
            ],
        ),
    ],
)
