"""Pre-built e-commerce data generators.

This module provides specialized data generators for e-commerce testing
scenarios, including products, carts, orders, and inventory management.

Example:
    >>> from venomqa.data.ecommerce import ecommerce
    >>>
    >>> # Generate a product catalog
    >>> products = ecommerce.product_catalog(10)
    >>>
    >>> # Generate a complete checkout scenario
    >>> checkout = ecommerce.checkout_scenario()
    >>> print(checkout["cart"])
    >>> print(checkout["payment"])
    >>> print(checkout["order"])
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from venomqa.data.generators import FakeDataGenerator
from venomqa.data.generators import fake as default_fake


@dataclass
class EcommerceGenerator:
    """Specialized generator for e-commerce test data.

    Provides methods for generating complex e-commerce data structures
    like product catalogs, shopping carts, orders, and inventory.
    """

    fake: FakeDataGenerator = field(default_factory=lambda: default_fake)

    def product_variant(
        self,
        product_id: str | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a product variant (size, color, etc.)."""
        colors = ["Red", "Blue", "Green", "Black", "White", "Gray", "Navy", "Pink"]
        sizes = ["XS", "S", "M", "L", "XL", "XXL"]

        variant = {
            "id": self.fake.uuid(),
            "product_id": product_id or self.fake.uuid(),
            "sku": self.fake.sku(),
            "color": random.choice(colors),
            "size": random.choice(sizes),
            "price": self.fake.price(10, 200),
            "stock_quantity": random.randint(0, 100),
            "is_available": random.random() > 0.1,
            "weight": self.fake._faker.weight(),
            "image_url": self.fake._faker.image_url(),
        }
        variant.update(overrides)
        return variant

    def product_with_variants(
        self,
        variant_count: int = 4,
        **overrides: Any,
    ) -> dict:
        """Generate a product with multiple variants."""
        product = self.fake.product(**overrides)
        product_id = product["id"]
        product["variants"] = [
            self.product_variant(product_id=product_id) for _ in range(variant_count)
        ]
        product["total_stock"] = sum(v["stock_quantity"] for v in product["variants"])
        return product

    def product_catalog(
        self,
        count: int = 10,
        categories: list[str] | None = None,
        with_variants: bool = False,
    ) -> list[dict]:
        """Generate a product catalog.

        Args:
            count: Number of products to generate.
            categories: Optional list of categories to use.
            with_variants: Whether to include product variants.

        Returns:
            A list of product dictionaries.
        """
        products = []
        for _ in range(count):
            category = random.choice(categories) if categories else self.fake.product_category()
            if with_variants:
                product = self.product_with_variants(category=category)
            else:
                product = self.fake.product(category=category)
            products.append(product)
        return products

    def product_review(
        self,
        product_id: str | None = None,
        user_id: str | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a product review."""
        review = {
            "id": self.fake.uuid(),
            "product_id": product_id or self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "user_name": self.fake.name(),
            "rating": random.randint(1, 5),
            "title": self.fake.sentence(words=6),
            "content": self.fake.paragraph(sentences=3),
            "helpful_count": random.randint(0, 50),
            "verified_purchase": random.random() > 0.3,
            "images": [
                self.fake._faker.image_url()
                for _ in range(random.randint(0, 3))
            ],
            "created_at": self.fake.datetime().isoformat(),
        }
        review.update(overrides)
        return review

    def product_with_reviews(
        self,
        review_count: int = 5,
        **overrides: Any,
    ) -> dict:
        """Generate a product with reviews."""
        product = self.fake.product(**overrides)
        product_id = product["id"]
        reviews = [
            self.product_review(product_id=product_id)
            for _ in range(review_count)
        ]
        product["reviews"] = reviews
        product["average_rating"] = (
            sum(r["rating"] for r in reviews) / len(reviews) if reviews else 0
        )
        product["review_count"] = len(reviews)
        return product

    def shopping_cart(
        self,
        user_id: str | None = None,
        item_count: int | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a shopping cart with items."""
        return self.fake.cart(user_id=user_id, item_count=item_count, **overrides)

    def abandoned_cart(
        self,
        user_id: str | None = None,
        days_old: int = 7,
        **overrides: Any,
    ) -> dict:
        """Generate an abandoned shopping cart."""
        cart = self.shopping_cart(user_id=user_id, **overrides)
        abandoned_at = datetime.now() - timedelta(days=random.randint(1, days_old))
        cart["status"] = "abandoned"
        cart["abandoned_at"] = abandoned_at.isoformat()
        cart["recovery_email_sent"] = random.random() > 0.5
        return cart

    def wishlist(
        self,
        user_id: str | None = None,
        item_count: int | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a user wishlist."""
        if item_count is None:
            item_count = random.randint(3, 10)

        items = []
        for _ in range(item_count):
            items.append({
                "id": self.fake.uuid(),
                "product_id": self.fake.uuid(),
                "product_name": self.fake.product_name(),
                "price": self.fake.price(),
                "image_url": self.fake._faker.image_url(),
                "added_at": self.fake.datetime().isoformat(),
                "is_available": random.random() > 0.1,
                "price_drop_alert": random.random() > 0.5,
            })

        wishlist = {
            "id": self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "name": random.choice(["My Wishlist", "Favorites", "For Later", "Gift Ideas"]),
            "items": items,
            "is_public": random.random() > 0.7,
            "created_at": self.fake.datetime().isoformat(),
            "updated_at": self.fake.datetime().isoformat(),
        }
        wishlist.update(overrides)
        return wishlist

    def order_with_items(
        self,
        user_id: str | None = None,
        item_count: int | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a complete order with items."""
        if item_count is None:
            item_count = random.randint(1, 5)
        items = [self.fake.order_item() for _ in range(item_count)]
        return self.fake.order(user_id=user_id, items=items, **overrides)

    def order_history(
        self,
        user_id: str | None = None,
        count: int = 5,
        date_range_days: int = 365,
    ) -> list[dict]:
        """Generate order history for a user.

        Args:
            user_id: User ID for all orders.
            count: Number of orders to generate.
            date_range_days: Range of days for order dates.

        Returns:
            A list of orders sorted by date (newest first).
        """
        user_id = user_id or self.fake.uuid()
        orders = []

        statuses_by_age = {
            "recent": ["pending", "confirmed", "processing", "shipped"],
            "mid": ["shipped", "delivered"],
            "old": ["delivered", "completed"],
        }

        for _i in range(count):
            days_ago = random.randint(0, date_range_days)
            age = "recent" if days_ago < 7 else ("mid" if days_ago < 30 else "old")
            status = random.choice(statuses_by_age[age])

            order_date = datetime.now() - timedelta(days=days_ago)
            order = self.order_with_items(
                user_id=user_id,
                status=status,
                created_at=order_date.isoformat(),
            )
            orders.append(order)

        return sorted(orders, key=lambda x: x["created_at"], reverse=True)

    def return_request(
        self,
        order_id: str | None = None,
        user_id: str | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a return request."""
        reasons = [
            "Wrong size",
            "Defective product",
            "Not as described",
            "Changed mind",
            "Better price elsewhere",
            "Arrived too late",
        ]

        request = {
            "id": self.fake.uuid(),
            "order_id": order_id or self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "reason": random.choice(reasons),
            "description": self.fake.text(200),
            "status": random.choice(["pending", "approved", "rejected", "completed"]),
            "refund_amount": self.fake.price(10, 500),
            "refund_method": random.choice(["original_payment", "store_credit"]),
            "images": [
                self.fake._faker.image_url()
                for _ in range(random.randint(0, 3))
            ],
            "created_at": self.fake.datetime().isoformat(),
            "updated_at": self.fake.datetime().isoformat(),
        }
        request.update(overrides)
        return request

    def inventory_item(
        self,
        product_id: str | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate inventory item data."""
        quantity = random.randint(0, 500)
        reorder_point = random.randint(10, 50)

        item = {
            "id": self.fake.uuid(),
            "product_id": product_id or self.fake.uuid(),
            "sku": self.fake.sku(),
            "warehouse_id": self.fake.uuid(),
            "quantity": quantity,
            "reserved_quantity": random.randint(0, min(quantity, 20)),
            "reorder_point": reorder_point,
            "reorder_quantity": reorder_point * 2,
            "is_low_stock": quantity <= reorder_point,
            "last_restocked": self.fake.past_datetime(days=30).isoformat(),
            "last_sold": self.fake.past_datetime(days=7).isoformat(),
        }
        item.update(overrides)
        return item

    def inventory_snapshot(
        self,
        product_count: int = 20,
    ) -> dict:
        """Generate an inventory snapshot."""
        items = [self.inventory_item() for _ in range(product_count)]

        return {
            "id": self.fake.uuid(),
            "timestamp": datetime.now().isoformat(),
            "warehouse_id": self.fake.uuid(),
            "items": items,
            "total_items": sum(i["quantity"] for i in items),
            "low_stock_count": sum(1 for i in items if i["is_low_stock"]),
            "out_of_stock_count": sum(1 for i in items if i["quantity"] == 0),
        }

    def coupon(self, **overrides: Any) -> dict:
        """Generate a coupon/discount code."""
        coupon_types = ["percentage", "fixed_amount", "free_shipping", "buy_x_get_y"]
        coupon_type = random.choice(coupon_types)

        coupon = {
            "id": self.fake.uuid(),
            "code": self.fake.coupon_code(),
            "type": coupon_type,
            "value": (
                random.randint(5, 50) if coupon_type == "percentage"
                else self.fake.price(5, 50)
            ),
            "minimum_order": self.fake.price(20, 100) if random.random() > 0.5 else None,
            "maximum_discount": self.fake.price(50, 100) if random.random() > 0.5 else None,
            "usage_limit": random.randint(100, 1000) if random.random() > 0.5 else None,
            "usage_count": random.randint(0, 50),
            "per_user_limit": random.randint(1, 3),
            "valid_from": self.fake.past_datetime(days=30).isoformat(),
            "valid_until": self.fake.future_datetime(days=30).isoformat(),
            "is_active": random.random() > 0.2,
            "applicable_categories": (
                [self.fake.product_category() for _ in range(random.randint(1, 3))]
                if random.random() > 0.5 else None
            ),
        }
        coupon.update(overrides)
        return coupon

    def checkout_scenario(
        self,
        user_id: str | None = None,
        with_coupon: bool = False,
    ) -> dict:
        """Generate a complete checkout scenario.

        This generates all the data needed for a checkout test:
        cart, shipping, payment, and resulting order.

        Args:
            user_id: Optional user ID.
            with_coupon: Whether to include a coupon.

        Returns:
            A dictionary with cart, user, payment, and order data.
        """
        user_id = user_id or self.fake.uuid()

        # Generate cart
        cart = self.shopping_cart(user_id=user_id, item_count=random.randint(1, 4))

        # Generate addresses
        shipping = self.fake.shipping_address()
        billing = self.fake.billing_address()

        # Generate payment
        payment = {
            "method": self.fake.payment_method(),
            "card_number": self.fake.test_card_number(),
            "card_expiry": self.fake.card_expiry(),
            "cvv": self.fake.cvv(),
            "card_holder": self.fake.card_holder_name(),
        }

        # Calculate totals
        subtotal = cart["subtotal"]
        discount = 0
        coupon_data = None

        if with_coupon:
            coupon_data = self.coupon(type="percentage")
            if coupon_data["type"] == "percentage":
                discount = round(subtotal * coupon_data["value"] / 100, 2)
            else:
                discount = min(coupon_data["value"], subtotal)

        tax = round((subtotal - discount) * 0.1, 2)
        shipping_cost = round(random.uniform(5, 15), 2)
        total = round(subtotal - discount + tax + shipping_cost, 2)

        # Generate order from cart
        order = {
            "id": self.fake.uuid(),
            "order_number": self.fake.order_number(),
            "user_id": user_id,
            "status": "confirmed",
            "items": cart["items"],
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "shipping_cost": shipping_cost,
            "total": total,
            "shipping_address": shipping,
            "billing_address": billing,
            "payment_method": payment["method"],
            "coupon_code": coupon_data["code"] if coupon_data else None,
            "created_at": datetime.now().isoformat(),
        }

        return {
            "user_id": user_id,
            "cart": cart,
            "shipping_address": shipping,
            "billing_address": billing,
            "payment": payment,
            "coupon": coupon_data,
            "order": order,
        }

    def subscription(
        self,
        user_id: str | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a subscription."""
        plans = [
            {"name": "Basic", "price": 9.99, "interval": "month"},
            {"name": "Pro", "price": 19.99, "interval": "month"},
            {"name": "Enterprise", "price": 49.99, "interval": "month"},
            {"name": "Basic Annual", "price": 99.99, "interval": "year"},
            {"name": "Pro Annual", "price": 199.99, "interval": "year"},
        ]
        plan = random.choice(plans)

        subscription = {
            "id": self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "plan_name": plan["name"],
            "price": plan["price"],
            "interval": plan["interval"],
            "status": random.choice(["active", "cancelled", "past_due", "trial"]),
            "trial_ends_at": (
                self.fake.future_datetime(days=14).isoformat()
                if random.random() > 0.7 else None
            ),
            "current_period_start": self.fake.past_datetime(days=30).isoformat(),
            "current_period_end": self.fake.future_datetime(days=30).isoformat(),
            "cancel_at_period_end": random.random() > 0.9,
            "payment_method_id": self.fake.uuid(),
            "created_at": self.fake.datetime().isoformat(),
        }
        subscription.update(overrides)
        return subscription


# Global instance for convenience
ecommerce = EcommerceGenerator()


def create_ecommerce_generator(
    locale: str = "en_US",
    seed: int | None = None,
) -> EcommerceGenerator:
    """Create a new EcommerceGenerator with custom settings.

    Args:
        locale: Locale for generated data.
        seed: Seed for reproducible generation.

    Returns:
        A configured EcommerceGenerator instance.
    """
    from venomqa.data.generators import create_fake

    return EcommerceGenerator(fake=create_fake(locale, seed))
