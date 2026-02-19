# Advanced Topics

Deep dives into VenomQA's architecture, extension points, and optimization techniques.

## Overview

This section covers advanced topics for users who want to extend VenomQA, optimize performance, or understand the internals.

!!! tip "Prerequisites"
    Before diving into advanced topics, ensure you're comfortable with:
    
    - [Core Concepts](../concepts/index.md) - Actions, Invariants, World
    - [Basic Usage](../getting-started/quickstart.md) - Running explorations
    - [State Management](../concepts/state.md) - Context and checkpoints

## Topics

<div class="grid cards" markdown>

-   :material-chart-line: __Performance Tuning__
    
    ---
    
    Optimize exploration speed, memory usage, and CI integration. Learn about parallel exploration, state pruning, and benchmarking.
    
    [:octicons-arrow-right-24: Performance Guide](performance.md)

-   :material-palette: __Custom Reporters__
    
    ---
    
    Create custom output formats for Slack, Discord, or your own dashboards. Implement the Reporter protocol.
    
    [:octicons-arrow-right-24: Custom Reporters](custom-reporters.md)

-   :material-database: __Custom Backends__
    
    ---
    
    Add support for MongoDB, Elasticsearch, or custom data stores. Implement the SystemAdapter protocol.
    
    [:octicons-arrow-right-24: Custom Backends](custom-backends.md)

-   :material-test-tube: __Testing Patterns__
    
    ---
    
    Common patterns for testing CRUD operations, auth flows, payment systems, and multi-tenant applications.
    
    [:octicons-arrow-right-24: Testing Patterns](testing-patterns.md)

</div>

## When to Use Advanced Features

| Scenario | Recommended Topic |
|----------|-------------------|
| Exploration too slow | [Performance Tuning](performance.md) |
| Need Slack/Discord alerts | [Custom Reporters](custom-reporters.md) |
| Using MongoDB, Elasticsearch | [Custom Backends](custom-backends.md) |
| Complex business logic | [Testing Patterns](testing-patterns.md) |
| Large state space | [Performance Tuning](performance.md) |
| CI/CD integration | [Performance Tuning](performance.md) |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                        Agent                            │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Strategy   │  │   Invariants │  │    Graph      │  │
│  │ (BFS/DFS/..)│  │   Checker    │  │   (States)    │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                        World                            │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │    API      │  │   Context    │  │    Systems    │  │
│  │  (HTTP/ASGI)│  │  (Key-Value) │  │  (DB/Cache)   │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                   Rollbackable Systems                  │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ PostgreSQL  │  │    Redis     │  │  Custom DB    │  │
│  │ (SAVEPOINT) │  │ (DUMP/RESTORE)│  │ (Your Impl)  │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Extension Points

VenomQA is designed for extensibility at every layer:

| Layer | Extension Point | Protocol/Class |
|-------|-----------------|----------------|
| Exploration | Custom strategies | `ExplorationStrategy` |
| Reporting | Custom reporters | Callable or class |
| State | Custom backends | `Rollbackable` |
| Actions | Custom action logic | Callable `(api, context)` |
| Invariants | Custom checks | Callable `(world)` |

## Getting Help

- [GitHub Discussions](https://github.com/namanag97/venomqa/discussions) - Ask questions
- [GitHub Issues](https://github.com/namanag97/venomqa/issues) - Report bugs
- [Examples](../examples/index.md) - Code examples
