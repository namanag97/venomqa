"""VenomQA Test Suite for Medusa E-commerce.

This module provides comprehensive QA testing for Medusa JS e-commerce platform.

Features:
    - Customer authentication and registration
    - Product catalog browsing
    - Shopping cart management
    - Checkout with multiple payment methods
    - Order management and tracking

Example:
    >>> from venomqa import Client, JourneyRunner
    >>> from qa.journeys.checkout_flow import checkout_journey
    >>>
    >>> client = Client(base_url="http://localhost:9000")
    >>> runner = JourneyRunner(client=client)
    >>> result = runner.run(checkout_journey)
    >>> print(f"Journey passed: {result.success}")
"""

# Imports are available when running from the medusa-integration directory
# Use: from qa.actions import auth, cart, etc.

__all__ = [
    "actions",
    "fixtures",
    "journeys",
]
