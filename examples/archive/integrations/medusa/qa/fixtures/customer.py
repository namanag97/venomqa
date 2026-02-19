"""Customer Fixtures for Medusa E-commerce Testing.

Factory-based test data generation for customer accounts and authentication.

Example:
    >>> from examples.medusa_integration.qa.fixtures.customer import CustomerFactory
    >>>
    >>> # Create a test customer
    >>> customer = CustomerFactory.build()
    >>> print(customer.email)
    >>>
    >>> # Create an authenticated customer context
    >>> context = AuthenticatedCustomerFactory.build_context()
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from venomqa.fixtures.factory import DataFactory, LazyAttribute, LazyFunction

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.core.context import ExecutionContext


@dataclass
class MedusaCustomer:
    """Medusa customer data model.

    Attributes:
        id: Customer ID.
        email: Customer email address.
        first_name: Customer first name.
        last_name: Customer last name.
        phone: Customer phone number.
        has_account: Whether customer has an account.
        created_at: Account creation timestamp.
        metadata: Custom metadata.
    """

    id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None
    has_account: bool
    created_at: datetime
    metadata: dict[str, Any]


@dataclass
class MedusaAddress:
    """Medusa address data model.

    Attributes:
        id: Address ID.
        customer_id: Associated customer ID.
        first_name: First name.
        last_name: Last name.
        address_1: Address line 1.
        address_2: Address line 2 (optional).
        city: City.
        province: State/province.
        postal_code: Postal/zip code.
        country_code: ISO country code.
        phone: Phone number.
        is_default_shipping: Whether this is default shipping address.
        is_default_billing: Whether this is default billing address.
    """

    id: str
    customer_id: str
    first_name: str
    last_name: str
    address_1: str
    address_2: str | None
    city: str
    province: str
    postal_code: str
    country_code: str
    phone: str | None
    is_default_shipping: bool
    is_default_billing: bool


class CustomerFactory(DataFactory[MedusaCustomer]):
    """Factory for creating Medusa customer test data.

    Example:
        >>> customer = CustomerFactory.build()
        >>> customer_dict = CustomerFactory.to_dict(customer)
    """

    _model = MedusaCustomer

    id: str = LazyFunction(lambda: f"cus_{CustomerFactory._get_faker().uuid4()[:12]}")
    email: LazyAttribute = LazyAttribute(lambda _: CustomerFactory._get_faker().email())
    first_name: LazyAttribute = LazyAttribute(lambda _: CustomerFactory._get_faker().first_name())
    last_name: LazyAttribute = LazyAttribute(lambda _: CustomerFactory._get_faker().last_name())
    phone: LazyAttribute = LazyAttribute(lambda _: CustomerFactory._get_faker().phone_number())
    has_account: bool = True
    created_at: LazyAttribute = LazyAttribute(
        lambda _: CustomerFactory._get_faker().date_time_this_year()
    )
    metadata: dict = {}

    @classmethod
    def guest(cls, **kwargs: Any) -> MedusaCustomer:
        """Create a guest customer (no account)."""
        return cls.build(has_account=False, **kwargs)

    @classmethod
    def with_email(cls, email: str, **kwargs: Any) -> MedusaCustomer:
        """Create a customer with specific email."""
        return cls.build(email=email, **kwargs)


class AddressFactory(DataFactory[MedusaAddress]):
    """Factory for creating Medusa address test data.

    Example:
        >>> address = AddressFactory.build()
        >>> us_address = AddressFactory.us_address()
    """

    _model = MedusaAddress

    id: str = LazyFunction(lambda: f"addr_{AddressFactory._get_faker().uuid4()[:12]}")
    customer_id: str = LazyFunction(lambda: f"cus_{AddressFactory._get_faker().uuid4()[:12]}")
    first_name: LazyAttribute = LazyAttribute(lambda _: AddressFactory._get_faker().first_name())
    last_name: LazyAttribute = LazyAttribute(lambda _: AddressFactory._get_faker().last_name())
    address_1: LazyAttribute = LazyAttribute(
        lambda _: AddressFactory._get_faker().street_address()
    )
    address_2: str | None = None
    city: LazyAttribute = LazyAttribute(lambda _: AddressFactory._get_faker().city())
    province: LazyAttribute = LazyAttribute(lambda _: AddressFactory._get_faker().state_abbr())
    postal_code: LazyAttribute = LazyAttribute(lambda _: AddressFactory._get_faker().postcode())
    country_code: str = "us"
    phone: LazyAttribute = LazyAttribute(lambda _: AddressFactory._get_faker().phone_number())
    is_default_shipping: bool = True
    is_default_billing: bool = True

    @classmethod
    def us_address(cls, **kwargs: Any) -> MedusaAddress:
        """Create a US address."""
        return cls.build(
            country_code="us",
            province=cls._get_faker().state_abbr(),
            postal_code=cls._get_faker().zipcode(),
            **kwargs,
        )

    @classmethod
    def eu_address(cls, **kwargs: Any) -> MedusaAddress:
        """Create a European address (Germany)."""
        return cls.build(
            country_code="de",
            province="Bayern",
            postal_code=cls._get_faker().postcode(),
            city=cls._get_faker().city(),
            **kwargs,
        )

    @classmethod
    def shipping_only(cls, **kwargs: Any) -> MedusaAddress:
        """Create a shipping-only address."""
        return cls.build(
            is_default_shipping=True,
            is_default_billing=False,
            **kwargs,
        )

    @classmethod
    def billing_only(cls, **kwargs: Any) -> MedusaAddress:
        """Create a billing-only address."""
        return cls.build(
            is_default_shipping=False,
            is_default_billing=True,
            **kwargs,
        )


class AuthenticatedCustomerFactory:
    """Factory for creating authenticated customer contexts.

    Creates a full execution context with customer authentication,
    ready for testing authenticated flows.

    Example:
        >>> context = AuthenticatedCustomerFactory.build_context(
        ...     client=client,
        ...     email="test@example.com"
        ... )
        >>> # context now has customer_token, customer_id, etc.
    """

    @classmethod
    def build_context(
        cls,
        client: Client | None = None,
        email: str | None = None,
        password: str = "testpassword123",
        region_id: str | None = None,
        publishable_api_key: str | None = None,
    ) -> dict[str, Any]:
        """Build an execution context with authenticated customer.

        Args:
            client: VenomQA HTTP client (optional, for actual auth).
            email: Customer email (generated if not provided).
            password: Customer password.
            region_id: Medusa region ID.
            publishable_api_key: Medusa publishable API key.

        Returns:
            Context dict with customer authentication setup.
        """
        customer = CustomerFactory.build(email=email) if email else CustomerFactory.build()
        address = AddressFactory.us_address(customer_id=customer.id)

        context: dict[str, Any] = {
            # Customer data
            "customer_email": customer.email,
            "customer_password": password,
            "customer_id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "customer_phone": customer.phone,
            # Address data
            "shipping_address": {
                "first_name": address.first_name,
                "last_name": address.last_name,
                "address_1": address.address_1,
                "address_2": address.address_2,
                "city": address.city,
                "province": address.province,
                "postal_code": address.postal_code,
                "country_code": address.country_code,
                "phone": address.phone,
            },
            "billing_address": {
                "first_name": address.first_name,
                "last_name": address.last_name,
                "address_1": address.address_1,
                "address_2": address.address_2,
                "city": address.city,
                "province": address.province,
                "postal_code": address.postal_code,
                "country_code": address.country_code,
                "phone": address.phone,
            },
        }

        # Add optional Medusa configuration
        if region_id:
            context["region_id"] = region_id
        if publishable_api_key:
            context["publishable_api_key"] = publishable_api_key

        # If client provided, actually authenticate
        if client is not None:
            from qa.actions.auth import register

            register(
                client,
                context,
                email=customer.email,
                password=password,
                first_name=customer.first_name,
                last_name=customer.last_name,
            )

        return context

    @classmethod
    def guest_context(
        cls,
        email: str | None = None,
        region_id: str | None = None,
        publishable_api_key: str | None = None,
    ) -> dict[str, Any]:
        """Build a guest (unauthenticated) context.

        Args:
            email: Guest email (generated if not provided).
            region_id: Medusa region ID.
            publishable_api_key: Medusa publishable API key.

        Returns:
            Context dict for guest checkout.
        """
        customer = CustomerFactory.guest(email=email) if email else CustomerFactory.guest()
        address = AddressFactory.us_address()

        context: dict[str, Any] = {
            # Guest data
            "customer_email": customer.email,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            # Address data
            "shipping_address": {
                "first_name": address.first_name,
                "last_name": address.last_name,
                "address_1": address.address_1,
                "city": address.city,
                "province": address.province,
                "postal_code": address.postal_code,
                "country_code": address.country_code,
                "phone": address.phone,
            },
            "billing_address": {
                "first_name": address.first_name,
                "last_name": address.last_name,
                "address_1": address.address_1,
                "city": address.city,
                "province": address.province,
                "postal_code": address.postal_code,
                "country_code": address.country_code,
                "phone": address.phone,
            },
        }

        if region_id:
            context["region_id"] = region_id
        if publishable_api_key:
            context["publishable_api_key"] = publishable_api_key

        return context
