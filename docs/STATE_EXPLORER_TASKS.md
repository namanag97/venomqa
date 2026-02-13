# State Explorer Implementation Tasks

> **Last Updated:** 2026-02-13
> **Status:** Phase 1 - Foundation

---

## Quick Status

| Phase | Status | Progress |
|-------|--------|----------|
| Phase 1: Foundation | IN PROGRESS | 20% |
| Phase 2: API Discovery | NOT STARTED | 0% |
| Phase 3: State Detection | NOT STARTED | 0% |
| Phase 4: Exploration Engine | NOT STARTED | 0% |
| Phase 5: Issue Detection | NOT STARTED | 0% |
| Phase 6: Visualization | NOT STARTED | 0% |
| Phase 7: Integration | NOT STARTED | 0% |

---

## Phase 1: Foundation (Current)

### Completed
- [x] Create project structure (`venomqa/explorer/`)
- [x] Create project plan document
- [x] Create technical specification
- [x] Define data models (State, Transition, Action, StateGraph)
- [x] Create module skeleton files

### In Progress
- [ ] Implement StateGraph core methods
- [ ] Implement State fingerprinting
- [ ] Add unit tests for models

### Pending
- [ ] Add serialization/deserialization for StateGraph
- [ ] Implement graph traversal utilities
- [ ] Add model validation

---

## Phase 2: API Discovery

### Tasks
- [ ] Implement OpenAPI spec parser
- [ ] Extract endpoints, methods, parameters
- [ ] Extract request/response schemas
- [ ] Implement endpoint crawling (fallback)
- [ ] Handle authentication requirements
- [ ] Unit tests for discoverer

---

## Phase 3: State Detection

### Tasks
- [ ] Implement state fingerprint algorithm
- [ ] Detect auth state from responses
- [ ] Detect entity states from responses
- [ ] Handle HATEOAS links for available actions
- [ ] Implement state caching
- [ ] Unit tests for detector

---

## Phase 4: Exploration Engine

### Tasks
- [ ] Implement BFS exploration strategy
- [ ] Implement DFS exploration strategy
- [ ] Implement action execution
- [ ] Handle state transitions
- [ ] Implement depth limiting
- [ ] Implement cycle detection
- [ ] Add database rollback integration
- [ ] Unit tests for engine

---

## Phase 5: Issue Detection

### Tasks
- [ ] Detect error responses (4xx, 5xx)
- [ ] Detect dead-end states
- [ ] Detect unreachable states
- [ ] Detect cycles/infinite loops
- [ ] Detect slow transitions
- [ ] Generate fix suggestions
- [ ] Unit tests for issue detector

---

## Phase 6: Visualization & Reporting

### Tasks
- [ ] Implement DOT format export
- [ ] Implement Mermaid format export
- [ ] Implement PNG rendering (graphviz)
- [ ] Implement interactive HTML (vis.js)
- [ ] Generate coverage reports
- [ ] Generate issue reports
- [ ] Unit tests for visualizer/reporter

---

## Phase 7: Integration

### Tasks
- [ ] Integrate with VenomQA Client
- [ ] Integrate with StateManager (rollbacks)
- [ ] Add CLI commands (`venomqa explore`)
- [ ] Add to existing reporters
- [ ] Integration tests with todo_app
- [ ] Documentation and examples

---

## Session Log

### Session 1 (2026-02-13)
- Created project structure
- Created STATE_EXPLORER_PROJECT.md (57KB)
- Created STATE_EXPLORER_SPEC.md (85KB)
- Created module skeleton files:
  - models.py (19KB) - Data models
  - explorer.py (12KB) - Main orchestrator
  - engine.py (11KB) - Exploration engine
  - visualizer.py (9.4KB) - Graph visualization
  - reporter.py (9.5KB) - Report generation
  - discoverer.py (8.3KB) - API discovery
  - detector.py (8.6KB) - State detection
- Verified module imports successfully

**Next Session Priority:**
1. Implement StateGraph.add_state() and add_transition()
2. Implement State fingerprinting
3. Write unit tests for models
4. Start on APIDiscoverer (OpenAPI parsing)

---

## Files Reference

| File | Purpose | Status |
|------|---------|--------|
| `docs/STATE_EXPLORER_PROJECT.md` | Project plan & architecture | Complete |
| `docs/STATE_EXPLORER_SPEC.md` | Technical specification | Complete |
| `docs/STATE_EXPLORER_TASKS.md` | Task tracking (this file) | Active |
| `venomqa/explorer/models.py` | Data models | Skeleton |
| `venomqa/explorer/explorer.py` | Main StateExplorer class | Skeleton |
| `venomqa/explorer/engine.py` | Exploration engine | Skeleton |
| `venomqa/explorer/discoverer.py` | API endpoint discovery | Skeleton |
| `venomqa/explorer/detector.py` | State detection | Skeleton |
| `venomqa/explorer/visualizer.py` | Graph visualization | Skeleton |
| `venomqa/explorer/reporter.py` | Report generation | Skeleton |

---

## How to Continue Development

```bash
# 1. Check current status
cat docs/STATE_EXPLORER_TASKS.md

# 2. Read the project plan
cat docs/STATE_EXPLORER_PROJECT.md

# 3. Read technical spec for implementation details
cat docs/STATE_EXPLORER_SPEC.md

# 4. Work on current phase tasks
# Update this file after completing tasks
```

---

## Commands for Testing

```bash
# Verify module imports
python3 -c "from venomqa.explorer import StateExplorer; print('OK')"

# Run explorer tests (when written)
pytest tests/test_explorer/ -v

# Test with todo_app (after integration)
cd examples/todo_app/qa
venomqa explore --openapi ../app/openapi.json
```
