"""Tests for data generation module."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from venomqa.data import (
    FakeDataGenerator,
    content,
    create_content_generator,
    create_ecommerce_generator,
    create_fake,
    create_user_generator,
    ecommerce,
    fake,
    reset_global_seed,
    set_global_seed,
    users,
)


class TestFakeDataGenerator:
    """Tests for the main FakeDataGenerator class."""

    def test_basic_string_generation(self) -> None:
        """Test generating basic string data."""
        name = fake.name()
        email = fake.email()
        username = fake.username()

        assert isinstance(name, str)
        assert len(name) > 0
        assert "@" in email
        assert isinstance(username, str)

    def test_email_with_custom_domain(self) -> None:
        """Test generating email with custom domain."""
        email = fake.email(domain="example.com")
        assert email.endswith("@example.com")

    def test_safe_email(self) -> None:
        """Test generating safe email addresses."""
        email = fake.safe_email()
        assert "@example" in email or "@example.com" in email or "@example.org" in email or "@example.net" in email

    def test_password_generation(self) -> None:
        """Test password generation with options."""
        password = fake.password(length=16, include_special=True)
        assert len(password) == 16

        # Test minimum requirements
        password = fake.password(
            length=12,
            include_uppercase=True,
            include_numbers=True,
            include_special=True,
        )
        assert any(c.isupper() for c in password)
        assert any(c.isdigit() for c in password)
        assert any(c in "!@#$%^&*()_+-=" for c in password)

    def test_numeric_generation(self) -> None:
        """Test generating numeric data."""
        integer = fake.integer(min_value=1, max_value=100)
        assert 1 <= integer <= 100

        decimal = fake.decimal(min_value=0.0, max_value=100.0, places=2)
        assert isinstance(decimal, Decimal)
        assert 0 <= float(decimal) <= 100

    def test_date_generation(self) -> None:
        """Test date and datetime generation."""
        d = fake.date()
        assert isinstance(d, date)

        dt = fake.datetime()
        assert isinstance(dt, datetime)

        past = fake.past_date(days=30)
        assert past <= date.today()

        future = fake.future_date(days=30)
        assert future >= date.today()

    def test_text_generation(self) -> None:
        """Test text generation methods."""
        text = fake.text(max_chars=200)
        assert isinstance(text, str)
        assert len(text) <= 200

        paragraph = fake.paragraph(sentences=3)
        assert isinstance(paragraph, str)

        sentence = fake.sentence(words=10)
        assert isinstance(sentence, str)

    def test_address_generation(self) -> None:
        """Test address generation."""
        address = fake.address()
        assert isinstance(address, str)

        city = fake.city()
        assert isinstance(city, str)

        postal_code = fake.postal_code()
        assert isinstance(postal_code, str)

        full_addr = fake.full_address()
        assert isinstance(full_addr, str)
        assert len(full_addr) > 0

    def test_localization(self) -> None:
        """Test locale support."""
        fake_de = fake.with_locale("de_DE")
        german_name = fake_de.name()
        assert isinstance(german_name, str)

        fake_fr = FakeDataGenerator(locale="fr_FR")
        french_city = fake_fr.city()
        assert isinstance(french_city, str)

    def test_seeded_generation(self) -> None:
        """Test reproducible generation with seeds."""
        # Create generator with a seed
        gen = FakeDataGenerator(seed=12345)

        email1 = gen.email()
        name1 = gen.name()

        # Reset the seed and generate again
        gen.reset_seed()

        email2 = gen.email()
        name2 = gen.name()

        # They should produce the same sequence
        assert email1 == email2
        assert name1 == name2

    def test_seed_reset(self) -> None:
        """Test resetting the seed."""
        gen = FakeDataGenerator(seed=12345)

        email1 = gen.email()
        name1 = gen.name()

        gen.reset_seed()

        email2 = gen.email()
        name2 = gen.name()

        assert email1 == email2
        assert name1 == name2

    def test_global_seed(self) -> None:
        """Test global seed functions."""
        set_global_seed(54321)
        email1 = fake.email()

        reset_global_seed()
        email2 = fake.email()

        assert email1 == email2

    def test_seeded_context_manager(self) -> None:
        """Test temporary seed with context manager."""
        gen = FakeDataGenerator(seed=11111)
        original_email = gen.email()

        gen.reset_seed()

        # Use a different seed temporarily
        with gen.seeded(99999):
            temp_email = gen.email()
            assert temp_email != original_email

    def test_user_generation(self) -> None:
        """Test complete user object generation."""
        user = fake.user()

        assert "id" in user
        assert "email" in user
        assert "@" in user["email"]
        assert "username" in user
        assert "first_name" in user
        assert "last_name" in user
        assert "password" in user
        assert "created_at" in user

    def test_user_with_overrides(self) -> None:
        """Test user generation with overrides."""
        user = fake.user(email="custom@example.com", user_type="admin")

        assert user["email"] == "custom@example.com"
        assert user["user_type"] == "admin"

    def test_customer_generation(self) -> None:
        """Test customer user generation."""
        customer = fake.customer()
        assert customer["user_type"] == "customer"
        assert customer["status"] == "active"

    def test_admin_generation(self) -> None:
        """Test admin user generation."""
        admin = fake.admin()
        assert admin["user_type"] == "admin"
        assert admin["status"] == "active"

    def test_product_generation(self) -> None:
        """Test product generation."""
        product = fake.product()

        assert "id" in product
        assert "sku" in product
        assert "title" in product
        assert "price" in product
        assert isinstance(product["price"], float)
        assert product["price"] > 0

    def test_order_generation(self) -> None:
        """Test order generation."""
        order = fake.order()

        assert "id" in order
        assert "order_number" in order
        assert "items" in order
        assert len(order["items"]) > 0
        assert "total" in order
        assert order["total"] > 0

    def test_order_with_specific_user(self) -> None:
        """Test order generation with specific user ID."""
        user_id = "user-123"
        order = fake.order(user_id=user_id)
        assert order["user_id"] == user_id

    def test_payment_generation(self) -> None:
        """Test payment data generation."""
        payment = fake.payment()

        assert "id" in payment
        assert "transaction_id" in payment
        assert "amount" in payment
        assert "method" in payment
        assert "card_last_four" in payment

    def test_article_generation(self) -> None:
        """Test article generation."""
        article = fake.article()

        assert "id" in article
        assert "title" in article
        assert "slug" in article
        assert "body" in article
        assert "tags" in article
        assert isinstance(article["tags"], list)

    def test_batch_generation(self) -> None:
        """Test batch generation methods."""
        users_list = fake.users(5)
        assert len(users_list) == 5
        assert all("email" in u for u in users_list)

        products = fake.products(3)
        assert len(products) == 3
        assert all("sku" in p for p in products)

        orders = fake.orders(4)
        assert len(orders) == 4
        assert all("order_number" in o for o in orders)


class TestEcommerceGenerator:
    """Tests for the EcommerceGenerator class."""

    def test_product_variant(self) -> None:
        """Test product variant generation."""
        variant = ecommerce.product_variant()

        assert "id" in variant
        assert "sku" in variant
        assert "color" in variant
        assert "size" in variant
        assert "price" in variant
        assert "stock_quantity" in variant

    def test_product_with_variants(self) -> None:
        """Test product with variants generation."""
        product = ecommerce.product_with_variants(variant_count=3)

        assert "variants" in product
        assert len(product["variants"]) == 3
        assert "total_stock" in product

    def test_product_catalog(self) -> None:
        """Test product catalog generation."""
        catalog = ecommerce.product_catalog(10)

        assert len(catalog) == 10
        assert all("id" in p for p in catalog)
        assert all("title" in p for p in catalog)

    def test_product_catalog_with_variants(self) -> None:
        """Test product catalog with variants."""
        catalog = ecommerce.product_catalog(5, with_variants=True)

        assert len(catalog) == 5
        assert all("variants" in p for p in catalog)

    def test_product_review(self) -> None:
        """Test product review generation."""
        review = ecommerce.product_review()

        assert "id" in review
        assert "rating" in review
        assert 1 <= review["rating"] <= 5
        assert "content" in review

    def test_product_with_reviews(self) -> None:
        """Test product with reviews generation."""
        product = ecommerce.product_with_reviews(review_count=5)

        assert "reviews" in product
        assert len(product["reviews"]) == 5
        assert "average_rating" in product
        assert "review_count" in product

    def test_shopping_cart(self) -> None:
        """Test shopping cart generation."""
        cart = ecommerce.shopping_cart(item_count=3)

        assert "id" in cart
        assert "items" in cart
        assert len(cart["items"]) == 3
        assert "subtotal" in cart

    def test_abandoned_cart(self) -> None:
        """Test abandoned cart generation."""
        cart = ecommerce.abandoned_cart()

        assert cart["status"] == "abandoned"
        assert "abandoned_at" in cart

    def test_wishlist(self) -> None:
        """Test wishlist generation."""
        wishlist = ecommerce.wishlist(item_count=5)

        assert "id" in wishlist
        assert "items" in wishlist
        assert len(wishlist["items"]) == 5

    def test_order_history(self) -> None:
        """Test order history generation."""
        history = ecommerce.order_history(count=5)

        assert len(history) == 5
        # Should be sorted by date (newest first)
        dates = [o["created_at"] for o in history]
        assert dates == sorted(dates, reverse=True)

    def test_return_request(self) -> None:
        """Test return request generation."""
        request = ecommerce.return_request()

        assert "id" in request
        assert "reason" in request
        assert "status" in request
        assert "refund_amount" in request

    def test_inventory_item(self) -> None:
        """Test inventory item generation."""
        item = ecommerce.inventory_item()

        assert "id" in item
        assert "quantity" in item
        assert "reorder_point" in item
        assert "is_low_stock" in item

    def test_inventory_snapshot(self) -> None:
        """Test inventory snapshot generation."""
        snapshot = ecommerce.inventory_snapshot(product_count=10)

        assert "items" in snapshot
        assert len(snapshot["items"]) == 10
        assert "total_items" in snapshot
        assert "low_stock_count" in snapshot

    def test_coupon(self) -> None:
        """Test coupon generation."""
        coupon = ecommerce.coupon()

        assert "id" in coupon
        assert "code" in coupon
        assert "type" in coupon
        assert "value" in coupon

    def test_checkout_scenario(self) -> None:
        """Test complete checkout scenario generation."""
        scenario = ecommerce.checkout_scenario()

        assert "user_id" in scenario
        assert "cart" in scenario
        assert "shipping_address" in scenario
        assert "billing_address" in scenario
        assert "payment" in scenario
        assert "order" in scenario

        # Verify order totals
        order = scenario["order"]
        assert order["subtotal"] > 0
        assert order["total"] > order["subtotal"]  # Includes tax and shipping

    def test_checkout_with_coupon(self) -> None:
        """Test checkout scenario with coupon."""
        scenario = ecommerce.checkout_scenario(with_coupon=True)

        assert "coupon" in scenario
        assert scenario["coupon"] is not None
        assert scenario["order"]["discount"] > 0

    def test_subscription(self) -> None:
        """Test subscription generation."""
        subscription = ecommerce.subscription()

        assert "id" in subscription
        assert "plan_name" in subscription
        assert "price" in subscription
        assert "status" in subscription

    def test_custom_ecommerce_generator(self) -> None:
        """Test creating custom ecommerce generator."""
        gen = create_ecommerce_generator(locale="de_DE", seed=12345)
        product = gen.product_catalog(1)[0]
        assert "id" in product


class TestUserGenerator:
    """Tests for the UserGenerator class."""

    def test_customer(self) -> None:
        """Test customer generation."""
        customer = users.customer()
        assert customer["user_type"] == "customer"

    def test_admin(self) -> None:
        """Test admin generation."""
        admin = users.admin()
        assert admin["user_type"] == "admin"

    def test_moderator(self) -> None:
        """Test moderator generation."""
        moderator = users.moderator()
        assert moderator["user_type"] == "moderator"

    def test_vendor(self) -> None:
        """Test vendor generation."""
        vendor = users.vendor()

        assert vendor["user_type"] == "vendor"
        assert "company_name" in vendor
        assert "tax_id" in vendor

    def test_support_agent(self) -> None:
        """Test support agent generation."""
        agent = users.support_agent()

        assert agent["user_type"] == "support"
        assert "department" in agent
        assert "languages" in agent

    def test_guest_user(self) -> None:
        """Test guest user generation."""
        guest = users.guest_user()

        assert guest["is_guest"] is True
        assert "session_id" in guest

    def test_user_profile(self) -> None:
        """Test user profile generation."""
        profile = users.user_profile()

        assert "display_name" in profile
        assert "bio" in profile
        assert "social_links" in profile
        assert "timezone" in profile

    def test_user_preferences(self) -> None:
        """Test user preferences generation."""
        prefs = users.user_preferences()

        assert "theme" in prefs
        assert "language" in prefs
        assert "notifications" in prefs
        assert "privacy" in prefs

    def test_login_credentials(self) -> None:
        """Test login credentials generation."""
        creds = users.login_credentials()

        assert "email" in creds
        assert "password" in creds
        assert "@" in creds["email"]
        assert len(creds["password"]) >= 8

    def test_registration_data(self) -> None:
        """Test registration data generation."""
        data = users.registration_data()

        assert "email" in data
        assert "username" in data
        assert "password" in data
        assert "password_confirmation" in data
        assert data["password"] == data["password_confirmation"]
        assert data["accept_terms"] is True

    def test_session(self) -> None:
        """Test session generation."""
        session = users.session()

        assert "id" in session
        assert "token" in session
        assert "refresh_token" in session
        assert "device_type" in session
        assert "expires_at" in session

    def test_api_credentials(self) -> None:
        """Test API credentials generation."""
        creds = users.api_credentials()

        assert "api_key" in creds
        assert "api_secret" in creds
        assert "scopes" in creds
        assert isinstance(creds["scopes"], list)

    def test_oauth_authorization(self) -> None:
        """Test OAuth authorization generation."""
        auth = users.oauth_authorization()

        assert "provider" in auth
        assert "access_token" in auth
        assert "refresh_token" in auth

    def test_two_factor_setup(self) -> None:
        """Test 2FA setup generation."""
        setup = users.two_factor_setup()

        assert "method" in setup
        assert "secret" in setup
        assert "backup_codes" in setup
        assert len(setup["backup_codes"]) == 10

    def test_team(self) -> None:
        """Test team generation."""
        team = users.team()

        assert "id" in team
        assert "name" in team
        assert "owner_id" in team
        assert "settings" in team

    def test_team_with_members(self) -> None:
        """Test team with members generation."""
        team = users.team_with_members(member_count=5)

        assert "members" in team
        assert len(team["members"]) == 5
        # First member should be owner
        assert team["members"][0]["role"] == "owner"

    def test_team_invitation(self) -> None:
        """Test team invitation generation."""
        invitation = users.team_invitation()

        assert "email" in invitation
        assert "role" in invitation
        assert "token" in invitation
        assert "status" in invitation

    def test_role(self) -> None:
        """Test role generation."""
        role = users.role()

        assert "id" in role
        assert "name" in role
        assert "permissions" in role
        assert isinstance(role["permissions"], list)

    def test_user_activity(self) -> None:
        """Test user activity generation."""
        activity = users.user_activity()

        assert "id" in activity
        assert "action" in activity
        assert "resource_type" in activity
        assert "created_at" in activity

    def test_activity_log(self) -> None:
        """Test activity log generation."""
        log = users.activity_log(count=10)

        assert len(log) == 10
        # Should be sorted by date (newest first)
        dates = [a["created_at"] for a in log]
        assert dates == sorted(dates, reverse=True)

    def test_notification(self) -> None:
        """Test notification generation."""
        notification = users.notification()

        assert "id" in notification
        assert "type" in notification
        assert "title" in notification
        assert "message" in notification

    def test_user_stats(self) -> None:
        """Test user statistics generation."""
        stats = users.user_stats()

        assert "orders_count" in stats
        assert "total_spent" in stats
        assert "points_balance" in stats

    def test_custom_user_generator(self) -> None:
        """Test creating custom user generator."""
        gen = create_user_generator(locale="fr_FR", seed=12345)
        customer = gen.customer()
        assert "email" in customer


class TestContentGenerator:
    """Tests for the ContentGenerator class."""

    def test_article(self) -> None:
        """Test article generation."""
        article = content.article()

        assert "id" in article
        assert "title" in article
        assert "slug" in article
        assert "body" in article
        assert "tags" in article

    def test_blog_post(self) -> None:
        """Test blog post generation."""
        post = content.blog_post()

        assert "id" in post
        assert "title" in post
        assert "content" in post
        assert "content_html" in post
        assert "author" in post
        assert "featured_image" in post

    def test_comment(self) -> None:
        """Test comment generation."""
        comment_obj = content.comment()

        assert "id" in comment_obj
        assert "body" in comment_obj
        assert "user" in comment_obj
        assert "likes" in comment_obj

    def test_comment_thread(self) -> None:
        """Test comment thread generation."""
        thread = content.comment_thread(depth=2)

        assert len(thread) > 0
        # Should have both root and nested comments
        root_comments = [c for c in thread if c["parent_id"] is None]
        nested_comments = [c for c in thread if c["parent_id"] is not None]
        assert len(root_comments) > 0
        assert len(nested_comments) >= 0

    def test_blog_post_with_comments(self) -> None:
        """Test blog post with comments generation."""
        post = content.blog_post_with_comments(comment_count=5)

        assert "comments" in post
        assert len(post["comments"]) == 5
        assert post["comments_count"] == 5

    def test_page(self) -> None:
        """Test CMS page generation."""
        page = content.page()

        assert "id" in page
        assert "title" in page
        assert "slug" in page
        assert "template" in page
        assert "status" in page

    def test_media_item(self) -> None:
        """Test media item generation."""
        item = content.media_item()

        assert "id" in item
        assert "filename" in item
        assert "type" in item
        assert "url" in item
        assert "size_bytes" in item

    def test_media_library(self) -> None:
        """Test media library generation."""
        library = content.media_library(count=10)

        assert len(library) == 10
        assert all("type" in m for m in library)

    def test_gallery(self) -> None:
        """Test gallery generation."""
        gallery = content.gallery(image_count=5)

        assert "id" in gallery
        assert "images" in gallery
        assert len(gallery["images"]) == 5

    def test_category(self) -> None:
        """Test category generation."""
        cat = content.category()

        assert "id" in cat
        assert "name" in cat
        assert "slug" in cat

    def test_category_tree(self) -> None:
        """Test category tree generation."""
        tree = content.category_tree(depth=2)

        assert len(tree) > 0
        # Should have nested categories
        root_cats = [c for c in tree if c["parent_id"] is None]
        nested_cats = [c for c in tree if c["parent_id"] is not None]
        assert len(root_cats) > 0
        assert len(nested_cats) >= 0

    def test_tag(self) -> None:
        """Test tag generation."""
        tag = content.tag()

        assert "id" in tag
        assert "name" in tag
        assert "slug" in tag

    def test_newsletter(self) -> None:
        """Test newsletter generation."""
        newsletter = content.newsletter()

        assert "id" in newsletter
        assert "title" in newsletter
        assert "content_html" in newsletter
        assert "recipient_count" in newsletter

    def test_subscriber(self) -> None:
        """Test subscriber generation."""
        subscriber = content.subscriber()

        assert "id" in subscriber
        assert "email" in subscriber
        assert "status" in subscriber
        assert "preferences" in subscriber

    def test_content_feed(self) -> None:
        """Test content feed generation."""
        feed = content.content_feed(count=10)

        assert len(feed) == 10
        assert all("content_type" in item for item in feed)
        # Should be sorted by date
        dates = [item["created_at"] for item in feed]
        assert dates == sorted(dates, reverse=True)

    def test_search_results(self) -> None:
        """Test search results generation."""
        results = content.search_results(query="test", count=5)

        assert "query" in results
        assert "results" in results
        assert len(results["results"]) == 5
        assert "facets" in results
        assert "suggestions" in results

    def test_revision(self) -> None:
        """Test content revision generation."""
        revision = content.revision()

        assert "id" in revision
        assert "version" in revision
        assert "content" in revision
        assert "changes_summary" in revision

    def test_content_with_revisions(self) -> None:
        """Test content with revisions generation."""
        article = content.content_with_revisions(revision_count=5)

        assert "revisions" in article
        assert len(article["revisions"]) == 5
        assert article["current_version"] == 5

    def test_custom_content_generator(self) -> None:
        """Test creating custom content generator."""
        gen = create_content_generator(locale="es_ES", seed=12345)
        article = gen.article()
        assert "title" in article


class TestPaymentDataGeneration:
    """Tests for payment data generation."""

    def test_test_card_number(self) -> None:
        """Test generating test card numbers."""
        visa = fake.test_card_number("visa")
        assert visa.startswith("4")
        assert len(visa) >= 13

        mastercard = fake.test_card_number("mastercard")
        assert mastercard.startswith("5")

    def test_card_expiry(self) -> None:
        """Test card expiry generation."""
        expiry = fake.card_expiry()
        assert re.match(r"\d{2}/\d{2}", expiry)

        # Parse and verify it's in the future
        month, year = expiry.split("/")
        full_year = 2000 + int(year)
        assert full_year >= datetime.now().year

    def test_cvv(self) -> None:
        """Test CVV generation."""
        cvv = fake.cvv()
        assert len(cvv) == 3
        assert cvv.isdigit()

        cvv_amex = fake.cvv(length=4)
        assert len(cvv_amex) == 4

    def test_transaction_id(self) -> None:
        """Test transaction ID generation."""
        txn_id = fake.transaction_id()
        assert txn_id.startswith("txn_")

        custom_txn = fake.transaction_id(prefix="pay")
        assert custom_txn.startswith("pay_")


class TestEcommerceDataGeneration:
    """Tests for e-commerce specific data generation."""

    def test_product_name(self) -> None:
        """Test product name generation."""
        name = fake.product_name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_product_category(self) -> None:
        """Test product category generation."""
        category = fake.product_category()
        assert isinstance(category, str)

    def test_sku(self) -> None:
        """Test SKU generation."""
        sku = fake.sku()
        assert "-" in sku

        custom_sku = fake.sku(prefix="PROD")
        assert custom_sku.startswith("PROD-")

    def test_price(self) -> None:
        """Test price generation."""
        price = fake.price(min_price=10, max_price=100)
        assert 10 <= price <= 100

    def test_order_number(self) -> None:
        """Test order number generation."""
        order_num = fake.order_number()
        assert order_num.startswith("ORD-")

        custom = fake.order_number(prefix="PO")
        assert custom.startswith("PO-")

    def test_order_status(self) -> None:
        """Test order status generation."""
        status = fake.order_status()
        valid_statuses = [
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
        assert status in valid_statuses

    def test_tracking_number(self) -> None:
        """Test tracking number generation."""
        tracking = fake.tracking_number()
        assert isinstance(tracking, str)
        assert len(tracking) > 0

        ups_tracking = fake.tracking_number("UPS")
        assert ups_tracking.startswith("1Z")

    def test_coupon_code(self) -> None:
        """Test coupon code generation."""
        code = fake.coupon_code()
        assert len(code) == 8

        custom_length = fake.coupon_code(length=12)
        assert len(custom_length) == 12


class TestUserDataGeneration:
    """Tests for user specific data generation."""

    def test_user_type(self) -> None:
        """Test user type generation."""
        user_type = fake.user_type()
        valid_types = ["customer", "admin", "moderator", "vendor", "support", "guest"]
        assert user_type in valid_types

    def test_account_status(self) -> None:
        """Test account status generation."""
        status = fake.account_status()
        valid_statuses = ["active", "inactive", "suspended", "pending_verification", "deleted"]
        assert status in valid_statuses

    def test_api_key(self) -> None:
        """Test API key generation."""
        key = fake.api_key()
        assert key.startswith("vqa_")

        custom = fake.api_key(prefix="sk")
        assert custom.startswith("sk_")

    def test_auth_token(self) -> None:
        """Test auth token generation."""
        token = fake.auth_token()
        assert len(token) == 64  # Two UUID hex values

    def test_verification_code(self) -> None:
        """Test verification code generation."""
        code = fake.verification_code()
        assert len(code) == 6
        assert code.isdigit()

        custom_length = fake.verification_code(length=8)
        assert len(custom_length) == 8


class TestContentDataGeneration:
    """Tests for content specific data generation."""

    def test_article_title(self) -> None:
        """Test article title generation."""
        title = fake.article_title()
        assert isinstance(title, str)
        assert not title.endswith(".")

    def test_article_slug(self) -> None:
        """Test article slug generation."""
        slug = fake.article_slug("Hello World!")
        assert slug == "hello-world"

        auto_slug = fake.article_slug()
        assert isinstance(auto_slug, str)
        assert " " not in auto_slug

    def test_article_excerpt(self) -> None:
        """Test article excerpt generation."""
        excerpt = fake.article_excerpt(length=100)
        assert len(excerpt) <= 100

    def test_article_body(self) -> None:
        """Test article body generation."""
        body = fake.article_body(paragraphs=3)
        assert isinstance(body, str)
        assert len(body) > 0

    def test_comment_generation(self) -> None:
        """Test comment text generation."""
        comment_text = fake.comment(max_length=200)
        assert len(comment_text) <= 200

    def test_tags_generation(self) -> None:
        """Test tags list generation."""
        tags = fake.tags(count=5)
        assert len(tags) == 5
        assert all(isinstance(t, str) for t in tags)


class TestAddressDataGeneration:
    """Tests for address data generation."""

    def test_shipping_address(self) -> None:
        """Test shipping address generation."""
        address = fake.shipping_address()

        assert "street1" in address
        assert "city" in address
        assert "postal_code" in address
        assert "country" in address
        assert address["type"] == "shipping"
        assert "recipient_name" in address

    def test_billing_address(self) -> None:
        """Test billing address generation."""
        address = fake.billing_address()

        assert "street1" in address
        assert address["type"] == "billing"

    def test_coordinates(self) -> None:
        """Test coordinates generation."""
        lat, lon = fake.coordinates()

        assert -90 <= lat <= 90
        assert -180 <= lon <= 180


class TestCreateFakeFunction:
    """Tests for the create_fake factory function."""

    def test_create_with_locale(self) -> None:
        """Test creating generator with locale."""
        gen = create_fake(locale="ja_JP")
        name = gen.name()
        assert isinstance(name, str)

    def test_create_with_seed(self) -> None:
        """Test creating generator with seed."""
        gen = create_fake(seed=99999)
        email1 = gen.email()

        gen.reset_seed()
        email2 = gen.email()

        assert email1 == email2

    def test_create_with_locale_and_seed(self) -> None:
        """Test creating generator with both locale and seed."""
        gen = create_fake(locale="it_IT", seed=11111)
        email1 = gen.email()

        gen.reset_seed()
        email2 = gen.email()

        assert email1 == email2
