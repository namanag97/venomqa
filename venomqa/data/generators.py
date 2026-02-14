"""Data generators using Faker for realistic test data.

This module provides a comprehensive set of data generators for creating
realistic test data using the Faker library. It supports localization,
seeded generation for reproducibility, and pre-built generators for
common domains like e-commerce, users, and content.

Example:
    >>> from venomqa.data import fake
    >>>
    >>> # Generate user data
    >>> email = fake.email()
    >>> name = fake.name()
    >>> password = fake.password()
    >>>
    >>> # Use with fixtures
    >>> customer = {
    ...     "email": fake.email(),
    ...     "name": fake.name(),
    ...     "password": fake.password(),
    ... }

    >>> # Seeded generation for reproducibility
    >>> from venomqa.data import FakeDataGenerator
    >>> fake = FakeDataGenerator(seed=12345)
    >>> email1 = fake.email()
    >>>
    >>> # Reset to get same data
    >>> fake.reset_seed()
    >>> email2 = fake.email()
    >>> assert email1 == email2
"""

from __future__ import annotations

import hashlib
import random
import re
import string
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterator, TypeVar

from faker import Faker
from faker.providers import BaseProvider

T = TypeVar("T")


class EcommerceDataProvider(BaseProvider):
    """Provider for e-commerce related test data."""

    product_categories = [
        "Electronics",
        "Clothing",
        "Books",
        "Home & Garden",
        "Sports & Outdoors",
        "Toys & Games",
        "Food & Grocery",
        "Health & Beauty",
        "Automotive",
        "Office Supplies",
        "Pet Supplies",
        "Jewelry",
        "Music & Instruments",
        "Software",
        "Video Games",
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
        "Portable",
        "Wireless",
        "Smart",
        "Eco-Friendly",
        "Vintage",
        "Modern",
        "Classic",
        "Ultra",
        "Mini",
        "Pro",
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
        "Station",
        "Hub",
        "Adapter",
        "Controller",
        "Monitor",
        "Scanner",
        "Printer",
        "Speaker",
        "Camera",
        "Sensor",
    ]

    order_statuses = [
        "pending",
        "confirmed",
        "processing",
        "shipped",
        "out_for_delivery",
        "delivered",
        "cancelled",
        "refunded",
        "returned",
        "on_hold",
    ]

    payment_methods = [
        "credit_card",
        "debit_card",
        "paypal",
        "bank_transfer",
        "crypto",
        "cash_on_delivery",
        "apple_pay",
        "google_pay",
        "affirm",
        "klarna",
    ]

    shipping_methods = [
        "standard",
        "express",
        "overnight",
        "same_day",
        "economy",
        "freight",
        "pickup",
    ]

    currency_codes = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "CNY", "INR", "BRL"]

    def product_name(self) -> str:
        """Generate a realistic product name."""
        adj = self.random_element(self.product_adjectives)
        noun = self.random_element(self.product_nouns)
        return f"{adj} {noun}"

    def product_title(self, brand: str | None = None) -> str:
        """Generate a full product title with optional brand."""
        brand = brand or self.generator.company()
        name = self.product_name()
        model = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"{brand} {name} {model}"

    def product_description(self, sentences: int = 3) -> str:
        """Generate a product description."""
        return self.generator.paragraph(nb_sentences=sentences)

    def product_category(self) -> str:
        """Generate a product category."""
        return self.random_element(self.product_categories)

    def product_subcategory(self, category: str | None = None) -> str:
        """Generate a product subcategory."""
        category = category or self.product_category()
        subcategories = {
            "Electronics": ["Smartphones", "Laptops", "Tablets", "Accessories", "Audio"],
            "Clothing": ["Men's", "Women's", "Kids", "Shoes", "Accessories"],
            "Books": ["Fiction", "Non-Fiction", "Technical", "Children's", "Comics"],
        }
        subs = subcategories.get(category, ["General", "Popular", "Trending"])
        return self.random_element(subs)

    def sku(self, prefix: str | None = None) -> str:
        """Generate a product SKU."""
        prefix = prefix or "".join(random.choices(string.ascii_uppercase, k=3))
        suffix = "".join(random.choices(string.digits, k=6))
        return f"{prefix}-{suffix}"

    def upc(self) -> str:
        """Generate a UPC barcode."""
        return "".join(random.choices(string.digits, k=12))

    def ean(self) -> str:
        """Generate an EAN-13 barcode."""
        return "".join(random.choices(string.digits, k=13))

    def price(
        self,
        min_price: float = 1.0,
        max_price: float = 1000.0,
        decimals: int = 2,
    ) -> float:
        """Generate a product price."""
        price = random.uniform(min_price, max_price)
        return round(price, decimals)

    def price_decimal(
        self,
        min_price: float = 1.0,
        max_price: float = 1000.0,
    ) -> Decimal:
        """Generate a product price as Decimal."""
        price = self.price(min_price, max_price)
        return Decimal(str(price))

    def discount_percent(self, max_discount: int = 50) -> int:
        """Generate a discount percentage."""
        return random.randint(5, max_discount)

    def quantity(self, min_qty: int = 1, max_qty: int = 100) -> int:
        """Generate a quantity."""
        return random.randint(min_qty, max_qty)

    def stock_quantity(self) -> int:
        """Generate a stock quantity."""
        return random.randint(0, 1000)

    def order_status(self) -> str:
        """Generate an order status."""
        return self.random_element(self.order_statuses)

    def order_number(self, prefix: str = "ORD") -> str:
        """Generate an order number."""
        timestamp = datetime.now().strftime("%Y%m%d")
        sequence = "".join(random.choices(string.digits, k=6))
        return f"{prefix}-{timestamp}-{sequence}"

    def invoice_number(self, prefix: str = "INV") -> str:
        """Generate an invoice number."""
        year = datetime.now().year
        sequence = "".join(random.choices(string.digits, k=8))
        return f"{prefix}-{year}-{sequence}"

    def tracking_number(self, carrier: str = "USPS") -> str:
        """Generate a tracking number."""
        carriers = {
            "USPS": lambda: "".join(random.choices(string.digits, k=22)),
            "UPS": lambda: "1Z" + "".join(random.choices(string.ascii_uppercase + string.digits, k=16)),
            "FEDEX": lambda: "".join(random.choices(string.digits, k=15)),
            "DHL": lambda: "".join(random.choices(string.digits, k=10)),
        }
        generator = carriers.get(carrier.upper(), carriers["USPS"])
        return generator()

    def payment_method(self) -> str:
        """Generate a payment method."""
        return self.random_element(self.payment_methods)

    def shipping_method(self) -> str:
        """Generate a shipping method."""
        return self.random_element(self.shipping_methods)

    def currency_code(self) -> str:
        """Generate a currency code."""
        return self.random_element(self.currency_codes)

    def coupon_code(self, length: int = 8) -> str:
        """Generate a coupon code."""
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

    def weight(self, min_weight: float = 0.1, max_weight: float = 50.0, unit: str = "kg") -> dict:
        """Generate product weight."""
        value = round(random.uniform(min_weight, max_weight), 2)
        return {"value": value, "unit": unit}

    def dimensions(self, unit: str = "cm") -> dict:
        """Generate product dimensions."""
        return {
            "length": round(random.uniform(1, 100), 1),
            "width": round(random.uniform(1, 100), 1),
            "height": round(random.uniform(1, 100), 1),
            "unit": unit,
        }


