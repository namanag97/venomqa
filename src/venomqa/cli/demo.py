"""Demo server and command for VenomQA.

Provides a zero-config way to see VenomQA in action without setting up an API.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

import click


class DemoAPIHandler(BaseHTTPRequestHandler):
    """Simple REST API handler for demo purposes."""

    # In-memory storage
    items: dict[str, dict[str, Any]] = {}
    _counter: int = 0

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self._send_json(200, {"status": "healthy", "version": "1.0.0"})

        elif path == "/items":
            self._send_json(200, list(self.items.values()))

        elif path.startswith("/items/"):
            item_id = path.split("/")[-1]
            if item_id in self.items:
                self._send_json(200, self.items[item_id])
            else:
                self._send_json(404, {"error": "Item not found", "id": item_id})

        else:
            self._send_json(404, {"error": "Not found", "path": path})

    def do_POST(self) -> None:
        if self.path == "/items":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

                DemoAPIHandler._counter += 1
                item_id = str(DemoAPIHandler._counter)

                item = {
                    "id": item_id,
                    "name": body.get("name", "Unnamed"),
                    "description": body.get("description", ""),
                    "price": body.get("price", 0.0),
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                self.items[item_id] = item
                self._send_json(201, item)

            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_PUT(self) -> None:
        if self.path.startswith("/items/"):
            item_id = self.path.split("/")[-1]
            if item_id not in self.items:
                self._send_json(404, {"error": "Item not found"})
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

                item = self.items[item_id]
                item["name"] = body.get("name", item["name"])
                item["description"] = body.get("description", item["description"])
                item["price"] = body.get("price", item["price"])
                item["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

                self._send_json(200, item)

            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_DELETE(self) -> None:
        if self.path.startswith("/items/"):
            item_id = self.path.split("/")[-1]
            if item_id in self.items:
                del self.items[item_id]
                self._send_json(204, None)
            else:
                self._send_json(404, {"error": "Item not found"})
        else:
            self._send_json(404, {"error": "Not found"})

    def _send_json(self, status: int, data: Any) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if data is not None:
            self.wfile.write(json.dumps(data, indent=2).encode())

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass


def start_demo_server(port: int = 8000) -> HTTPServer:
    """Start the demo server in a background thread."""
    # Reset state
    DemoAPIHandler.items = {}
    DemoAPIHandler._counter = 0

    server = HTTPServer(("127.0.0.1", port), DemoAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_demo_journey(base_url: str) -> dict[str, Any]:
    """Run a demo using v1 API - simple linear sequence for clarity.

    For the demo, we run a clear linear CRUD flow so new users can see
    each step succeed. Full BFS exploration is demonstrated in examples/.
    """
    from venomqa.adapters.http import HttpClient
    from venomqa.v1.core.context import Context

    results: dict[str, Any] = {"steps": [], "success": True}
    api = HttpClient(base_url)
    context = Context()
    start_time = time.time()

    # Step definitions with expected outcomes
    steps = [
        ("health_check", lambda: api.get("/health"), 200),
        ("list_items", lambda: api.get("/items"), 200),
        ("create_item", lambda: api.post("/items", json={
            "name": "VenomQA Demo Item",
            "description": "Created by venomqa demo",
            "price": 29.99,
        }), 201),
        ("get_item", lambda: api.get(f"/items/{context.get('item_id')}"), 200),
        ("update_item", lambda: api.put(f"/items/{context.get('item_id')}", json={
            "name": "Updated Demo Item",
            "price": 39.99,
        }), 200),
        ("delete_item", lambda: api.delete(f"/items/{context.get('item_id')}"), 204),
        ("verify_deleted", lambda: api.get(f"/items/{context.get('_deleted_id')}"), 404),
    ]

    all_success = True
    for name, action, expected_status in steps:
        step_start = time.time()
        try:
            resp = action()
            success = resp.status_code == expected_status

            # Store context for subsequent steps
            if name == "create_item" and resp.status_code == 201:
                data = resp.json()
                context.set("item_id", data["id"])
            elif name == "delete_item" and resp.status_code == 204:
                context.set("_deleted_id", context.get("item_id"))
                context.delete("item_id")

        except Exception as e:
            success = False
            _ = e  # Suppress unused variable warning

        step_duration = (time.time() - step_start) * 1000
        results["steps"].append({
            "name": name,
            "success": success,
            "duration_ms": step_duration,
        })
        if not success:
            all_success = False

    results["success"] = all_success
    results["duration_ms"] = (time.time() - start_time) * 1000
    return results


@click.command()
@click.option("--port", "-p", default=8000, help="Port for demo server (default: 8000)")
@click.option("--server-only", is_flag=True, help="Only start the server, don't run journey")
@click.option("--keep-running", "-k", is_flag=True, help="Keep server running after journey")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed step output")
@click.option("--explain", "-e", is_flag=True, help="Explain each step as it runs")
def demo(port: int, server_only: bool, keep_running: bool, verbose: bool, explain: bool) -> None:
    """Run a quick demo to see VenomQA in action.

    The demo runs a complete CRUD journey against a built-in mock API:

    \b
    1. Health Check    - Verify API is responding
    2. List Items      - GET /items (empty list)
    3. Create Item     - POST /items with JSON body
    4. Get Item        - GET /items/{id}
    5. Update Item     - PUT /items/{id}
    6. Delete Item     - DELETE /items/{id}
    7. Verify Deleted  - GET /items/{id} (expect 404)

    No configuration file needed - this works out of the box!

    \b
    Examples:
        venomqa demo                    # Run full demo
        venomqa demo --explain          # Show what each step does
        venomqa demo --server-only      # Just start the server
        venomqa demo --keep-running     # Keep server after demo
        venomqa demo --port 9000        # Use different port

    After running the demo, create your own project with:
        venomqa init --with-sample
    """
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()

    # Header
    console.print()
    console.print(Panel.fit(
        "[bold magenta]VenomQA Demo[/bold magenta]\n"
        "[dim]See VenomQA in action with zero configuration[/dim]",
        border_style="magenta",
    ))
    console.print()

    # Start server
    console.print(f"[cyan]Starting demo server on http://127.0.0.1:{port}...[/cyan]")
    try:
        server = start_demo_server(port)
        time.sleep(0.5)  # Give server time to start
        console.print(f"[green]Demo server running on http://127.0.0.1:{port}[/green]")
        console.print()
    except OSError as e:
        console.print(f"[red]Failed to start server: {e}[/red]")
        console.print(f"[yellow]Tip: Is port {port} already in use? Try --port 9000[/yellow]")
        raise SystemExit(1)

    if server_only:
        console.print("[cyan]Server-only mode. Press Ctrl+C to stop.[/cyan]")
        console.print()
        console.print("[dim]Available endpoints:[/dim]")
        console.print(f"  GET    http://127.0.0.1:{port}/health")
        console.print(f"  GET    http://127.0.0.1:{port}/items")
        console.print(f"  POST   http://127.0.0.1:{port}/items")
        console.print(f"  GET    http://127.0.0.1:{port}/items/{{id}}")
        console.print(f"  PUT    http://127.0.0.1:{port}/items/{{id}}")
        console.print(f"  DELETE http://127.0.0.1:{port}/items/{{id}}")
        console.print()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/yellow]")
            server.shutdown()
        return

    # Explain mode header
    if explain:
        console.print(Panel(
            "[bold]What is VenomQA?[/bold]\n\n"
            "VenomQA is a stateful API testing framework that:\n"
            "  [green]●[/green] Tests complete user journeys, not isolated endpoints\n"
            "  [green]●[/green] Passes context between steps (like auth tokens)\n"
            "  [green]●[/green] Supports branching to test multiple paths\n"
            "  [green]●[/green] Captures and reports issues with full context\n\n"
            "[dim]Let's watch a simple CRUD journey in action...[/dim]",
            title="Learning Mode",
            border_style="blue",
        ))
        console.print()

    # Run demo journey
    console.print("[cyan]Running demo journey...[/cyan]")
    console.print()

    if explain:
        console.print("[dim]Journey: demo_journey - Tests basic CRUD operations[/dim]")
        console.print("[dim]Each step will execute in sequence, passing data forward[/dim]")
        console.print()

    base_url = f"http://127.0.0.1:{port}"
    results = run_demo_journey(base_url)

    # Step explanations for explain mode
    step_explanations = {
        "health_check": "Calls GET /health to verify API is responding. Stores health status in context.",
        "list_items": "Calls GET /items to list existing items. Should return empty array initially.",
        "create_item": "Calls POST /items with JSON body. Stores created item ID in context['item_id'].",
        "get_item": "Calls GET /items/{id} using context['item_id']. Verifies item was created.",
        "update_item": "Calls PUT /items/{id} to modify the item. Updates name and price.",
        "delete_item": "Calls DELETE /items/{id} to remove the item.",
        "verify_deleted": "Calls GET /items/{id} expecting 404. Uses expect_failure=True.",
    }

    # Display results
    if explain:
        console.print("[bold]Step-by-Step Results:[/bold]")
        console.print()
        for i, step in enumerate(results["steps"], 1):
            status_icon = "[green]✓[/green]" if step["success"] else "[red]✗[/red]"
            console.print(f"  {status_icon} [bold]Step {i}:[/bold] {step['name']} ({step['duration_ms']:.0f}ms)")
            if step["name"] in step_explanations:
                console.print(f"     [dim]{step_explanations[step['name']]}[/dim]")
            console.print()
    else:
        table = Table(
            title="Demo Journey Results",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Step", style="white")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right")

        for step in results["steps"]:
            status = "[green]PASS[/green]" if step["success"] else "[red]FAIL[/red]"
            duration = f"{step['duration_ms']:.0f}ms"
            table.add_row(step["name"], status, duration)

        console.print(table)
        console.print()

    # Summary
    passed = sum(1 for s in results["steps"] if s["success"])
    total = len(results["steps"])

    if results["success"]:
        console.print(Panel(
            f"[bold green]Demo Complete![/bold green]\n\n"
            f"All {passed}/{total} steps passed in {results['duration_ms']:.0f}ms\n\n"
            "[dim]VenomQA is ready to test your APIs.[/dim]",
            border_style="green",
        ))
    else:
        console.print(Panel(
            f"[bold red]Demo had failures[/bold red]\n\n"
            f"{passed}/{total} steps passed",
            border_style="red",
        ))

    console.print()

    # Next steps
    console.print("[bold]Next Steps:[/bold]")
    console.print()
    console.print("  1. [cyan]venomqa init[/cyan]           Create your project structure")
    console.print("  2. Edit [cyan]venomqa.yaml[/cyan]      Point to your API")
    console.print("  3. Write journeys in [cyan]journeys/[/cyan]")
    console.print("  4. [cyan]venomqa run[/cyan]            Run your tests")
    console.print()

    if explain:
        console.print("[bold]Example Code (v1 API):[/bold]")
        console.print()
        console.print("[dim]```python[/dim]")
        console.print("[yellow]from venomqa import Action, Agent, World, BFS, Invariant, Severity[/yellow]")
        console.print("[yellow]from venomqa.adapters.http import HttpClient[/yellow]")
        console.print()
        console.print("[green]def login(api, context):  # signature: (api, context)[/green]")
        console.print("[green]    resp = api.post('/auth/login', json={...})[/green]")
        console.print("[green]    context.set('token', resp.json()['token'])[/green]")
        console.print("[green]    return resp[/green]")
        console.print()
        console.print("[cyan]agent = Agent([/cyan]")
        console.print("[cyan]    world=World(api=HttpClient('http://localhost:8000')),[/cyan]")
        console.print("[cyan]    actions=[Action(name='login', execute=login)],[/cyan]")
        console.print("[cyan]    invariants=[...],[/cyan]")
        console.print("[cyan]    strategy=BFS(),[/cyan]")
        console.print("[cyan])[/cyan]")
        console.print("[cyan]result = agent.explore()[/cyan]")
        console.print("[dim]```[/dim]")
        console.print()

    console.print("[dim]Documentation: https://venomqa.dev[/dim]")
    console.print("[dim]GitHub: https://github.com/namanag97/venomqa[/dim]")
    console.print()

    if keep_running:
        console.print(f"[cyan]Server still running on http://127.0.0.1:{port}[/cyan]")
        console.print("[dim]Press Ctrl+C to stop[/dim]")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/yellow]")
            server.shutdown()
    else:
        server.shutdown()
