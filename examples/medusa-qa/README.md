# Medusa E-commerce QA with VenomQA

Complete QA test suite for a Medusa-style e-commerce API using VenomQA's stateful journey testing and state exploration.

> **Note**: This example uses a FastAPI-based mock Medusa API for quick testing and demonstration. The API structure mimics the real [Medusa](https://medusajs.com/) e-commerce platform.

## Overview

This example demonstrates:
- **Journey Testing**: Structured test flows for auth, products, cart, and orders
- **State Branching**: Test multiple paths from checkpoints (e.g., fulfill vs cancel order)
- **State Chain Exploration**: Automatic API discovery with context-aware request chaining
- **Real E-commerce Flows**: End-to-end scenarios from product browsing to order fulfillment

## Architecture

```
medusa-qa/
├── docker-compose.yml          # Medusa + Postgres + Redis
├── qa/
│   ├── venomqa.yaml           # VenomQA configuration
│   ├── actions/               # Reusable API actions
│   │   ├── auth_actions.py    # Login, register, logout
│   │   ├── product_actions.py # Product CRUD operations
│   │   ├── cart_actions.py    # Shopping cart operations
│   │   └── order_actions.py   # Order management
│   ├── journeys/              # Test journeys
│   │   ├── auth_journey.py    # Authentication flows
│   │   ├── products_journey.py # Product management
│   │   ├── cart_journey.py    # Cart operations
│   │   └── orders_journey.py  # Order lifecycle
│   └── explore_medusa.py      # State chain exploration script
└── README.md
```

## Quick Start

### 1. Start the Mock Medusa API

```bash
cd examples/medusa-qa
docker compose up -d
```

The API starts in ~10 seconds. Check it's ready:

```bash
curl http://localhost:9000/health
# Should return: {"status":"ok"}
```

View the API docs:
```bash
open http://localhost:9000/docs
```

### 2. Run Basic Test

Verify the API is working with a simple end-to-end test:

```bash
cd qa
python3 test_basic.py
```

This will:
- Test all major API endpoints
- Demonstrate context passing (IDs from one request used in the next)
- Show a complete e-commerce flow from browsing to order completion
- Verify admin operations (product CRUD, order management)

Output shows each step with request/response details and accumulated context.

### 3. Run State Exploration

Automatically discover and test the Medusa API:

```bash
python qa/explore_medusa.py
```

This will:
- Discover API endpoints
- Execute requests with context-aware parameter substitution
- Extract IDs, tokens from responses
- Use extracted data in subsequent requests
- Build a complete state graph
- Generate visualizations and reports

Output:
```
VenomQA State Chain Exploration - Medusa E-commerce
================================================================================

Base URL: http://localhost:9000
Strategy: BFS
Max Depth: 8
Initial Actions: 4

Starting exploration...
...

SUMMARY:
  States Discovered: 42
  Transitions: 87
  Duration: 0:01:23
  Total Requests: 87
  Success Rate: 94.3%

Saved JSON: qa/exploration_results/exploration_result.json
Saved Graph: qa/exploration_results/state_graph.png
Saved HTML: qa/exploration_results/state_graph.html
```

### 4. Run Journeys (TODO)

Run specific test journeys:

```bash
# From the examples/medusa-qa/qa directory
cd qa

# Run all journeys
venomqa run

# Run specific journey
venomqa run complete_order_flow

# Run with verbose output
venomqa run admin_authentication --verbose
```

Available journeys:
- `admin_authentication` - Admin login/logout
- `customer_authentication` - Customer register/login/logout
- `product_crud` - Create, update, delete products
- `product_browsing` - List and search products
- `cart_operations` - Cart CRUD with branching (update vs remove vs checkout)
- `complete_order_flow` - Full checkout flow
- `order_management` - Admin order fulfillment and cancellation

## Understanding the Flows

### 1. Authentication Journey

```python
# journeys/auth_journey.py
Journey:
  1. Admin Login → Get admin token
  2. Admin Logout → Clear session
```

### 2. Product CRUD Journey

```python
# journeys/products_journey.py
Journey:
  1. Admin Login
  2. List Products
  3. Create Product → Extract product_id
  4. [CHECKPOINT: product_created]
  5. Update Product → Uses product_id from context
  6. [CHECKPOINT: product_updated]
  7. Delete Product
```

### 3. Cart Operations Journey (with Branching)

```python
# journeys/cart_journey.py
Journey:
  1. List Products → Extract product_id, variant_id
  2. Create Cart → Extract cart_id
  3. Add to Cart → Uses cart_id + variant_id
  4. [CHECKPOINT: item_in_cart]
  5. BRANCH:
     Path A: Update Quantity
     Path B: Remove Item
     Path C: Add Shipping
```

Each branch starts from the same `item_in_cart` checkpoint, ensuring consistent test state.

### 4. Complete Order Flow

```python
# journeys/orders_journey.py
Journey:
  1. List Products → Get product data
  2. Create Cart → Get cart_id
  3. Add to Cart → Add product to cart
  4. Add Shipping Address → Fill shipping info
  5. Create Payment Session → Initialize payment
  6. Select Payment Session → Choose payment method
  7. Complete Cart → Create order, get order_id
  8. [CHECKPOINT: order_created]
  9. Get Order → Verify order
```

## State Chain Exploration

The `explore_medusa.py` script demonstrates VenomQA's context-aware exploration:

### How It Works

1. **Initial Actions**: Start with entry points (health check, list products, login)

2. **Context Extraction**: From each response, extract:
   - IDs: `product_id`, `cart_id`, `order_id`, `variant_id`
   - Tokens: `auth_token`, session cookies
   - References: URLs, links

3. **Path Parameter Substitution**:
   - Template: `/store/products/{product_id}`
   - Context: `{"product_id": "prod_abc123"}`
   - Result: `/store/products/prod_abc123` ✅ (real ID, not placeholder!)

4. **Deep Chains**: Build connected flows:
   ```
   POST /store/carts
     → {cart_id: "cart_123"}
     → POST /store/carts/cart_123/line-items
       → {line_item_id: "item_456"}
       → DELETE /store/carts/cart_123/line-items/item_456
   ```

5. **State Graph**: Visualize all discovered paths and transitions

### Example Output

```
STATE GRAPH SAMPLE:
  [1] Initial
  [2] Anonymous | Products Listed
      Context: product_id=prod_01H..., variant_id=variant_01H...
  [3] Anonymous | Cart Created
      Context: cart_id=cart_01H..., region_id=reg_01H...
  [4] Anonymous | Cart + Item
      Context: cart_id=cart_01H..., line_item_id=item_01H...
  [5] Authenticated Admin
      Context: admin_token=eyJhb..., admin_id=usr_01H...
  [6] Authenticated Admin | Product Created
      Context: admin_token=..., created_product_id=prod_01H...
```

## API Coverage

The test suite covers these Medusa API areas:

### Store API (Public)
- ✅ Products: List, get, search
- ✅ Carts: Create, update, add items, remove items
- ✅ Checkout: Shipping, payment, order completion
- ✅ Orders: Get order details

### Admin API (Authenticated)
- ✅ Authentication: Login, logout
- ✅ Products: CRUD operations
- ✅ Orders: List, get, fulfill, cancel
- ✅ Fulfillments: Create, cancel

## Cleanup

Stop and remove containers:

```bash
docker compose down -v
```

## Troubleshooting

### Medusa not starting

Check logs:
```bash
docker compose logs medusa
```

Common issues:
- Database migrations not complete (wait longer)
- Port 9000 already in use
- PostgreSQL connection issues

### Exploration errors

If exploration fails with 404s:
- Check Medusa is fully initialized
- Verify admin user was created (check docker logs)
- Try running exploration again (Medusa may be seeding data)

### Authentication failures

Default admin credentials:
- Email: `admin@test.com`
- Password: `supersecret`

These are set in `docker-compose.yml` and used in `actions/auth_actions.py`.

## Next Steps

1. **Add More Journeys**: Create journeys for returns, refunds, discounts
2. **Custom Actions**: Add actions for collections, regions, gift cards
3. **Integration Tests**: Combine multiple journeys for full user flows
4. **Performance Testing**: Use VenomQA's load testing features
5. **CI/CD**: Integrate into your pipeline with JUnit reports

## Resources

- [Medusa Documentation](https://docs.medusajs.com/)
- [Medusa API Reference](https://docs.medusajs.com/api)
- [VenomQA Documentation](../../docs/)
- [State Chain Spec](../../docs/STATE_CHAIN_SPEC.md)
- [State Explorer Guide](../../docs/STATE_EXPLORER_PROJECT.md)

## License

MIT
