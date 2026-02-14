# VenomQA Examples

Welcome to the VenomQA examples directory! This guide helps you find the right example to start with based on your needs.

## Which Example Should I Use?

```
New to VenomQA?
    │
    ▼
quickstart/         ← First experience (<2 min)
    │
    ▼
Want to learn patterns?
    │
    ▼
todo_app/           ← Learn actions, journeys, branching (<5 min)
    │
    ▼
Need all features?
    │
    ▼
full_featured_app/  ← All ports, enterprise patterns (<10 min)
    │
    ▼
Integrating with a platform?
    │
    ▼
integrations/       ← Real-world integration examples
```

## Examples Overview

| Example | Time | Best For |
|---------|------|----------|
| **quickstart/** | 2 min | Your first VenomQA experience |
| **todo_app/** | 5 min | Learning journeys, checkpoints, branches |
| **full_featured_app/** | 10 min | All VenomQA features, enterprise patterns |
| **integrations/medusa/** | 10 min | E-commerce platform integration |

## Quick Start

### Option 1: Quickstart (Fastest)

```bash
cd examples/quickstart
pip install venomqa
venomqa run hello_journey
```

### Option 2: Todo App (Most Educational)

```bash
cd examples/todo_app
docker compose up -d
cd qa
venomqa run
```

See the [todo_app README](./todo_app/README.md) for complete instructions.

## What Each Example Demonstrates

### quickstart/

Your first VenomQA experience in under 2 minutes:

- **Minimal setup** - Just pip install and run
- **Hello World journey** - See the core concepts
- **Clean code structure** - Actions and journeys organized
- **Real API patterns** - Health checks, CRUD operations

Perfect for: Getting started quickly, understanding the basics.

**See**: [quickstart/qa/journeys/hello_journey.py](./quickstart/qa/journeys/hello_journey.py)

### todo_app/

A complete, production-ready example:

- **Flask REST API** with CRUD operations
- **File upload/download** handling
- **PostgreSQL** database integration
- **Journey tests** with checkpoints and branches
- **Error handling** and validation testing
- **Docker Compose** for local development

Perfect for: Understanding how to structure a VenomQA project.

**See**: [todo_app/README.md](./todo_app/README.md)

### full_featured_app/

An enterprise example demonstrating ALL VenomQA capabilities:

- **All 10 VenomQA ports** (Client, Database, State, File, Mail, Queue, Cache, Search, WebSocket, Time)
- **FastAPI** application (more advanced than Flask)
- **Real-time** communication with WebSocket
- **Background jobs** with Celery
- **Email testing** with Mailhog
- **Caching** with Redis
- **Search** with Elasticsearch
- **Rate limiting** and webhooks

Perfect for: Advanced patterns and understanding how different ports work together.

**See**: [full_featured_app/README.md](./full_featured_app/README.md)

### integrations/medusa/

Real-world e-commerce platform integration:

- **Medusa JS** e-commerce backend testing
- **Customer authentication** flows
- **Cart management** and checkout
- **Order processing** with branching paths
- **Production-like** test scenarios

Perfect for: Seeing how VenomQA integrates with real platforms.

**See**: [integrations/medusa/README.md](./integrations/medusa/README.md)

## Project Structure

```
examples/
├── quickstart/              # START HERE - 2 minute intro
│   ├── app/                 # Simple API server
│   └── qa/
│       ├── actions/         # Reusable action functions
│       └── journeys/        # Test journeys
│
├── todo_app/                # NEXT - complete Flask example
│   ├── app/                 # Flask REST API
│   ├── docker-compose.yml   # Docker setup
│   └── qa/
│       ├── actions/         # CRUD actions
│       └── journeys/        # Comprehensive journeys
│
├── full_featured_app/       # ADVANCED - all features
│   ├── app/                 # FastAPI application
│   ├── docker/              # Full stack Compose
│   └── qa/                  # All port examples
│
├── integrations/            # PLATFORM INTEGRATIONS
│   └── medusa/              # E-commerce platform
│       ├── qa/              # Integration tests
│       └── README.md
│
├── test-server/             # Mock server for testing
│   └── test_server.py       # Runnable FastAPI server
│
├── seeds/                   # Data seeding examples
├── plugins/                 # Custom plugin examples
└── README.md                # This file
```

## Running Examples

### With Docker (Recommended)

```bash
cd examples/<example_name>
docker compose up -d          # Start app
cd qa
venomqa run                   # Run tests
```

### Without Docker

```bash
cd examples/<example_name>
pip install -r requirements.txt
python -m app.app             # Start app
cd qa
venomqa run                   # Run tests
```

## Common Tasks

### Learning VenomQA

1. Start with `quickstart/` to see the basics
2. Move to `todo_app/` for real-world patterns
3. Study `full_featured_app/` for advanced features

### Writing Your Own Tests

1. Copy the structure from `todo_app/qa/`
2. Create `actions/` folder for reusable functions
3. Create `journeys/` folder for test scenarios
4. Add `venomqa.yaml` for configuration

### Integrating with Your Platform

1. Check `integrations/` for similar platforms
2. Copy the structure and adapt to your API
3. Use actions from your closest match as templates

## Troubleshooting

### Services Won't Start

```bash
docker compose logs app
docker compose down -v
docker compose up -d
```

### Import Errors

```bash
pip install -e ../../..
python -c "import venomqa; print(venomqa.__version__)"
```

### Tests Failing

```bash
curl http://localhost:PORT/health  # Check app is running
venomqa run --verbose              # Get detailed output
```

## Next Steps

After exploring the examples:

1. **Read the docs**: See `/docs/` in the root directory
2. **Build your journey**: Follow patterns from todo_app
3. **Set up CI/CD**: Check `/docs/ci-cd.md`
4. **Join the community**: See CONTRIBUTING.md
