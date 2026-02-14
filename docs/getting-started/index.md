# Getting Started

Welcome to VenomQA! This section will help you get up and running quickly.

## Overview

VenomQA is a stateful journey testing framework for API quality assurance. It enables you to:

- **Test complex user flows** as connected journeys rather than isolated tests
- **Save and restore database state** at checkpoints
- **Branch execution** to test multiple scenarios from the same starting point
- **Generate detailed reports** for debugging and CI/CD integration

## Quick Links

<div class="feature-grid" markdown>

<div class="feature-card" markdown>

### [Quickstart](quickstart.md)

Get your first journey running in 5 minutes.

</div>

<div class="feature-card" markdown>

### [Installation](installation.md)

Detailed installation instructions and dependencies.

</div>

<div class="feature-card" markdown>

### [Configuration](configuration.md)

Configure VenomQA for your project.

</div>

</div>

## Prerequisites

Before you begin, ensure you have:

- **Python 3.10 or higher** installed
- **pip** (Python package manager)
- **Docker** (optional, for infrastructure management)

## Your First Steps

1. **Install VenomQA**
   ```bash
   pip install venomqa
   ```

2. **Create a journey file**
   ```python
   # journeys/hello.py
   from venomqa import Journey, Step

   journey = Journey(
       name="hello_world",
       steps=[
           Step(name="health_check", action=lambda c, ctx: c.get("/health")),
       ],
   )
   ```

3. **Run it**
   ```bash
   venomqa run hello_world
   ```

## What's Next?

After completing the quickstart, explore:

- [Core Concepts](../concepts/index.md) - Understand Journeys, Checkpoints, and Branches
- [Tutorials](../tutorials/index.md) - Step-by-step guides for common scenarios
- [API Reference](../reference/api.md) - Complete API documentation