class PaymentDataProvider(BaseProvider):
    """Provider for payment-related test data."""

    # Test card numbers that won't charge real money
    test_card_numbers = {
        "visa": ["4111111111111111", "4012888888881881", "4222222222222"],
        "mastercard": ["5555555555554444", "5105105105105100"],
        "amex": ["378282246310005", "371449635398431"],
        "discover": ["6011111111111117", "6011000990139424"],
        "diners": ["30569309025904", "38520000023237"],
        "jcb": ["3530111333300000", "3566002020360505"],
    }

    def test_card_number(self, card_type: str = "visa") -> str:
        """Generate a test card number."""
        cards = self.test_card_numbers.get(card_type.lower(), self.test_card_numbers["visa"])
        return self.random_element(cards)

    def card_number_masked(self, card_type: str = "visa") -> str:
        """Generate a masked card number (last 4 digits visible)."""
        full_number = self.test_card_number(card_type)
        return f"****-****-****-{full_number[-4:]}"

    def card_expiry(self, min_years: int = 1, max_years: int = 5) -> str:
        """Generate a card expiry date (MM/YY)."""
        today = date.today()
        years_ahead = random.randint(min_years, max_years)
        month = random.randint(1, 12)
        year = (today.year + years_ahead) % 100
        return f"{month:02d}/{year:02d}"

    def card_expiry_date(self, min_years: int = 1, max_years: int = 5) -> date:
        """Generate a card expiry date as a date object."""
        today = date.today()
        years_ahead = random.randint(min_years, max_years)
        month = random.randint(1, 12)
        year = today.year + years_ahead
        # Use last day of month
        if month == 12:
            return date(year + 1, 1, 1) - timedelta(days=1)
        return date(year, month + 1, 1) - timedelta(days=1)

    def cvv(self, length: int = 3) -> str:
        """Generate a CVV/CVC code."""
        return "".join(random.choices(string.digits, k=length))

    def card_holder_name(self) -> str:
        """Generate a card holder name."""
        return self.generator.name().upper()

    def bank_account_number(self, length: int = 10) -> str:
        """Generate a bank account number."""
        return "".join(random.choices(string.digits, k=length))

    def routing_number(self) -> str:
        """Generate a bank routing number."""
        return "".join(random.choices(string.digits, k=9))

    def iban(self, country_code: str = "DE") -> str:
        """Generate an IBAN."""
        check_digits = "".join(random.choices(string.digits, k=2))
        bban = "".join(random.choices(string.digits, k=18))
        return f"{country_code}{check_digits}{bban}"

    def swift_code(self) -> str:
        """Generate a SWIFT/BIC code."""
        bank_code = "".join(random.choices(string.ascii_uppercase, k=4))
        country_code = "".join(random.choices(string.ascii_uppercase, k=2))
        location_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=2))
        branch_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
        return f"{bank_code}{country_code}{location_code}{branch_code}"

    def transaction_id(self, prefix: str = "txn") -> str:
        """Generate a transaction ID."""
        return f"{prefix}_{uuid.uuid4().hex}"

    def payment_reference(self) -> str:
        """Generate a payment reference."""
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=16))


