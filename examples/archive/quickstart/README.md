# VenomQA Quickstart

Get up and running with VenomQA in 5 minutes.

## Prerequisites

- Python 3.10+
- Docker and Docker Compose
- VenomQA installed (`pip install venomqa`)

## Quick Start

```bash
# 1. Navigate to this directory
cd examples/quickstart

# 2. Run everything with one command
./run.sh

# Or manually:
# Start the sample API
docker compose up -d

# Run the QA journeys
cd qa && venomqa run
```

## Project Structure

```
quickstart/
├── README.md               # This file
├── docker-compose.yml      # Sample API + PostgreSQL
├── run.sh                  # One command to run everything
├── app/
│   ├── Dockerfile          # Sample FastAPI app
│   ├── main.py             # API endpoints
│   └── requirements.txt    # API dependencies
└── qa/
    ├── venomqa.yaml        # VenomQA configuration
    ├── actions/
    │   ├── __init__.py
    │   └── hello_actions.py  # Reusable actions
    └── journeys/
        ├── __init__.py
        └── hello_journey.py  # Sample journey
```

## What This Example Demonstrates

1. **Simple API Testing**: Basic CRUD operations against a REST API
2. **Journey Definition**: How to define test journeys with steps
3. **Actions**: Reusable test actions
4. **Checkpoints**: State snapshots during test execution
5. **Docker Integration**: Running tests against containerized services

## Sample API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/items` | List all items |
| POST | `/api/items` | Create an item |
| GET | `/api/items/{id}` | Get item by ID |
| PUT | `/api/items/{id}` | Update an item |
| DELETE | `/api/items/{id}` | Delete an item |

## Running Tests

```bash
# Run all journeys
venomqa run

# Run specific journey
venomqa run hello_journey

# Run with verbose output
venomqa run -v

# Run with debug mode
venomqa run --debug

# Watch mode (re-run on file changes)
venomqa watch
```

## Customizing

1. Edit `qa/venomqa.yaml` to change the base URL or timeout
2. Add new actions in `qa/actions/`
3. Create new journeys in `qa/journeys/`
4. Modify `docker-compose.yml` to add more services

## Next Steps

- Read the [full documentation](https://venomqa.dev)
- Explore the [todo_app example](../todo_app/) for a more complex scenario
- Learn about [branching and checkpoints](https://venomqa.dev/docs/concepts/branching)
- Set up [CI/CD integration](https://venomqa.dev/docs/ci-cd)

## Troubleshooting

### API not starting
```bash
# Check logs
docker compose logs -f api

# Rebuild
docker compose down && docker compose up --build -d
```

### Connection refused
```bash
# Verify API is running
curl http://localhost:8000/health

# Check VenomQA config
cat qa/venomqa.yaml
```

### Run health check
```bash
venomqa doctor
```
