"""Product management journey - test CRUD operations for products."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from venomqa import Journey, Step, Checkpoint, Branch, Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "actions"))
from auth_actions import admin_login
from product_actions import (
    list_products,
    get_product,
    create_product,
    update_product,
    delete_product,
    search_products,
)


product_crud_journey = Journey(
    name="product_crud",
    description="Complete product CRUD operations",
    steps=[
        Step(
            name="admin_login",
            action=admin_login,
            description="Login as admin",
        ),
        Step(
            name="list_products",
            action=list_products,
            description="List all products",
        ),
        Step(
            name="create_product",
            action=create_product,
            description="Create a new product",
        ),
        Checkpoint(name="product_created"),
        Step(
            name="update_product",
            action=update_product,
            description="Update the product",
        ),
        Checkpoint(name="product_updated"),
        Step(
            name="delete_product",
            action=delete_product,
            description="Delete the product",
        ),
    ],
)


product_browsing_journey = Journey(
    name="product_browsing",
    description="Browse and search products",
    steps=[
        Step(
            name="list_products",
            action=list_products,
            description="List all products",
        ),
        Checkpoint(name="products_listed"),
        Branch(
            checkpoint_name="products_listed",
            paths=[
                Path(
                    name="view_product_details",
                    steps=[
                        Step(
                            name="get_product",
                            action=get_product,
                            description="Get product details",
                        ),
                    ],
                ),
                Path(
                    name="search_products",
                    steps=[
                        Step(
                            name="search",
                            action=search_products,
                            description="Search for products",
                        ),
                    ],
                ),
            ],
        ),
    ],
)
