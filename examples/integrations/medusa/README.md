# VenomQA Medusa E-commerce Integration

Complete VenomQA test suite for [Medusa JS](https://medusajs.com/) e-commerce platform.

## Features

- **Customer Authentication**: Register, login, and profile management
- **Product Catalog**: Browse products, categories, and collections
- **Shopping Cart**: Create carts, add items, apply promotions
- **Checkout Flow**: Multiple payment methods with branching scenarios
- **Order Management**: Order verification and tracking
- **Invariant Testing**: Cart total and inventory consistency checks

## Directory Structure

```
examples/medusa-integration/
├── venomqa.yaml           # VenomQA configuration
├── run_tests.py           # Test runner script
├── README.md              # This file
└── qa/
    ├── __init__.py
    ├── actions/           # Medusa Store API actions
    │   ├── __init__.py
    │   ├── auth.py        # Customer authentication
    │   ├── products.py    # Product catalog
    │   ├── cart.py        # Cart management
    │   ├── checkout.py    # Payment and checkout
    │   └── orders.py      # Order management
    ├── fixtures/          # Test data factories
    │   ├── __init__.py
    │   ├── customer.py    # Customer and address fixtures
    │   └── cart.py        # Cart and item fixtures
    └── journeys/          # Test journeys
        ├── __init__.py
        └── checkout_flow.py  # Main checkout journey with branching
```

## Journeys

### Main Checkout Journey (`checkout_journey`)

Complete checkout flow with payment branching:

1. **Setup Phase**
   - Initialize Medusa context
   - Configure test addresses

2. **Authentication Phase**
   - Register new customer
   - Login customer
   - **CHECKPOINT**: `authenticated`

3. **Product Selection Phase**
   - Browse products
   - Select product

4. **Cart Phase**
   - Create cart
   - Add items
   - Verify cart total invariant

5. **Shipping Phase**
   - Update cart with addresses
   - Select shipping method

6. **Payment Phase**
   - Create payment session
   - **CHECKPOINT**: `before_payment`
   - **BRANCH** with 3 paths:

     **Path 1: Successful Payment**
     - Complete cart
     - Verify order created
     - Check inventory decremented

     **Path 2: Failed Payment**
     - Simulate payment failure
     - Verify cart is intact
     - Verify no order created

     **Path 3: Abandoned Cart**
     - Simulate abandonment timeout
     - Verify cart abandoned state
     - Verify cart is recoverable

### Guest Checkout Journey (`guest_checkout_journey`)

Checkout flow without customer authentication.

### Express Checkout Journey (`express_checkout_journey`)

Streamlined checkout with saved payment methods.

## Usage

### Running Tests

```bash
cd examples/medusa-integration

# Run main checkout journey
python run_tests.py --base-url http://localhost:9000

# Run specific journey
python run_tests.py --journey guest

# Run all journeys
python run_tests.py --journey all --verbose
```

### Programmatic Usage

```python
from venomqa import Client, JourneyRunner
from qa.journeys.checkout_flow import checkout_journey

# Create client
client = Client(base_url="http://localhost:9000")

# Create runner
runner = JourneyRunner(
    client=client,
    fail_fast=False,
    capture_logs=True,
)

# Run journey
result = runner.run(checkout_journey)

# Check results
print(f"Journey: {result.journey_name}")
print(f"Status: {'PASSED' if result.success else 'FAILED'}")
print(f"Duration: {result.duration_ms:.2f}ms")
print(f"Steps: {result.passed_steps}/{result.total_steps}")
print(f"Paths: {result.passed_paths}/{result.total_paths}")

# Check issues
for issue in result.issues:
    print(f"Issue: [{issue.severity}] {issue.step}: {issue.error}")
```

### Using Fixtures

```python
from qa.fixtures.customer import CustomerFactory, AuthenticatedCustomerFactory
from qa.fixtures.cart import CartFactory, CartWithItemsFactory

# Create test customer
customer = CustomerFactory.build()

# Create authenticated context
context = AuthenticatedCustomerFactory.build_context(
    client=client,
    region_id="reg_01",
    publishable_api_key="pk_test_xxx",
)

# Create cart with items
cart = CartFactory.with_items(num_items=3)

# Create checkout-ready context
context = CartWithItemsFactory.checkout_ready_context(client=client)
```

## Configuration

### venomqa.yaml

Key configuration options:

```yaml
target:
  base_url: http://localhost:9000
  api_prefix: /store
  timeout: 30.0

database:
  type: postgresql
  checkpointing: true

auth:
  type: jwt
  header: Authorization
  scheme: Bearer

medusa:
  publishable_api_key: ${MEDUSA_PUBLISHABLE_KEY}
  region_id: ${MEDUSA_REGION_ID}
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MEDUSA_BASE_URL` | Medusa API URL | `http://localhost:9000` |
| `MEDUSA_PUBLISHABLE_KEY` | Publishable API key | `pk_test_key` |
| `MEDUSA_REGION_ID` | Region ID for pricing | `reg_01` |
| `MEDUSA_DB_PASSWORD` | PostgreSQL password | `medusa` |

## Invariants

The test suite includes invariant checks:

### Cart Total Invariant
Verifies that cart subtotal equals sum of line item totals.

### Inventory Invariant
Tracks expected inventory changes after order completion.

## Medusa API Reference

This test suite targets Medusa v2 Store API:

- [Authentication](https://docs.medusajs.com/api/store#tag/Auth)
- [Products](https://docs.medusajs.com/api/store#tag/Products)
- [Carts](https://docs.medusajs.com/api/store#tag/Carts)
- [Orders](https://docs.medusajs.com/api/store#tag/Orders)
- [Payment Collections](https://docs.medusajs.com/api/store#tag/Payment-Collections)

## Requirements

- Python 3.10+
- VenomQA framework
- Running Medusa instance
- PostgreSQL (for checkpointing)

## License

MIT
