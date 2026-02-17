"""High-level setup helpers for VenomQA.

This module provides simple abstractions for users to configure VenomQA
based on their codebase, without needing to understand ASGI, dependency
injection, or database connection sharing details.

Usage:
    from venomqa.v1.setup import connect_to_app

    # Option 1: FastAPI with PostgreSQL (in-process, full rollback)
    world = connect_to_app(
        app=my_fastapi_app,
        db_dependency=get_db,  # Your Depends(get_db) function
        db_url="postgresql://...",
    )

    # Option 2: External API with separate DB connection (limited rollback)
    world = connect_to_api(
        api_url="http://localhost:8000",
        db_url="postgresql://...",
    )

    # Option 3: Stateless API (no database)
    world = connect_to_api(
        api_url="http://localhost:8000",
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from venomqa.v1.world import World


class AppType(Enum):
    """Type of application being tested."""

    FASTAPI = "fastapi"
    STARLETTE = "starlette"
    FLASK = "flask"
    DJANGO = "django"
    EXTERNAL_HTTP = "external_http"


class DatabaseType(Enum):
    """Type of database used by the application."""

    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"
    MYSQL = "mysql"
    NONE = "none"


@dataclass
class AppConfig:
    """Configuration for connecting VenomQA to an application."""

    app_type: AppType
    db_type: DatabaseType

    # For in-process apps (FastAPI, Starlette)
    app: Any = None
    db_dependency: Callable | None = None

    # For external APIs
    api_url: str | None = None

    # Database connection
    db_url: str | None = None

    # SQLite specific
    db_path: str | None = None


def detect_app_type(app: Any) -> AppType:
    """Auto-detect the type of application."""
    app_class = type(app).__name__
    module = type(app).__module__

    if "fastapi" in module.lower() or app_class == "FastAPI":
        return AppType.FASTAPI
    elif "starlette" in module.lower() or app_class == "Starlette":
        return AppType.STARLETTE
    elif "flask" in module.lower() or app_class == "Flask":
        return AppType.FLASK
    elif "django" in module.lower():
        return AppType.DJANGO
    else:
        raise ValueError(
            f"Unknown app type: {app_class} from {module}. "
            "Use connect_to_api() for external HTTP APIs."
        )


def detect_db_type(url: str) -> DatabaseType:
    """Auto-detect database type from URL."""
    url_lower = url.lower()

    if url_lower.startswith("postgresql://") or url_lower.startswith("postgres://"):
        return DatabaseType.POSTGRESQL
    elif url_lower.startswith("sqlite://") or url_lower.endswith(".db"):
        return DatabaseType.SQLITE
    elif url_lower.startswith("mysql://"):
        return DatabaseType.MYSQL
    else:
        raise ValueError(
            f"Unknown database URL format: {url}. "
            "Expected postgresql://, sqlite://, or mysql://"
        )


def connect_to_app(
    app: Any,
    db_dependency: Callable,
    db_url: str,
    async_mode: bool = False,
) -> "World":
    """Connect VenomQA to an in-process application (FastAPI, Starlette).

    This is the RECOMMENDED setup for full SAVEPOINT rollback support.
    VenomQA shares its database connection with your app, so rollback
    actually undoes the writes.

    Args:
        app: Your FastAPI or Starlette application instance
        db_dependency: The dependency function used by your app (e.g., get_db)
        db_url: PostgreSQL or SQLite connection URL
        async_mode: Set True if your app uses async SQLAlchemy

    Returns:
        A configured World instance ready for Agent.explore()

    Example:
        from fastapi import FastAPI, Depends
        from myapp import app, get_db

        world = connect_to_app(
            app=app,
            db_dependency=get_db,
            db_url=os.environ["DATABASE_URL"],
        )

        agent = Agent(world=world, actions=[...], invariants=[...])
        result = agent.explore()
    """
    from venomqa.v1.adapters.asgi import ASGIAdapter, SharedPostgresAdapter
    from venomqa.v1.world import World

    app_type = detect_app_type(app)
    db_type = detect_db_type(db_url)

    if app_type not in (AppType.FASTAPI, AppType.STARLETTE):
        raise ValueError(
            f"connect_to_app() only supports FastAPI and Starlette. "
            f"Got: {app_type.value}. Use connect_to_api() for external HTTP APIs."
        )

    if db_type == DatabaseType.POSTGRESQL:
        # Full in-process setup with shared PostgreSQL connection
        db_adapter = SharedPostgresAdapter(
            url=db_url,
            app=app,
            dependency=db_dependency,
            async_mode=async_mode,
        )
        db_adapter.setup()

        return World(
            api=ASGIAdapter(app),
            systems={"db": db_adapter},
        )

    elif db_type == DatabaseType.SQLITE:
        # SQLite in-process (simpler, doesn't need connection sharing)
        from venomqa.v1.adapters.sqlite import SQLiteAdapter

        # Extract path from URL
        if db_url.startswith("sqlite:///"):
            db_path = db_url[10:]
        else:
            db_path = db_url

        return World(
            api=ASGIAdapter(app),
            systems={"db": SQLiteAdapter(db_path)},
        )

    else:
        raise ValueError(f"Unsupported database type for in-process: {db_type.value}")


def connect_to_api(
    api_url: str,
    db_url: str | None = None,
    state_keys: list[str] | None = None,
) -> "World":
    """Connect VenomQA to an external HTTP API.

    Use this when:
    - Your API runs as a separate process (Docker, etc.)
    - You can't modify the app to share connections
    - You're testing a third-party API

    Note: If you provide db_url, VenomQA will connect to the database
    SEPARATELY from the API. This means:
    - API commits are immediately visible
    - ROLLBACK only works if API hasn't committed yet
    - For full rollback support, use connect_to_app() instead

    Args:
        api_url: Base URL of the API (e.g., "http://localhost:8000")
        db_url: Optional database URL for state tracking
        state_keys: Context keys to track for state identity (if no db_url)

    Returns:
        A configured World instance

    Example:
        # With database (limited rollback)
        world = connect_to_api(
            api_url="http://localhost:8000",
            db_url="postgresql://user:pass@localhost/mydb",
        )

        # Without database (context-based state)
        world = connect_to_api(
            api_url="http://localhost:8000",
            state_keys=["user_id", "session_id"],
        )
    """
    from venomqa.v1.adapters.http import HttpClient
    from venomqa.v1.world import World

    api = HttpClient(api_url)

    if db_url:
        db_type = detect_db_type(db_url)

        if db_type == DatabaseType.POSTGRESQL:
            from venomqa.v1.adapters.postgres import PostgresAdapter
            return World(
                api=api,
                systems={"db": PostgresAdapter(db_url)},
            )
        elif db_type == DatabaseType.SQLITE:
            from venomqa.v1.adapters.sqlite import SQLiteAdapter
            if db_url.startswith("sqlite:///"):
                db_path = db_url[10:]
            else:
                db_path = db_url
            return World(
                api=api,
                systems={"db": SQLiteAdapter(db_path)},
            )
        elif db_type == DatabaseType.MYSQL:
            from venomqa.v1.adapters.mysql import MySQLAdapter
            return World(
                api=api,
                systems={"db": MySQLAdapter(db_url)},
            )

    # No database - use context-based state
    return World(
        api=api,
        state_from_context=state_keys or [],
    )


def setup_from_config(
    config_path: str = "venomqa/venomqa.yaml",
    app: Any = None,
    db_dependency: Callable | None = None,
) -> "World":
    """Set up VenomQA from a configuration file.

    Reads venomqa.yaml and creates the appropriate World.

    Args:
        config_path: Path to venomqa.yaml
        app: Optional FastAPI app for in-process mode
        db_dependency: Required if app is provided

    Returns:
        A configured World instance
    """
    import yaml
    from pathlib import Path

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            "Run 'venomqa init' to create one."
        )

    with open(config_file) as f:
        config = yaml.safe_load(f)

    api_url = config.get("base_url")
    db_url = config.get("db_url")
    state_keys = config.get("state_from_context", [])

    # Expand environment variables
    import os
    if db_url and db_url.startswith("${") and db_url.endswith("}"):
        env_var = db_url[2:-1]
        db_url = os.environ.get(env_var)

    if app and db_dependency:
        return connect_to_app(
            app=app,
            db_dependency=db_dependency,
            db_url=db_url,
        )
    else:
        return connect_to_api(
            api_url=api_url,
            db_url=db_url,
            state_keys=state_keys,
        )
