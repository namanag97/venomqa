# Full-Featured App Example

A comprehensive example demonstrating **ALL** VenomQA features in a single, runnable application.

## What This Example Demonstrates

### Application Features
- **CRUD Operations**: Users, Items, Orders
- **WebSocket**: Real-time communication
- **File Upload/Download**: Multipart file handling
- **Background Jobs**: Celery-based task processing
- **Email Sending**: SMTP via Mailhog
- **Rate Limiting**: Request throttling
- **Caching**: Redis-based response caching
- **Search**: Elasticsearch integration
- **Webhooks**: Webhook endpoint handling

### VenomQA Ports Demonstrated

| Port | Purpose | Example Usage |
|------|---------|---------------|
| `ClientPort` | HTTP API calls | Create users, items, orders |
| `DatabasePort` | Direct DB queries | Verify data in PostgreSQL |
| `StatePort` | State branching | Save/restore test state |
| `FilePort` | File operations | Upload and download files |
| `MailPort` | Email testing | Verify emails via Mailhog |
| `QueuePort` | Background jobs | Test Celery task execution |
| `CachePort` | Cache operations | Test Redis caching |
| `SearchPort` | Search testing | Index and search documents |
| `WebSocketPort` | Real-time | WebSocket ping/pong |
| `TimePort` | Temporal testing | Schedule and time operations |

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.11+ (for local development)

### Running the Full Stack

```bash
# Navigate to the example directory
cd examples/full_featured_app

# Start all services
docker-compose -f docker/docker-compose.yml up -d

# Wait for services to be healthy
docker-compose -f docker/docker-compose.yml ps

# Run the QA tests
docker-compose -f qa/docker-compose.qa.yml up qa-runner
```

### Running Locally (Development)

```bash
# Start infrastructure only
docker-compose -f docker/docker-compose.yml up -d postgres redis elasticsearch mailhog minio

# Install app dependencies
cd app
pip install -r requirements.txt

# Run the app
uvicorn main:app --reload --port 8000

# In another terminal, run the Celery worker
celery -A workers.celery_app worker --loglevel=info

# Run QA tests (from the qa directory)
cd ../qa
pip install -e ../../..  # Install VenomQA
venomqa run --journey-dir journeys --config venomqa.yaml
```

## Project Structure

```
full_featured_app/
├── app/                          # Application under test
│   ├── main.py                   # FastAPI application
│   ├── models.py                 # SQLAlchemy models
│   ├── workers.py                # Celery background tasks
│   ├── requirements.txt          # Python dependencies
│   └── Dockerfile                # App container
│
├── docker/
│   └── docker-compose.yml        # Full stack deployment
│
├── qa/                           # QA tests using VenomQA
│   ├── journeys/
│   │   └── complete_journey.py   # Journey using ALL ports
│   ├── actions/
│   │   └── __init__.py           # Reusable actions
│   ├── venomqa.yaml              # VenomQA configuration
│   ├── docker-compose.qa.yml     # QA runner compose
│   └── Dockerfile.qa             # QA runner container
│
└── README.md                     # This file
```

## API Endpoints

### Users
- `POST /api/users` - Create user
- `GET /api/users/{id}` - Get user

### Items (CRUD)
- `POST /api/items` - Create item
- `GET /api/items` - List items
- `GET /api/items/{id}` - Get item
- `PATCH /api/items/{id}` - Update item
- `DELETE /api/items/{id}` - Delete item

### Orders
- `POST /api/orders` - Create order (triggers background job)
- `GET /api/orders/{id}` - Get order
- `GET /api/orders/{id}/status` - Get order + job status

### Files
- `POST /api/files/upload` - Upload single file
- `POST /api/files/upload-many` - Upload multiple files
- `GET /api/files/download/{filename}` - Download file

### Email
- `POST /api/emails/send` - Queue email (async)
- `POST /api/emails/send-sync` - Send email synchronously

### Search
- `POST /api/search` - Search documents

