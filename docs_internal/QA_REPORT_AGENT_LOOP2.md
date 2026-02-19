# VenomQA Agent QA Loop — Report 2
**Date:** 2026-02-19
**Scope:** Deep behavioral QA — agent engine, reporters, adapters, strategies, OpenAPI generator, auth, violation paths
**Method:** 27 unit test files + 7 behavioral probe suites running against installed package

---

## Overall Result

| Area | Tests | Result |
|---|---|---|
| All 27 unit test files | 567 tests | ✅ 567 PASS |
| Agent behavioral probes (BFS/DFS/violations/rollback) | 19 probes | ✅ 19 PASS |
| Reporter probes (JSON/Markdown/JUnit/Console) | 9 probes | ✅ 9 PASS |
| Mock adapter probes (Queue/Mail/Time/Storage) | 22 probes | ✅ 22 PASS |
| Strategy probes (CoverageGuided, shrink) | 7 probes | ✅ 7 PASS |
| OpenAPI generator probes | 5 probes | ✅ 5 PASS |
| Auth helper probes (Bearer/ApiKey/MultiRole) | 8 probes | ✅ 8 PASS |
| Violation reproduction path probes | 8 probes | ✅ 8 PASS |
| github_stripe_qa integration example | 15 tests | ✅ 15 PASS |

**Total: 567 unit + 78 behavioral probes — 645 checks, 0 failures after fixes.**

---

## Bug Found and Fixed

### BUG — CRITICAL: `Invariant` severity/message fields swapped

**File:** `src/venomqa/v1/core/invariant.py`
**Symptom:** `Invariant("name", check, Severity.CRITICAL)` silently set `message=Severity.CRITICAL`, `severity=MEDIUM` (the default). Every user passing severity as the 3rd positional arg got wrong severity on violations.

```python
# Before (broken):
name: str
check: Callable
message: str = ""         # ← 3rd positional = message (wrong)
severity: Severity = Severity.MEDIUM

# After (fixed):
name: str
check: Callable
severity: Severity = Severity.MEDIUM  # ← 3rd positional = severity (correct)
message: str = ""
```

**Safe:** All existing tests used keyword args (`severity=Severity.HIGH`) — zero breakage.
**Verification:** `violation.severity == Severity.CRITICAL` now passes for positional construction.

---

## API Reference (Confirmed Working — No More Guessing)

### Agent
```python
# World needs state_from_context OR systems — bare World(api=api) raises ValueError
world = World(api=api, state_from_context=["order_id"])
# OR
world = World(api=api, systems={"db": SQLiteAdapter("path.db")})

# actions + invariants go on Agent, not World
agent = Agent(
    world=world,
    actions=[...],
    invariants=[...],
    strategy=BFS(),          # BFS() takes no args
    max_steps=100,           # depth control
    shrink=True,             # optional: shorten reproduction paths
)
result = agent.explore()     # NOT .run()
```

### Invariant (field order matters for positional use)
```python
Invariant("name", check_fn, Severity.CRITICAL)        # ✅ severity=CRITICAL
Invariant("name", check_fn, Severity.HIGH, "message") # ✅ severity=HIGH, message set
Invariant("name", check_fn, message="msg")             # ✅ keyword — severity=MEDIUM (default)
```

### Mock Adapters
```python
# MockQueue
q = MockQueue()
msg = q.push({"data": 1})    # NOT enqueue
item = q.pop()               # NOT dequeue; returns Message object or None
q.pending_count              # NOT depth
q.checkpoint("name") / q.rollback(snap)   # NOT get_state_snapshot

# MockMail
mail = MockMail()
mail.send(to="a@b.com", subject="Hi", body="test")
mail.sent_count              # property
emails = mail.get_sent()     # returns list[Email]
emails[0].to                 # list[str] — NOT dict, not subscriptable
mail.checkpoint("name") / mail.rollback(snap)

# MockTime
clock = MockTime()
clock.freeze()
t = clock.now                # property, datetime — NOT clock.now()
clock.advance(seconds=60)
clock.checkpoint("name") / clock.rollback(snap)

# MockStorage
store = MockStorage()
store.put("path", b"bytes")
f = store.get("path")        # StoredFile with .content attr
store.exists("path")
store.file_count             # property
store.checkpoint("name") / store.rollback(snap)
```

### Reporters — all return strings
```python
JSONReporter().report(result)       # → JSON string
MarkdownReporter().report(result)   # → Markdown string
JUnitReporter().report(result)      # → XML string
ConsoleReporter(file=f).report(r)   # → writes to stdout or file= via rich
```

### generate_actions — returns list[Action], not files
```python
actions = generate_actions("spec.yaml")       # from file path
actions = generate_actions(spec_dict)         # from dict
actions = generate_actions("spec.yaml", include_patterns=["*/users"])
# venomqa generate --from-openapi spec.yaml   ← CLI writes files
```

### Auth — takes callables, not strings
```python
BearerTokenAuth(token_fn=lambda ctx: "static_tok")
BearerTokenAuth(token_fn=lambda ctx: ctx.get("token"))  # reads from context
ApiKeyAuth(key_fn=lambda ctx: "key", header="X-API-Key")
MultiRoleAuth(roles={"admin": auth1, "user": auth2}, default="user")
auth.get_headers(context)            # → dict of headers
auth.get_headers(context, role="x")  # → MultiRoleAuth only
# returning None from token_fn/key_fn → header omitted silently
```

---

## Non-Issues (Probe Design, Not Bugs)

1. **"Action returning None crashes"** — intentional. Always `return resp`. Use preconditions to skip actions, not `return None`. Test `test_action_missing_return_raises_clear_error` guards this.

2. **Adapter rollback protocol is `checkpoint/rollback`** — not `get_state_snapshot/rollback_from_snapshot`. The `MockHTTPServer` pattern (for HTTP-backed mocks) uses the snapshot pattern; the pure in-memory adapters use checkpoint/rollback directly.

3. **BFS finding "spurious" queue violation** — the agent correctly found a 6-push sequence that exceeded the queue depth bound. The invariant was legitimately violated; the probe assertion was too strict.
