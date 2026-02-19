"""Medusa Test Fixtures.

Factory-based test data generation for Medusa e-commerce testing.

Fixtures:
    - customer: Customer account fixtures
    - cart: Shopping cart fixtures with items
"""

from qa.fixtures import cart, customer

__all__ = [
    "customer",
    "cart",
]
