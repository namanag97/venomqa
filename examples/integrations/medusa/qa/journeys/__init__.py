"""Medusa E-commerce Test Journeys.

Complete user journey definitions for Medusa testing with branching support.

Journeys:
    - checkout_flow: Main checkout journey with payment branching
    - customer_flow: Customer registration and authentication
    - catalog_flow: Product browsing and search
"""

from qa.journeys import checkout_flow

__all__ = [
    "checkout_flow",
]
