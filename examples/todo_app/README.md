# Todo App Example

A complete example application with VenomQA tests demonstrating:

- Flask REST API with full CRUD operations
- File upload/download functionality
- VenomQA journey tests with checkpoints and branches
- Docker Compose setup for local development and QA

## Project Structure

```
todo_app/
├── app/                      # Flask application
│   ├── app.py               # REST API endpoints
│   ├── models.py            # SQLAlchemy models
│   └── requirements.txt     # Python dependencies
├── docker/
│   ├── Dockerfile           # Application container
│   └── docker-compose.yml   # App + PostgreSQL
├── qa/                       # VenomQA tests
│   ├── journeys/            # Test journeys
│   │   ├── crud_journey.py
│   │   ├── file_upload_journey.py
│   │   └── error_handling_journey.py
│   ├── actions/             # Reusable actions
│   │   ├── todo_actions.py
│   │   └── __init__.py
│   ├── venomqa.yaml         # VenomQA configuration
│   └── docker-compose.qa.yml # Test infrastructure
└── README.md
```

## Quick Start

### Run the Application

```bash
cd examples/todo_app

# Start app with PostgreSQL
docker compose -f docker/docker-compose.yml up -d

# Check health
curl http://localhost:5000/health
```

### Run QA Tests

```bash
# From the todo_app directory
cd qa

# Start test infrastructure
docker compose -f docker-compose.qa.yml up -d

# Run VenomQA tests
docker compose -f docker-compose.qa.yml exec venomqa venomqa run

# View reports
open reports/journey_report.html
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/todos` | List todos (with pagination) |
| POST | `/todos` | Create todo |
| GET | `/todos/{id}` | Get single todo |
| PUT | `/todos/{id}` | Update todo |
| DELETE | `/todos/{id}` | Delete todo |
| POST | `/todos/{id}/attachments` | Upload file |
| GET | `/todos/{id}/attachments/{file_id}` | Download file |
| DELETE | `/todos/{id}/attachments/{file_id}` | Delete file |

## Example Usage

### Create a Todo

```bash
curl -X POST http://localhost:5000/todos \
  -H "Content-Type: application/json" \
  -d '{"title": "Buy groceries", "description": "Milk, eggs, bread"}'
```

### List Todos

```bash
curl "http://localhost:5000/todos?page=1&limit=10"
```

### Upload Attachment

```bash
curl -X POST http://localhost:5000/todos/1/attachments \
  -F "file=@document.pdf"
```

## Test Journeys

### CRUD Journey

Tests complete Create, Read, Update, Delete cycle:

- Health check
- Create todo
- Fetch created todo
- List all todos
- Update todo
- Delete todo
- Verify deletion

### File Upload Journey

Tests file operations:

- Create todo for attachments
- Upload text file
- Download file
- Upload multiple files
- Delete attachments

### Error Handling Journey

Tests API error responses:

- 404 Not Found scenarios
- Validation errors
- Invalid request handling

## Running Tests Manually

```python
import sys
sys.path.insert(0, '../../../')

from venomqa import Client, JourneyRunner
from journeys.crud_journey import crud_journey

client = Client(base_url="http://localhost:5000")
runner = JourneyRunner(client=client)
result = runner.run(crud_journey)

print(f"Passed: {result.success}")
print(f"Steps: {result.passed_steps}/{result.total_steps}")
```

## Development

### Local Development

```bash
# Install dependencies
cd app
pip install -r requirements.txt

# Run with SQLite (default)
python app.py

# Or with PostgreSQL
DATABASE_URL=postgresql://user:pass@localhost:5432/todos python app.py
```

### Run Tests with VenomQA CLI

```bash
cd qa

# Run all journeys
venomqa run

# Run specific journey
venomqa run --journey crud_operations

# Run with verbose output
venomqa run --verbose

# Generate specific report format
venomqa run --report html,json
```

## Configuration

The `qa/venomqa.yaml` file configures:

- **base_url**: API endpoint
- **timeout**: Request timeout in seconds
- **retry**: Retry policy for failed requests
- **report**: Output formats and directory
- **parallel_paths**: Number of parallel branches to execute

## Cleanup

```bash
# Stop all containers
docker compose -f docker/docker-compose.yml down
docker compose -f qa/docker-compose.qa.yml down

# Remove volumes
docker compose -f docker/docker-compose.yml down -v
```
