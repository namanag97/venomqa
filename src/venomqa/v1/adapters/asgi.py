"""ASGI Adapter for in-process API testing.

This adapter runs your FastAPI/Starlette app in the SAME process as VenomQA,
allowing database transactions to be shared. This is the ONLY way to make
SAVEPOINT rollback work across API writes.

How it works:
    1. VenomQA creates ONE database connection and begins a transaction
    2. Your app runs via ASGI (no HTTP, same process)
    3. Your app's database dependency is overridden to use VenomQA's connection
    4. All writes go through the same transaction
    5. ROLLBACK TO SAVEPOINT actually undoes the writes

Usage:
    from fastapi import FastAPI, Depends
    from venomqa.v1 import World, Agent
    from venomqa.v1.adapters.asgi import ASGIAdapter, SharedPostgresAdapter

    app = FastAPI()

    # Your normal dependency
    def get_db():
        return SessionLocal()

    @app.post("/users")
    def create_user(db = Depends(get_db)):
        ...

    # VenomQA setup - shares connection with app
    db_adapter = SharedPostgresAdapter(
        url="postgresql://...",
        app=app,
        dependency=get_db,  # VenomQA will override this
    )

    world = World(
        api=ASGIAdapter(app),
        systems={"db": db_adapter},
    )

    agent = Agent(world=world, actions=[...], invariants=[...])
    result = agent.explore()  # SAVEPOINT rollback works!
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

try:
    from starlette.testclient import TestClient
except ImportError:
    TestClient = None  # type: ignore

try:
    from httpx import Response as HttpxResponse
except ImportError:
    HttpxResponse = None  # type: ignore


@dataclass
class ASGIResponse:
    """Response wrapper that matches VenomQA's expected interface."""

    status_code: int
    headers: dict[str, str]
    content: bytes
    _json: Any = field(default=None, repr=False)

    def json(self) -> Any:
        """Parse response body as JSON."""
        if self._json is None:
            self._json = json.loads(self.content)
        return self._json

    @property
    def text(self) -> str:
        """Return response body as text."""
        return self.content.decode("utf-8")

    def expect_status(self, *expected: int) -> None:
        """Assert status code is one of the expected values."""
        if self.status_code not in expected:
            raise AssertionError(
                f"Expected status {expected}, got {self.status_code}: {self.text}"
            )

    def expect_json(self) -> Any:
        """Assert response is valid JSON and return it."""
        try:
            return self.json()
        except json.JSONDecodeError as e:
            raise AssertionError(f"Expected JSON response, got: {self.text}") from e

    def expect_json_field(self, field: str) -> Any:
        """Assert JSON response has a field and return the full JSON."""
        data = self.expect_json()
        if field not in data:
            raise AssertionError(f"Expected field '{field}' in response: {data}")
        return data

    def expect_json_list(self) -> list:
        """Assert response is a JSON array and return it."""
        data = self.expect_json()
        if not isinstance(data, list):
            raise AssertionError(f"Expected JSON array, got: {type(data).__name__}")
        return data


