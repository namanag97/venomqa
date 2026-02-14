"""State management module for VenomQA.

This module provides state management backends for test isolation and
database checkpointing. Each backend implements the StateManager protocol,
providing consistent APIs for creating checkpoints, rolling back state,
and resetting databases between tests.

Available Backends:
    - InMemoryStateManager: Fast in-memory snapshots for unit tests
    - SQLiteStateManager: SQLite savepoints for file-based testing
    - PostgreSQLStateManager: PostgreSQL savepoints for production-like tests
    - MySQLStateManager: MySQL savepoints for MySQL-specific testing

Quick Start:
    >>> from venomqa.state import StateManagerFactory
    >>>
    >>> # Create and use a state manager
    >>> with StateManagerFactory.from_url("memory://test") as state:
    ...     state.checkpoint("initial")
    ...     # ... perform operations ...
    ...     state.rollback("initial")  # Restore state

Factory Methods:
    StateManagerFactory provides convenient methods for creating managers:
    - create(backend, url, **kwargs): Create from backend name
    - from_config(config_dict): Create from configuration dictionary
    - from_url(url, **kwargs): Auto-detect backend from URL scheme
    - create_for_testing(): Quick setup for unit tests
"""

from venomqa.state.base import BaseStateManager, StateManager
from venomqa.state.factory import StateManagerFactory
from venomqa.state.memory import InMemoryStateManager
from venomqa.state.mysql import MySQLStateManager
from venomqa.state.postgres import PostgreSQLStateManager
from venomqa.state.sqlite import SQLiteStateManager

__all__ = [
    "StateManager",
    "BaseStateManager",
    "PostgreSQLStateManager",
    "SQLiteStateManager",
    "MySQLStateManager",
    "InMemoryStateManager",
    "StateManagerFactory",
]
