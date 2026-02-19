"""VenomQA Quickstart - Sample FastAPI Application.

A simple REST API for demonstrating VenomQA testing capabilities.
"""

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="VenomQA Quickstart API",
    description="Sample API for VenomQA testing",
    version="1.0.0",
)

# In-memory storage (replace with database in production)
items_db: dict[int, dict] = {}
next_id = 1


class ItemCreate(BaseModel):
    """Schema for creating an item."""
    name: str
    description: Optional[str] = None
    price: float = 0.0


class ItemUpdate(BaseModel):
    """Schema for updating an item."""
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None


class Item(BaseModel):
    """Schema for item response."""
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


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
    )


@app.get("/api/items", response_model=list[Item])
async def list_items():
    """List all items."""
    return [Item(**item) for item in items_db.values()]


@app.post("/api/items", response_model=Item, status_code=201)
async def create_item(item: ItemCreate):
    """Create a new item."""
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


@app.get("/api/items/{item_id}", response_model=Item)
async def get_item(item_id: int):
    """Get an item by ID."""
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    return Item(**items_db[item_id])


@app.put("/api/items/{item_id}", response_model=Item)
async def update_item(item_id: int, item: ItemUpdate):
    """Update an item."""
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    existing = items_db[item_id]

    if item.name is not None:
        existing["name"] = item.name
    if item.description is not None:
        existing["description"] = item.description
    if item.price is not None:
        existing["price"] = item.price

    existing["updated_at"] = datetime.utcnow().isoformat()

    return Item(**existing)


@app.delete("/api/items/{item_id}", status_code=204)
async def delete_item(item_id: int):
    """Delete an item."""
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    del items_db[item_id]
    return None


# Error handlers
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Handle unexpected errors."""
    return {"detail": "Internal server error", "type": type(exc).__name__}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
