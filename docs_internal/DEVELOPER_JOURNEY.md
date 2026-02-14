# Developer Journey Map

> Understanding how developers experience venomQA and where they struggle.

---

## The Journey Stages

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  Discovery  │──▶│   Install   │──▶│   Setup     │──▶│   Write     │──▶│    Run      │
│  "What is   │   │  & Demo     │   │  Project    │   │  Journeys   │   │   Tests     │
│   this?"    │   │             │   │             │   │             │   │             │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
                                                                              │
                                                                              ▼
                                                      ┌─────────────┐   ┌─────────────┐
                                                      │   Scale     │◀──│   Debug     │
                                                      │  & CI/CD    │   │  Failures   │
                                                      └─────────────┘   └─────────────┘
```

---

## Stage 1: Discovery

**What they do:** Read README, browse docs, watch demo

**Current Experience:**
- README is comprehensive but dense
- "First 5 Minutes Checklist" is excellent
- `venomqa demo --explain` is a standout feature

**Pain Points:**
- None significant - discovery is good

**Grade: A**

---

## Stage 2: Install & Demo

**What they do:** `pip install venomqa && venomqa demo`

**Current Experience:**
- Installation is smooth
- Demo runs without configuration
- Explain mode teaches concepts well

**Pain Points:**
- ⚠️ **Warning noise**: "Environment file not found: .env" appears even when not needed (TD-016)
- Could be intimidating for beginners who see warnings

**Grade: A-** (warning noise detracts slightly)

---

## Stage 3: Project Setup

**What they do:** `venomqa init`, edit `venomqa.yaml`

**Current Experience:**
- Creates sensible directory structure
- Config file has good comments
- README is generated with instructions

**Pain Points:**
- None significant

**Grade: A**

---

## Stage 4: Writing First Journey ⚠️

**What they do:** Create `journeys/my_journey.py`

**Current Experience:**
- Examples exist but patterns are inconsistent
- Generated code uses clean imports (sys.path is handled by `venomqa run`)

**Pain Points:**
1. ~~**Import confusion (TD-003)**~~: FIXED - The `_load_journey` function now automatically adds the project root to sys.path, so generated journeys don't need any path manipulation.

2. ⚠️ **Naming confusion (TD-001)**: Documentation says create `journeys/checkout.py` but discovery module only finds `*_journey.py` or `journey_*.py`. User creates `checkout.py`, CLI finds it, but if they use the API directly it might not work.

3. ⚠️ **No feedback on errors**: If journey has invalid structure (e.g., Branch references non-existent Checkpoint), they only find out at runtime.

**What they need:**
- Clear, consistent patterns
- No hacky workarounds visible to users
- Early validation with helpful errors

**Grade: C+**

---

## Stage 5: Running Tests

**What they do:** `venomqa run`

**Current Experience:**
- CLI output is clean and visual
- Progress indicators work well

**Pain Points:**
1. ⚠️ **Discovery inconsistency (TD-001)**: If they name file `checkout.py` instead of `checkout_journey.py`, behavior varies

2. ⚠️ **Silent checkpoint failure (TD-006)**: If they use `Checkpoint("save")` but didn't configure a StateManager:
   ```python
   journey = Journey(
       name="test",
       steps=[
           Step(name="setup", action=setup),
           Checkpoint(name="save"),  # SILENTLY DOES NOTHING
           Branch(checkpoint_name="save", paths=[...])  # Will fail confusingly
       ]
   )
   ```
   No warning. Checkpoint silently does nothing. Branch tries to rollback and fails with confusing error.

**Grade: B-**

---

## Stage 6: Debugging Failures ⚠️ CRITICAL

**What they do:** Figure out why a step failed

**Current Experience:**
- Errors show what failed
- Errors do NOT show how to fix

**Pain Points:**
1. 🔴 **No actionable guidance (TD-002)**: Error shows:
   ```
   [E001] Connection refused
   ```
   Should show:
   ```
   [E001] Connection refused: http://localhost:8000

   The API server is not responding. Try:
     1. Is your server running? curl http://localhost:8000/health
     2. Wrong URL? Check base_url in venomqa.yaml
   ```

2. 🔴 **Request/response hidden (TD-004)**: On failure, only shows "HTTP 422" not the actual error body. User has no idea what was wrong with their request.

3. **No context on Branch failures**: If a branch path fails, error doesn't clearly show which path, which step, what checkpoint was involved.

**What they need:**
- Error messages with "What to try" suggestions
- Always show request body and response body on failure
- Clear path through the failure: Journey → Path → Step → Error

**Grade: D**

---

## Stage 7: Scaling & CI/CD

**What they do:** Add more journeys, integrate with CI

**Current Experience:**
- JUnit XML output works
- GitHub Actions integration exists
- Reports are comprehensive

**Pain Points:**
- Documentation for CI/CD integration could be more prominent
- No graceful shutdown on Ctrl+C (TD-012)

**Grade: B**

---

## Priority Fixes (Developer Experience Order)

### Must Fix Before Launch

| Priority | Issue | Impact | Effort |
|----------|-------|--------|--------|
| 1 | TD-002: Error messages | Users give up when they can't debug | 2h |
| 2 | TD-006: Silent checkpoint | Confusing failures, looks like a bug | 1h |
| 3 | TD-001: Discovery consistency | "It worked, then didn't work" confusion | 2h |
| 4 | TD-004: Show request/response | Can't debug without this | 2h |

### Should Fix

| Priority | Issue | Impact | Effort |
|----------|-------|--------|--------|
| 5 | TD-003: Remove sys.path hack | Looks unprofessional | 3h |
| 6 | TD-005: Journey validation | Catch errors early | 3h |
| 7 | TD-016: .env warning noise | Minor annoyance | 30m |

---

## Key Insight

**The "Golden Path" is good. The "Error Path" is terrible.**

When everything works, venomQA is excellent:
- Demo is great
- CLI is clean
- Progress is visible

When something breaks, developers are stuck:
- No guidance on what went wrong
- No suggestion on how to fix
- Silent failures that look like bugs

**Fix the Error Path and venomQA becomes production-ready.**

---

## Quick Wins

1. **Add warning when Checkpoint used without StateManager** (30 min)
2. **Remove .env warning when .env not configured** (15 min)
3. **Always show request/response on failure** (1 hour)
4. **Add "What to try" to common errors** (2 hours)

These 4 changes would dramatically improve developer experience.
