"""Authentication domain journeys and actions.

Provides journey templates for:
- User registration with email verification
- OAuth flows (Google, GitHub, etc.)
- Password reset and change flows
"""

from venomqa.domains.auth.journeys.oauth import (
    oauth_github_flow,
    oauth_google_flow,
    oauth_linking_flow,
)
from venomqa.domains.auth.journeys.password import (
    password_change_flow,
    password_reset_flow,
    password_strength_flow,
)
from venomqa.domains.auth.journeys.registration import (
    email_verification_flow,
    registration_flow,
    registration_with_profile_flow,
)

__all__ = [
    "registration_flow",
    "email_verification_flow",
    "registration_with_profile_flow",
    "oauth_google_flow",
    "oauth_github_flow",
    "oauth_linking_flow",
    "password_reset_flow",
    "password_change_flow",
    "password_strength_flow",
]
