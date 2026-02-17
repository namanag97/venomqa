"""Mock GitHub API server with an intentional bug for VenomQA to discover.

Bug planted:
    GET /repos/{id}/issues?state=open returns closed issues whenever the repo
    has at least one closed issue. This simulates a real-world race-condition
    bug where the "state" filter is applied before a DB index is updated.

Run standalone:
    python mock_github.py
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Shared in-memory state
# ---------------------------------------------------------------------------

_state: dict[str, Any] = {
    "users": {},    # login -> {id, login, email}
    "repos": {},    # repo_id -> {id, name, owner_login, open_issues_count, stars}
    "issues": {},   # repo_id -> list[{number, title, state, body}]
    "_issue_counters": {},  # repo_id -> next issue number
}
_lock = threading.Lock()


def reset_state() -> None:
    """Reset all server state. Call between tests."""
    with _lock:
        _state["users"].clear()
        _state["repos"].clear()
        _state["issues"].clear()
        _state["_issue_counters"].clear()


def get_state_snapshot() -> dict[str, Any]:
    """Return a deep-copyable copy of state for checkpoint/rollback."""
    with _lock:
        return {
            "users": dict(_state["users"]),
            "_issue_counters": dict(_state["_issue_counters"]),
            "repos": dict(_state["repos"]),
            "issues": {k: list(v) for k, v in _state["issues"].items()},
        }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

def _send_json(handler: BaseHTTPRequestHandler, status: int, body: Any) -> None:
    data = json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class GitHubHandler(BaseHTTPRequestHandler):
    """Handles mock GitHub API requests."""

    def log_message(self, fmt: str, *args: Any) -> None:  # suppress output
        pass

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    # ------------------------------------------------------------------ POST
    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._read_body()

        with _lock:
            # POST /users
            if path == "/users":
                login = body.get("login") or f"user-{uuid.uuid4().hex[:6]}"
                if login in _state["users"]:
                    _send_json(self, 409, {"error": "User already exists"})
                    return
                user = {
                    "id": str(uuid.uuid4()),
                    "login": login,
                    "email": body.get("email", f"{login}@example.com"),
                }
                _state["users"][login] = user
                _send_json(self, 201, user)
                return

            # POST /repos
            if path == "/repos":
                owner = body.get("owner_login", "")
                if owner not in _state["users"]:
                    _send_json(self, 404, {"error": f"Owner '{owner}' not found"})
                    return
                repo_id = str(uuid.uuid4())
                repo = {
                    "id": repo_id,
                    "name": body.get("name", f"repo-{repo_id[:6]}"),
                    "owner_login": owner,
                    "open_issues_count": 0,
                    "stars": 0,
                }
                _state["repos"][repo_id] = repo
                _state["issues"][repo_id] = []
                _state["_issue_counters"][repo_id] = 0
                _send_json(self, 201, repo)
                return

            # POST /repos/{id}/issues
            m = re.match(r"^/repos/([^/]+)/issues$", path)
            if m:
                repo_id = m.group(1)
                if repo_id not in _state["repos"]:
                    _send_json(self, 404, {"error": "Repo not found"})
                    return
                _state["_issue_counters"][repo_id] += 1
                num = _state["_issue_counters"][repo_id]
                issue = {
                    "number": num,
                    "title": body.get("title", f"Issue #{num}"),
                    "body": body.get("body", ""),
                    "state": "open",
                    "repo_id": repo_id,
                }
                _state["issues"][repo_id].append(issue)
                _state["repos"][repo_id]["open_issues_count"] += 1
                _send_json(self, 201, issue)
                return

            _send_json(self, 404, {"error": "Not found"})

    # ------------------------------------------------------------------ GET
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        with _lock:
            # GET /users/{login}
            m = re.match(r"^/users/([^/]+)$", path)
            if m:
                login = m.group(1)
                if login not in _state["users"]:
                    _send_json(self, 404, {"error": "User not found"})
                    return
                _send_json(self, 200, _state["users"][login])
                return

            # GET /users  (list all users)
            if path == "/users":
                _send_json(self, 200, list(_state["users"].values()))
                return

            # GET /repos  (optional ?owner=login filter)
            if path == "/repos":
                owner = qs.get("owner", [None])[0]
                repos = list(_state["repos"].values())
                if owner:
                    repos = [r for r in repos if r["owner_login"] == owner]
                _send_json(self, 200, repos)
                return

            # GET /repos/{id}
            m = re.match(r"^/repos/([^/]+)$", path)
            if m:
                repo_id = m.group(1)
                if repo_id not in _state["repos"]:
                    _send_json(self, 404, {"error": "Repo not found"})
                    return
                _send_json(self, 200, _state["repos"][repo_id])
                return

            # GET /repos/{id}/issues  (optional ?state=open|closed|all)
            m = re.match(r"^/repos/([^/]+)/issues$", path)
            if m:
                repo_id = m.group(1)
                if repo_id not in _state["repos"]:
                    _send_json(self, 404, {"error": "Repo not found"})
                    return

                filter_state = qs.get("state", ["open"])[0]
                all_issues = _state["issues"].get(repo_id, [])

                if filter_state == "all":
                    result = list(all_issues)
                else:
                    result = [i for i in all_issues if i["state"] == filter_state]

                # -------------------------------------------------------
                # BUG: When filtering for "open" issues, the server ALWAYS
                # appends the first closed issue (if any exist). This
                # simulates a missing index / stale-read race condition.
                # -------------------------------------------------------
                if filter_state == "open":
                    closed = [i for i in all_issues if i["state"] == "closed"]
                    if closed:
                        result = result + [closed[0]]  # leak!

                _send_json(self, 200, result)
                return

            _send_json(self, 404, {"error": "Not found"})

    # ---------------------------------------------------------------- PATCH
    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        body = self._read_body()

        with _lock:
            # PATCH /repos/{id}/issues/{number}
            m = re.match(r"^/repos/([^/]+)/issues/(\d+)$", path)
            if m:
                repo_id, num = m.group(1), int(m.group(2))
                if repo_id not in _state["repos"]:
                    _send_json(self, 404, {"error": "Repo not found"})
                    return
                issues = _state["issues"].get(repo_id, [])
                issue = next((i for i in issues if i["number"] == num), None)
                if not issue:
                    _send_json(self, 404, {"error": "Issue not found"})
                    return

                old_state = issue["state"]
                new_state = body.get("state", old_state)
                issue["state"] = new_state
                if old_state == "open" and new_state == "closed":
                    _state["repos"][repo_id]["open_issues_count"] -= 1
                elif old_state == "closed" and new_state == "open":
                    _state["repos"][repo_id]["open_issues_count"] += 1

                _send_json(self, 200, issue)
                return

            _send_json(self, 404, {"error": "Not found"})

    # --------------------------------------------------------------- DELETE
    def do_DELETE(self) -> None:
        path = urlparse(self.path).path

        with _lock:
            # DELETE /repos/{id}
            m = re.match(r"^/repos/([^/]+)$", path)
            if m:
                repo_id = m.group(1)
                if repo_id not in _state["repos"]:
                    _send_json(self, 404, {"error": "Repo not found"})
                    return
                del _state["repos"][repo_id]
                _state["issues"].pop(repo_id, None)
                _state["_issue_counters"].pop(repo_id, None)
                # Return empty body with 204
                self.send_response(204)
                self.end_headers()
                return

            _send_json(self, 404, {"error": "Not found"})


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

def start_server(port: int = 8101) -> HTTPServer:
    """Start the mock GitHub server in a daemon thread and return it."""
    server = HTTPServer(("localhost", port), GitHubHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


if __name__ == "__main__":
    import time

    reset_state()
    srv = start_server(8101)
    print("Mock GitHub API running on http://localhost:8101")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.shutdown()
