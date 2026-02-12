"""User test data fixtures for authentication journeys.

Factory-based test data generation.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from venomqa.fixtures.factory import DataFactory, LazyAttribute, LazyFunction


@dataclass
class User:
    id: int
    email: str
    username: str
    name: str
    is_active: bool
    is_verified: bool
    role: str
    created_at: datetime


@dataclass
class UserProfile:
    user_id: int
    bio: str | None
    avatar_url: str | None
    timezone: str
    preferences: dict


@dataclass
class APIKey:
    id: int
    user_id: int
    name: str
    key_hash: str
    scopes: list
    expires_at: datetime | None
    created_at: datetime


class UserFactory(DataFactory[User]):
    _model = User

    id: int = LazyFunction(lambda: UserFactory._get_faker().random_int(min=1, max=99999))
    email: LazyAttribute = LazyAttribute(lambda _: UserFactory._get_faker().email())
    username: LazyAttribute = LazyAttribute(lambda _: UserFactory._get_faker().user_name())
    name: LazyAttribute = LazyAttribute(lambda _: UserFactory._get_faker().name())
    is_active: bool = True
    is_verified: bool = True
    role: LazyAttribute = LazyAttribute(
        lambda _: UserFactory._get_faker().random_element(["user", "admin", "moderator"])
    )
    created_at: LazyAttribute = LazyAttribute(
        lambda _: UserFactory._get_faker().date_time_this_year()
    )

    @classmethod
    def admin(cls, **kwargs: Any) -> User:
        return cls.build(role="admin", **kwargs)

    @classmethod
    def moderator(cls, **kwargs: Any) -> User:
        return cls.build(role="moderator", **kwargs)

    @classmethod
    def unverified(cls, **kwargs: Any) -> User:
        return cls.build(is_verified=False, **kwargs)

    @classmethod
    def inactive(cls, **kwargs: Any) -> User:
        return cls.build(is_active=False, **kwargs)


class UserProfileFactory(DataFactory[UserProfile]):
    _model = UserProfile

    user_id: int = LazyFunction(
        lambda: UserProfileFactory._get_faker().random_int(min=1, max=99999)
    )
    bio: LazyAttribute = LazyAttribute(lambda _: UserProfileFactory._get_faker().sentence())
    avatar_url: LazyAttribute = LazyAttribute(lambda _: UserProfileFactory._get_faker().image_url())
    timezone: LazyAttribute = LazyAttribute(lambda _: UserProfileFactory._get_faker().timezone())
    preferences: dict = {}


class APIKeyFactory(DataFactory[APIKey]):
    _model = APIKey

    id: int = LazyFunction(lambda: APIKeyFactory._get_faker().random_int(min=1, max=99999))
    user_id: int = LazyFunction(lambda: APIKeyFactory._get_faker().random_int(min=1, max=99999))
    name: LazyAttribute = LazyAttribute(lambda _: APIKeyFactory._get_faker().word() + " Key")
    key_hash: LazyAttribute = LazyAttribute(lambda _: APIKeyFactory._get_faker().sha256())
    scopes: list = []
    expires_at: datetime | None = None
    created_at: LazyAttribute = LazyAttribute(
        lambda _: APIKeyFactory._get_faker().date_time_this_year()
    )

    @classmethod
    def with_scopes(cls, scopes: list, **kwargs: Any) -> APIKey:
        return cls.build(scopes=scopes, **kwargs)

    @classmethod
    def expired(cls, **kwargs: Any) -> APIKey:
        return cls.build(
            expires_at=APIKeyFactory._get_faker().date_time_this_year(before_now=True), **kwargs
        )
