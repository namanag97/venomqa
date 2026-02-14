"""VenomQA Test Server - A simple API server for testing VenomQA.

Run this server to have a working API endpoint for the quickstart tutorial.
This is a standalone FastAPI server that new users can run immediately
without any external dependencies.

Usage:
    # Install dependencies
    pip install fastapi uvicorn

    # Run the server
    python test_server.py

    # Or with uvicorn directly
    uvicorn test_server:app --reload --port 8000

The server provides:
    - GET /health         - Health check endpoint
    - GET /items          - List all items
    - POST /items         - Create a new item
    - GET /items/{id}     - Get item by ID
    - PUT /items/{id}     - Update item by ID
    - DELETE /items/{id}  - Delete item by ID
"""

from datetime import datetime
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError:
    print("Error: FastAPI and Pydantic are required.")
    print("Install them with: pip install fastapi uvicorn pydantic")
    exit(1)

app = FastAPI(
    title="VenomQA Test Server",
    description="A simple API for testing VenomQA - use this to run through the quickstart tutorial.",
    version="1.0.0",
)


# ============================================================================
# In-memory storage (resets when server restarts)
# ============================================================================

items_db: dict[int, dict] = {}
next_id = 1


# ============================================================================
# Pydantic Models
# ============================================================================


class ItemCreate(BaseModel):
    """Request body for creating an item."""
    name: str
    description: Optional[str] = None
    price: float = 0.0


class ItemUpdate(BaseModel):
    """Request body for updating an item."""
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None


class Item(BaseModel):
    """Response model for an item."""
    id: int
    name: str
    description: Optional[str]
    price: float
    created_at: str
    updated_at: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    version: str
    items_count: int


class ItemsListResponse(BaseModel):
    """Response for listing items."""
    items: list[Item]
    total: int


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint.

    Returns the server status and current item count.
    Use this to verify the server is running.
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
        items_count=len(items_db),
    )


@app.get("/items", response_model=ItemsListResponse, tags=["Items"])
async def list_items():
    """List all items.

    Returns all items in the database.
    """
    items = [Item(**item) for item in items_db.values()]
    return ItemsListResponse(items=items, total=len(items))


@app.post("/items", response_model=Item, status_code=201, tags=["Items"])
async def create_item(item: ItemCreate):
    """Create a new item.

    Creates an item with the given name, description, and price.
    Returns the created item with its assigned ID.
    """
    global next_id

    now = datetime.utcnow().isoformat()
    new_item = {
        "id": next_id,
        "name": item.name,
        "description": item.description,
        "price": item.price,
        "created_at": now,
        "updated_at": now,
    }

    items_db[next_id] = new_item
    next_id += 1

    return Item(**new_item)


@app.get("/items/{item_id}", response_model=Item, tags=["Items"])
async def get_item(item_id: int):
    """Get an item by ID.

    Returns the item with the given ID.
    Returns 404 if item not found.
    """
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail=f"Item with id {item_id} not found")

    return Item(**items_db[item_id])


@app.put("/items/{item_id}", response_model=Item, tags=["Items"])
async def update_item(item_id: int, item: ItemUpdate):
    """Update an item.

    Updates the item with the given ID.
    Only provided fields are updated.
    Returns 404 if item not found.
    """
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail=f"Item with id {item_id} not found")

    existing = items_db[item_id]

    if item.name is not None:
        existing["name"] = item.name
    if item.description is not None:
        existing["description"] = item.description
    if item.price is not None:
        existing["price"] = item.price

    existing["updated_at"] = datetime.utcnow().isoformat()

    return Item(**existing)


@app.delete("/items/{item_id}", status_code=204, tags=["Items"])
async def delete_item(item_id: int):
    """Delete an item.

    Removes the item with the given ID.
    Returns 404 if item not found.
    Returns 204 (no content) on success.
    """
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail=f"Item with id {item_id} not found")

    del items_db[item_id]
    return None


@app.post("/reset", status_code=204, tags=["Admin"])
async def reset_database():
    """Reset the database.

    Clears all items from the in-memory database.
    Useful for cleaning up between test runs.
    """
    global next_id
    items_db.clear()
    next_id = 1
    return None


# ============================================================================
# Main entry point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("VenomQA Test Server")
    print("=" * 60)
    print()
    print("Starting server at http://localhost:8000")
    print()
    print("Available endpoints:")
    print("  GET  /health        - Health check")
    print("  GET  /items         - List all items")
    print("  POST /items         - Create item")
    print("  GET  /items/{id}    - Get item by ID")
    print("  PUT  /items/{id}    - Update item by ID")
    print("  DELETE /items/{id}  - Delete item by ID")
    print("  POST /reset         - Reset database")
    print()
    print("API docs: http://localhost:8000/docs")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
