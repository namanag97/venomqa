"""Autonomous VenomQA - zero-config API testing.

VenomQA reads your project's docker-compose.yml and OpenAPI spec,
spins up isolated test containers, and explores your API automatically.

Usage:
    venomqa  # Just run in your project directory

What happens:
    1. Finds docker-compose.yml -> understands your stack
    2. Finds openapi.yaml/swagger.json -> generates actions
    3. Spins up ISOLATED test containers (copies your setup)
    4. Runs state hypergraph exploration
    5. Reports bugs found
    6. Tears down containers
"""

from venomqa.autonomous.discovery import ProjectDiscovery
from venomqa.autonomous.runner import AutonomousRunner

__all__ = [
    "ProjectDiscovery",
    "AutonomousRunner",
]
