#!/usr/bin/env python3
"""
Mock Medusa E-commerce API for testing VenomQA.

This is a simplified mock that mimics the Medusa API structure
for demonstration and testing purposes.
"""

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uvicorn
import uuid

app = FastAPI(title="Mock Medusa API", version="1.0.0")

# In-memory storage
products_db = {}
carts_db = {}
orders_db = {}
customers_db = {}
sessions = {}

# Default admin credentials
ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "supersecret"


# Models
class LoginRequest(BaseModel):
    email: str
    password: str


class CustomerRegister(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str


class Product(BaseModel):
    title: str
    description: Optional[str] = None
    is_giftcard: bool = False
    discountable: bool = True


class LineItem(BaseModel):
    variant_id: str
    quantity: int


# Health check
@app.get("/health")
def health_check():
    return {"status": "ok"}


# Admin Auth
@app.post("/admin/auth")
def admin_login(request: LoginRequest, response: Response):
    if request.email == ADMIN_EMAIL and request.password == ADMIN_PASSWORD:
        session_id = str(uuid.uuid4())
        sessions[session_id] = {"type": "admin", "email": request.email}
        response.set_cookie("connect.sid", session_id)
        return {
            "user": {
                "id": "usr_admin",
                "email": request.email,
                "role": "admin"
            }
        }
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.delete("/admin/auth")
def admin_logout():
    return {"message": "Logged out successfully"}


# Store: Customers
@app.post("/store/customers")
def register_customer(customer: CustomerRegister):
    customer_id = f"cus_{uuid.uuid4().hex[:8]}"
    customers_db[customer_id] = {
        "id": customer_id,
        "email": customer.email,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "created_at": datetime.utcnow().isoformat()
    }
    return {"customer": customers_db[customer_id]}


@app.post("/store/auth")
def customer_login(request: LoginRequest, response: Response):
    # Find customer by email
    customer = None
    for cust in customers_db.values():
        if cust["email"] == request.email:
            customer = cust
            break

    if customer:
        session_id = str(uuid.uuid4())
        sessions[session_id] = {"type": "customer", "customer_id": customer["id"]}
        response.set_cookie("connect.sid", session_id)
        return {"customer": customer}
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.delete("/store/auth")
def customer_logout():
    return {"message": "Logged out successfully"}


# Store: Products
@app.get("/store/products")
def list_products():
    # Create some sample products if none exist
    if not products_db:
        for i in range(3):
            product_id = f"prod_{uuid.uuid4().hex[:8]}"
            variant_id = f"variant_{uuid.uuid4().hex[:8]}"
            products_db[product_id] = {
                "id": product_id,
                "title": f"Sample Product {i+1}",
                "description": f"Description for product {i+1}",
                "variants": [
                    {
                        "id": variant_id,
                        "title": "Default",
                        "prices": [
                            {"amount": 1000 * (i+1), "currency_code": "usd"}
                        ]
                    }
                ]
            }

    return {"products": list(products_db.values())}


@app.get("/store/products/{product_id}")
def get_product(product_id: str):
    if product_id in products_db:
        return {"product": products_db[product_id]}
    raise HTTPException(status_code=404, detail="Product not found")


# Admin: Products
@app.post("/admin/products")
def create_product(product: Dict[str, Any]):
    product_id = f"prod_{uuid.uuid4().hex[:8]}"
    variant_id = f"variant_{uuid.uuid4().hex[:8]}"

    new_product = {
        "id": product_id,
        "title": product.get("title", "New Product"),
        "description": product.get("description", ""),
        "is_giftcard": product.get("is_giftcard", False),
        "discountable": product.get("discountable", True),
        "variants": [
            {
                "id": variant_id,
                "title": "Default",
                "prices": [{"amount": 1000, "currency_code": "usd"}]
            }
        ],
        "created_at": datetime.utcnow().isoformat()
    }
    products_db[product_id] = new_product
    return {"product": new_product}


@app.post("/admin/products/{product_id}")
def update_product(product_id: str, updates: Dict[str, Any]):
    if product_id in products_db:
        products_db[product_id].update(updates)
        return {"product": products_db[product_id]}
    raise HTTPException(status_code=404, detail="Product not found")


@app.delete("/admin/products/{product_id}")
def delete_product(product_id: str):
    if product_id in products_db:
        del products_db[product_id]
        return {"id": product_id, "object": "product", "deleted": True}
    raise HTTPException(status_code=404, detail="Product not found")


# Store: Carts
@app.post("/store/carts")
def create_cart():
    cart_id = f"cart_{uuid.uuid4().hex[:8]}"
    region_id = f"reg_{uuid.uuid4().hex[:8]}"

    carts_db[cart_id] = {
        "id": cart_id,
        "region_id": region_id,
        "items": [],
        "total": 0,
        "created_at": datetime.utcnow().isoformat()
    }
    return {"cart": carts_db[cart_id]}


@app.get("/store/carts/{cart_id}")
def get_cart(cart_id: str):
    if cart_id in carts_db:
        return {"cart": carts_db[cart_id]}
    raise HTTPException(status_code=404, detail="Cart not found")


@app.post("/store/carts/{cart_id}/line-items")
def add_to_cart(cart_id: str, item: LineItem):
    if cart_id not in carts_db:
        raise HTTPException(status_code=404, detail="Cart not found")

    line_item_id = f"item_{uuid.uuid4().hex[:8]}"
    line_item = {
        "id": line_item_id,
        "variant_id": item.variant_id,
        "quantity": item.quantity,
        "unit_price": 1000
    }

    carts_db[cart_id]["items"].append(line_item)
    # BUG: Wrong calculation - divides instead of multiplies
    carts_db[cart_id]["total"] = sum(
        item["unit_price"] // item["quantity"]  # WRONG: should be *
        for item in carts_db[cart_id]["items"]
    )

    return {"cart": carts_db[cart_id]}


@app.post("/store/carts/{cart_id}/line-items/{line_item_id}")
def update_cart_item(cart_id: str, line_item_id: str, updates: Dict[str, Any]):
    if cart_id not in carts_db:
        raise HTTPException(status_code=404, detail="Cart not found")

    for item in carts_db[cart_id]["items"]:
        if item["id"] == line_item_id:
            item["quantity"] = updates.get("quantity", item["quantity"])
            carts_db[cart_id]["total"] = sum(
                i["unit_price"] * i["quantity"]
                for i in carts_db[cart_id]["items"]
            )
            return {"cart": carts_db[cart_id]}

    raise HTTPException(status_code=404, detail="Line item not found")


@app.delete("/store/carts/{cart_id}/line-items/{line_item_id}")
def remove_from_cart(cart_id: str, line_item_id: str):
    if cart_id not in carts_db:
        raise HTTPException(status_code=404, detail="Cart not found")

    carts_db[cart_id]["items"] = [
        item for item in carts_db[cart_id]["items"]
        if item["id"] != line_item_id
    ]
    carts_db[cart_id]["total"] = sum(
        item["unit_price"] * item["quantity"]
        for item in carts_db[cart_id]["items"]
    )

    return {"cart": carts_db[cart_id]}


# Orders
@app.post("/store/carts/{cart_id}/complete")
def complete_cart(cart_id: str):
    if cart_id not in carts_db:
        raise HTTPException(status_code=404, detail="Cart not found")

    order_id = f"order_{uuid.uuid4().hex[:8]}"
    cart = carts_db[cart_id]

    orders_db[order_id] = {
        "id": order_id,
        "status": "pending",
        "fulfillment_status": "not_fulfilled",
        "payment_status": "awaiting",
        "items": cart["items"],
        "total": cart["total"],
        "created_at": datetime.utcnow().isoformat()
    }

    return {"data": orders_db[order_id]}


@app.get("/store/orders/{order_id}")
def get_order(order_id: str):
    if order_id in orders_db:
        return {"order": orders_db[order_id]}
    raise HTTPException(status_code=404, detail="Order not found")


@app.get("/admin/orders")
def list_orders():
    return {"orders": list(orders_db.values())}


@app.get("/admin/orders/{order_id}")
def get_order_admin(order_id: str):
    if order_id in orders_db:
        return {"order": orders_db[order_id]}
    raise HTTPException(status_code=404, detail="Order not found")


@app.post("/admin/orders/{order_id}/cancel")
def cancel_order(order_id: str):
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")

    orders_db[order_id]["status"] = "cancelled"
    return {"order": orders_db[order_id]}


if __name__ == "__main__":
    print("=" * 80)
    print("Mock Medusa E-commerce API Server")
    print("=" * 80)
    print()
    print("Server starting on: http://localhost:9000")
    print("Admin credentials:")
    print(f"  Email: {ADMIN_EMAIL}")
    print(f"  Password: {ADMIN_PASSWORD}")
    print()
    print("API Documentation: http://localhost:9000/docs")
    print("=" * 80)
    print()

    uvicorn.run(app, host="0.0.0.0", port=9000)
