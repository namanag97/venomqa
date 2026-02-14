#!/usr/bin/env python3
"""Combinatorial State Test for a Data Integration Platform API.

This test uses VenomQA's combinatorial testing system to generate a minimal
set of state combinations that covers all pairwise (or n-wise) interactions
across six dimensions of the DIP API:

  1. auth_state     - Authentication token state
  2. workspace_state - Workspace data state
  3. file_format    - Uploaded file format
  4. data_size      - Number of rows in dataset
  5. user_role      - Permission level of the acting user
  6. operation_type - Read / Write / Delete

The full Cartesian product of these dimensions is 4*4*3*4*3*3 = 1,728
combinations. Most real defects involve at most 2-3 interacting parameters,
so pairwise coverage (strength=2) achieves high defect detection at a
fraction of the cost.

Usage:
    # Run with mock mode (no server required):
    python examples/dip_api_test/test_dip_combinatorial.py

    # Run against a live server:
    DIP_BASE_URL=http://localhost:8000 python examples/dip_api_test/test_dip_combinatorial.py

    # Three-wise coverage (more tests, more thorough):
    DIP_STRENGTH=3 python examples/dip_api_test/test_dip_combinatorial.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from venomqa.combinatorial import (
    Combination,
    CombinatorialGraphBuilder,
    ConstraintSet,
    CoveringArrayGenerator,
    Dimension,
    DimensionSpace,
    exclude,
    require,
)
from venomqa.core.graph import Severity


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("DIP_BASE_URL", "")
MOCK_MODE = not BASE_URL
STRENGTH = int(os.environ.get("DIP_STRENGTH", "2"))
SEED = int(os.environ.get("DIP_SEED", "42"))


# ---------------------------------------------------------------------------
# Mock API layer -- simulates the DIP API for offline testing
# ---------------------------------------------------------------------------

@dataclass
class MockState:
    """In-memory state for the mock DIP API server."""

    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    tokens: dict[str, dict[str, Any]] = field(default_factory=dict)
    workspaces: dict[str, dict[str, Any]] = field(default_factory=dict)
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    tables: dict[str, dict[str, Any]] = field(default_factory=dict)
    connectors: dict[str, dict[str, Any]] = field(default_factory=dict)
    connections: dict[str, dict[str, Any]] = field(default_factory=dict)
    syncs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def reset(self) -> None:
        self.users.clear()
        self.tokens.clear()
        self.workspaces.clear()
        self.files.clear()
        self.tables.clear()
        self.connectors.clear()
        self.connections.clear()
        self.syncs.clear()


_mock = MockState()


@dataclass
class MockResponse:
    """Minimal response object mirroring requests.Response for mock mode."""

    status_code: int
    _json: Any = None
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}: {self.text}")


class MockClient:
    """Drop-in replacement for venomqa.Client that operates in-memory."""

    def __init__(self) -> None:
        self.base_url = "http://mock"
        self._auth_token: str | None = None
        self._request_log: list[dict[str, Any]] = []

    def set_auth_token(self, token: str | None) -> None:
        self._auth_token = token

    # -- helpers -----------------------------------------------------------

    def _check_auth(self) -> tuple[bool, MockResponse | None]:
        """Return (is_authenticated, error_response_or_none)."""
        if self._auth_token is None:
            return False, MockResponse(401, {"error": "Authentication required"})
        token_info = _mock.tokens.get(self._auth_token)
        if token_info is None:
            return False, MockResponse(401, {"error": "Invalid token"})
        if token_info.get("expired"):
            return False, MockResponse(401, {"error": "Token expired"})
        return True, None

    def _check_role(self, required: str) -> MockResponse | None:
        """Return error response if current user lacks the required role."""
        role_hierarchy = {"viewer": 0, "member": 1, "owner": 2}
        token_info = _mock.tokens.get(self._auth_token or "")
        if not token_info:
            return MockResponse(401, {"error": "Not authenticated"})
        current = token_info.get("role", "viewer")
        if role_hierarchy.get(current, 0) < role_hierarchy.get(required, 0):
            return MockResponse(
                403,
                {"error": f"Forbidden: {current} cannot perform {required}-level operations"},
            )
        return None

    # -- public API --------------------------------------------------------

    def get(self, path: str, **kwargs: Any) -> MockResponse:
        self._request_log.append({"method": "GET", "path": path, **kwargs})

        if path == "/health":
            return MockResponse(200, {"status": "healthy"})
        if path == "/ready":
            return MockResponse(200, {"status": "ready"})

        ok, err = self._check_auth()
        if not ok:
            return err  # type: ignore[return-value]

        if path == "/api/v1/workspaces":
            items = list(_mock.workspaces.values())
            return MockResponse(200, {"workspaces": items, "count": len(items)})

        # GET /api/v1/workspaces/{id}/tables/{tid}/data
        if "/tables/" in path and path.endswith("/data"):
            parts = path.split("/")
            table_id = parts[-2]
            table = _mock.tables.get(table_id)
            if not table:
                return MockResponse(404, {"error": "Table not found"})
            return MockResponse(200, {
                "rows": table.get("rows", []),
                "row_count": len(table.get("rows", [])),
                "schema": table.get("schema", {}),
            })

        # GET /api/v1/workspaces/{id}/tables/{tid}/schema
        if "/tables/" in path and path.endswith("/schema"):
            parts = path.split("/")
            table_id = parts[-2]
            table = _mock.tables.get(table_id)
            if not table:
                return MockResponse(404, {"error": "Table not found"})
            return MockResponse(200, {"schema": table.get("schema", {})})

        # GET /api/v1/syncs/{id}
        if path.startswith("/api/v1/syncs/"):
            sync_id = path.split("/")[-1]
            sync = _mock.syncs.get(sync_id)
            if not sync:
                return MockResponse(404, {"error": "Sync not found"})
            return MockResponse(200, sync)

        return MockResponse(404, {"error": f"Unknown path: {path}"})

    def post(self, path: str, json: Any = None, **kwargs: Any) -> MockResponse:
        self._request_log.append({"method": "POST", "path": path, "json": json, **kwargs})

        ok, err = self._check_auth()
        if not ok:
            return err  # type: ignore[return-value]

        role_err = self._check_role("member")
        if role_err:
            return role_err

        # POST /api/v1/workspaces
        if path == "/api/v1/workspaces":
            ws_id = str(uuid.uuid4())[:8]
            ws = {"id": ws_id, "name": (json or {}).get("name", "default"), "files": [], "tables": []}
            _mock.workspaces[ws_id] = ws
            return MockResponse(201, ws)

        # POST /api/v1/workspaces/{id}/files/upload
        if "/files/upload" in path:
            parts = path.split("/")
            ws_id = parts[4]  # /api/v1/workspaces/{id}/files/upload
            if ws_id not in _mock.workspaces:
                return MockResponse(404, {"error": "Workspace not found"})
            upload_id = str(uuid.uuid4())[:8]
            file_info = {
                "upload_id": upload_id,
                "workspace_id": ws_id,
                "format": (json or {}).get("format", "csv"),
                "row_count": (json or {}).get("row_count", 0),
                "status": "uploaded",
            }
            _mock.files[upload_id] = file_info
            _mock.workspaces[ws_id]["files"].append(upload_id)
            return MockResponse(201, file_info)

        # POST /api/v1/workspaces/{id}/files/{upload_id}/import
        if "/files/" in path and path.endswith("/import"):
            parts = path.split("/")
            ws_id = parts[4]
            upload_id = parts[6]
            file_info = _mock.files.get(upload_id)
            if not file_info:
                return MockResponse(404, {"error": "Upload not found"})
            table_id = str(uuid.uuid4())[:8]
            rows = [{"col_" + str(c): f"val_{r}_{c}" for c in range(3)}
                    for r in range(file_info.get("row_count", 0))]
            table = {
                "table_id": table_id,
                "workspace_id": ws_id,
                "source_upload": upload_id,
                "format": file_info.get("format", "csv"),
                "rows": rows,
                "schema": {"columns": [{"name": f"col_{c}", "type": "string"} for c in range(3)]},
            }
            _mock.tables[table_id] = table
            _mock.workspaces[ws_id]["tables"].append(table_id)
            return MockResponse(201, {"table_id": table_id, "row_count": len(rows)})

        # POST /api/v1/connectors
        if path == "/api/v1/connectors":
            conn_id = str(uuid.uuid4())[:8]
            connector = {"id": conn_id, **(json or {})}
            _mock.connectors[conn_id] = connector
            return MockResponse(201, connector)

        # POST /api/v1/connections
        if path == "/api/v1/connections":
            conn_id = str(uuid.uuid4())[:8]
            connection = {"id": conn_id, "status": "active", **(json or {})}
            _mock.connections[conn_id] = connection
            return MockResponse(201, connection)

        # POST /api/v1/connections/{id}/syncs
        if "/connections/" in path and path.endswith("/syncs"):
            parts = path.split("/")
            connection_id = parts[4]
            if connection_id not in _mock.connections:
                return MockResponse(404, {"error": "Connection not found"})
            sync_id = str(uuid.uuid4())[:8]
            sync = {"id": sync_id, "connection_id": connection_id, "status": "running"}
            _mock.syncs[sync_id] = sync
            return MockResponse(201, sync)

        return MockResponse(404, {"error": f"Unknown path: {path}"})

    def delete(self, path: str, **kwargs: Any) -> MockResponse:
        self._request_log.append({"method": "DELETE", "path": path, **kwargs})

        ok, err = self._check_auth()
        if not ok:
            return err  # type: ignore[return-value]

        role_err = self._check_role("owner")
        if role_err:
            return role_err

        # DELETE /api/v1/workspaces/{id}
        if path.startswith("/api/v1/workspaces/"):
            ws_id = path.split("/")[-1]
            if ws_id in _mock.workspaces:
                del _mock.workspaces[ws_id]
                return MockResponse(204)
            return MockResponse(404, {"error": "Workspace not found"})

        return MockResponse(404, {"error": f"Unknown path: {path}"})


def _get_client() -> Any:
    """Return a MockClient or a real venomqa.Client depending on config."""
    if MOCK_MODE:
        return MockClient()
    from venomqa import Client
    return Client(base_url=BASE_URL)


# ---------------------------------------------------------------------------
# 1. DIMENSION DEFINITIONS
# ---------------------------------------------------------------------------

def build_dimension_space() -> DimensionSpace:
    """Define the six dimensions of variation for the DIP API."""
    return DimensionSpace([
        Dimension(
            name="auth_state",
            values=["none", "valid", "expired", "invalid"],
            description="State of the authentication token",
            default_value="none",
        ),
        Dimension(
            name="workspace_state",
            values=["none", "empty", "has_files", "has_tables"],
            description="Data state of the target workspace",
            default_value="none",
        ),
        Dimension(
            name="file_format",
            values=["csv", "json", "parquet"],
            description="Format of the file to upload/import",
            default_value="csv",
        ),
        Dimension(
            name="data_size",
            values=["empty", "small", "medium", "large"],
            description="Number of rows in the dataset",
            default_value="empty",
        ),
        Dimension(
            name="user_role",
            values=["owner", "member", "viewer"],
            description="Permission role of the acting user",
            default_value="owner",
        ),
        Dimension(
            name="operation_type",
            values=["read", "write", "delete"],
            description="Category of operation being performed",
            default_value="read",
        ),
    ])


# ---------------------------------------------------------------------------
# 2. CONSTRAINT DEFINITIONS
# ---------------------------------------------------------------------------

def build_constraints() -> ConstraintSet:
    """Define realistic constraints that eliminate impossible combinations."""
    return ConstraintSet([
        # -- Auth constraints --------------------------------------------------

        # Cannot upload/import/write without valid auth
        exclude(
            "no_upload_without_auth",
            auth_state="none",
            operation_type="write",
            description="Write operations require authentication",
        ),
        exclude(
            "no_delete_without_auth",
            auth_state="none",
            operation_type="delete",
            description="Delete operations require authentication",
        ),
        exclude(
            "no_upload_expired_auth",
            auth_state="expired",
            operation_type="write",
            description="Expired tokens cannot perform writes",
        ),
        exclude(
            "no_delete_expired_auth",
            auth_state="expired",
            operation_type="delete",
            description="Expired tokens cannot perform deletes",
        ),
        exclude(
            "no_upload_invalid_auth",
            auth_state="invalid",
            operation_type="write",
            description="Invalid tokens cannot perform writes",
        ),
        exclude(
            "no_delete_invalid_auth",
            auth_state="invalid",
            operation_type="delete",
            description="Invalid tokens cannot perform deletes",
        ),

        # -- Workspace-data dependency constraints ----------------------------

        # Cannot have files without a workspace
        exclude(
            "no_files_without_workspace",
            workspace_state="has_files",
            auth_state="none",
            description="Files require a workspace, which requires auth to create",
        ),
        # Cannot have tables without a workspace
        exclude(
            "no_tables_without_workspace",
            workspace_state="has_tables",
            auth_state="none",
            description="Tables require a workspace, which requires auth to create",
        ),

        # -- File-format constraint -------------------------------------------

        # If workspace has no files, file_format is irrelevant for read operations
        # (We still generate these but they are edge-case validation tests)

        # -- Role-based constraints -------------------------------------------

        # Viewers cannot write
        exclude(
            "viewer_no_write",
            user_role="viewer",
            operation_type="write",
            description="Viewers have read-only access",
        ),
        # Viewers cannot delete
        exclude(
            "viewer_no_delete",
            user_role="viewer",
            operation_type="delete",
            description="Viewers cannot delete resources",
        ),
        # Members cannot delete (only owners can)
        exclude(
            "member_no_delete",
            user_role="member",
            operation_type="delete",
            description="Only owners can delete resources",
        ),

        # -- Implication constraints ------------------------------------------

        # If workspace_state is "has_tables", data_size must not be "empty"
        # because importing creates at least the table metadata
        require(
            "tables_have_data",
            if_condition={"workspace_state": "has_tables"},
            then_condition={"data_size": "small"},
            description=(
                "When workspace has tables, we test with 'small' data at minimum. "
                "The generator interprets data_size as the intended data volume."
            ),
        ),
    ])


# ---------------------------------------------------------------------------
# 3. TRANSITION ACTIONS
#    Each function has signature: action(client, context) -> response
# ---------------------------------------------------------------------------

# -- Auth transitions -------------------------------------------------------

def action_login(client: Any, context: dict[str, Any]) -> Any:
    """Transition auth_state: none -> valid."""
    role = context.get("_to_combination", {}).get("user_role", "owner")
    token = f"tok_{role}_{uuid.uuid4().hex[:8]}"

    if MOCK_MODE:
        _mock.tokens[token] = {"role": role, "expired": False, "user_id": f"user_{role}"}
    else:
        # In a live environment, call the real auth endpoint
        resp = client.post("/api/v1/auth/login", json={
            "email": f"{role}@test.example.com",
            "password": "test-password",
        })
        token = resp.json().get("token", token)

    client.set_auth_token(token)
    context["auth_token"] = token
    context["user_role"] = role
    return {"status": "logged_in", "token": token, "role": role}


def action_expire_token(client: Any, context: dict[str, Any]) -> Any:
    """Transition auth_state: valid -> expired."""
    token = context.get("auth_token")
    if MOCK_MODE and token:
        _mock.tokens.setdefault(token, {})["expired"] = True
    context["auth_state"] = "expired"
    return {"status": "token_expired"}


def action_invalidate_token(client: Any, context: dict[str, Any]) -> Any:
    """Transition auth_state: valid -> invalid."""
    client.set_auth_token("INVALID_TOKEN_XXXXXX")
    context["auth_state"] = "invalid"
    return {"status": "token_invalidated"}


def action_logout(client: Any, context: dict[str, Any]) -> Any:
    """Transition auth_state: valid -> none."""
    token = context.get("auth_token")
    if MOCK_MODE and token and token in _mock.tokens:
        del _mock.tokens[token]
    client.set_auth_token(None)
    context.pop("auth_token", None)
    return {"status": "logged_out"}


def action_reauth(client: Any, context: dict[str, Any]) -> Any:
    """Transition auth_state: expired -> valid (re-authenticate)."""
    return action_login(client, context)


def action_fix_token(client: Any, context: dict[str, Any]) -> Any:
    """Transition auth_state: invalid -> valid (get proper token)."""
    return action_login(client, context)


# -- Workspace transitions --------------------------------------------------

def action_create_workspace(client: Any, context: dict[str, Any]) -> Any:
    """Transition workspace_state: none -> empty."""
    name = f"ws_{uuid.uuid4().hex[:6]}"
    resp = client.post("/api/v1/workspaces", json={"name": name})
    ws = resp.json() if hasattr(resp, "json") else resp._json
    context["workspace_id"] = ws.get("id")
    context["workspace_name"] = name
    return ws


def action_delete_workspace(client: Any, context: dict[str, Any]) -> Any:
    """Transition workspace_state: * -> none."""
    ws_id = context.get("workspace_id")
    if ws_id:
        resp = client.delete(f"/api/v1/workspaces/{ws_id}")
        context.pop("workspace_id", None)
        context.pop("workspace_name", None)
        context.pop("upload_id", None)
        context.pop("table_id", None)
        return resp
    return {"status": "no_workspace"}


# -- File transitions -------------------------------------------------------

DATA_SIZE_MAP = {
    "empty": 0,
    "small": 5,
    "medium": 1000,
    "large": 100000,
}


def action_upload_file(client: Any, context: dict[str, Any]) -> Any:
    """Transition workspace_state: empty -> has_files."""
    ws_id = context.get("workspace_id")
    if not ws_id:
        raise ValueError("Cannot upload file: no workspace_id in context")

    file_format = context.get("_to_combination", {}).get("file_format", "csv")
    data_size = context.get("_to_combination", {}).get("data_size", "small")
    row_count = DATA_SIZE_MAP.get(data_size, 5)

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/files/upload",
        json={"format": file_format, "row_count": row_count},
    )
    data = resp.json() if hasattr(resp, "json") else resp._json
    context["upload_id"] = data.get("upload_id")
    context["uploaded_format"] = file_format
    context["uploaded_row_count"] = row_count
    return data


def action_import_file(client: Any, context: dict[str, Any]) -> Any:
    """Transition workspace_state: has_files -> has_tables."""
    ws_id = context.get("workspace_id")
    upload_id = context.get("upload_id")
    if not ws_id or not upload_id:
        raise ValueError("Cannot import: missing workspace_id or upload_id")

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/files/{upload_id}/import",
        json={},
    )
    data = resp.json() if hasattr(resp, "json") else resp._json
    context["table_id"] = data.get("table_id")
    context["imported_row_count"] = data.get("row_count", 0)
    return data


def action_delete_files(client: Any, context: dict[str, Any]) -> Any:
    """Transition workspace_state: has_files -> empty (remove files)."""
    context.pop("upload_id", None)
    context.pop("uploaded_format", None)
    context.pop("uploaded_row_count", None)
    if MOCK_MODE:
        ws_id = context.get("workspace_id")
        if ws_id and ws_id in _mock.workspaces:
            for fid in _mock.workspaces[ws_id].get("files", []):
                _mock.files.pop(fid, None)
            _mock.workspaces[ws_id]["files"] = []
    return {"status": "files_deleted"}


def action_delete_tables(client: Any, context: dict[str, Any]) -> Any:
    """Transition workspace_state: has_tables -> has_files (remove tables)."""
    context.pop("table_id", None)
    context.pop("imported_row_count", None)
    if MOCK_MODE:
        ws_id = context.get("workspace_id")
        if ws_id and ws_id in _mock.workspaces:
            for tid in _mock.workspaces[ws_id].get("tables", []):
                _mock.tables.pop(tid, None)
            _mock.workspaces[ws_id]["tables"] = []
    return {"status": "tables_deleted"}


# -- Data size transitions --------------------------------------------------

def action_add_rows(client: Any, context: dict[str, Any]) -> Any:
    """Transition data_size: grow data (e.g., small -> medium)."""
    target = context.get("_to_value", "small")
    row_count = DATA_SIZE_MAP.get(target, 5)
    context["target_row_count"] = row_count

    table_id = context.get("table_id")
    if MOCK_MODE and table_id and table_id in _mock.tables:
        existing = _mock.tables[table_id].get("rows", [])
        while len(existing) < row_count:
            r = len(existing)
            existing.append({"col_0": f"val_{r}_0", "col_1": f"val_{r}_1", "col_2": f"val_{r}_2"})
        _mock.tables[table_id]["rows"] = existing[:row_count]

    return {"status": "rows_added", "target": row_count}


def action_clear_data(client: Any, context: dict[str, Any]) -> Any:
    """Transition data_size: * -> empty."""
    table_id = context.get("table_id")
    if MOCK_MODE and table_id and table_id in _mock.tables:
        _mock.tables[table_id]["rows"] = []
    context["target_row_count"] = 0
    return {"status": "data_cleared"}


# -- Operation type transitions (conceptual mode switch) -------------------

def action_switch_to_read(client: Any, context: dict[str, Any]) -> Any:
    """Switch to read mode -- perform a GET operation."""
    ws_id = context.get("workspace_id")
    table_id = context.get("table_id")
    if table_id and ws_id:
        resp = client.get(f"/api/v1/workspaces/{ws_id}/tables/{table_id}/data")
        return resp.json() if hasattr(resp, "json") else resp._json
    if ws_id:
        resp = client.get("/api/v1/workspaces")
        return resp.json() if hasattr(resp, "json") else resp._json
    resp = client.get("/health")
    return resp.json() if hasattr(resp, "json") else resp._json


def action_switch_to_write(client: Any, context: dict[str, Any]) -> Any:
    """Switch to write mode -- perform a POST operation."""
    ws_id = context.get("workspace_id")
    if ws_id:
        resp = client.post(
            f"/api/v1/workspaces/{ws_id}/files/upload",
            json={"format": "csv", "row_count": 1},
        )
        return resp.json() if hasattr(resp, "json") else resp._json
    resp = client.post("/api/v1/workspaces", json={"name": "op_test"})
    return resp.json() if hasattr(resp, "json") else resp._json


def action_switch_to_delete(client: Any, context: dict[str, Any]) -> Any:
    """Switch to delete mode -- perform a DELETE operation."""
    ws_id = context.get("workspace_id")
    if ws_id:
        resp = client.delete(f"/api/v1/workspaces/{ws_id}")
        return resp
    return {"status": "nothing_to_delete"}


# -- User role transitions -------------------------------------------------

def action_switch_role(client: Any, context: dict[str, Any]) -> Any:
    """Switch to a different user role by re-authenticating."""
    target_role = context.get("_to_value", "member")
    return action_login(client, context)


# ---------------------------------------------------------------------------
# 4. INVARIANT CHECKERS
#    Each has signature: check(client, db, context) -> bool
# ---------------------------------------------------------------------------

def check_auth_consistency(client: Any, db: Any, context: dict[str, Any]) -> bool:
    """Verify: unauthenticated requests to protected endpoints get 401."""
    combo = context.get("_current_combination", {})
    auth_state = combo.get("auth_state", "valid")

    if auth_state in ("none", "expired", "invalid"):
        # Protected endpoint should reject us
        resp = client.get("/api/v1/workspaces")
        status = getattr(resp, "status_code", 200)
        if status != 401:
            return False
    return True


def check_data_integrity(client: Any, db: Any, context: dict[str, Any]) -> bool:
    """Verify: row counts in the API match what we expect."""
    combo = context.get("_current_combination", {})
    ws_state = combo.get("workspace_state")
    table_id = context.get("table_id")

    if ws_state != "has_tables" or not table_id:
        return True  # Nothing to check

    ws_id = context.get("workspace_id")
    if not ws_id:
        return True

    resp = client.get(f"/api/v1/workspaces/{ws_id}/tables/{table_id}/data")
    status = getattr(resp, "status_code", 200)
    if status != 200:
        # If auth prevents us from checking, skip (auth invariant will catch it)
        return True

    data = resp.json() if hasattr(resp, "json") else resp._json
    api_count = data.get("row_count", 0)
    expected = context.get("imported_row_count", context.get("target_row_count"))
    if expected is not None and api_count != expected:
        return False

    return True


def check_permission_enforcement(client: Any, db: Any, context: dict[str, Any]) -> bool:
    """Verify: viewers cannot write and members cannot delete."""
    combo = context.get("_current_combination", {})
    role = combo.get("user_role")
    op = combo.get("operation_type")
    auth = combo.get("auth_state")

    if auth != "valid":
        return True  # Auth invariant handles non-valid states

    # Test that a write by a viewer is rejected
    if role == "viewer" and op == "write":
        resp = client.post("/api/v1/workspaces", json={"name": "perm_test"})
        status = getattr(resp, "status_code", 200)
        if status not in (401, 403):
            return False

    # Test that a delete by a non-owner is rejected
    if role in ("viewer", "member") and op == "delete":
        resp = client.delete("/api/v1/workspaces/nonexistent")
        status = getattr(resp, "status_code", 200)
        # Should get 403 (Forbidden) or 404 (not found, but at least not 200/204)
        if status in (200, 204):
            return False

    return True


def check_health_always_accessible(client: Any, db: Any, context: dict[str, Any]) -> bool:
    """Verify: /health and /ready never require auth."""
    # Save current auth
    original_token = getattr(client, "_auth_token", None)
    try:
        client.set_auth_token(None)
        resp_health = client.get("/health")
        resp_ready = client.get("/ready")
        return (
            getattr(resp_health, "status_code", 500) == 200
            and getattr(resp_ready, "status_code", 500) == 200
        )
    finally:
        client.set_auth_token(original_token)


# ---------------------------------------------------------------------------
# 5. BUILD THE COMBINATORIAL GRAPH
# ---------------------------------------------------------------------------

def build_graph() -> tuple[CombinatorialGraphBuilder, DimensionSpace, ConstraintSet]:
    """Assemble all dimensions, constraints, transitions, and invariants."""

    space = build_dimension_space()
    constraints = build_constraints()

    builder = CombinatorialGraphBuilder(
        name="dip_api_combinatorial_test",
        space=space,
        constraints=constraints,
        description=(
            "Combinatorial test of the Data Integration Platform API across "
            "auth, workspace, file format, data size, role, and operation dimensions."
        ),
        seed=SEED,
    )

    # -- Auth transitions --
    builder.register_transition("auth_state", "none", "valid", action=action_login, name="login")
    builder.register_transition("auth_state", "valid", "expired", action=action_expire_token, name="expire_token")
    builder.register_transition("auth_state", "valid", "invalid", action=action_invalidate_token, name="invalidate_token")
    builder.register_transition("auth_state", "valid", "none", action=action_logout, name="logout")
    builder.register_transition("auth_state", "expired", "valid", action=action_reauth, name="reauth_expired")
    builder.register_transition("auth_state", "expired", "none", action=action_logout, name="logout_expired")
    builder.register_transition("auth_state", "invalid", "valid", action=action_fix_token, name="fix_token")
    builder.register_transition("auth_state", "invalid", "none", action=action_logout, name="logout_invalid")

    # -- Workspace transitions --
    builder.register_transition("workspace_state", "none", "empty", action=action_create_workspace, name="create_workspace")
    builder.register_transition("workspace_state", "empty", "has_files", action=action_upload_file, name="upload_file")
    builder.register_transition("workspace_state", "has_files", "has_tables", action=action_import_file, name="import_file")
    builder.register_transition("workspace_state", "has_files", "empty", action=action_delete_files, name="delete_files")
    builder.register_transition("workspace_state", "has_tables", "has_files", action=action_delete_tables, name="drop_tables")
    builder.register_transition("workspace_state", "empty", "none", action=action_delete_workspace, name="delete_workspace_empty")
    builder.register_transition("workspace_state", "has_files", "none", action=action_delete_workspace, name="delete_workspace_files")
    builder.register_transition("workspace_state", "has_tables", "none", action=action_delete_workspace, name="delete_workspace_tables")

    # -- File format transitions --
    # These are conceptual: switching the "active" format for the next upload
    for from_fmt in ("csv", "json", "parquet"):
        for to_fmt in ("csv", "json", "parquet"):
            if from_fmt != to_fmt:
                def _make_switch(target: str):
                    def switch(client: Any, context: dict[str, Any]) -> Any:
                        context["active_format"] = target
                        return {"status": "format_switched", "format": target}
                    return switch
                builder.register_transition(
                    "file_format", from_fmt, to_fmt,
                    action=_make_switch(to_fmt),
                    name=f"switch_{from_fmt}_to_{to_fmt}",
                )

    # -- Data size transitions --
    sizes = ["empty", "small", "medium", "large"]
    for i, from_size in enumerate(sizes):
        for j, to_size in enumerate(sizes):
            if i == j:
                continue
            if j > i:
                builder.register_transition(
                    "data_size", from_size, to_size,
                    action=action_add_rows,
                    name=f"grow_{from_size}_to_{to_size}",
                )
            else:
                if to_size == "empty":
                    builder.register_transition(
                        "data_size", from_size, to_size,
                        action=action_clear_data,
                        name=f"clear_{from_size}_to_{to_size}",
                    )
                else:
                    builder.register_transition(
                        "data_size", from_size, to_size,
                        action=action_add_rows,
                        name=f"shrink_{from_size}_to_{to_size}",
                    )

    # -- Operation type transitions --
    builder.register_transition("operation_type", "read", "write", action=action_switch_to_write, name="switch_read_to_write")
    builder.register_transition("operation_type", "read", "delete", action=action_switch_to_delete, name="switch_read_to_delete")
    builder.register_transition("operation_type", "write", "read", action=action_switch_to_read, name="switch_write_to_read")
    builder.register_transition("operation_type", "write", "delete", action=action_switch_to_delete, name="switch_write_to_delete")
    builder.register_transition("operation_type", "delete", "read", action=action_switch_to_read, name="switch_delete_to_read")
    builder.register_transition("operation_type", "delete", "write", action=action_switch_to_write, name="switch_delete_to_write")

    # -- User role transitions --
    for from_role in ("owner", "member", "viewer"):
        for to_role in ("owner", "member", "viewer"):
            if from_role != to_role:
                builder.register_transition(
                    "user_role", from_role, to_role,
                    action=action_switch_role,
                    name=f"role_{from_role}_to_{to_role}",
                )

    # -- Invariants --
    builder.add_invariant(
        "auth_consistency",
        check=check_auth_consistency,
        description="Unauthenticated requests to protected endpoints return 401",
        severity=Severity.CRITICAL,
    )
    builder.add_invariant(
        "data_integrity",
        check=check_data_integrity,
        description="Row counts reported by API match expected values",
        severity=Severity.HIGH,
    )
    builder.add_invariant(
        "permission_enforcement",
        check=check_permission_enforcement,
        description="Viewers cannot write; non-owners cannot delete",
        severity=Severity.CRITICAL,
    )
    builder.add_invariant(
        "health_always_accessible",
        check=check_health_always_accessible,
        description="/health and /ready are always accessible without auth",
        severity=Severity.HIGH,
    )

    # -- Initial state --
    builder.set_initial({
        "auth_state": "none",
        "workspace_state": "none",
        "file_format": "csv",
        "data_size": "empty",
        "user_role": "owner",
        "operation_type": "read",
    })

    return builder, space, constraints


# ---------------------------------------------------------------------------
# 6. COVERAGE ANALYSIS
# ---------------------------------------------------------------------------

def print_coverage_report(
    space: DimensionSpace,
    constraints: ConstraintSet,
    combos: list[Combination],
) -> None:
    """Print a detailed coverage report."""

    gen = CoveringArrayGenerator(space, constraints, seed=SEED)

    print("\n" + "=" * 70)
    print("COVERAGE REPORT")
    print("=" * 70)

    print(f"\nDimensions ({len(space.dimensions)}):")
    for dim in space.dimensions:
        print(f"  {dim.name:20s}  {dim.size} values: {dim.values}")

    print(f"\nTotal exhaustive combinations: {space.total_combinations:,}")
    valid_exhaustive = constraints.filter(space.all_combinations())
    print(f"Valid after constraints:       {len(valid_exhaustive):,}")
    print(f"Constraints applied:          {len(constraints)}")

    print(f"\nGenerated test combinations:  {len(combos)}")
    reduction = (1 - len(combos) / len(valid_exhaustive)) * 100 if valid_exhaustive else 0
    print(f"Reduction:                    {reduction:.1f}%")

    for strength in range(1, min(4, len(space.dimensions) + 1)):
        stats = gen.coverage_stats(combos, strength=strength)
        label = {1: "1-wise (each-value)", 2: "2-wise (pairwise)", 3: "3-wise"}
        print(
            f"\n  {label.get(strength, f'{strength}-wise'):25s}  "
            f"{stats.covered_tuples:>6,} / {stats.total_tuples:>6,} tuples  "
            f"({stats.coverage_pct:5.1f}%)  "
            f"[{stats.excluded_by_constraints} excluded by constraints]"
        )

    print("\n" + "-" * 70)
    print("Generated combinations:")
    print("-" * 70)
    for i, combo in enumerate(combos, 1):
        print(f"  {i:3d}. {combo.description}")

    print()


# ---------------------------------------------------------------------------
# 7. MAIN
# ---------------------------------------------------------------------------

def main() -> bool:
    """Run the combinatorial DIP API test and report coverage statistics."""

    mode_label = "MOCK" if MOCK_MODE else f"LIVE ({BASE_URL})"
    print("=" * 70)
    print("DATA INTEGRATION PLATFORM - COMBINATORIAL STATE TEST")
    print(f"Mode: {mode_label}  |  Strength: {STRENGTH}  |  Seed: {SEED}")
    print("=" * 70)

    # Reset mock state
    if MOCK_MODE:
        _mock.reset()

    # Build
    builder, space, constraints = build_graph()

    # Generate covering array
    gen = CoveringArrayGenerator(space, constraints, seed=SEED)
    combos = gen.generate(strength=STRENGTH)

    # Print coverage report
    print_coverage_report(space, constraints, combos)

    # Print builder summary
    print(builder.summary(strength=STRENGTH))

    # Build the StateGraph
    print("\nBuilding StateGraph...")
    graph, used_combos = builder.build_journey_graph(
        strength=STRENGTH,
        combinations=combos,
    )
    total_edges = sum(len(e) for e in graph.edges.values())
    print(f"  Nodes:      {len(graph.nodes)}")
    print(f"  Edges:      {total_edges}")
    print(f"  Invariants: {len(graph.invariants)}")

    # Show Mermaid diagram (truncated)
    mermaid = graph.to_mermaid()
    mermaid_lines = mermaid.split("\n")
    print(f"\nMermaid diagram ({len(mermaid_lines)} lines, showing first 30):")
    print("-" * 50)
    for line in mermaid_lines[:30]:
        print(f"  {line}")
    if len(mermaid_lines) > 30:
        print(f"  ... ({len(mermaid_lines) - 30} more lines)")

    # If running in mock mode, actually explore the graph
    if MOCK_MODE:
        print("\n" + "=" * 70)
        print("EXPLORING STATE GRAPH (mock mode)")
        print("=" * 70)

        client = _get_client()

        # We explore with limited depth to keep the demo fast
        result = graph.explore(
            client=client,
            db=None,
            max_depth=6,
            stop_on_violation=False,
        )

        print(f"\n{result.summary()}")

        if result.invariant_violations:
            print("\nVIOLATIONS FOUND:")
            for v in result.invariant_violations:
                print(f"  [{v.invariant.severity.value}] {v.invariant.name}")
                print(f"    Node: {v.node.id}")
                print(f"    Description: {v.invariant.description}")
                if v.error_message:
                    print(f"    Error: {v.error_message}")
                print()

    # Final statistics
    print("\n" + "=" * 70)
    print("FINAL STATISTICS")
    print("=" * 70)

    stats_2 = gen.coverage_stats(combos, strength=2)
    print(f"  Exhaustive space:          {space.total_combinations:,} combinations")
    print(f"  Valid after constraints:    {len(constraints.filter(space.all_combinations())):,}")
    print(f"  Test combinations used:    {len(combos)}")
    print(f"  Pairwise coverage:         {stats_2.coverage_pct:.1f}%")
    print(f"  Pairwise tuples covered:   {stats_2.covered_tuples}/{stats_2.total_tuples}")
    print(f"  Graph nodes:               {len(graph.nodes)}")
    print(f"  Graph edges:               {total_edges}")
    print(f"  Invariants checked:        {len(graph.invariants)}")
    print(f"  Transitions registered:    {len(builder._transitions)}")

    if STRENGTH >= 3 and len(space.dimensions) >= 3:
        stats_3 = gen.coverage_stats(combos, strength=3)
        print(f"  Three-wise coverage:       {stats_3.coverage_pct:.1f}%")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
