"""Pre-built user data generators.

This module provides specialized data generators for user-related testing
scenarios, including customers, admins, teams, and authentication data.

Example:
    >>> from venomqa.data.users import users
    >>>
    >>> # Generate a team with members
    >>> team = users.team_with_members(5)
    >>>
    >>> # Generate authentication test data
    >>> auth_data = users.login_credentials()
    >>> print(auth_data["email"])
    >>> print(auth_data["password"])
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from venomqa.data.generators import FakeDataGenerator, fake as default_fake


@dataclass
class UserGenerator:
    """Specialized generator for user-related test data.

    Provides methods for generating complex user data structures
    including profiles, teams, permissions, and authentication data.
    """

    fake: FakeDataGenerator = field(default_factory=lambda: default_fake)

    def customer(self, **overrides: Any) -> dict:
        """Generate a customer user."""
        return self.fake.customer(**overrides)

    def admin(self, **overrides: Any) -> dict:
        """Generate an admin user."""
        return self.fake.admin(**overrides)

    def moderator(self, **overrides: Any) -> dict:
        """Generate a moderator user."""
        defaults = {"user_type": "moderator", "status": "active"}
        defaults.update(overrides)
        return self.fake.user(**defaults)

    def vendor(self, **overrides: Any) -> dict:
        """Generate a vendor user."""
        vendor = self.fake.user(user_type="vendor", status="active", **overrides)
        vendor["company_name"] = self.fake.company()
        vendor["business_email"] = self.fake.company_email()
        vendor["business_phone"] = self.fake.phone_number()
        vendor["tax_id"] = "".join(random.choices("0123456789", k=9))
        vendor["commission_rate"] = round(random.uniform(5, 20), 2)
        return vendor

    def support_agent(self, **overrides: Any) -> dict:
        """Generate a support agent user."""
        agent = self.fake.user(user_type="support", status="active", **overrides)
        agent["department"] = random.choice([
            "General Support",
            "Technical Support",
            "Billing",
            "Sales",
            "Returns",
        ])
        agent["languages"] = random.sample(
            ["English", "Spanish", "French", "German", "Chinese", "Japanese"],
            k=random.randint(1, 3),
        )
        agent["max_concurrent_chats"] = random.randint(3, 8)
        agent["is_available"] = random.random() > 0.3
        return agent

    def guest_user(self, **overrides: Any) -> dict:
        """Generate a guest user (no account)."""
        guest = {
            "id": self.fake.uuid(),
            "session_id": self.fake._faker.session_id(),
            "email": self.fake.email() if random.random() > 0.5 else None,
            "ip_address": self.fake._faker.ipv4(),
            "user_agent": self.fake._faker.user_agent(),
            "created_at": self.fake.datetime().isoformat(),
            "is_guest": True,
        }
        guest.update(overrides)
        return guest

    def user_profile(self, user_id: str | None = None, **overrides: Any) -> dict:
        """Generate a user profile."""
        profile = {
            "user_id": user_id or self.fake.uuid(),
            "display_name": self.fake.username(),
            "full_name": self.fake.name(),
            "avatar_url": self.fake._faker.avatar_url(),
            "cover_image_url": self.fake._faker.featured_image_url(),
            "bio": self.fake._faker.bio(300),
            "tagline": self.fake._faker.tagline(),
            "website": self.fake._faker.website_url(),
            "location": f"{self.fake.city()}, {self.fake.country()}",
            "timezone": random.choice([
                "America/New_York",
                "America/Los_Angeles",
                "Europe/London",
                "Europe/Paris",
                "Asia/Tokyo",
                "Australia/Sydney",
            ]),
            "language": random.choice(["en", "es", "fr", "de", "ja", "zh"]),
            "social_links": {
                "twitter": self.fake._faker.social_handle("twitter"),
                "linkedin": f"linkedin.com/in/{self.fake.username()}",
                "github": f"github.com/{self.fake.username()}",
            },
            "interests": self.fake.tags(random.randint(3, 8)),
            "is_public": random.random() > 0.3,
            "created_at": self.fake.datetime().isoformat(),
            "updated_at": self.fake.datetime().isoformat(),
        }
        profile.update(overrides)
        return profile

    def user_preferences(self, user_id: str | None = None, **overrides: Any) -> dict:
        """Generate user preferences/settings."""
        preferences = {
            "user_id": user_id or self.fake.uuid(),
            "theme": random.choice(["light", "dark", "system"]),
            "language": random.choice(["en", "es", "fr", "de", "ja"]),
            "timezone": random.choice([
                "America/New_York",
                "Europe/London",
                "Asia/Tokyo",
            ]),
            "notifications": {
                "email": {
                    "marketing": random.random() > 0.5,
                    "product_updates": random.random() > 0.3,
                    "order_updates": True,
                    "security_alerts": True,
                },
                "push": {
                    "enabled": random.random() > 0.4,
                    "sound": random.random() > 0.5,
                    "vibrate": random.random() > 0.5,
                },
                "sms": {
                    "enabled": random.random() > 0.7,
                    "order_updates": random.random() > 0.5,
                },
            },
            "privacy": {
                "profile_visible": random.random() > 0.3,
                "show_online_status": random.random() > 0.5,
                "allow_messages": random.random() > 0.4,
                "data_sharing": random.random() > 0.6,
            },
            "accessibility": {
                "high_contrast": random.random() > 0.9,
                "reduce_motion": random.random() > 0.9,
                "screen_reader_optimized": random.random() > 0.95,
            },
        }
        preferences.update(overrides)
        return preferences

    def login_credentials(self, **overrides: Any) -> dict:
        """Generate login credentials for testing."""
        password = self.fake.password()
        credentials = {
            "email": self.fake.email(),
            "password": password,
            "password_hash": self.fake._faker.password_hash(password),
            "remember_me": random.random() > 0.5,
        }
        credentials.update(overrides)
        return credentials

    def registration_data(self, **overrides: Any) -> dict:
        """Generate registration form data."""
        password = self.fake.password()
        data = {
            "email": self.fake.email(),
            "username": self.fake.username(),
            "password": password,
            "password_confirmation": password,
            "first_name": self.fake.first_name(),
            "last_name": self.fake.last_name(),
            "phone": self.fake.phone_number(),
            "date_of_birth": self.fake.date(start_date="-50y", end_date="-18y").isoformat(),
            "accept_terms": True,
            "accept_marketing": random.random() > 0.5,
            "referral_code": (
                self.fake._faker.referral_code()
                if random.random() > 0.7 else None
            ),
        }
        data.update(overrides)
        return data

    def password_reset_request(self, **overrides: Any) -> dict:
        """Generate password reset request data."""
        request = {
            "id": self.fake.uuid(),
            "user_id": self.fake.uuid(),
            "email": self.fake.email(),
            "token": self.fake.auth_token(),
            "ip_address": self.fake._faker.ipv4(),
            "user_agent": self.fake._faker.user_agent(),
            "created_at": self.fake.datetime().isoformat(),
            "expires_at": self.fake.future_datetime(days=1).isoformat(),
            "used_at": None,
            "is_valid": True,
        }
        request.update(overrides)
        return request

    def session(self, user_id: str | None = None, **overrides: Any) -> dict:
        """Generate a user session."""
        session = {
            "id": self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "token": self.fake.auth_token(),
            "refresh_token": self.fake.auth_token(),
            "ip_address": self.fake._faker.ipv4(),
            "user_agent": self.fake._faker.user_agent(),
            "device_type": random.choice(["desktop", "mobile", "tablet"]),
            "browser": random.choice(["Chrome", "Firefox", "Safari", "Edge"]),
            "os": random.choice(["Windows", "macOS", "Linux", "iOS", "Android"]),
            "location": {
                "country": self.fake.country(),
                "city": self.fake.city(),
                "coordinates": self.fake.coordinates(),
            },
            "is_active": True,
            "last_activity": self.fake.datetime().isoformat(),
            "created_at": self.fake.datetime().isoformat(),
            "expires_at": self.fake.future_datetime(days=7).isoformat(),
        }
        session.update(overrides)
        return session

    def api_credentials(self, user_id: str | None = None, **overrides: Any) -> dict:
        """Generate API credentials."""
        credentials = {
            "id": self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "name": f"{self.fake.word().title()} Integration",
            "api_key": self.fake.api_key(),
            "api_secret": self.fake.auth_token(),
            "scopes": random.sample(
                ["read", "write", "delete", "admin"],
                k=random.randint(1, 3),
            ),
            "rate_limit": random.choice([100, 500, 1000, 5000]),
            "is_active": True,
            "last_used": self.fake.past_datetime(days=7).isoformat(),
            "created_at": self.fake.datetime().isoformat(),
        }
        credentials.update(overrides)
        return credentials

    def oauth_authorization(self, user_id: str | None = None, **overrides: Any) -> dict:
        """Generate OAuth authorization data."""
        providers = ["google", "github", "facebook", "twitter", "apple"]
        auth = {
            "id": self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "provider": random.choice(providers),
            "provider_user_id": self.fake.uuid(),
            "access_token": self.fake.auth_token(),
            "refresh_token": self.fake.auth_token(),
            "token_expires_at": self.fake.future_datetime(days=30).isoformat(),
            "scopes": ["profile", "email"],
            "created_at": self.fake.datetime().isoformat(),
            "updated_at": self.fake.datetime().isoformat(),
        }
        auth.update(overrides)
        return auth

    def two_factor_setup(self, user_id: str | None = None, **overrides: Any) -> dict:
        """Generate 2FA setup data."""
        setup = {
            "user_id": user_id or self.fake.uuid(),
            "method": random.choice(["totp", "sms", "email"]),
            "secret": self.fake.auth_token()[:32],
            "backup_codes": [
                self.fake._faker.verification_code(8)
                for _ in range(10)
            ],
            "phone_number": self.fake.phone_number() if random.random() > 0.5 else None,
            "is_enabled": True,
            "verified_at": self.fake.datetime().isoformat(),
        }
        setup.update(overrides)
        return setup

    def team(self, **overrides: Any) -> dict:
        """Generate a team."""
        team = {
            "id": self.fake.uuid(),
            "name": f"{self.fake.company()} Team",
            "slug": self.fake.username(),
            "description": self.fake.text(200),
            "avatar_url": self.fake._faker.avatar_url(),
            "owner_id": self.fake.uuid(),
            "member_count": random.randint(1, 50),
            "plan": random.choice(["free", "pro", "enterprise"]),
            "settings": {
                "allow_member_invites": random.random() > 0.5,
                "require_2fa": random.random() > 0.7,
                "default_role": "member",
            },
            "created_at": self.fake.datetime().isoformat(),
            "updated_at": self.fake.datetime().isoformat(),
        }
        team.update(overrides)
        return team

    def team_member(
        self,
        team_id: str | None = None,
        user_id: str | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a team member."""
        roles = ["owner", "admin", "member", "viewer"]
        member = {
            "id": self.fake.uuid(),
            "team_id": team_id or self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "user": self.fake.user(),
            "role": random.choice(roles),
            "permissions": random.sample(
                ["read", "write", "delete", "invite", "manage"],
                k=random.randint(1, 4),
            ),
            "invited_by": self.fake.uuid(),
            "joined_at": self.fake.datetime().isoformat(),
        }
        member.update(overrides)
        return member

    def team_with_members(
        self,
        member_count: int = 5,
        **overrides: Any,
    ) -> dict:
        """Generate a team with members."""
        team = self.team(**overrides)
        team_id = team["id"]

        # First member is always the owner
        members = [
            self.team_member(team_id=team_id, role="owner", user_id=team["owner_id"])
        ]

        # Add additional members
        for _ in range(member_count - 1):
            members.append(self.team_member(team_id=team_id))

        team["members"] = members
        team["member_count"] = len(members)
        return team

    def team_invitation(
        self,
        team_id: str | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a team invitation."""
        invitation = {
            "id": self.fake.uuid(),
            "team_id": team_id or self.fake.uuid(),
            "email": self.fake.email(),
            "role": random.choice(["admin", "member", "viewer"]),
            "token": self.fake.auth_token(),
            "invited_by": self.fake.uuid(),
            "status": random.choice(["pending", "accepted", "expired", "revoked"]),
            "created_at": self.fake.datetime().isoformat(),
            "expires_at": self.fake.future_datetime(days=7).isoformat(),
        }
        invitation.update(overrides)
        return invitation

    def permission(self, **overrides: Any) -> dict:
        """Generate a permission."""
        resources = ["users", "products", "orders", "reports", "settings"]
        actions = ["create", "read", "update", "delete", "manage"]

        permission = {
            "id": self.fake.uuid(),
            "name": f"{random.choice(resources)}:{random.choice(actions)}",
            "description": self.fake.sentence(),
            "resource": random.choice(resources),
            "action": random.choice(actions),
            "conditions": (
                {"own_only": True}
                if random.random() > 0.7 else None
            ),
        }
        permission.update(overrides)
        return permission

    def role(self, **overrides: Any) -> dict:
        """Generate a role with permissions."""
        role_names = ["admin", "manager", "editor", "viewer", "support"]
        name = random.choice(role_names)

        role = {
            "id": self.fake.uuid(),
            "name": name,
            "display_name": name.title(),
            "description": self.fake.text(100),
            "permissions": [self.permission() for _ in range(random.randint(3, 10))],
            "is_system": random.random() > 0.8,
            "created_at": self.fake.datetime().isoformat(),
        }
        role.update(overrides)
        return role

    def user_activity(
        self,
        user_id: str | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a user activity log entry."""
        actions = [
            "login",
            "logout",
            "password_change",
            "profile_update",
            "settings_change",
            "order_placed",
            "payment_made",
            "item_viewed",
            "search_performed",
            "file_uploaded",
        ]

        activity = {
            "id": self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "action": random.choice(actions),
            "resource_type": random.choice(["user", "order", "product", "file"]),
            "resource_id": self.fake.uuid(),
            "ip_address": self.fake._faker.ipv4(),
            "user_agent": self.fake._faker.user_agent(),
            "metadata": {
                "browser": random.choice(["Chrome", "Firefox", "Safari"]),
                "device": random.choice(["desktop", "mobile"]),
            },
            "created_at": self.fake.datetime().isoformat(),
        }
        activity.update(overrides)
        return activity

    def activity_log(
        self,
        user_id: str | None = None,
        count: int = 20,
    ) -> list[dict]:
        """Generate a user activity log."""
        user_id = user_id or self.fake.uuid()
        activities = []

        for _ in range(count):
            activity = self.user_activity(user_id=user_id)
            activities.append(activity)

        return sorted(activities, key=lambda x: x["created_at"], reverse=True)

    def notification(
        self,
        user_id: str | None = None,
        **overrides: Any,
    ) -> dict:
        """Generate a user notification."""
        types = [
            "order_update",
            "payment_received",
            "message_received",
            "mention",
            "comment",
            "follow",
            "like",
            "system",
        ]

        notification = {
            "id": self.fake.uuid(),
            "user_id": user_id or self.fake.uuid(),
            "type": random.choice(types),
            "title": self.fake.sentence(words=5),
            "message": self.fake.text(150),
            "action_url": self.fake.url() if random.random() > 0.3 else None,
            "is_read": random.random() > 0.6,
            "read_at": (
                self.fake.datetime().isoformat()
                if random.random() > 0.6 else None
            ),
            "created_at": self.fake.datetime().isoformat(),
        }
        notification.update(overrides)
        return notification

    def notifications(
        self,
        user_id: str | None = None,
        count: int = 10,
    ) -> list[dict]:
        """Generate multiple notifications."""
        user_id = user_id or self.fake.uuid()
        return [
            self.notification(user_id=user_id)
            for _ in range(count)
        ]

    def user_stats(self, user_id: str | None = None, **overrides: Any) -> dict:
        """Generate user statistics."""
        stats = {
            "user_id": user_id or self.fake.uuid(),
            "orders_count": random.randint(0, 100),
            "total_spent": round(random.uniform(0, 10000), 2),
            "average_order_value": round(random.uniform(20, 200), 2),
            "reviews_count": random.randint(0, 50),
            "average_rating_given": round(random.uniform(3, 5), 1),
            "referrals_count": random.randint(0, 20),
            "referral_earnings": round(random.uniform(0, 500), 2),
            "points_balance": random.randint(0, 5000),
            "member_since": self.fake.date(start_date="-5y").isoformat(),
            "last_order_date": self.fake.past_date(days=90).isoformat(),
            "last_login": self.fake.past_datetime(days=7).isoformat(),
        }
        stats.update(overrides)
        return stats


# Global instance for convenience
users = UserGenerator()


def create_user_generator(
    locale: str = "en_US",
    seed: int | None = None,
) -> UserGenerator:
    """Create a new UserGenerator with custom settings.

    Args:
        locale: Locale for generated data.
        seed: Seed for reproducible generation.

    Returns:
        A configured UserGenerator instance.
    """
    from venomqa.data.generators import create_fake

    return UserGenerator(fake=create_fake(locale, seed))
