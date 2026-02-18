# VenomQA Autonomous Demo

This example demonstrates VenomQA's autonomous mode with:
- **API Key authentication** (X-API-Key header)
- **A planted bug**: The refund endpoint allows over-refunds

## Quick Start

### 1. Copy environment file
```bash
cp .env.example .env
```

### 2. Run VenomQA
```bash
venomqa
```

VenomQA will:
1. Detect `docker-compose.yml` and `openapi.yaml`
2. Run preflight checks
3. Start isolated containers
4. Generate actions from OpenAPI
5. Explore API sequences
6. Find the over-refund bug!

## The Planted Bug

The `/orders/{id}/refund` endpoint allows refunding more than the order amount:

```python
# BUG: This check is missing:
# if order["refunded_amount"] + refund.amount > order["amount"]:
#     raise HTTPException(status_code=400, detail="Refund exceeds order amount")
```

VenomQA should find this by exploring sequences like:
1. Create order (amount: $100)
2. Refund $60
3. Refund $60 again  # Bug! Total refund $120 > $100

## Manual Testing

If you want to run the API manually:

```bash
# Start the API
docker compose up -d

# Create an order
curl -X POST http://localhost:8000/orders \
  -H "X-API-Key: demo-api-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100}'

# Refund it (first refund works)
curl -X POST http://localhost:8000/orders/order_1/refund \
  -H "X-API-Key: demo-api-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"amount": 60}'

# Over-refund (should fail but doesn't!)
curl -X POST http://localhost:8000/orders/order_1/refund \
  -H "X-API-Key: demo-api-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"amount": 60}'

# Check the order - refunded_amount > amount!
curl http://localhost:8000/orders/order_1 \
  -H "X-API-Key: demo-api-key-12345"
```

## Authentication Options

VenomQA supports multiple ways to provide the API key:

```bash
# Option 1: CLI flag
venomqa --api-key demo-api-key-12345

# Option 2: Environment variable
export VENOMQA_API_KEY=demo-api-key-12345
venomqa

# Option 3: .env file (recommended)
cp .env.example .env
venomqa

# Option 4: Interactive prompt (if TTY available)
venomqa  # Will prompt for auth type
```

## Skipping Preflight Checks

If you already have Docker running and want to skip checks:

```bash
venomqa --skip-preflight
```

## Files

- `app/main.py` - FastAPI app with the planted bug
- `docker-compose.yml` - Container setup
- `openapi.yaml` - OpenAPI spec (3 endpoints)
- `.env.example` - Example environment variables