class ASGIAdapter:
    """HTTP client that calls ASGI apps in-process (no network).

    This adapter uses Starlette's TestClient to make requests directly
    to your ASGI application without going through HTTP. This means:

    1. No network overhead (faster tests)
    2. Same process = can share database connections
    3. SAVEPOINT rollback works because writes use VenomQA's connection

    Example:
        from fastapi import FastAPI
        from venomqa.v1.adapters.asgi import ASGIAdapter

        app = FastAPI()

        @app.get("/health")
        def health():
            return {"status": "ok"}

        # Use ASGIAdapter instead of HttpClient
        api = ASGIAdapter(app)
        resp = api.get("/health")
        assert resp.json() == {"status": "ok"}
    """

    def __init__(
        self,
        app: Any,
        base_url: str = "http://testserver",
        raise_server_exceptions: bool = False,
    ):
        """Initialize ASGI adapter.

        Args:
            app: ASGI application (FastAPI, Starlette, etc.)
            base_url: Base URL for requests (only used for headers, no actual network)
            raise_server_exceptions: If True, re-raise exceptions from the app
        """
        if TestClient is None:
            raise ImportError(
                "ASGIAdapter requires 'starlette' or 'fastapi'. "
                "Install with: pip install starlette"
            )

        self.app = app
        self.base_url = base_url.rstrip("/")
        self._client = TestClient(
            app,
            base_url=base_url,
            raise_server_exceptions=raise_server_exceptions,
        )

    def _make_response(self, httpx_resp: Any) -> ASGIResponse:
        """Convert httpx Response to ASGIResponse."""
        return ASGIResponse(
            status_code=httpx_resp.status_code,
            headers=dict(httpx_resp.headers),
            content=httpx_resp.content,
        )

    def get(self, path: str, **kwargs: Any) -> ASGIResponse:
        """Send GET request to the ASGI app."""
        resp = self._client.get(path, **kwargs)
        return self._make_response(resp)

    def post(self, path: str, **kwargs: Any) -> ASGIResponse:
        """Send POST request to the ASGI app."""
        resp = self._client.post(path, **kwargs)
        return self._make_response(resp)

    def put(self, path: str, **kwargs: Any) -> ASGIResponse:
        """Send PUT request to the ASGI app."""
        resp = self._client.put(path, **kwargs)
        return self._make_response(resp)

    def patch(self, path: str, **kwargs: Any) -> ASGIResponse:
        """Send PATCH request to the ASGI app."""
        resp = self._client.patch(path, **kwargs)
        return self._make_response(resp)

    def delete(self, path: str, **kwargs: Any) -> ASGIResponse:
        """Send DELETE request to the ASGI app."""
        resp = self._client.delete(path, **kwargs)
        return self._make_response(resp)

    def request(self, method: str, path: str, **kwargs: Any) -> ASGIResponse:
        """Send arbitrary request to the ASGI app."""
        resp = self._client.request(method, path, **kwargs)
        return self._make_response(resp)


