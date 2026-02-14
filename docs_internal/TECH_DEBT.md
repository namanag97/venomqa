# Technical Debt Tracker

> Track technical debt and plan payoff.

---

## Summary

| Priority | Count | Estimated Effort |
|----------|-------|------------------|
| Critical | 2 | 4 hours |
| High | 5 | 12 hours |
| Medium | 8 | 20 hours |
| Low | 6 | 15 hours |

---

## Critical (Fix ASAP)

### TD-001: Two Journey Discovery Mechanisms
**Location:** `venomqa/cli/commands.py:365` and `venomqa/plugins/discovery.py:167`

**Problem:**
```python
# commands.py - discovers ALL .py files
for journey_file in journeys_dir.glob("*.py"):

# discovery.py - only specific patterns
patterns = ["*_journey.py", "journey_*.py"]
```

**Impact:** Users create `journeys/hello.py` but discovery may not find it consistently.

**Fix:** Unify to one approach - discover all `.py` files with `journey` variable.

**Effort:** 2 hours

---

### TD-002: Error Messages Missing "How to Fix"
**Location:** `venomqa/errors/base.py`

**Problem:** Errors show what failed but not how to fix:
```
[E001] Connection refused
```

**Should be:**
```
[E001] Connection refused: http://localhost:8000

The API server is not responding. Try:
  1. Is your server running? curl http://localhost:8000/health
  2. Wrong URL? Check base_url in venomqa.yaml
```

**Impact:** Users give up instead of fixing issues.

**Effort:** 2 hours

---

## High Priority

### TD-003: Import Path Manipulation in Generated Code
**Location:** `venomqa/cli/commands.py` (SAMPLE_JOURNEY_PY template)

**Problem:**
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

**Impact:** Confuses beginners, looks hacky.

**Fix:** Either make package-style imports work or keep journeys self-contained.

**Effort:** 3 hours

---

### TD-004: Request/Response Hidden by Default
**Location:** `venomqa/runner/__init__.py`

**Problem:** On failure, users only see "HTTP 422" not the actual response body.

**Impact:** Hard to debug without `--debug` flag.

**Fix:** Always show request/response on failure (not just in debug mode).

**Effort:** 2 hours

---

### TD-005: No Validation of Journey Structure
**Location:** `venomqa/core/models.py`

**Problem:** Invalid journey structures fail at runtime with confusing errors.

**Fix:** Add `journey.validate()` method, call on load.

**Effort:** 3 hours

---

### TD-006: StateManager Not Required but Used
**Location:** `venomqa/runner/__init__.py`

**Problem:** Checkpoints silently do nothing if StateManager not configured.

**Fix:** Warn or error when Checkpoint used without StateManager.

**Effort:** 1 hour

---

### TD-007: Circular Import Risk
**Location:** Various `__init__.py` files

**Problem:** Large `__init__.py` with many imports can cause circular imports.

**Fix:** Lazy imports or restructure modules.

**Effort:** 3 hours

---

## Medium Priority

### TD-008: Broken Internal Doc Links
**Location:** `docs/**/*.md`

**Problem:** ~20 broken links like `getting-started.md`, `FAQ.md` in wrong paths.

**Impact:** Poor documentation UX.

**Effort:** 2 hours

---

### TD-009: No Type Hints on Some Functions
**Location:** Various older files

**Problem:** Inconsistent type coverage.

**Fix:** Add type hints, enable strict mypy.

**Effort:** 4 hours

---

### TD-010: Duplicate Code in Adapters
**Location:** `venomqa/adapters/`

**Problem:** Redis cache and Redis queue share connection logic.

**Fix:** Extract common `RedisConnection` base.

**Effort:** 2 hours

---

### TD-011: Tests for Adapters Incomplete
**Location:** `tests/adapters/`

**Problem:** Some adapters have no tests.

**Effort:** 4 hours

---

### TD-012: No Graceful Shutdown
**Location:** `venomqa/cli/demo.py`, `venomqa/runner/`

**Problem:** Ctrl+C may leave resources open.

**Fix:** Add signal handlers, cleanup on exit.

**Effort:** 2 hours

---

### TD-013: Config Schema Not Enforced
**Location:** `venomqa/config/loader.py`

**Problem:** Invalid config keys silently ignored.

**Fix:** Use pydantic or schema validation.

**Effort:** 3 hours

---

### TD-014: No Retry on Checkpoint Failure
**Location:** `venomqa/state/`

**Problem:** Checkpoint creation can fail transiently.

**Fix:** Add retry logic with backoff.

**Effort:** 1 hour

---

### TD-015: Large Response Bodies in Memory
**Location:** `venomqa/client/__init__.py`

**Problem:** 100MB response loads entirely into memory.

**Fix:** Stream large responses to disk.

**Effort:** 2 hours

---

## Low Priority

### TD-016: `.env not found` Warning Noise
**Location:** `venomqa/client/__init__.py`

**Problem:** Prints warning even when `.env` not needed.

**Fix:** Only warn if explicitly configured.

**Effort:** 30 min

---

### TD-017: No Docstrings on Private Methods
**Location:** Various

**Problem:** Internal methods undocumented.

**Effort:** 3 hours

---

### TD-018: Magic Numbers in Code
**Location:** Various

**Problem:** Hardcoded values like `timeout=30`, `retry=3`.

**Fix:** Move to constants or config.

**Effort:** 1 hour

---

### TD-019: No Changelog Automation
**Location:** `CHANGELOG.md`

**Problem:** Manually maintained.

**Fix:** Use conventional commits + auto-changelog.

**Effort:** 2 hours

---

### TD-020: Old Python Version Support
**Location:** `pyproject.toml`

**Problem:** Supporting 3.10+ limits modern features.

**Consider:** Dropping 3.10, requiring 3.11+.

**Effort:** 1 hour

---

### TD-021: No Benchmarks
**Location:** N/A

**Problem:** No performance regression detection.

**Fix:** Add benchmark suite with pytest-benchmark.

**Effort:** 4 hours

---

## Debt Payoff Plan

### Sprint 1 (This Week)
- [ ] TD-001: Journey discovery (Critical)
- [ ] TD-002: Error messages (Critical)

### Sprint 2 (Next Week)
- [ ] TD-004: Request/response on failure
- [ ] TD-003: Import path fix
- [ ] TD-006: StateManager warning

### Sprint 3
- [ ] TD-008: Fix doc links
- [ ] TD-005: Journey validation
- [ ] TD-016: .env warning

### Backlog
- All Medium and Low items
