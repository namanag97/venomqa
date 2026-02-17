"""Dimension enums for multi-dimensional state space exploration."""

from __future__ import annotations

from enum import Enum


class AuthStatus(Enum):
    """Authentication status dimension."""

    ANON = "anon"         # Not authenticated
    AUTH = "auth"         # Authenticated with standard privileges
    EXPIRED = "expired"   # Token expired


class UserRole(Enum):
    """User role dimension."""

    NONE = "none"         # No role (anon users)
    USER = "user"         # Standard user
    ADMIN = "admin"       # Administrator
    SUPERADMIN = "superadmin"  # Super administrator


class EntityStatus(Enum):
    """Generic entity lifecycle status dimension."""

    NONE = "none"         # No entity in context
    ACTIVE = "active"     # Entity is active
    INACTIVE = "inactive" # Entity is inactive / soft-deleted
    PENDING = "pending"   # Entity awaiting activation
    ARCHIVED = "archived" # Entity archived


class CountClass(Enum):
    """Ordinal bucket for collection sizes."""

    ZERO = "zero"         # Empty collection
    ONE = "one"           # Exactly one item
    FEW = "few"           # 2-10 items
    MANY = "many"         # 10+ items


class UsageClass(Enum):
    """Dimension tracking resource usage level."""

    NONE = "none"         # No usage
    LOW = "low"           # Below 25% of limit
    MEDIUM = "medium"     # 25-75%
    HIGH = "high"         # 75-99%
    EXCEEDED = "exceeded" # At or over limit


class PlanType(Enum):
    """Subscription / plan tier dimension."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# The canonical set of built-in dimension names (key used in Hyperedge.dimensions)
BUILTIN_DIMENSIONS: dict[str, type[Enum]] = {
    "auth": AuthStatus,
    "role": UserRole,
    "entity_status": EntityStatus,
    "count": CountClass,
    "usage": UsageClass,
    "plan": PlanType,
}
