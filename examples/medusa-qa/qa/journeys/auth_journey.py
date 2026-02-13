"""Authentication journey - test login, logout flows."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from venomqa import Journey, Step

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "actions"))
from auth_actions import admin_login, admin_logout, customer_register, customer_login, customer_logout


admin_auth_journey = Journey(
    name="admin_authentication",
    description="Test admin login and logout flow",
    steps=[
        Step(
            name="admin_login",
            action=admin_login,
            description="Login as admin user",
        ),
        Step(
            name="admin_logout",
            action=admin_logout,
            description="Logout admin user",
        ),
    ],
)


customer_auth_journey = Journey(
    name="customer_authentication",
    description="Test customer registration and login flow",
    steps=[
        Step(
            name="customer_register",
            action=customer_register,
            description="Register a new customer",
        ),
        Step(
            name="customer_login",
            action=customer_login,
            description="Login as customer",
        ),
        Step(
            name="customer_logout",
            action=customer_logout,
            description="Logout customer",
        ),
    ],
)
