"""Demo command for VenomQA.

Shows a compelling demo with a planted bug that VenomQA finds.
The bug only appears when you call refund twice - unit tests miss this.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

import click


class BuggyOrderAPI(BaseHTTPRequestHandler):
    """Mock order API with a planted bug: allows double refunds.

    The bug: You can refund an order multiple times, exceeding the original amount.
    Unit tests pass because they test refund in isolation.
    VenomQA finds it by testing: create_order → refund → refund → check
    """

    orders: dict[str, dict[str, Any]] = {}
    _counter: int = 0

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self._send_json(200, {"status": "ok"})

        elif path == "/orders":
            self._send_json(200, list(self.orders.values()))

        elif path.startswith("/orders/"):
            order_id = path.split("/")[-1]
            if order_id in self.orders:
                self._send_json(200, self.orders[order_id])
            else:
                self._send_json(404, {"error": "Order not found"})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

        if self.path == "/orders":
            # Create order
            BuggyOrderAPI._counter += 1
            order_id = str(BuggyOrderAPI._counter)
            order = {
                "id": order_id,
                "amount": body.get("amount", 100),
                "refunded": 0,
                "status": "paid",
            }
            self.orders[order_id] = order
            self._send_json(201, order)

        elif self.path.startswith("/orders/") and self.path.endswith("/refund"):
            # Refund order - BUG: doesn't check if already fully refunded!
            order_id = self.path.split("/")[-2]
            if order_id not in self.orders:
                self._send_json(404, {"error": "Order not found"})
                return

            order = self.orders[order_id]
            refund_amount = body.get("amount", order["amount"])

            # BUG: We add to refunded without checking if it exceeds amount!
            # A correct implementation would check: order["refunded"] + refund_amount <= order["amount"]
            order["refunded"] += refund_amount
            order["status"] = "refunded" if order["refunded"] >= order["amount"] else "partially_refunded"

            self._send_json(200, {"refunded": refund_amount, "order": order})
        else:
            self._send_json(404, {"error": "Not found"})

    def _send_json(self, status: int, data: Any) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if data is not None:
            self.wfile.write(json.dumps(data).encode())

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress logging


def start_demo_server(port: int = 8000) -> HTTPServer:
    """Start the demo server."""
    BuggyOrderAPI.orders = {}
    BuggyOrderAPI._counter = 0
    server = HTTPServer(("127.0.0.1", port), BuggyOrderAPI)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_demo_exploration(base_url: str) -> dict[str, Any]:
    """Run exploration and find the double-refund bug."""
    from venomqa import Action, Agent, World, BFS, Invariant, Severity
    from venomqa.adapters.http import HttpClient

    api = HttpClient(base_url)

    # Track what we found
    results = {
        "bug_found": False,
        "bug_sequence": [],
        "states_visited": 0,
        "transitions": 0,
    }

    # --- Actions ---

    def create_order(api: Any, context: Any) -> Any:
        resp = api.post("/orders", json={"amount": 100})
        if resp.status_code == 201:
            context.set("order_id", resp.json()["id"])
            context.set("order_amount", 100)
        return resp

    def refund_order(api: Any, context: Any) -> Any:
        order_id = context.get("order_id")
        resp = api.post(f"/orders/{order_id}/refund", json={"amount": 100})
        return resp

    def get_order(api: Any, context: Any) -> Any:
        order_id = context.get("order_id")
        resp = api.get(f"/orders/{order_id}")
        if resp.status_code == 200:
            context.set("current_order", resp.json())
        return resp

    # --- Invariant: The bug detector ---

    def no_over_refund(world: Any) -> bool:
        """Refunded amount must never exceed order amount."""
        order_id = world.context.get("order_id")
        if not order_id:
            return True

        resp = world.api.get(f"/orders/{order_id}")
        if resp.status_code != 200:
            return True

        order = resp.json()
        # THE CHECK: refunded should never exceed amount
        return order.get("refunded", 0) <= order.get("amount", 0)

    # --- Run exploration ---

    world = World(api=api, state_from_context=["order_id"])

    agent = Agent(
        world=world,
        actions=[
            Action(name="create_order", execute=create_order, expected_status=[201]),
            Action(name="refund", execute=refund_order, expected_status=[200],
                   preconditions=["create_order"]),
            Action(name="get_order", execute=get_order, expected_status=[200],
                   preconditions=["create_order"]),
        ],
        invariants=[
            Invariant(
                name="no_over_refund",
                check=no_over_refund,
                message="Refunded amount exceeds order total!",
                severity=Severity.CRITICAL,
            ),
        ],
        strategy=BFS(),
        max_steps=20,
    )

    result = agent.explore()

    results["states_visited"] = result.states_visited
    results["transitions"] = result.transitions_taken

    if result.violations:
        results["bug_found"] = True
        # Get the path to the bug
        v = result.violations[0]
        results["bug_message"] = v.message
        results["violation"] = v

    return results


@click.command()
@click.option("--port", "-p", default=8000, help="Port for demo server")
@click.option("--verbose", "-v", is_flag=True, help="Show HTTP requests")
def demo(port: int, verbose: bool) -> None:
    """See VenomQA find a real bug that unit tests miss.

    This demo runs a mock Order API with a hidden bug:
    you can refund the same order multiple times, exceeding the original amount.

    Unit tests pass because they test "refund" in isolation.
    VenomQA finds the bug by testing the SEQUENCE: create → refund → refund

    \b
    After the demo, try it on YOUR API:
        venomqa init --with-sample
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box

    console = Console()
    console.print()

    # === INTRO: Explain the problem ===
    console.print(Panel.fit(
        "[bold cyan]What VenomQA Does[/bold cyan]\n\n"
        "[white]Your unit tests check endpoints ONE AT A TIME:[/white]\n"
        "  [green]✓[/green] POST /orders returns 201\n"
        "  [green]✓[/green] POST /orders/:id/refund returns 200\n"
        "  [green]✓[/green] GET /orders/:id returns 200\n\n"
        "[white]VenomQA tests [bold]SEQUENCES[/bold] to find bugs that appear when:[/white]\n"
        "  [yellow]create_order → refund → refund → get_order[/yellow]\n\n"
        "[dim]Let's demonstrate with a mock API that has a hidden bug...[/dim]",
        border_style="cyan",
    ))
    console.print()

    # === START SERVER ===
    console.print(f"[cyan]Starting mock Order API on http://127.0.0.1:{port}...[/cyan]")
    try:
        server = start_demo_server(port)
        time.sleep(0.3)
        console.print("[green]Server running.[/green]")
    except OSError as e:
        console.print(f"[red]Failed to start server: {e}[/red]")
        console.print(f"[yellow]Try: venomqa demo --port 9000[/yellow]")
        raise SystemExit(1)

    console.print()

    # === SHOW UNIT TEST RESULTS ===
    console.print("[bold]Step 1: Unit Tests (what you probably have)[/bold]")
    console.print()

    # Simulate unit test results
    from venomqa.adapters.http import HttpClient
    api = HttpClient(f"http://127.0.0.1:{port}")

    unit_tests = [
        ("POST /orders", lambda: api.post("/orders", json={"amount": 100}), 201),
        ("POST /orders/1/refund", lambda: api.post("/orders/1/refund", json={"amount": 100}), 200),
        ("GET /orders/1", lambda: api.get("/orders/1"), 200),
    ]

    # Reset server state
    BuggyOrderAPI.orders = {}
    BuggyOrderAPI._counter = 0

    table = Table(title="Unit Test Results", box=box.ROUNDED)
    table.add_column("Test", style="white")
    table.add_column("Status", justify="center")

    for name, action, expected in unit_tests:
        resp = action()
        status = "[green]PASS[/green]" if resp.status_code == expected else "[red]FAIL[/red]"
        table.add_row(name, status)

    console.print(table)
    console.print()
    console.print("[green]All unit tests pass![/green] [dim]But there's a bug hiding...[/dim]")
    console.print()

    # === RUN VENOMQA EXPLORATION ===
    console.print("[bold]Step 2: VenomQA Exploration (testing sequences)[/bold]")
    console.print()
    console.print("[dim]Exploring all possible action sequences...[/dim]")
    console.print()

    # Reset server state for exploration
    BuggyOrderAPI.orders = {}
    BuggyOrderAPI._counter = 0

    results = run_demo_exploration(f"http://127.0.0.1:{port}")

    console.print(f"  States explored: {results['states_visited']}")
    console.print(f"  Transitions: {results['transitions']}")
    console.print()

    # === SHOW THE BUG ===
    if results["bug_found"]:
        console.print(Panel(
            "[bold red]BUG FOUND![/bold red]\n\n"
            "[white]Sequence that triggers the bug:[/white]\n"
            "  [yellow]create_order → refund → refund[/yellow]\n\n"
            "[white]Problem:[/white]\n"
            "  Order amount: $100\n"
            "  Refunded: $200 [red](exceeds order!)[/red]\n\n"
            "[white]The API accepted two $100 refunds on a $100 order.[/white]\n"
            "[white]This passes unit tests but loses money in production![/white]\n\n"
            "[dim]VenomQA found this by testing EVERY possible sequence.[/dim]",
            title="[red]CRITICAL VIOLATION[/red]",
            border_style="red",
        ))
    else:
        console.print("[yellow]No bugs found (unexpected for this demo)[/yellow]")

    console.print()

    # === NEXT STEPS ===
    console.print(Panel(
        "[bold]Ready to find bugs in YOUR API?[/bold]\n\n"
        "1. [cyan]venomqa init --with-sample[/cyan]\n"
        "   Creates project structure with example code\n\n"
        "2. Edit [cyan]venomqa/venomqa.yaml[/cyan]\n"
        "   Set your API URL and database connection\n\n"
        "3. Write actions in [cyan]venomqa/actions/[/cyan]\n"
        "   Define what API calls to test\n\n"
        "4. Run [cyan]python3 venomqa/journeys/sample_journey.py[/cyan]\n"
        "   Find bugs in YOUR API\n\n"
        "[dim]Database required: VenomQA needs to rollback state between[/dim]\n"
        "[dim]branches to test all sequences. Connect to your API's database.[/dim]",
        title="Next Steps",
        border_style="green",
    ))

    console.print()
    console.print("[dim]Docs: https://venomqa.dev | Help: venomqa llm-docs[/dim]")
    console.print()

    server.shutdown()