class UserDataProvider(BaseProvider):
    """Provider for user-related test data."""

    user_types = ["customer", "admin", "moderator", "vendor", "support", "guest"]
    account_statuses = ["active", "inactive", "suspended", "pending_verification", "deleted"]
    subscription_plans = ["free", "basic", "pro", "enterprise", "custom"]
    roles = ["viewer", "editor", "admin", "owner", "contributor", "reviewer"]

    def user_type(self) -> str:
        """Generate a user type."""
        return self.random_element(self.user_types)

    def account_status(self) -> str:
        """Generate an account status."""
        return self.random_element(self.account_statuses)

    def subscription_plan(self) -> str:
        """Generate a subscription plan."""
        return self.random_element(self.subscription_plans)

    def role(self) -> str:
        """Generate a user role."""
        return self.random_element(self.roles)

    def avatar_url(self, style: str = "avataaars") -> str:
        """Generate an avatar URL using DiceBear."""
        seed = self.generator.uuid4()
        return f"https://api.dicebear.com/7.x/{style}/svg?seed={seed}"

    def profile_picture_url(self) -> str:
        """Generate a profile picture URL."""
        user_id = random.randint(1, 1000)
        return f"https://picsum.photos/seed/{user_id}/200/200"

    def bio(self, max_length: int = 200) -> str:
        """Generate a user bio."""
        return self.generator.text(max_nb_chars=max_length)

    def tagline(self) -> str:
        """Generate a user tagline."""
        return self.generator.sentence(nb_words=6).rstrip(".")

    def website_url(self) -> str:
        """Generate a personal website URL."""
        username = self.generator.user_name()
        domains = ["dev", "io", "me", "com", "net"]
        domain = self.random_element(domains)
        return f"https://{username}.{domain}"

    def social_handle(self, platform: str = "twitter") -> str:
        """Generate a social media handle."""
        username = self.generator.user_name()
        return f"@{username}"

    def password(
        self,
        length: int = 16,
        include_special: bool = True,
        include_numbers: bool = True,
        include_uppercase: bool = True,
    ) -> str:
        """Generate a secure password."""
        chars = string.ascii_lowercase
        if include_uppercase:
            chars += string.ascii_uppercase
        if include_numbers:
            chars += string.digits
        if include_special:
            chars += "!@#$%^&*()_+-="

        # Ensure at least one of each required character type
        password_chars = []
        if include_uppercase:
            password_chars.append(random.choice(string.ascii_uppercase))
        if include_numbers:
            password_chars.append(random.choice(string.digits))
        if include_special:
            password_chars.append(random.choice("!@#$%^&*()_+-="))
        password_chars.append(random.choice(string.ascii_lowercase))

        # Fill remaining length
        remaining = length - len(password_chars)
        password_chars.extend(random.choices(chars, k=remaining))

        # Shuffle
        random.shuffle(password_chars)
        return "".join(password_chars)

    def password_hash(self, password: str | None = None) -> str:
        """Generate a password hash (SHA-256, for testing only)."""
        if password is None:
            password = self.password()
        return hashlib.sha256(password.encode()).hexdigest()

    def api_key(self, prefix: str = "vqa") -> str:
        """Generate an API key."""
        key = uuid.uuid4().hex + uuid.uuid4().hex
        return f"{prefix}_{key}"

    def auth_token(self) -> str:
        """Generate an authentication token."""
        return uuid.uuid4().hex + uuid.uuid4().hex

    def session_id(self) -> str:
        """Generate a session ID."""
        return uuid.uuid4().hex

    def verification_code(self, length: int = 6) -> str:
        """Generate a verification code."""
        return "".join(random.choices(string.digits, k=length))

    def otp(self) -> str:
        """Generate a one-time password."""
        return self.verification_code(6)

    def referral_code(self, length: int = 8) -> str:
        """Generate a referral code."""
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


