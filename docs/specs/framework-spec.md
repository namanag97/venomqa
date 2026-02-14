clauc# Stateful Journey QA Framework Specification

> A generic framework for end-to-end testing with state exploration

## 1. Overview

A testing framework that:
- Tests applications as a **user would** (API calls, not function calls)
- Explores **multiple paths** through stateful systems
- Uses **database savepoints** to branch and rollback
- Captures **full context** on failures (request, response, logs)
- Manages **real infrastructure** (Docker, databases, services)

```
┌─────────────────────────────────────────────────────────────┐
│                    JOURNEY FRAMEWORK                         │
│                                                              │
│   Journey ─┬─ Step ─── Step ─── Checkpoint ─┬─ Path A       │
│            │                                 ├─ Path B       │
│            │                                 └─ Path C       │
│            │                                                 │
│            └─ Branch (explores all paths, rolls back)        │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Core Concepts

### 2.1 Journey
A complete user scenario from start to finish.

```python
Journey(
    name="user_registration",
    description="User signs up, verifies email, logs in",
    steps=[...]
)
```

### 2.2 Step
A single action with assertions.

```python
Step(
    name="create_account",
    action=create_account,      # Callable
    description="Create new user account",
    expect_failure=False,       # Set True to test error paths
)
```

### 2.3 Checkpoint
A savepoint for state - can rollback here later.

```python
Checkpoint("before_payment")
```

### 2.4 Branch
Fork execution to explore multiple paths from a checkpoint.

```python
Branch(
    checkpoint_name="before_payment",
    paths=[
        Path("payment_success", [...]),
        Path("payment_declined", [...]),
        Path("payment_timeout", [...]),
    ]
)
```

### 2.5 Path
A sequence of steps within a branch.

```python
Path(
    name="payment_success",
    description="Happy path - payment completes",
    steps=[
        Step("submit_payment", submit_payment),
        Step("verify_receipt", verify_receipt),
    ]
)
```

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         QA FRAMEWORK                             │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Runner    │  │   State     │  │   Client    │              │
│  │             │  │   Manager   │  │             │              │
│  │ Executes    │  │             │  │ HTTP calls  │              │
│  │ journeys    │  │ Savepoints  │  │ + history   │              │
│  │ + branches  │  │ + rollback  │  │ + auth      │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│         │                │                │                      │
│         └────────────────┴────────────────┘                      │
│                          │                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Reporter   │  │Infrastructure│ │   Actions   │              │
│  │             │  │             │  │             │              │
│  │ Issue list  │  │ Docker up/  │  │ Reusable    │              │
│  │ + markdown  │  │ down/logs   │  │ API calls   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 Runner
Executes journeys, handles branching logic.

```python
class JourneyRunner:
    def run(self, journey: Journey) -> JourneyResult:
        for step in journey.steps:
            if isinstance(step, Checkpoint):
                self.state.checkpoint(step.name)
            elif isinstance(step, Branch):
                for path in step.paths:
                    self._run_path(path)
                    self.state.rollback(step.checkpoint_name)
            elif isinstance(step, Step):
                self._run_step(step)
```

### 3.2 State Manager
Manages database state via savepoints.

```python
class StateManager:
    def checkpoint(self, name: str):
        self.conn.execute(f"SAVEPOINT {name}")

    def rollback(self, name: str):
        self.conn.execute(f"ROLLBACK TO SAVEPOINT {name}")

    def reset(self):
        # Truncate all tables for clean slate
```

### 3.3 Client
HTTP client that captures everything.

```python
class Client:
    def request(self, method, path, **kwargs) -> Response:
        response = self.http.request(method, path, **kwargs)
        self.history.append({
            "request": {"method": method, "path": path, "body": kwargs},
            "response": {"status": response.status, "body": response.json()},
            "timestamp": now(),
        })
        return response
```

### 3.4 Reporter
Generates human-readable reports.

```python
class Reporter:
    def generate(self) -> str:
        return f"""
        # QA Report

        ## Summary: {passed}/{total} journeys passed

        ## Issues Found
        {self._format_issues()}
        """
```

### 3.5 Infrastructure
Manages external dependencies.

```python
class Infrastructure:
    def start(self):
        subprocess.run(["docker", "compose", "up", "-d"])
        self._wait_healthy()

    def stop(self):
        subprocess.run(["docker", "compose", "down", "-v"])

    def logs(self, service: str) -> str:
        return subprocess.check_output(["docker", "logs", service])
```

---

## 4. Issue Capture

When a step fails, capture full context:

```python
@dataclass
class Issue:
    journey: str          # Which journey
    path: str             # Which branch path
    step: str             # Which step failed
    error: str            # Error message
    request: dict | None  # HTTP request that failed
    response: dict | None # HTTP response received
    logs: list[str]       # Recent server logs
    suggestion: str       # Auto-generated fix suggestion
