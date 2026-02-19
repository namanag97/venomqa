"""Test data generation, seeding and cleanup management for VenomQA.

This module provides comprehensive data generation capabilities using Faker,
along with infrastructure for seeding test data and managing cleanup.

Data Generation:
    >>> from venomqa.data import fake
    >>>
    >>> # Generate basic data
    >>> email = fake.email()
    >>> name = fake.name()
    >>> password = fake.password()
    >>>
    >>> # Generate complex objects
    >>> user = fake.user()
    >>> product = fake.product()
    >>> order = fake.order()

Localization:
    >>> from venomqa.data import FakeDataGenerator
    >>>
    >>> # Create generator with specific locale
    >>> fake_de = FakeDataGenerator(locale="de_DE")
    >>> german_name = fake_de.name()

Reproducible Tests:
    >>> from venomqa.data import set_global_seed
    >>>
    >>> # Set seed for reproducible data
    >>> set_global_seed(12345)
    >>> email1 = fake.email()

Domain-Specific Generators:
    >>> from venomqa.data import ecommerce, users, content
    >>>
    >>> # E-commerce data
    >>> catalog = ecommerce.product_catalog(10)
    >>> checkout = ecommerce.checkout_scenario()
    >>>
    >>> # User data
    >>> team = users.team_with_members(5)
    >>> auth = users.login_credentials()
    >>>
    >>> # Content data
    >>> post = content.blog_post_with_comments(10)
    >>> feed = content.content_feed(20)

Seeding and Cleanup:
    >>> from venomqa.data import SeedManager, CleanupManager
    >>> from venomqa.data import CleanupStrategy, SeedMode
    >>>
    >>> # Load and apply seeds
    >>> seed_manager = SeedManager(client=client, database=db)
    >>> seeds = seed_manager.load("seeds/base.yaml")
    >>> seed_manager.apply(seeds, mode=SeedMode.API)
    >>>
    >>> # Configure cleanup
    >>> cleanup = CleanupManager(strategy=CleanupStrategy.REVERSE_DELETE)
    >>> cleanup.register_resources(seed_manager.created_resources)
    >>> cleanup.cleanup()

Integration with Fixtures:
    >>> from venomqa.data import fake
    >>>
    >>> @fixture
    ... def customer(client, ctx):
    ...     return {
    ...         "email": fake.email(),
    ...         "name": fake.name(),
    ...         "password": fake.password(),
    ...     }
"""

from venomqa.data.cleanup import (
    CleanupConfig,
    CleanupManager,
    CleanupResult,
    CleanupStrategy,
    ResourceTracker,
    TrackedResource,
)
from venomqa.data.content import ContentGenerator, content, create_content_generator
from venomqa.data.ecommerce import EcommerceGenerator, create_ecommerce_generator, ecommerce
from venomqa.data.generators import (
    AddressDataProvider,
    ContentDataProvider,
    EcommerceDataProvider,
    FakeDataGenerator,
    PaymentDataProvider,
    UserDataProvider,
    create_fake,
    fake,
    reset_global_seed,
    set_global_seed,
)
from venomqa.data.seeding import (
    SeedConfig,
    SeedData,
    SeedFile,
    SeedManager,
    SeedMode,
    SeedResult,
    seed_fixture,
)
from venomqa.data.users import UserGenerator, create_user_generator, users

__all__ = [
    # Data Generation - Main
    "FakeDataGenerator",
    "fake",
    "create_fake",
    "set_global_seed",
    "reset_global_seed",
    # Data Generation - Providers
    "EcommerceDataProvider",
    "PaymentDataProvider",
    "UserDataProvider",
    "ContentDataProvider",
    "AddressDataProvider",
    # Data Generation - E-commerce
    "EcommerceGenerator",
    "ecommerce",
    "create_ecommerce_generator",
    # Data Generation - Users
    "UserGenerator",
    "users",
    "create_user_generator",
    # Data Generation - Content
    "ContentGenerator",
    "content",
    "create_content_generator",
    # Seeding
    "SeedManager",
    "SeedMode",
    "SeedConfig",
    "SeedData",
    "SeedFile",
    "SeedResult",
    "seed_fixture",
    # Cleanup
    "CleanupManager",
    "CleanupStrategy",
    "CleanupConfig",
    "CleanupResult",
    "ResourceTracker",
    "TrackedResource",
]
