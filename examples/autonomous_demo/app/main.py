"""Demo API with X-API-Key authentication and a planted bug.

This API demonstrates:
1. API key authentication (X-API-Key header)
2. A planted bug: refund endpoint allows over-refunds

Run with: uvicorn main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel


# In-memory storage (for demo purposes)
orders: dict[str, dict[str, Any]] = {}
order_counter = 0

# API Key (from environment or default)
API_KEY = os.environ.get("API_KEY", "demo-api-key-12345")


app = FastAPI(
    title="Demo Orders API",
    description="A simple orders API with API key auth and a planted bug",
    version="1.0.0",
)


# Models
class OrderCreate(BaseModel):
    amount: float
    description: str = ""


class RefundRequest(BaseModel):
    amount: float


class Order(BaseModel):
    id: str
    amount: float
    description: str
    refunded_amount: float
    status: str


# Auth dependency
def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# Endpoints
@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint (no auth required)."""
    return {"status": "healthy"}


@app.post("/orders", response_model=Order, dependencies=[Depends(verify_api_key)])
def create_order(order: OrderCreate) -> Order:
    """Create a new order."""
    global order_counter
    order_counter += 1
    order_id = f"order_{order_counter}"

    orders[order_id] = {
        "id": order_id,
        "amount": order.amount,
        "description": order.description,
        "refunded_amount": 0.0,
        "status": "created",
    }

    return Order(**orders[order_id])


@app.get("/orders/{order_id}", response_model=Order, dependencies=[Depends(verify_api_key)])
def get_order(order_id: str) -> Order:
    """Get an order by ID."""
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found")
    return Order(**orders[order_id])


@app.post("/orders/{order_id}/refund", response_model=Order, dependencies=[Depends(verify_api_key)])
def refund_order(order_id: str, refund: RefundRequest) -> Order:
    """Refund an order (partial or full).

    BUG: This endpoint allows refunding more than the order amount!
    The check `refund.amount <= order["amount"]` is missing.
    """
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found")

    order = orders[order_id]

    if refund.amount <= 0:
        raise HTTPException(status_code=400, detail="Refund amount must be positive")

    # BUG: Missing check - should verify:
    # if order["refunded_amount"] + refund.amount > order["amount"]:
    #     raise HTTPException(status_code=400, detail="Refund exceeds order amount")

    order["refunded_amount"] += refund.amount
    order["status"] = "refunded" if order["refunded_amount"] >= order["amount"] else "partially_refunded"

    return Order(**order)


@app.get("/orders", response_model=list[Order], dependencies=[Depends(verify_api_key)])
def list_orders() -> list[Order]:
    """List all orders."""
    return [Order(**o) for o in orders.values()]


@app.delete("/orders/{order_id}", dependencies=[Depends(verify_api_key)])
def delete_order(order_id: str) -> dict[str, str]:
    """Delete an order."""
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found")
    del orders[order_id]
    return {"status": "deleted"}


# Reset endpoint for testing
@app.post("/reset", dependencies=[Depends(verify_api_key)])
def reset() -> dict[str, str]:
    """Reset all data (for testing)."""
    global orders, order_counter
    orders = {}
    order_counter = 0
    return {"status": "reset"}
