"""Environment management for VenomQA.

This module provides comprehensive environment management for testing across
different environments (local, staging, production, etc.).

Key Features:
    - Environment configuration loading from YAML
    - Environment-specific behavior (read-only mode, disable state management)
    - Secret management per environment (.env files, AWS Secrets Manager, Vault)
    - Environment health checks
    - Environment comparison (run same journey in multiple environments)

Example:
    Basic environment configuration in venomqa.yaml::

        environments:
          local:
            base_url: http://localhost:8000
            database: postgresql://localhost/test
          staging:
            base_url: https://staging.example.com
            database: postgresql://staging-db/test
          production:
            base_url: https://api.example.com
            database: null  # No direct DB access
            read_only: true

        default_environment: local

    Using the environment manager::

        from venomqa.environments import EnvironmentManager

        manager = EnvironmentManager("venomqa.yaml")
        env = manager.get_environment("staging")

        # Check environment health
        health = manager.check_health("staging")

        # Compare environments
        comparison = manager.compare_environments(
            journey=my_journey,
            env1="staging",
            env2="production"
        )

See Also:
    - EnvironmentManager: Main environment management class
    - Environment: Single environment configuration
    - EnvironmentComparison: Compare journey results across environments
    - EnvironmentHealthCheck: Health check results
"""

from venomqa.environments.manager import (
    Environment,
    EnvironmentComparison,
    EnvironmentConfig,
    EnvironmentHealthCheck,
    EnvironmentHealthResult,
    EnvironmentManager,
    EnvironmentSecrets,
    ResponseDifference,
    SecretProvider,
)

__all__ = [
    "Environment",
    "EnvironmentConfig",
    "EnvironmentManager",
    "EnvironmentSecrets",
    "EnvironmentHealthCheck",
    "EnvironmentHealthResult",
    "EnvironmentComparison",
    "ResponseDifference",
    "SecretProvider",
]
