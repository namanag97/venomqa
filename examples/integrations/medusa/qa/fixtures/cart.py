"""Cart Fixtures for Medusa E-commerce Testing.

Factory-based test data generation for shopping carts and cart items.

Example:
    >>> from examples.medusa_integration.qa.fixtures.cart import CartFactory, CartItemFactory
    >>>
    >>> # Create a cart with items
    >>> cart = CartFactory.with_items(num_items=3)
    >>>
    >>> # Create a checkout-ready cart context
    >>> context = CartWithItemsFactory.build_context(client)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from venomqa.fixtures.factory import DataFactory, LazyAttribute, LazyFunction

if TYPE_CHECKING:
    from venomqa.client import Client


@dataclass
class MedusaCartItem:
    """Medusa cart line item data model.

    Attributes:
        id: Line item ID.
        cart_id: Parent cart ID.
        variant_id: Product variant ID.
        product_id: Product ID.
        title: Product title.
        description: Item description.
        thumbnail: Thumbnail URL.
        quantity: Item quantity.
        unit_price: Price per unit (in cents).
        subtotal: Line item subtotal (in cents).
        total: Line item total with adjustments (in cents).
    """

    id: str
    cart_id: str
    variant_id: str
    product_id: str
    title: str
    description: str
    thumbnail: str | None
    quantity: int
    unit_price: int
    subtotal: int
    total: int


@dataclass
class MedusaCart:
    """Medusa shopping cart data model.

    Attributes:
        id: Cart ID.
        region_id: Region ID for pricing.
        customer_id: Customer ID (if authenticated).
        email: Customer email.
        items: List of line items.
        shipping_address: Shipping address dict.
        billing_address: Billing address dict.
        shipping_methods: Selected shipping methods.
        payment_session: Current payment session.
        subtotal: Cart subtotal (in cents).
        discount_total: Total discounts (in cents).
        shipping_total: Shipping cost (in cents).
        tax_total: Tax amount (in cents).
        total: Cart total (in cents).
        completed_at: Completion timestamp (null if not completed).
        created_at: Cart creation timestamp.
    """

    id: str
    region_id: str
    customer_id: str | None
    email: str | None
    items: list[MedusaCartItem]
    shipping_address: dict[str, Any] | None
    billing_address: dict[str, Any] | None
    shipping_methods: list[dict[str, Any]]
    payment_session: dict[str, Any] | None
    subtotal: int
    discount_total: int
    shipping_total: int
    tax_total: int
    total: int
    completed_at: datetime | None
    created_at: datetime


class CartItemFactory(DataFactory[MedusaCartItem]):
    """Factory for creating Medusa cart item test data.

    Example:
        >>> item = CartItemFactory.build()
        >>> expensive_item = CartItemFactory.build(unit_price=99999)
    """

    _model = MedusaCartItem

    id: str = LazyFunction(lambda: f"item_{CartItemFactory._get_faker().uuid4()[:12]}")
    cart_id: str = LazyFunction(lambda: f"cart_{CartItemFactory._get_faker().uuid4()[:12]}")
    variant_id: str = LazyFunction(lambda: f"variant_{CartItemFactory._get_faker().uuid4()[:12]}")
    product_id: str = LazyFunction(lambda: f"prod_{CartItemFactory._get_faker().uuid4()[:12]}")
    title: LazyAttribute = LazyAttribute(lambda _: CartItemFactory._get_faker().product_name())
    description: LazyAttribute = LazyAttribute(lambda _: CartItemFactory._get_faker().sentence())
    thumbnail: str | None = None
    quantity: int = 1
    unit_price: int = 2999  # $29.99 in cents
    subtotal: LazyAttribute = LazyAttribute(
        lambda obj: obj.unit_price * obj.quantity if obj else 2999
    )
    total: LazyAttribute = LazyAttribute(lambda obj: obj.subtotal if obj else 2999)

    @classmethod
    def build(cls, **kwargs: Any) -> MedusaCartItem:
        """Build a cart item with calculated subtotal and total."""
        instance = super().build(**kwargs)
        # Recalculate if needed
        if instance.subtotal != instance.unit_price * instance.quantity:
            instance.subtotal = instance.unit_price * instance.quantity
            instance.total = instance.subtotal
        return instance

    @classmethod
    def with_quantity(cls, quantity: int, **kwargs: Any) -> MedusaCartItem:
        """Create item with specific quantity."""
        return cls.build(quantity=quantity, **kwargs)

    @classmethod
    def expensive(cls, **kwargs: Any) -> MedusaCartItem:
        """Create an expensive item ($100+)."""
        return cls.build(unit_price=10000 + cls._get_faker().random_int(0, 50000), **kwargs)

    @classmethod
    def cheap(cls, **kwargs: Any) -> MedusaCartItem:
        """Create a cheap item (under $10)."""
        return cls.build(unit_price=cls._get_faker().random_int(99, 999), **kwargs)


class CartFactory(DataFactory[MedusaCart]):
    """Factory for creating Medusa cart test data.

    Example:
        >>> cart = CartFactory.build()
        >>> cart_with_items = CartFactory.with_items(num_items=3)
    """

    _model = MedusaCart

    id: str = LazyFunction(lambda: f"cart_{CartFactory._get_faker().uuid4()[:12]}")
    region_id: str = "reg_us"  # Default US region
    customer_id: str | None = None
    email: LazyAttribute = LazyAttribute(lambda _: CartFactory._get_faker().email())
    items: list[MedusaCartItem] = field(default_factory=list)
    shipping_address: dict[str, Any] | None = None
    billing_address: dict[str, Any] | None = None
    shipping_methods: list[dict[str, Any]] = field(default_factory=list)
    payment_session: dict[str, Any] | None = None
    subtotal: int = 0
    discount_total: int = 0
    shipping_total: int = 0
    tax_total: int = 0
    total: int = 0
    completed_at: datetime | None = None
    created_at: LazyAttribute = LazyAttribute(
        lambda _: CartFactory._get_faker().date_time_this_year()
    )

    @classmethod
    def with_items(cls, num_items: int = 1, **kwargs: Any) -> MedusaCart:
        """Create a cart with the specified number of items.

        Args:
            num_items: Number of items to add to the cart.
            **kwargs: Additional cart attributes.

        Returns:
            MedusaCart with items and calculated totals.
        """
        cart_id = kwargs.get("id", f"cart_{cls._get_faker().uuid4()[:12]}")
        items = [CartItemFactory.build(cart_id=cart_id) for _ in range(num_items)]

        subtotal = sum(item.total for item in items)
        tax_total = int(subtotal * 0.08)  # 8% tax
        total = subtotal + tax_total

        return cls.build(
            id=cart_id,
            items=items,
            subtotal=subtotal,
            tax_total=tax_total,
            total=total,
            **kwargs,
        )

    @classmethod
    def with_shipping(cls, **kwargs: Any) -> MedusaCart:
        """Create a cart with shipping address and method."""
        faker = cls._get_faker()
        shipping_address = {
            "first_name": faker.first_name(),
            "last_name": faker.last_name(),
            "address_1": faker.street_address(),
            "city": faker.city(),
            "province": faker.state_abbr(),
            "postal_code": faker.zipcode(),
            "country_code": "us",
            "phone": faker.phone_number(),
        }
        shipping_methods = [
            {
                "id": f"sm_{faker.uuid4()[:8]}",
                "shipping_option_id": "so_standard",
                "price": 500,  # $5.00
            }
        ]
        return cls.build(
            shipping_address=shipping_address,
            billing_address=shipping_address,
            shipping_methods=shipping_methods,
            shipping_total=500,
            **kwargs,
        )

    @classmethod
    def checkout_ready(cls, **kwargs: Any) -> MedusaCart:
        """Create a cart ready for checkout with items, shipping, and payment."""
        cart = cls.with_items(num_items=2, **kwargs)
        faker = cls._get_faker()

        # Add shipping
        shipping_address = {
            "first_name": faker.first_name(),
            "last_name": faker.last_name(),
            "address_1": faker.street_address(),
            "city": faker.city(),
            "province": faker.state_abbr(),
            "postal_code": faker.zipcode(),
            "country_code": "us",
            "phone": faker.phone_number(),
        }
        cart.shipping_address = shipping_address
        cart.billing_address = shipping_address
        cart.shipping_methods = [
            {
                "id": f"sm_{faker.uuid4()[:8]}",
                "shipping_option_id": "so_standard",
                "price": 500,
            }
        ]
        cart.shipping_total = 500

        # Add payment session
        cart.payment_session = {
            "id": f"ps_{faker.uuid4()[:8]}",
            "provider_id": "pp_system_default",
            "status": "pending",
        }

        # Recalculate total
        cart.total = cart.subtotal + cart.tax_total + cart.shipping_total - cart.discount_total

        return cart


class CartWithItemsFactory:
    """Factory for creating complete cart contexts for testing.

    Creates execution contexts with carts, items, and all necessary
    data for testing checkout flows.

    Example:
        >>> context = CartWithItemsFactory.build_context(client)
        >>> # context has cart_id, cart_items, product_variant_id, etc.
    """

    @classmethod
    def build_context(
        cls,
        client: Client | None = None,
        region_id: str | None = None,
        publishable_api_key: str | None = None,
        num_items: int = 1,
        include_shipping: bool = True,
        customer_email: str | None = None,
    ) -> dict[str, Any]:
        """Build an execution context with a cart containing items.

        Args:
            client: VenomQA HTTP client (optional, for actual cart creation).
            region_id: Medusa region ID.
            publishable_api_key: Medusa publishable API key.
            num_items: Number of items to add.
            include_shipping: Whether to include shipping address.
            customer_email: Customer email for the cart.

        Returns:
            Context dict with cart setup.
        """
        cart = CartFactory.with_items(num_items=num_items)
        faker = CartFactory._get_faker()

        context: dict[str, Any] = {
            # Cart data
            "cart_id": cart.id,
            "cart": CartFactory.to_dict(cart),
            "cart_items": [CartItemFactory.to_dict(item) for item in cart.items],
            "cart_total": cart.total,
            "cart_subtotal": cart.subtotal,
            "cart_item_count": len(cart.items),
            # Email
            "customer_email": customer_email or cart.email,
        }

        # Add variant IDs from items
        if cart.items:
            context["product_variant_id"] = cart.items[0].variant_id
            context["first_variant_id"] = cart.items[0].variant_id
            context["product_id"] = cart.items[0].product_id

        # Add shipping address if requested
        if include_shipping:
            shipping_address = {
                "first_name": faker.first_name(),
                "last_name": faker.last_name(),
                "address_1": faker.street_address(),
                "city": faker.city(),
                "province": faker.state_abbr(),
                "postal_code": faker.zipcode(),
                "country_code": "us",
                "phone": faker.phone_number(),
            }
            context["shipping_address"] = shipping_address
            context["billing_address"] = shipping_address

        # Add Medusa configuration
        if region_id:
            context["region_id"] = region_id
        if publishable_api_key:
            context["publishable_api_key"] = publishable_api_key

        # If client provided, actually create the cart
        if client is not None:
            from qa.actions.cart import add_line_item, create_cart
            from qa.actions.products import list_products

            # Get real products first
            list_products(client, context)

            # Create real cart
            create_cart(client, context)

            # Add items
            for _ in range(num_items):
                add_line_item(client, context)

        return context

    @classmethod
    def checkout_ready_context(
        cls,
        client: Client | None = None,
        region_id: str | None = None,
        publishable_api_key: str | None = None,
    ) -> dict[str, Any]:
        """Build a context ready for checkout completion.

        Args:
            client: VenomQA HTTP client.
            region_id: Medusa region ID.
            publishable_api_key: Medusa publishable API key.

        Returns:
            Context dict with cart ready for payment.
        """
        context = cls.build_context(
            client=client,
            region_id=region_id,
            publishable_api_key=publishable_api_key,
            num_items=2,
            include_shipping=True,
        )

        # If client provided, set up shipping and payment
        if client is not None:
            from qa.actions.cart import (
                add_shipping_method,
                update_cart,
            )
            from qa.actions.checkout import create_payment_session
            from qa.actions.products import get_shipping_options

            # Update cart with addresses
            update_cart(
                client,
                context,
                email=context.get("customer_email"),
                shipping_address=context.get("shipping_address"),
                billing_address=context.get("billing_address"),
            )

            # Get and add shipping method
            get_shipping_options(client, context)
            add_shipping_method(client, context)

            # Create payment session
            create_payment_session(client, context)

        return context


def calculate_cart_total(items: list[dict[str, Any]]) -> dict[str, int]:
    """Calculate cart totals from items.

    Helper function for invariant testing.

    Args:
        items: List of cart item dicts with quantity and unit_price.

    Returns:
        Dict with subtotal, tax_total, and total (in cents).
    """
    subtotal = sum(item.get("unit_price", 0) * item.get("quantity", 0) for item in items)
    tax_total = int(subtotal * 0.08)  # 8% tax
    total = subtotal + tax_total

    return {
        "subtotal": subtotal,
        "tax_total": tax_total,
        "total": total,
    }


def verify_cart_total_invariant(cart: dict[str, Any]) -> tuple[bool, str]:
    """Verify that cart total equals sum of line items.

    Invariant check for cart consistency.

    Args:
        cart: Cart dict with items and total.

    Returns:
        Tuple of (passed, message).
    """
    items = cart.get("items", [])
    if not items:
        return True, "Cart has no items"

    calculated = calculate_cart_total(items)
    actual_subtotal = cart.get("subtotal", 0)

    # Allow small rounding differences
    if abs(calculated["subtotal"] - actual_subtotal) <= 1:
        return True, f"Cart subtotal matches: {actual_subtotal}"
    else:
        return False, (
            f"Cart subtotal mismatch: expected {calculated['subtotal']}, "
            f"got {actual_subtotal}"
        )