### System
- `GET /health` - Health check
- `GET /ready` - Readiness check
- `GET /api/time` - Server time
- `GET /api/cached` - Cached response
- `DELETE /api/cache/clear` - Clear cache
- `GET /api/rate-limited` - Rate limited endpoint

### WebSocket
- `WS /ws` - Main WebSocket endpoint
- `WS /ws/notifications` - Notification stream

### Jobs
- `POST /api/jobs/generate-report` - Start report generation
- `GET /api/jobs/{task_id}` - Get job status

## Available Journeys

### 1. Complete Feature Journey
Tests ALL ports in a single comprehensive journey.

```python
from journeys.complete_journey import complete_journey

# Run via CLI
venomqa run --journey complete_feature_journey
```

### 2. CRUD Operations Journey
Basic CRUD testing with branching.

```python
from journeys.complete_journey import crud_only_journey
```

### 3. WebSocket Journey
Real-time communication testing.

```python
from journeys.complete_journey import websocket_journey
```

### 4. Email Journey
Email sending and verification.

```python
from journeys.complete_journey import email_journey
```

### 5. Rate Limit Journey
Rate limiting validation.

```python
from journeys.complete_journey import rate_limit_journey
```

### 6. Cache Journey
Cache operations testing.

```python
from journeys.complete_journey import cache_journey
```

### 7. Search Journey
Search indexing and querying.

```python
from journeys.complete_journey import search_journey
```

### 8. Background Job Journey
Background job processing.

```python
from journeys.complete_journey import background_job_journey
```

## Writing Custom Journeys

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path
from actions import create_user, create_item, cleanup_all

my_journey = Journey(
    name="my_custom_journey",
    description="Custom test journey",
    tags=["custom", "example"],
    steps=[
        Step(name="setup_user", action=create_user),
        Checkpoint(name="user_ready"),
        Step(name="setup_item", action=create_item),
        Checkpoint(name="item_ready"),
        Branch(
            checkpoint_name="item_ready",
            paths=[
                Path(
                    name="positive_path",
                    steps=[
                        Step(name="verify", action=lambda db, ctx: db.query("SELECT 1")),
                    ],
                ),
            ],
        ),
        Step(name="cleanup", action=cleanup_all),
    ],
)
```

## Service Endpoints

| Service | Port | URL |
|---------|------|-----|
| API | 8000 | http://localhost:8000 |
| API Docs | 8000 | http://localhost:8000/docs |
| PostgreSQL | 5432 | localhost:5432 |
| Redis | 6379 | localhost:6379 |
| Elasticsearch | 9200 | http://localhost:9200 |
| Mailhog SMTP | 1025 | localhost:1025 |
| Mailhog UI | 8025 | http://localhost:8025 |
| MinIO API | 9000 | http://localhost:9000 |
| MinIO Console | 9001 | http://localhost:9001 |

## Troubleshooting

### Services not starting
```bash
# Check service status
docker-compose -f docker/docker-compose.yml ps

# View logs
docker-compose -f docker/docker-compose.yml logs app
docker-compose -f docker/docker-compose.yml logs worker
```

### Database connection issues
```bash
# Check PostgreSQL is ready
docker-compose -f docker/docker-compose.yml exec postgres pg_isready -U appuser

# Connect to database
docker-compose -f docker/docker-compose.yml exec postgres psql -U appuser -d appdb
```

### Elasticsearch memory issues
```bash
# Increase memory limit in docker-compose.yml
environment:
  - "ES_JAVA_OPTS=-Xms1g -Xmx1g"
```

### Tests failing
```bash
# Run with verbose output
venomqa run --journey-dir journeys --config venomqa.yaml --verbose

# Check reports
open reports/journey_report.html
```

## Clean Up

```bash
# Stop all services
docker-compose -f docker/docker-compose.yml down

# Remove volumes (clears all data)
docker-compose -f docker/docker-compose.yml down -v
```

## License

MIT License - See root project for details.