class SharedPostgresAdapter:
    """PostgreSQL adapter that shares its connection with a FastAPI app.

    This adapter:
    1. Creates a single database connection
    2. Begins a transaction with SAVEPOINTs
    3. Overrides your app's database dependency to use this connection
    4. Allows ROLLBACK TO SAVEPOINT to undo all writes

    This is the KEY to making VenomQA's state exploration work with real APIs.

    Example:
        from fastapi import FastAPI, Depends
        from sqlalchemy.orm import Session

        app = FastAPI()

        def get_db():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        @app.post("/users")
        def create_user(name: str, db: Session = Depends(get_db)):
            user = User(name=name)
            db.add(user)
            db.commit()
            return {"id": user.id}

        # VenomQA setup
        db_adapter = SharedPostgresAdapter(
            url="postgresql://user:pass@localhost/mydb",
            app=app,
            dependency=get_db,
        )

        # Now when VenomQA calls the API:
        # 1. The POST /users uses db_adapter's connection
        # 2. db.commit() commits to a SAVEPOINT, not the real DB
        # 3. db_adapter.rollback() undoes the insert
    """

    def __init__(
        self,
        url: str,
        app: Any,
        dependency: Callable,
        async_mode: bool = False,
    ):
        """Initialize shared PostgreSQL adapter.

        Args:
            url: PostgreSQL connection URL
            app: FastAPI/Starlette application
            dependency: The database dependency function to override (e.g., get_db)
            async_mode: Use async SQLAlchemy (for async FastAPI apps)
        """
        self.url = url
        self.app = app
        self.dependency = dependency
        self.async_mode = async_mode

        self._connection = None
        self._session = None
        self._savepoint_stack: list[str] = []
        self._savepoint_counter = 0
        self._original_override = None

        # Lazy imports
        self._engine = None
        self._Session = None

    def _setup_sync(self) -> None:
        """Set up synchronous SQLAlchemy connection."""
        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import sessionmaker

        self._engine = create_engine(self.url)
        self._connection = self._engine.connect()
        self._transaction = self._connection.begin()

        # Create session bound to this connection
        self._Session = sessionmaker(bind=self._connection)
        self._session = self._Session()

        # Event listener: restart SAVEPOINT after app commits
        @event.listens_for(self._session, "after_transaction_end")
        def restart_savepoint(session, transaction):
            if transaction.nested and not transaction._parent.nested:
                # App committed a SAVEPOINT, start a new one
                session.begin_nested()

        # Start initial SAVEPOINT
        self._session.begin_nested()

        # Override app's dependency
        self._original_override = self.app.dependency_overrides.get(self.dependency)
        self.app.dependency_overrides[self.dependency] = lambda: self._session

    async def _setup_async(self) -> None:
        """Set up async SQLAlchemy connection."""
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        self._engine = create_async_engine(self.url)
        self._connection = await self._engine.connect()
        self._transaction = await self._connection.begin()

        # Create async session with savepoint mode
        self._session = AsyncSession(
            bind=self._connection,
            join_transaction_mode="create_savepoint",
        )

        # Override app's dependency
        self._original_override = self.app.dependency_overrides.get(self.dependency)

        async def get_shared_session():
            return self._session

        self.app.dependency_overrides[self.dependency] = get_shared_session

    def setup(self) -> None:
        """Initialize the shared connection and override app dependency."""
        if self.async_mode:
            import asyncio
            asyncio.get_event_loop().run_until_complete(self._setup_async())
        else:
            self._setup_sync()

    def checkpoint(self) -> str:
        """Create a SAVEPOINT and return its name."""
        self._savepoint_counter += 1
        name = f"venomqa_sp_{self._savepoint_counter}"

        if self.async_mode:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                self._connection.execute(f"SAVEPOINT {name}")
            )
        else:
            self._connection.execute(f"SAVEPOINT {name}")

        self._savepoint_stack.append(name)
        return name

    def rollback(self, savepoint_name: str | None = None) -> None:
        """Rollback to a SAVEPOINT."""
        if savepoint_name is None:
            if not self._savepoint_stack:
                raise RuntimeError("No savepoint to rollback to")
            savepoint_name = self._savepoint_stack[-1]

        if self.async_mode:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            )
        else:
            self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")

        # Remove rolled-back savepoints from stack
        while self._savepoint_stack and self._savepoint_stack[-1] != savepoint_name:
            self._savepoint_stack.pop()

    def cleanup(self) -> None:
        """Clean up: rollback transaction and restore app dependency."""
        # Restore original dependency override
        if self._original_override is not None:
            self.app.dependency_overrides[self.dependency] = self._original_override
        elif self.dependency in self.app.dependency_overrides:
            del self.app.dependency_overrides[self.dependency]

        # Rollback the entire transaction
        if self.async_mode:
            import asyncio
            loop = asyncio.get_event_loop()
            if self._session:
                loop.run_until_complete(self._session.close())
            if self._transaction:
                loop.run_until_complete(self._transaction.rollback())
            if self._connection:
                loop.run_until_complete(self._connection.close())
            if self._engine:
                loop.run_until_complete(self._engine.dispose())
        else:
            if self._session:
                self._session.close()
            if self._transaction:
                self._transaction.rollback()
            if self._connection:
                self._connection.close()
            if self._engine:
                self._engine.dispose()

    # Rollbackable interface for VenomQA World
    def get_state_snapshot(self) -> str:
        """Create a checkpoint and return its name."""
        return self.checkpoint()

    def rollback_from_snapshot(self, snapshot: str) -> None:
        """Rollback to a checkpoint."""
        self.rollback(snapshot)

    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False
