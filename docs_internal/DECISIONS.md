# Architecture Decision Records (ADRs)

> Key technical decisions and their rationale.

---

## ADR-001: Python as Primary Language

**Date:** 2024-01

**Status:** Accepted

**Context:**
Need to choose a language for an API testing framework.

**Options:**
1. Python - Large ecosystem, easy to learn, good for QA
2. Go - Fast, good CLI, but smaller testing ecosystem
3. TypeScript - Good for frontend teams, but Python dominates backend QA

**Decision:** Python

**Rationale:**
- QA engineers often know Python
- Pytest ecosystem compatibility
- Faker, httpx, rich libraries available
- Easy integration with data science tools

**Consequences:**
- GIL limits true parallelism (mitigated with threads/processes)
- Slower than Go for CLI startup
- Need to support Python 3.10+

---

## ADR-002: Ports & Adapters Architecture

**Date:** 2024-01

**Status:** Accepted

**Context:**
Tests need to work with different backends (Postgres, MySQL, Redis, etc.).

**Options:**
1. Direct dependencies - Simple but inflexible
2. Dependency injection - Flexible but complex
3. Ports & Adapters - Clean boundaries, testable

**Decision:** Ports & Adapters

**Rationale:**
- Clear separation of concerns
- Easy to mock for testing
- Users can swap implementations
- Follows hexagonal architecture principles

**Consequences:**
- More files/interfaces
- Slight learning curve
- Need to maintain port interfaces

---

## ADR-003: Context Passing vs Global State

**Date:** 2024-01

**Status:** Accepted

**Context:**
Steps need to share data (auth tokens, created IDs, etc.).

**Options:**
1. Global variables - Simple but not thread-safe
2. Class instance variables - Couples tests to classes
3. Explicit context dict - Verbose but clear

**Decision:** Explicit context dict

```python
def login(client, context):
    context["token"] = response.json()["token"]

def get_profile(client, context):
    client.headers["Authorization"] = f"Bearer {context['token']}"
```

**Rationale:**
- Thread-safe
- Testable (can inject context)
- Explicit data flow
- Easy to serialize for checkpoints

**Consequences:**
- Slightly more verbose
- Users must remember to pass context

---

## ADR-004: Checkpoint = Database Savepoint

**Date:** 2024-02

**Status:** Accepted

**Context:**
Branches need to start from identical state.

**Options:**
1. Re-run setup steps - Slow, may not be deterministic
2. Database savepoints - Fast, exact state
3. Full database dump/restore - Accurate but slow

**Decision:** Database savepoints (with fallback to dump/restore)

**Rationale:**
- Savepoints are fast (~ms)
- Exact state reproduction
- Standard SQL feature
- Can fallback for complex cases

**Consequences:**
- Requires database support
- In-memory state not captured (must use context)
- Some DBs have savepoint limitations

---

## ADR-005: BFS for State Graph Exploration

**Date:** 2024-02

**Status:** Accepted

**Context:**
Need algorithm to explore all paths through state graph.

**Options:**
1. DFS - Deep paths first, memory efficient
2. BFS - Short paths first, finds bugs faster
3. Random walk - Good for fuzzing, not deterministic

**Decision:** BFS with max_depth limit

**Rationale:**
- Finds short bug-triggering paths first
- Deterministic
- Easy to parallelize
- max_depth prevents infinite loops

**Consequences:**
- Memory grows with breadth
- May miss deep bugs (mitigated by max_depth)

---

## ADR-006: Click for CLI Framework

**Date:** 2024-01

**Status:** Accepted

**Context:**
Need CLI framework for `venomqa` commands.

**Options:**
1. argparse - Standard but verbose
2. Click - Declarative, good UX
3. Typer - Modern but less mature

**Decision:** Click

**Rationale:**
- Battle-tested
- Good help formatting
- Subcommand support
- Rich integration possible

**Consequences:**
- Dependency on Click
- Different style than argparse

---

## ADR-007: YAML for Configuration

**Date:** 2024-01

**Status:** Accepted

**Context:**
Users need to configure VenomQA.

**Options:**
1. YAML - Human-readable, comments
2. TOML - Python standard (pyproject.toml)
3. JSON - Universal but no comments

**Decision:** YAML (venomqa.yaml)

**Rationale:**
- Human-readable
- Supports comments
- Common in DevOps tools
- Environment variable substitution

**Consequences:**
- PyYAML dependency
- Indentation-sensitive

---

## ADR-008: Journey Variable Convention

**Date:** 2024-02

**Status:** Accepted

**Context:**
How should users define journeys in files?

**Options:**
1. `journey = Journey(...)` - Simple, discoverable
2. `@journey decorator` - More magic
3. `def create_journey():` - Factory pattern

**Decision:** `journey` variable at module level

```python
# journeys/checkout.py
journey = Journey(name="checkout", steps=[...])
```

**Rationale:**
- Simple to understand
- Easy to discover with import
- No decorators/magic
- Can still use factories if needed

**Consequences:**
- One journey per file (or use list)
- Must use exact variable name

---

## ADR-009: Rich for Terminal Output

**Date:** 2024-01

**Status:** Accepted

**Context:**
Need beautiful terminal output for test results.

**Options:**
1. Plain print - Simple but ugly
2. Colorama - Colors only
3. Rich - Full terminal UI

**Decision:** Rich

**Rationale:**
- Tables, panels, progress bars
- Markdown rendering
- Good Windows support
- Active maintenance

**Consequences:**
- Heavy dependency
- May not work in all terminals

---

## ADR-010: httpx over requests

**Date:** 2024-01

**Status:** Accepted

**Context:**
Need HTTP client library.

**Options:**
1. requests - Standard, widely used
2. httpx - Modern, async support
3. aiohttp - Async-only

**Decision:** httpx

**Rationale:**
- requests-compatible API
- Built-in async support (future)
- HTTP/2 support
- Better timeout handling

**Consequences:**
- Less tutorials available than requests
- Slightly different edge cases

---

## Pending Decisions

### ADR-011: Async Support (Draft)

**Status:** Under Discussion

**Context:**
Should we support async actions?

**Options:**
1. Sync only - Simple, current approach
2. Async optional - Detect and await
3. Async first - Breaking change

**Leaning:** Async optional (detect `async def`)

---

### ADR-012: Plugin System (Draft)

**Status:** Under Discussion

**Context:**
How should third-party plugins work?

**Options:**
1. Entry points - Standard Python
2. Directory scanning - Simple
3. Registry pattern - Explicit

**Leaning:** Entry points + registry