class ContentDataProvider(BaseProvider):
    """Provider for content-related test data."""

    content_types = ["article", "blog_post", "news", "tutorial", "review", "guide"]
    content_statuses = ["draft", "pending_review", "published", "archived", "deleted"]
    comment_statuses = ["pending", "approved", "spam", "deleted"]

    def article_title(self) -> str:
        """Generate an article title."""
        return self.generator.sentence(nb_words=random.randint(5, 10)).rstrip(".")

    def article_slug(self, title: str | None = None) -> str:
        """Generate a URL slug from a title."""
        if title is None:
            title = self.article_title()
        slug = title.lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)
        return slug.strip("-")

    def article_excerpt(self, length: int = 200) -> str:
        """Generate an article excerpt."""
        return self.generator.text(max_nb_chars=length)

    def article_body(self, paragraphs: int = 5) -> str:
        """Generate an article body."""
        return "\n\n".join(self.generator.paragraphs(nb=paragraphs))

    def article_body_html(self, paragraphs: int = 5) -> str:
        """Generate an article body in HTML format."""
        paras = self.generator.paragraphs(nb=paragraphs)
        return "".join(f"<p>{p}</p>\n" for p in paras)

    def article_body_markdown(self, sections: int = 3) -> str:
        """Generate an article body in Markdown format."""
        content = []
        for i in range(sections):
            heading = self.generator.sentence(nb_words=4).rstrip(".")
            content.append(f"## {heading}\n")
            content.append(self.generator.paragraph(nb_sentences=5) + "\n")
            if random.random() > 0.5:
                items = [f"- {self.generator.sentence()}" for _ in range(3)]
                content.append("\n".join(items) + "\n")
        return "\n".join(content)

    def content_type(self) -> str:
        """Generate a content type."""
        return self.random_element(self.content_types)

    def content_status(self) -> str:
        """Generate a content status."""
        return self.random_element(self.content_statuses)

    def comment(self, max_length: int = 500) -> str:
        """Generate a comment."""
        return self.generator.text(max_nb_chars=max_length)

    def comment_status(self) -> str:
        """Generate a comment status."""
        return self.random_element(self.comment_statuses)

    def tag(self) -> str:
        """Generate a tag."""
        return self.generator.word()

    def tags(self, count: int = 5) -> list[str]:
        """Generate a list of tags."""
        return [self.generator.word() for _ in range(count)]

    def category(self) -> str:
        """Generate a category name."""
        categories = [
            "Technology",
            "Business",
            "Lifestyle",
            "Health",
            "Travel",
            "Food",
            "Entertainment",
            "Sports",
            "Science",
            "Education",
        ]
        return self.random_element(categories)

    def image_url(self, width: int = 800, height: int = 600) -> str:
        """Generate an image URL."""
        seed = random.randint(1, 10000)
        return f"https://picsum.photos/seed/{seed}/{width}/{height}"

    def thumbnail_url(self) -> str:
        """Generate a thumbnail URL."""
        return self.image_url(150, 150)

    def featured_image_url(self) -> str:
        """Generate a featured image URL."""
        return self.image_url(1200, 630)

    def video_url(self) -> str:
        """Generate a video URL (YouTube-like)."""
        video_id = "".join(random.choices(string.ascii_letters + string.digits, k=11))
        return f"https://www.youtube.com/watch?v={video_id}"

    def reading_time(self, word_count: int | None = None) -> int:
        """Calculate reading time in minutes."""
        if word_count is None:
            word_count = random.randint(500, 5000)
        return max(1, word_count // 200)


class AddressDataProvider(BaseProvider):
    """Provider for address-related test data."""

    countries = [
        ("US", "United States"),
        ("CA", "Canada"),
        ("GB", "United Kingdom"),
        ("DE", "Germany"),
        ("FR", "France"),
        ("AU", "Australia"),
        ("JP", "Japan"),
        ("BR", "Brazil"),
        ("IN", "India"),
        ("MX", "Mexico"),
    ]

    address_types = ["home", "work", "billing", "shipping", "other"]

    def full_address(self) -> str:
        """Generate a full address string."""
        street = self.generator.street_address()
        city = self.generator.city()
        state = self.generator.state_abbr() if hasattr(self.generator, "state_abbr") else ""
        zipcode = self.generator.postcode()
        country = self.country_name()
        if state:
            return f"{street}, {city}, {state} {zipcode}, {country}"
        return f"{street}, {city} {zipcode}, {country}"

    def address_dict(self) -> dict:
        """Generate an address as a dictionary."""
        return {
            "street1": self.generator.street_address(),
            "street2": self.generator.secondary_address() if random.random() > 0.7 else None,
            "city": self.generator.city(),
            "state": self.generator.state() if hasattr(self.generator, "state") else None,
            "postal_code": self.generator.postcode(),
            "country": self.country_name(),
            "country_code": self.country_code(),
        }

    def shipping_address(self) -> dict:
        """Generate a shipping address."""
        addr = self.address_dict()
        addr["type"] = "shipping"
        addr["recipient_name"] = self.generator.name()
        addr["phone"] = self.generator.phone_number()
        return addr

    def billing_address(self) -> dict:
        """Generate a billing address."""
        addr = self.address_dict()
        addr["type"] = "billing"
        return addr

    def country_code(self) -> str:
        """Generate a country code."""
        code, _ = self.random_element(self.countries)
        return code

    def country_name(self) -> str:
        """Generate a country name."""
        _, name = self.random_element(self.countries)
        return name

    def address_type(self) -> str:
        """Generate an address type."""
        return self.random_element(self.address_types)

    def latitude(self) -> float:
        """Generate a latitude coordinate."""
        return round(random.uniform(-90, 90), 6)

    def longitude(self) -> float:
        """Generate a longitude coordinate."""
        return round(random.uniform(-180, 180), 6)

    def coordinates(self) -> tuple[float, float]:
        """Generate latitude and longitude coordinates."""
        return (self.latitude(), self.longitude())

    def geo_point(self) -> dict:
        """Generate a GeoJSON point."""
        return {
            "type": "Point",
            "coordinates": [self.longitude(), self.latitude()],
        }


@dataclass
class FakeDataGenerator:
    """Main data generator with Faker integration and seed support.

    This class provides a convenient interface for generating fake test data
    with support for localization, seeded generation, and custom providers.

    Example:
        >>> fake = FakeDataGenerator(locale="en_US", seed=12345)
        >>>
        >>> # Generate user data
        >>> user = fake.user()
        >>> print(user["email"])
        >>>
        >>> # Generate product data
        >>> product = fake.product()
        >>> print(product["title"])
        >>>
        >>> # Use with different locale
        >>> fake_de = fake.with_locale("de_DE")
        >>> german_name = fake_de.name()
    """

    locale: str = "en_US"
    seed: int | None = None
    _faker: Faker = field(init=False, repr=False)
    _original_seed: int | None = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the Faker instance with providers."""
        self._original_seed = self.seed
        self._faker = Faker(self.locale)
        self._faker.add_provider(EcommerceDataProvider)
        self._faker.add_provider(PaymentDataProvider)
        self._faker.add_provider(UserDataProvider)
        self._faker.add_provider(ContentDataProvider)
        self._faker.add_provider(AddressDataProvider)
        if self.seed is not None:
            Faker.seed(self.seed)
            random.seed(self.seed)

    def reset_seed(self) -> None:
        """Reset to the original seed for reproducible generation."""
        if self._original_seed is not None:
            Faker.seed(self._original_seed)
            random.seed(self._original_seed)

    def set_seed(self, seed: int) -> None:
        """Set a new seed for reproducible generation."""
        self.seed = seed
        self._original_seed = seed
        Faker.seed(seed)
        random.seed(seed)

    def with_locale(self, locale: str) -> "FakeDataGenerator":
        """Create a new generator with a different locale.

        Args:
            locale: The locale code (e.g., "de_DE", "fr_FR", "ja_JP").

        Returns:
            A new FakeDataGenerator instance with the specified locale.
        """
        return FakeDataGenerator(locale=locale, seed=self.seed)

    @contextmanager
    def seeded(self, seed: int) -> Iterator["FakeDataGenerator"]:
        """Context manager for temporarily using a different seed.

        Args:
            seed: The temporary seed to use.

        Yields:
            Self with the temporary seed applied.
        """
        old_seed = self.seed
        self.set_seed(seed)
        try:
            yield self
        finally:
            if old_seed is not None:
                self.set_seed(old_seed)
            else:
                self.seed = None
                self._original_seed = None

    # Basic Faker methods
    def name(self) -> str:
        """Generate a full name."""
        return self._faker.name()

    def first_name(self) -> str:
        """Generate a first name."""
        return self._faker.first_name()

    def last_name(self) -> str:
        """Generate a last name."""
        return self._faker.last_name()

    def email(self, domain: str | None = None) -> str:
        """Generate an email address."""
        if domain:
            username = self._faker.user_name()
            return f"{username}@{domain}"
        return self._faker.email()

    def safe_email(self) -> str:
        """Generate a safe email address (example.com domain)."""
        return self._faker.safe_email()

    def company_email(self) -> str:
        """Generate a company email address."""
        return self._faker.company_email()

    def phone_number(self) -> str:
        """Generate a phone number."""
        return self._faker.phone_number()

    def username(self) -> str:
        """Generate a username."""
        return self._faker.user_name()

    def uuid(self) -> str:
        """Generate a UUID."""
        return str(uuid.uuid4())

    def company(self) -> str:
        """Generate a company name."""
        return self._faker.company()

    def job_title(self) -> str:
        """Generate a job title."""
        return self._faker.job()

    def date(self, start_date: str = "-30y", end_date: str = "today") -> date:
        """Generate a date."""
        return self._faker.date_between(start_date=start_date, end_date=end_date)

    def datetime(self, start_date: str = "-30y", end_date: str = "now") -> datetime:
        """Generate a datetime."""
        return self._faker.date_time_between(start_date=start_date, end_date=end_date)

    def past_date(self, days: int = 30) -> date:
        """Generate a date in the past."""
        return self._faker.date_between(start_date=f"-{days}d", end_date="today")

    def future_date(self, days: int = 30) -> date:
        """Generate a date in the future."""
        return self._faker.date_between(start_date="today", end_date=f"+{days}d")

    def past_datetime(self, days: int = 30) -> datetime:
        """Generate a datetime in the past."""
        return self._faker.date_time_between(start_date=f"-{days}d", end_date="now")

    def future_datetime(self, days: int = 30) -> datetime:
        """Generate a datetime in the future."""
        return self._faker.date_time_between(start_date="now", end_date=f"+{days}d")

    def text(self, max_chars: int = 200) -> str:
        """Generate random text."""
        return self._faker.text(max_nb_chars=max_chars)

    def paragraph(self, sentences: int = 5) -> str:
        """Generate a paragraph."""
        return self._faker.paragraph(nb_sentences=sentences)

    def paragraphs(self, count: int = 3) -> list[str]:
        """Generate multiple paragraphs."""
        return self._faker.paragraphs(nb=count)

    def sentence(self, words: int = 10) -> str:
        """Generate a sentence."""
        return self._faker.sentence(nb_words=words)

    def word(self) -> str:
        """Generate a word."""
        return self._faker.word()

    def words(self, count: int = 5) -> list[str]:
        """Generate multiple words."""
        return self._faker.words(nb=count)

    def url(self) -> str:
        """Generate a URL."""
        return self._faker.url()

    def image_url(self, width: int = 800, height: int = 600) -> str:
        """Generate an image URL."""
        return self._faker.image_url(width, height)

    def boolean(self, chance_of_true: int = 50) -> bool:
        """Generate a boolean value."""
        return self._faker.boolean(chance_of_getting_true=chance_of_true)

    def integer(self, min_value: int = 0, max_value: int = 10000) -> int:
        """Generate an integer."""
        return random.randint(min_value, max_value)

    def decimal(
        self,
        min_value: float = 0.0,
        max_value: float = 10000.0,
        places: int = 2,
    ) -> Decimal:
        """Generate a decimal number."""
        value = random.uniform(min_value, max_value)
        return Decimal(str(round(value, places)))

    # User generators
    def password(
        self,
        length: int = 16,
        include_special: bool = True,
        include_numbers: bool = True,
        include_uppercase: bool = True,
    ) -> str:
        """Generate a secure password."""
        chars = string.ascii_lowercase
        if include_uppercase:
            chars += string.ascii_uppercase
        if include_numbers:
            chars += string.digits
        if include_special:
            chars += "!@#$%^&*()_+-="

        # Ensure at least one of each required character type
        password_chars = []
        if include_uppercase:
            password_chars.append(random.choice(string.ascii_uppercase))
        if include_numbers:
            password_chars.append(random.choice(string.digits))
        if include_special:
            password_chars.append(random.choice("!@#$%^&*()_+-="))
        password_chars.append(random.choice(string.ascii_lowercase))

        # Fill remaining length
        remaining = length - len(password_chars)
        password_chars.extend(random.choices(chars, k=remaining))

        # Shuffle
        random.shuffle(password_chars)
        return "".join(password_chars)

    def user_type(self) -> str:
        """Generate a user type."""
        return self._faker.user_type()

    def account_status(self) -> str:
        """Generate an account status."""
        return self._faker.account_status()

    def api_key(self, prefix: str = "vqa") -> str:
        """Generate an API key."""
        return self._faker.api_key(prefix)

    def auth_token(self) -> str:
        """Generate an authentication token."""
        return self._faker.auth_token()

    def verification_code(self, length: int = 6) -> str:
        """Generate a verification code."""
        return self._faker.verification_code(length)

    # E-commerce generators
    def product_name(self) -> str:
        """Generate a product name."""
        return self._faker.product_name()

    def product_title(self, brand: str | None = None) -> str:
        """Generate a full product title."""
        return self._faker.product_title(brand)

    def product_description(self, sentences: int = 3) -> str:
        """Generate a product description."""
        return self._faker.product_description(sentences)

    def product_category(self) -> str:
        """Generate a product category."""
        return self._faker.product_category()

    def sku(self, prefix: str | None = None) -> str:
        """Generate a product SKU."""
        return self._faker.sku(prefix)

    def price(
        self,
        min_price: float = 1.0,
        max_price: float = 1000.0,
        decimals: int = 2,
    ) -> float:
        """Generate a price."""
        return self._faker.price(min_price, max_price, decimals)

    def quantity(self, min_qty: int = 1, max_qty: int = 100) -> int:
        """Generate a quantity."""
        return self._faker.quantity(min_qty, max_qty)

    def order_status(self) -> str:
        """Generate an order status."""
        return self._faker.order_status()

    def order_number(self, prefix: str = "ORD") -> str:
        """Generate an order number."""
        return self._faker.order_number(prefix)

    def tracking_number(self, carrier: str = "USPS") -> str:
        """Generate a tracking number."""
        return self._faker.tracking_number(carrier)

    def payment_method(self) -> str:
        """Generate a payment method."""
        return self._faker.payment_method()

    def coupon_code(self, length: int = 8) -> str:
        """Generate a coupon code."""
        return self._faker.coupon_code(length)

    # Payment generators
    def test_card_number(self, card_type: str = "visa") -> str:
        """Generate a test card number."""
        return self._faker.test_card_number(card_type)

    def card_expiry(self, min_years: int = 1, max_years: int = 5) -> str:
        """Generate a card expiry date (MM/YY)."""
        return self._faker.card_expiry(min_years, max_years)

    def cvv(self, length: int = 3) -> str:
        """Generate a CVV code."""
        return self._faker.cvv(length)

    def card_holder_name(self) -> str:
        """Generate a card holder name."""
        return self._faker.card_holder_name()

    def transaction_id(self, prefix: str = "txn") -> str:
        """Generate a transaction ID."""
        return self._faker.transaction_id(prefix)

    # Content generators
    def article_title(self) -> str:
        """Generate an article title."""
        return self._faker.article_title()

    def article_slug(self, title: str | None = None) -> str:
        """Generate an article slug."""
        return self._faker.article_slug(title)

    def article_excerpt(self, length: int = 200) -> str:
        """Generate an article excerpt."""
        return self._faker.article_excerpt(length)

    def article_body(self, paragraphs: int = 5) -> str:
        """Generate an article body."""
        return self._faker.article_body(paragraphs)

    def comment(self, max_length: int = 500) -> str:
        """Generate a comment."""
        return self._faker.comment(max_length)

    def tag(self) -> str:
        """Generate a tag."""
        return self._faker.tag()

    def tags(self, count: int = 5) -> list[str]:
        """Generate tags."""
        return self._faker.tags(count)

    # Address generators
    def address(self) -> str:
        """Generate a street address."""
        return self._faker.address()

    def street_address(self) -> str:
        """Generate a street address."""
        return self._faker.street_address()

    def city(self) -> str:
        """Generate a city name."""
        return self._faker.city()

    def state(self) -> str:
        """Generate a state name."""
        return self._faker.state() if hasattr(self._faker, "state") else ""

    def postal_code(self) -> str:
        """Generate a postal code."""
        return self._faker.postcode()

    def country(self) -> str:
        """Generate a country name."""
        return self._faker.country_name()

    def country_code(self) -> str:
        """Generate a country code."""
        return self._faker.country_code()

    def full_address(self) -> str:
        """Generate a full address string."""
        return self._faker.full_address()

    def address_dict(self) -> dict:
        """Generate an address as a dictionary."""
        return self._faker.address_dict()

    def shipping_address(self) -> dict:
        """Generate a shipping address."""
        return self._faker.shipping_address()

    def billing_address(self) -> dict:
        """Generate a billing address."""
        return self._faker.billing_address()

    def coordinates(self) -> tuple[float, float]:
        """Generate latitude and longitude coordinates."""
        return self._faker.coordinates()

    # Complete entity generators
    def user(self, **overrides: Any) -> dict:
        """Generate a complete user object.

        Args:
            **overrides: Fields to override in the generated user.

        Returns:
            A dictionary representing a user.
        """
        user_data = {
            "id": self.uuid(),
            "email": self.email(),
            "username": self.username(),
            "first_name": self.first_name(),
            "last_name": self.last_name(),
            "password": self.password(),
            "phone": self.phone_number(),
            "user_type": self.user_type(),
            "status": self.account_status(),
            "avatar_url": self._faker.avatar_url(),
            "bio": self._faker.bio(),
            "created_at": self.datetime().isoformat(),
            "updated_at": self.datetime().isoformat(),
        }
        user_data.update(overrides)
        return user_data

    def customer(self, **overrides: Any) -> dict:
        """Generate a customer user object."""
        defaults = {"user_type": "customer", "status": "active"}
        defaults.update(overrides)
        return self.user(**defaults)

    def admin(self, **overrides: Any) -> dict:
        """Generate an admin user object."""
        defaults = {"user_type": "admin", "status": "active"}
        defaults.update(overrides)
        return self.user(**defaults)

    def product(self, **overrides: Any) -> dict:
        """Generate a complete product object.

        Args:
            **overrides: Fields to override in the generated product.

        Returns:
            A dictionary representing a product.
        """
        product_data = {
            "id": self.uuid(),
            "sku": self.sku(),
            "title": self.product_title(),
            "name": self.product_name(),
            "description": self.product_description(),
            "category": self.product_category(),
            "price": self.price(),
            "currency": self._faker.currency_code(),
            "stock_quantity": self._faker.stock_quantity(),
            "weight": self._faker.weight(),
            "dimensions": self._faker.dimensions(),
            "image_url": self._faker.image_url(),
            "is_active": True,
            "created_at": self.datetime().isoformat(),
            "updated_at": self.datetime().isoformat(),
        }
        product_data.update(overrides)
        return product_data

    def order(self, user_id: str | None = None, items: list | None = None, **overrides: Any) -> dict:
        """Generate a complete order object.

        Args:
            user_id: Optional user ID. If not provided, one will be generated.
            items: Optional list of order items.
            **overrides: Fields to override in the generated order.

        Returns:
            A dictionary representing an order.
        """
        if items is None:
            items = [self.order_item() for _ in range(random.randint(1, 5))]

        subtotal = sum(item["subtotal"] for item in items)
        tax = round(subtotal * 0.1, 2)
        shipping = round(random.uniform(5, 20), 2)
        total = round(subtotal + tax + shipping, 2)

        order_data = {
            "id": self.uuid(),
            "order_number": self.order_number(),
            "user_id": user_id or self.uuid(),
            "status": self.order_status(),
            "items": items,
            "subtotal": subtotal,
            "tax": tax,
            "shipping_cost": shipping,
            "total": total,
            "currency": self._faker.currency_code(),
            "shipping_address": self.shipping_address(),
            "billing_address": self.billing_address(),
            "payment_method": self.payment_method(),
            "tracking_number": self.tracking_number() if random.random() > 0.5 else None,
            "notes": self.text(100) if random.random() > 0.7 else None,
            "created_at": self.datetime().isoformat(),
            "updated_at": self.datetime().isoformat(),
        }
        order_data.update(overrides)
        return order_data

    def order_item(self, product_id: str | None = None, **overrides: Any) -> dict:
        """Generate an order item.

        Args:
            product_id: Optional product ID.
            **overrides: Fields to override.

        Returns:
            A dictionary representing an order item.
        """
        quantity = self.quantity(1, 10)
        unit_price = self.price(5, 500)
        item_data = {
            "id": self.uuid(),
            "product_id": product_id or self.uuid(),
            "product_name": self.product_name(),
            "sku": self.sku(),
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": round(quantity * unit_price, 2),
        }
        item_data.update(overrides)
        return item_data

    def cart(self, user_id: str | None = None, item_count: int | None = None, **overrides: Any) -> dict:
        """Generate a shopping cart.

        Args:
            user_id: Optional user ID.
            item_count: Number of items to include.
            **overrides: Fields to override.

        Returns:
            A dictionary representing a cart.
        """
        if item_count is None:
            item_count = random.randint(1, 5)

        items = [self.cart_item() for _ in range(item_count)]
        subtotal = sum(item["subtotal"] for item in items)

        cart_data = {
            "id": self.uuid(),
            "user_id": user_id or self.uuid(),
            "items": items,
            "item_count": sum(item["quantity"] for item in items),
            "subtotal": subtotal,
            "currency": self._faker.currency_code(),
            "created_at": self.datetime().isoformat(),
            "updated_at": self.datetime().isoformat(),
        }
        cart_data.update(overrides)
        return cart_data

    def cart_item(self, **overrides: Any) -> dict:
        """Generate a cart item."""
        quantity = self.quantity(1, 5)
        unit_price = self.price(10, 200)
        item_data = {
            "id": self.uuid(),
            "product_id": self.uuid(),
            "product_name": self.product_name(),
            "sku": self.sku(),
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": round(quantity * unit_price, 2),
            "image_url": self._faker.image_url(),
        }
        item_data.update(overrides)
        return item_data

    def payment(self, order_id: str | None = None, amount: float | None = None, **overrides: Any) -> dict:
        """Generate a payment object.

        Args:
            order_id: Optional order ID.
            amount: Optional payment amount.
            **overrides: Fields to override.

        Returns:
            A dictionary representing a payment.
        """
        payment_data = {
            "id": self.uuid(),
            "transaction_id": self.transaction_id(),
            "order_id": order_id or self.uuid(),
            "amount": amount or self.price(10, 1000),
            "currency": self._faker.currency_code(),
            "method": self.payment_method(),
            "status": random.choice(["pending", "completed", "failed", "refunded"]),
            "card_last_four": self.test_card_number()[-4:],
            "card_type": random.choice(["visa", "mastercard", "amex"]),
            "created_at": self.datetime().isoformat(),
        }
        payment_data.update(overrides)
        return payment_data

    def article(self, author_id: str | None = None, **overrides: Any) -> dict:
        """Generate an article object.

        Args:
            author_id: Optional author ID.
            **overrides: Fields to override.

        Returns:
            A dictionary representing an article.
        """
        title = self.article_title()
        article_data = {
            "id": self.uuid(),
            "title": title,
            "slug": self.article_slug(title),
            "excerpt": self.article_excerpt(),
            "body": self.article_body(),
            "author_id": author_id or self.uuid(),
            "author_name": self.name(),
            "category": self._faker.category(),
            "tags": self.tags(random.randint(3, 7)),
            "status": self._faker.content_status(),
            "featured_image_url": self._faker.featured_image_url(),
            "reading_time": self._faker.reading_time(),
            "views": random.randint(0, 10000),
            "likes": random.randint(0, 1000),
            "published_at": self.datetime().isoformat() if random.random() > 0.3 else None,
            "created_at": self.datetime().isoformat(),
            "updated_at": self.datetime().isoformat(),
        }
        article_data.update(overrides)
        return article_data

    def comment_obj(self, article_id: str | None = None, user_id: str | None = None, **overrides: Any) -> dict:
        """Generate a comment object.

        Args:
            article_id: Optional article ID.
            user_id: Optional user ID.
            **overrides: Fields to override.

        Returns:
            A dictionary representing a comment.
        """
        comment_data = {
            "id": self.uuid(),
            "article_id": article_id or self.uuid(),
            "user_id": user_id or self.uuid(),
            "user_name": self.name(),
            "avatar_url": self._faker.avatar_url(),
            "content": self.comment(),
            "status": self._faker.comment_status(),
            "likes": random.randint(0, 100),
            "created_at": self.datetime().isoformat(),
            "updated_at": self.datetime().isoformat(),
        }
        comment_data.update(overrides)
        return comment_data

    # Batch generation methods
    def users(self, count: int, **overrides: Any) -> list[dict]:
        """Generate multiple users."""
        return [self.user(**overrides) for _ in range(count)]

    def customers(self, count: int, **overrides: Any) -> list[dict]:
        """Generate multiple customers."""
        return [self.customer(**overrides) for _ in range(count)]

    def products(self, count: int, **overrides: Any) -> list[dict]:
        """Generate multiple products."""
        return [self.product(**overrides) for _ in range(count)]

    def orders(self, count: int, user_id: str | None = None, **overrides: Any) -> list[dict]:
        """Generate multiple orders."""
        return [self.order(user_id=user_id, **overrides) for _ in range(count)]

    def articles(self, count: int, author_id: str | None = None, **overrides: Any) -> list[dict]:
        """Generate multiple articles."""
        return [self.article(author_id=author_id, **overrides) for _ in range(count)]


# Global instance for convenience
fake = FakeDataGenerator()


def create_fake(locale: str = "en_US", seed: int | None = None) -> FakeDataGenerator:
    """Create a new FakeDataGenerator instance.

    Args:
        locale: The locale for generating localized data.
        seed: Optional seed for reproducible generation.

    Returns:
        A configured FakeDataGenerator instance.
    """
    return FakeDataGenerator(locale=locale, seed=seed)


def set_global_seed(seed: int) -> None:
    """Set the seed for the global fake instance.

    Args:
        seed: The seed value for reproducible generation.
    """
    fake.set_seed(seed)


def reset_global_seed() -> None:
    """Reset the global fake instance to its original seed."""
    fake.reset_seed()
