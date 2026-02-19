# Specifications

Technical specifications for VenomQA internals.

## Overview

These specifications define the internal architecture and contracts of VenomQA. They are intended for:

- Contributors extending VenomQA
- Users building custom adapters/reporters
- Anyone understanding the "why" behind design decisions

<div class="grid cards" markdown>

-   :material-cube:{ .lg .middle } __Framework Spec__

    ---

    Core abstractions, extension points, and the plugin architecture.

    [:octicons-arrow-right-24: Read](framework-spec.md)

-   :material-link:{ .lg .middle } __State Chain__

    ---

    Checkpoint/rollback semantics, state hashing, and transaction isolation.

    [:octicons-arrow-right-24: Read](state-chain.md)

-   :material-graph:{ .lg .middle } __State Explorer__

    ---

    Exploration algorithms (BFS, DFS, CoverageGuided), guarantees, and tradeoffs.

    [:octicons-arrow-right-24: Read](state-explorer.md)

-   :material-package:{ .lg .middle } __Publishing__

    ---

    Release process, versioning strategy, and changelog management.

    [:octicons-arrow-right-24: Read](publishing.md)

</div>

## Versioning

VenomQA follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking API changes
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible

## Stability Guarantees

| Component | Stability |
|-----------|-----------|
| `venomqa.Action` | Stable |
| `venomqa.Invariant` | Stable |
| `venomqa.Agent` | Stable |
| `venomqa.World` | Stable |
| `venomqa.adapters.http` | Stable |
| `venomqa.adapters.postgres` | Stable |
| `venomqa.adapters.*` | Experimental |
| `venomqa.reporters.*` | Experimental |
