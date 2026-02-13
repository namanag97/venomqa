# Quick Start Guide - Medusa QA Example

## Prerequisites
- Docker (for running the mock API)
- Python 3.10+ (for running tests)

## 3-Step Setup

### 1. Start the API
```bash
cd /Users/namanagarwal/venomQA/examples/medusa-qa
docker compose up -d
```

Wait 10 seconds for the API to start.

### 2. Verify API is Running
```bash
curl http://localhost:9000/health
```

Should return: `{"status":"ok"}`

### 3. Run the Test
```bash
cd qa
python3 test_basic.py
```

## What You'll See

The test will execute 15 API operations demonstrating:

1. **Health Check** - Verify API is responsive
2. **Browse Products** - List available products (public endpoint)
3. **View Product** - Get product details using extracted product_id
4. **Create Cart** - Start shopping session
5. **Add to Cart** - Add product using variant_id from step 2
6. **Update Quantity** - Modify cart using line_item_id from step 5
7. **Create Order** - Complete checkout flow
8. **View Order** - Get order details using order_id
9. **Admin Login** - Authenticate as admin
10. **List Orders** - Admin view all orders
11. **Get Order Details** - Admin view specific order
12. **Cancel Order** - Admin cancel the order
13. **Create Product** - Admin create new product
14. **Update Product** - Admin modify product using extracted product_id
15. **Delete Product** - Admin remove product

## Expected Output

```
ALL TESTS PASSED!

Context accumulated through the journey:
  product_id: prod_xxx
  variant_id: variant_xxx
  cart_id: cart_xxx
  line_item_id: item_xxx
  order_id: order_xxx
  admin_token: xxx
  new_product_id: prod_xxx
```

## What This Demonstrates

### Context-Aware Testing
Each step extracts data (IDs, tokens) and uses them in subsequent steps:
```
List Products → extract product_id
  → Get Product(product_id)
    → Create Cart → extract cart_id
      → Add to Cart(cart_id, variant_id)
```

No hardcoded IDs. No placeholder values. Real context flow.

### E-commerce User Journey
- Customer browses products
- Adds items to cart
- Modifies quantities
- Completes checkout
- Admin manages orders and products

This is how real users interact with the system.

## Cleanup

Stop the API:
```bash
docker compose down
```

Remove volumes (reset all data):
```bash
docker compose down -v
```

## Next Steps

1. **Explore the Actions** - See `qa/actions/` for reusable API functions
2. **Check the Journeys** - See `qa/journeys/` for test scenarios
3. **Read the Docs** - See `README.md` for complete documentation
4. **Try State Exploration** - Run `python3 explore_medusa.py` (WIP)

## Troubleshooting

**Can't connect to API:**
- Check Docker is running: `docker ps`
- Check port 9000 is free: `lsof -i :9000`
- View logs: `docker compose logs`

**Tests fail:**
- Restart API: `docker compose restart`
- Check API health: `curl http://localhost:9000/health`
- Run with verbose output: `python3 test_basic.py -v`

## API Documentation

View the interactive API docs:
```bash
open http://localhost:9000/docs
```

This shows all available endpoints, request/response schemas, and lets you try the API directly in your browser.
