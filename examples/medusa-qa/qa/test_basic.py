#!/usr/bin/env python3
"""
Basic functional test for the Medusa Mock API.

This script verifies that the mock API is working and demonstrates
the basic flow of a user journey through the e-commerce system.
"""

import requests
import json


def print_section(title):
    print()
    print("=" * 80)
    print(f" {title}")
    print("=" * 80)


def print_response(response):
    print(f"Status: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response: {response.text}")


def main():
    base_url = "http://localhost:9000"
    context = {}

    print("=" * 80)
    print(" Medusa E-commerce API - Basic Journey Test")
    print("=" * 80)

    # 1. Health Check
    print_section("1. Health Check")
    response = requests.get(f"{base_url}/health")
    print_response(response)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    print("✓ Health check passed")

    # 2. List Products (Public)
    print_section("2. List Products (No Auth Required)")
    response = requests.get(f"{base_url}/store/products")
    print_response(response)
    assert response.status_code == 200
    products = response.json()["products"]
    assert len(products) > 0
    print(f"✓ Found {len(products)} products")

    # Extract product and variant IDs
    product = products[0]
    context["product_id"] = product["id"]
    context["variant_id"] = product["variants"][0]["id"]
    print(f"  Using product: {context['product_id']}")
    print(f"  Using variant: {context['variant_id']}")

    # 3. Get Specific Product
    print_section("3. Get Product Details")
    response = requests.get(f"{base_url}/store/products/{context['product_id']}")
    print_response(response)
    assert response.status_code == 200
    print("✓ Product details retrieved")

    # 4. Create Cart
    print_section("4. Create Shopping Cart")
    response = requests.post(f"{base_url}/store/carts")
    print_response(response)
    assert response.status_code == 200
    cart = response.json()["cart"]
    context["cart_id"] = cart["id"]
    print(f"✓ Cart created: {context['cart_id']}")

    # 5. Add Item to Cart
    print_section("5. Add Item to Cart")
    response = requests.post(
        f"{base_url}/store/carts/{context['cart_id']}/line-items",
        json={
            "variant_id": context["variant_id"],
            "quantity": 2
        }
    )
    print_response(response)
    assert response.status_code == 200
    cart = response.json()["cart"]
    assert len(cart["items"]) == 1
    context["line_item_id"] = cart["items"][0]["id"]
    print(f"✓ Item added to cart")
    print(f"  Line item: {context['line_item_id']}")
    print(f"  Cart total: ${cart['total'] / 100}")

    # 6. Update Cart Item Quantity
    print_section("6. Update Item Quantity")
    response = requests.post(
        f"{base_url}/store/carts/{context['cart_id']}/line-items/{context['line_item_id']}",
        json={"quantity": 3}
    )
    print_response(response)
    assert response.status_code == 200
    cart = response.json()["cart"]
    assert cart["items"][0]["quantity"] == 3
    print(f"✓ Quantity updated to 3")
    print(f"  New total: ${cart['total'] / 100}")

    # 7. Complete Cart (Create Order)
    print_section("7. Complete Cart / Create Order")
    response = requests.post(f"{base_url}/store/carts/{context['cart_id']}/complete")
    print_response(response)
    assert response.status_code == 200
    order = response.json()["data"]
    context["order_id"] = order["id"]
    print(f"✓ Order created: {context['order_id']}")
    print(f"  Status: {order['status']}")
    print(f"  Total: ${order['total'] / 100}")

    # 8. Get Order Details
    print_section("8. Get Order Details")
    response = requests.get(f"{base_url}/store/orders/{context['order_id']}")
    print_response(response)
    assert response.status_code == 200
    print("✓ Order details retrieved")

    # 9. Admin Login
    print_section("9. Admin Login")
    response = requests.post(
        f"{base_url}/admin/auth",
        json={
            "email": "admin@test.com",
            "password": "supersecret"
        }
    )
    print_response(response)
    assert response.status_code == 200
    context["admin_token"] = response.cookies.get("connect.sid")
    print(f"✓ Admin logged in")
    print(f"  Session: {context['admin_token'][:20]}...")

    # 10. List Orders (Admin)
    print_section("10. List All Orders (Admin)")
    response = requests.get(
        f"{base_url}/admin/orders",
        cookies={"connect.sid": context["admin_token"]}
    )
    print_response(response)
    assert response.status_code == 200
    orders = response.json()["orders"]
    print(f"✓ Found {len(orders)} orders")

    # 11. Get Order (Admin)
    print_section("11. Get Order Details (Admin)")
    response = requests.get(
        f"{base_url}/admin/orders/{context['order_id']}",
        cookies={"connect.sid": context["admin_token"]}
    )
    print_response(response)
    assert response.status_code == 200
    print("✓ Order details retrieved (admin view)")

    # 12. Cancel Order
    print_section("12. Cancel Order (Admin)")
    response = requests.post(
        f"{base_url}/admin/orders/{context['order_id']}/cancel",
        cookies={"connect.sid": context["admin_token"]}
    )
    print_response(response)
    assert response.status_code == 200
    order = response.json()["order"]
    assert order["status"] == "cancelled"
    print("✓ Order cancelled successfully")

    # 13. Create Product (Admin)
    print_section("13. Create Product (Admin)")
    response = requests.post(
        f"{base_url}/admin/products",
        json={
            "title": "Test Product",
            "description": "A product created by test"
        },
        cookies={"connect.sid": context["admin_token"]}
    )
    print_response(response)
    assert response.status_code == 200
    product = response.json()["product"]
    context["new_product_id"] = product["id"]
    print(f"✓ Product created: {context['new_product_id']}")

    # 14. Update Product (Admin)
    print_section("14. Update Product (Admin)")
    response = requests.post(
        f"{base_url}/admin/products/{context['new_product_id']}",
        json={
            "title": "Updated Test Product",
            "description": "Updated description"
        },
        cookies={"connect.sid": context["admin_token"]}
    )
    print_response(response)
    assert response.status_code == 200
    print("✓ Product updated")

    # 15. Delete Product (Admin)
    print_section("15. Delete Product (Admin)")
    response = requests.delete(
        f"{base_url}/admin/products/{context['new_product_id']}",
        cookies={"connect.sid": context["admin_token"]}
    )
    print_response(response)
    assert response.status_code == 200
    print("✓ Product deleted")

    # Summary
    print()
    print("=" * 80)
    print(" ALL TESTS PASSED!")
    print("=" * 80)
    print()
    print("Context accumulated through the journey:")
    for key, value in context.items():
        if isinstance(value, str) and len(value) > 40:
            print(f"  {key}: {value[:37]}...")
        else:
            print(f"  {key}: {value}")
    print()


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print()
        print("✗ TEST FAILED")
        print(f"  {e}")
        exit(1)
    except requests.RequestException as e:
        print()
        print("✗ CONNECTION ERROR")
        print(f"  {e}")
        print()
        print("Make sure the API is running:")
        print("  cd examples/medusa-qa")
        print("  docker compose up -d")
        exit(1)
    except Exception as e:
        print()
        print("✗ UNEXPECTED ERROR")
        print(f"  {e}")
        import traceback
        traceback.print_exc()
        exit(1)
