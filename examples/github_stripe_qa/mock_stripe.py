"""Mock Stripe API server with an intentional bug for VenomQA to discover.

Bug planted:
    POST /refunds does NOT validate that the refund amount is ≤ the original
    payment intent amount. A real Stripe API returns an error
    ("amount_too_large") when you try to over-refund; this mock silently
    accepts any amount, causing refunded_amount > amount on the PaymentIntent.

Run standalone:
    python mock_stripe.py
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Shared in-memory state
# ---------------------------------------------------------------------------

_state: dict[str, Any] = {
    "customers": {},        # id -> {id, email, name, balance}
    "payment_intents": {},  # id -> {id, amount, currency, status, customer_id, refunded_amount}
    "refunds": {},          # id -> {id, amount, payment_intent_id, status}
}
_lock = threading.Lock()


def reset_state() -> None:
    """Reset all server state. Call between tests."""
    with _lock:
        _state["customers"].clear()
        _state["payment_intents"].clear()
        _state["refunds"].clear()


def get_state_snapshot() -> dict[str, Any]:
    """Return a copy of state for invariant inspection."""
    with _lock:
        return {
            "customers": dict(_state["customers"]),
            "payment_intents": dict(_state["payment_intents"]),
            "refunds": dict(_state["refunds"]),
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


class StripeHandler(BaseHTTPRequestHandler):
    """Handles mock Stripe API requests."""

    def log_message(self, fmt: str, *args: Any) -> None:
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
            # POST /customers
            if path == "/customers":
                cid = f"cus_{uuid.uuid4().hex[:14]}"
                customer = {
                    "id": cid,
                    "email": body.get("email", ""),
                    "name": body.get("name", ""),
                    "balance": 0,
                }
                _state["customers"][cid] = customer
                _send_json(self, 201, customer)
                return

            # POST /payment_intents
            if path == "/payment_intents":
                customer_id = body.get("customer_id")
                if customer_id and customer_id not in _state["customers"]:
                    _send_json(self, 404, {"error": "Customer not found"})
                    return
                pid = f"pi_{uuid.uuid4().hex[:14]}"
                amount = int(body.get("amount", 0))
                pi = {
                    "id": pid,
                    "amount": amount,
                    "currency": body.get("currency", "usd"),
                    "status": "requires_confirmation",
                    "customer_id": customer_id,
                    "refunded_amount": 0,
                }
                _state["payment_intents"][pid] = pi
                _send_json(self, 201, pi)
                return

            # POST /payment_intents/{id}/confirm
            m = re.match(r"^/payment_intents/([^/]+)/confirm$", path)
            if m:
                pid = m.group(1)
                if pid not in _state["payment_intents"]:
                    _send_json(self, 404, {"error": "PaymentIntent not found"})
                    return
                pi = _state["payment_intents"][pid]
                pi["status"] = "succeeded"
                _send_json(self, 200, pi)
                return

            # POST /refunds
            if path == "/refunds":
                pid = body.get("payment_intent_id")
                refund_amount = int(body.get("amount", 0))

                if not pid or pid not in _state["payment_intents"]:
                    _send_json(self, 404, {"error": "PaymentIntent not found"})
                    return

                pi = _state["payment_intents"][pid]

                # -------------------------------------------------------
                # BUG: Missing validation — a real Stripe API would reject
                # this with HTTP 400 / code "amount_too_large" when:
                #   refund_amount > (pi["amount"] - pi["refunded_amount"])
                # This mock silently accepts the over-refund.
                # -------------------------------------------------------

                rid = f"re_{uuid.uuid4().hex[:14]}"
                refund = {
                    "id": rid,
                    "amount": refund_amount,
                    "payment_intent_id": pid,
                    "status": "succeeded",
                }
                _state["refunds"][rid] = refund
                pi["refunded_amount"] += refund_amount
                _send_json(self, 201, refund)
                return

            _send_json(self, 404, {"error": "Not found"})

    # ------------------------------------------------------------------ GET
    def do_GET(self) -> None:
        path = urlparse(self.path).path

        with _lock:
            # GET /customers/{id}
            m = re.match(r"^/customers/([^/]+)$", path)
            if m:
                cid = m.group(1)
                if cid not in _state["customers"]:
                    _send_json(self, 404, {"error": "Customer not found"})
                    return
                _send_json(self, 200, _state["customers"][cid])
                return

            # GET /payment_intents
            if path == "/payment_intents":
                _send_json(self, 200, list(_state["payment_intents"].values()))
                return

            # GET /payment_intents/{id}
            m = re.match(r"^/payment_intents/([^/]+)$", path)
            if m:
                pid = m.group(1)
                if pid not in _state["payment_intents"]:
                    _send_json(self, 404, {"error": "PaymentIntent not found"})
                    return
                _send_json(self, 200, _state["payment_intents"][pid])
                return

            # GET /refunds/{id}
            m = re.match(r"^/refunds/([^/]+)$", path)
            if m:
                rid = m.group(1)
                if rid not in _state["refunds"]:
                    _send_json(self, 404, {"error": "Refund not found"})
                    return
                _send_json(self, 200, _state["refunds"][rid])
                return

            _send_json(self, 404, {"error": "Not found"})


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

def start_server(port: int = 8102) -> HTTPServer:
    """Start the mock Stripe server in a daemon thread and return it."""
    server = HTTPServer(("localhost", port), StripeHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


if __name__ == "__main__":
    import time

    reset_state()
    srv = start_server(8102)
    print("Mock Stripe API running on http://localhost:8102")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.shutdown()