```

### 4.1 Auto-Suggestions

Pattern match errors to suggestions:

```python
SUGGESTIONS = {
    "401": "Check authentication - token may be invalid",
    "404": "Endpoint not found - check route registration",
    "422": "Validation error - check request schema",
    "500": "Server error - check logs for traceback",
    "timeout": "Operation timed out - check if service is running",
    "connection refused": "Service not running - check Docker",
}
```

---

## 5. Journey Definition DSL

### 5.1 Simple Journey

```python
journey = Journey(
    name="basic_crud",
    steps=[
        Step("create", lambda c, ctx: c.post("/items", json={"name": "test"})),
        Step("read", lambda c, ctx: c.get(f"/items/{ctx['create']['id']}")),
        Step("update", lambda c, ctx: c.put(f"/items/{ctx['create']['id']}", json={"name": "updated"})),
        Step("delete", lambda c, ctx: c.delete(f"/items/{ctx['create']['id']}")),
    ]
)
```

### 5.2 Branching Journey

```python
journey = Journey(
    name="payment_flow",
    steps=[
        Step("add_to_cart", add_item_to_cart),
        Step("checkout", start_checkout),
        Checkpoint("before_payment"),
        Branch(
            checkpoint_name="before_payment",
            paths=[
                Path("success", [
                    Step("pay", pay_with_valid_card),
                    Step("verify_order", check_order_confirmed),
                ]),
                Path("declined", [
                    Step("pay", pay_with_declined_card, expect_failure=True),
                    Step("verify_cart", check_cart_still_exists),
                ]),
                Path("cancel", [
                    Step("cancel", cancel_checkout),
                    Step("verify_cart", check_cart_restored),
                ]),
            ]
        ),
    ]
)
```

---

## 6. Execution Model

```
Journey Start
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1 ──► Step 2 ──► Checkpoint("X") ──► Branch          │
│                                              │              │
│                            ┌─────────────────┼──────────┐   │
│                            ▼                 ▼          ▼   │
│                        Path A            Path B      Path C │
│                            │                 │          │   │
│                            ▼                 ▼          ▼   │
│                        [steps]           [steps]    [steps] │
│                            │                 │          │   │
│                            └─────────────────┴──────────┘   │
│                                      │                      │
│                            Rollback to "X" after each       │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
Journey End (all paths explored)
```

---

## 7. Configuration

```python
@dataclass
class QAConfig:
    base_url: str = "http://localhost:8000"
    db_url: str = "postgresql://..."
    docker_compose_file: str = "docker-compose.qa.yml"
    timeout: int = 30
    retry_count: int = 3
    capture_logs: bool = True
    log_lines: int = 50
```

---

## 8. CLI Interface

```bash
# Run all journeys
qa run

# Run specific journeys
qa run j01 j02 j05

# Skip infrastructure management
qa run --no-infra

# Generate report only
qa report

# List available journeys
qa list
```

---

## 9. Integration Points

### 9.1 CI/CD Pipeline

```yaml
# .github/workflows/qa.yml
qa:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: docker compose -f docker-compose.qa.yml up -d
    - run: python -m qa
    - uses: actions/upload-artifact@v4
      with:
        name: qa-report
        path: qa/QA-REPORT.md
```

### 9.2 Pre-commit Hook

```bash
#!/bin/bash
# Run smoke test before push
python -m qa j01 --no-infra || exit 1
```

---

## 10. Improvements Roadmap

### Phase 1: Bug Detection Automation
- [ ] Fuzzing: Random valid inputs to find edge cases
- [ ] Property-based testing: Hypothesis integration
- [ ] Invariant checking: Assert system invariants after each step

### Phase 2: Intelligence
- [ ] Failure clustering: Group similar failures
- [ ] Root cause analysis: Trace failures to code changes
- [ ] Flaky test detection: Track intermittent failures

### Phase 3: Generation
- [ ] Journey generation from OpenAPI spec
- [ ] Action generation from route definitions
- [ ] Assertion generation from response schemas

### Phase 4: Continuous QA
- [ ] Watch mode: Re-run on file changes
- [ ] Parallel execution: Run journeys concurrently
- [ ] Distributed execution: Run across machines

---

## 11. Comparison to Existing Tools

| Feature | Our Framework | Playwright | Postman | pytest-bdd |
|---------|---------------|------------|---------|------------|
| API testing | ✅ | ✅ | ✅ | ✅ |
| State branching | ✅ | ❌ | ❌ | ❌ |
| DB savepoints | ✅ | ❌ | ❌ | ❌ |
| Docker mgmt | ✅ | ❌ | ❌ | ❌ |
| Issue capture | ✅ | Partial | Partial | ❌ |
| Auto-suggestions | ✅ | ❌ | ❌ | ❌ |
| Journey DSL | ✅ | ❌ | Collections | Gherkin |

---

## 12. Generic Implementation Checklist

To implement for any codebase:

1. [ ] Define `Client` for your API (HTTP, gRPC, GraphQL)
2. [ ] Define `StateManager` for your database
3. [ ] Define `Infrastructure` for your services
4. [ ] Create `actions/` with reusable API calls
5. [ ] Create `journeys/` with user scenarios
6. [ ] Create `docker-compose.qa.yml` for test infra
7. [ ] Add `__main__.py` entry point
8. [ ] Add to CI/CD pipeline
