"""Custom Faker providers for realistic test data."""

from __future__ import annotations

import random
import string
from typing import Any

try:
    from faker import Faker
    from faker.providers import BaseProvider

    HAS_FAKER = True
except ImportError:
    HAS_FAKER = False
    Faker = None
    BaseProvider = object


class EcommerceProvider(BaseProvider):
    """Provider for e-commerce related test data."""

    product_categories = [
        "Electronics",
        "Clothing",
        "Books",
        "Home & Garden",
        "Sports",
        "Toys",
        "Food",
        "Health",
        "Beauty",
        "Automotive",
    ]

    product_adjectives = [
        "Premium",
        "Deluxe",
        "Professional",
        "Essential",
        "Basic",
        "Advanced",
        "Compact",
        "Heavy-Duty",
        "Lightweight",
        "Ergonomic",
    ]

    product_nouns = [
        "Widget",
        "Gadget",
        "Device",
        "Tool",
        "Kit",
        "Set",
        "Bundle",
        "Pack",
        "Collection",
        "System",
    ]

    order_statuses = [
        "pending",
        "confirmed",
        "processing",
        "shipped",
        "delivered",
        "cancelled",
        "refunded",
    ]

    payment_methods = [
        "credit_card",
        "debit_card",
        "paypal",
        "bank_transfer",
        "crypto",
        "cash_on_delivery",
    ]

    def product_name(self) -> str:
        adj = self.random_element(self.product_adjectives)
        noun = self.random_element(self.product_nouns)
        return f"{adj} {noun}"

    def product_category(self) -> str:
        return self.random_element(self.product_categories)

    def sku(self) -> str:
        prefix = self.random_element(string.ascii_uppercase for _ in range(3))
        suffix = "".join(random.choices(string.digits, k=6))
        return f"{prefix}-{suffix}"

    def order_status(self) -> str:
        return self.random_element(self.order_statuses)

    def payment_method(self) -> str:
        return self.random_element(self.payment_methods)

    def price(self, min_price: float = 1.0, max_price: float = 1000.0) -> float:
        return round(random.uniform(min_price, max_price), 2)

    def quantity(self, min_qty: int = 1, max_qty: int = 100) -> int:
        return random.randint(min_qty, max_qty)


class UserProvider(BaseProvider):
    """Provider for user-related test data."""

    user_types = ["customer", "admin", "moderator", "vendor", "support"]
    account_statuses = ["active", "inactive", "suspended", "pending_verification"]

    def username(self) -> str:
        return self.generator.user_name()

    def user_type(self) -> str:
        return self.random_element(self.user_types)

    def account_status(self) -> str:
        return self.random_element(self.account_statuses)

    def avatar_url(self) -> str:
        user_id = random.randint(1, 1000)
        return f"https://api.dicebear.com/7.x/avataaars/svg?seed={user_id}"

    def bio(self, max_length: int = 200) -> str:
        return self.generator.text(max_nb_chars=max_length)


class AddressProvider(BaseProvider):
    """Provider for address-related test data."""

    countries = [
        "United States",
        "Canada",
        "United Kingdom",
        "Germany",
        "France",
        "Australia",
        "Japan",
        "Brazil",
        "India",
        "Mexico",
    ]

    def full_address(self) -> str:
        street = self.generator.street_address()
        city = self.generator.city()
        country = self.random_element(self.countries)
        return f"{street}, {city}, {country}"

    def country(self) -> str:
        return self.random_element(self.countries)


def get_faker(locale: str = "en_US") -> Any:
    """Get a configured Faker instance with custom providers."""
    if not HAS_FAKER:
        raise ImportError("Faker is not installed. Install with: pip install faker")
    fake = Faker(locale)
    fake.add_provider(EcommerceProvider)
    fake.add_provider(UserProvider)
    fake.add_provider(AddressProvider)
    return fake


def create_faker_instance(locale: str = "en_US", seed: int | None = None) -> Any:
    """Create a new Faker instance with optional seed for reproducibility."""
    fake = get_faker(locale)
    if seed is not None:
        Faker.seed(seed)
    return fake
