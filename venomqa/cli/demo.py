"""Demo server and command for VenomQA.

Provides a zero-config way to see VenomQA in action without setting up an API.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

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
    """Run a demo journey and return results."""
    from venomqa import Client, Journey, Step
    from venomqa.runner import JourneyRunner

    results: dict[str, Any] = {"steps": [], "success": True}

    def health_check(client: Any, ctx: dict) -> Any:
        response = client.get("/health")
        ctx["health_status"] = response.json().get("status")
        return response

    def list_items_empty(client: Any, ctx: dict) -> Any:
        response = client.get("/items")
        ctx["initial_count"] = len(response.json())
        return response

    def create_item(client: Any, ctx: dict) -> Any:
        response = client.post("/items", json={
            "name": "VenomQA Demo Item",
            "description": "Created automatically by venomqa demo",
            "price": 29.99,
        })
        if response.status_code == 201:
            ctx["item_id"] = response.json()["id"]
            ctx["item_name"] = response.json()["name"]
        return response

    def get_item(client: Any, ctx: dict) -> Any:
        item_id = ctx.get("item_id", "1")
        return client.get(f"/items/{item_id}")

    def update_item(client: Any, ctx: dict) -> Any:
        item_id = ctx.get("item_id", "1")
        return client.put(f"/items/{item_id}", json={
            "name": "Updated Demo Item",
            "price": 39.99,
        })

    def delete_item(client: Any, ctx: dict) -> Any:
        item_id = ctx.get("item_id", "1")
        return client.delete(f"/items/{item_id}")

    def verify_deleted(client: Any, ctx: dict) -> Any:
        item_id = ctx.get("item_id", "1")
        return client.get(f"/items/{item_id}")

    journey = Journey(
        name="demo_journey",
        description="VenomQA Demo - CRUD Operations",
        steps=[
            Step(name="health_check", action=health_check, description="Check API health"),
            Step(name="list_items", action=list_items_empty, description="List items (empty)"),
            Step(name="create_item", action=create_item, description="Create a new item"),
            Step(name="get_item", action=get_item, description="Retrieve the item"),
            Step(name="update_item", action=update_item, description="Update the item"),
            Step(name="delete_item", action=delete_item, description="Delete the item"),
            Step(name="verify_deleted", action=verify_deleted, description="Verify deletion (expect 404)", expect_failure=True),
        ],
    )

    client = Client(base_url=base_url)
    runner = JourneyRunner(client=client)
    result = runner.run(journey)

    results["success"] = result.success
    results["duration_ms"] = result.duration_ms
    results["steps"] = [
        {
            "name": sr.step_name,
            "success": sr.success,
            "duration_ms": sr.duration_ms,
        }
        for sr in result.step_results
    ]

    return results


@click.command()
@click.option("--port", "-p", default=8000, help="Port for demo server (default: 8000)")
@click.option("--server-only", is_flag=True, help="Only start the server, don't run journey")
@click.option("--keep-running", "-k", is_flag=True, help="Keep server running after journey")
def demo(port: int, server_only: bool, keep_running: bool) -> None:
    """Run a quick demo to see VenomQA in action.

    This command:
    1. Starts a built-in demo API server
    2. Runs an example journey (CRUD operations)
    3. Shows the results

    No configuration needed - just run it!

    \b
    Examples:
        venomqa demo                    # Run full demo
        venomqa demo --server-only      # Just start the server
        venomqa demo --keep-running     # Keep server after demo
        venomqa demo --port 9000        # Use different port
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box

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

    # Run demo journey
    console.print("[cyan]Running demo journey...[/cyan]")
    console.print()

    base_url = f"http://127.0.0.1:{port}"
    results = run_demo_journey(base_url)

    # Display results
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
