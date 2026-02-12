"""E-commerce domain journeys and actions.

Provides journey templates for:
- Full checkout flows with multiple payment methods
- Inventory management and stock tracking
- Payment processing with refunds and cancellations
"""

from venomqa.domains.ecommerce.journeys.checkout import (
    checkout_flow,
    express_checkout_flow,
    guest_checkout_flow,
)
from venomqa.domains.ecommerce.journeys.inventory import (
    inventory_reconciliation_flow,
    inventory_update_flow,
    stock_alert_flow,
)
from venomqa.domains.ecommerce.journeys.payment import (
    payment_failure_flow,
    payment_processing_flow,
    refund_flow,
)

__all__ = [
    "checkout_flow",
    "guest_checkout_flow",
    "express_checkout_flow",
    "inventory_update_flow",
    "stock_alert_flow",
    "inventory_reconciliation_flow",
    "payment_processing_flow",
    "refund_flow",
    "payment_failure_flow",
]
