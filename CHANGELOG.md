# Changelog

All notable changes to VenomQA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.5] - 2026-02-17

### Added

- **`BearerTokenAuth`, `ApiKeyAuth`, `MultiRoleAuth`** — built-in auth helpers that eliminate the `_auth(context)` helper copy-pasted in every action file. Pass `auth=` to `World` and every request gets the token injected automatically:
  ```python
  from venomqa.v1 import BearerTokenAuth, MultiRoleAuth, World
  world = World(api=api, auth=BearerTokenAuth(lambda ctx: ctx.get("token")))
  # In actions: api.get("/x")  ← no manual headers needed

  # Multi-role RBAC:
  world = World(api=api, auth=MultiRoleAuth(
      roles={"admin": BearerTokenAuth(lambda c: c.get("token")),
             "viewer": BearerTokenAuth(lambda c: c.get("viewer_token"))},
      default="admin",
  ))
  def viewer_cannot_delete(api, context):
      return api.delete("/resource/1", role="viewer")  # viewer token injected
  # or: viewer = api.with_role("viewer"); viewer.delete("/resource/1")
  ```

- **`Agent(shrink=True)`** — automatic path shrinking. After finding a violation with a long reproduction path (e.g. 15 steps), VenomQA delta-debugs it down to the minimal sequence that still triggers the same invariant. The violation message notes how many steps were removed. Off by default (opt-in).

- **`OpenAPISchemaInvariant`** — validates every HTTP response against the OpenAPI spec automatically. No per-endpoint invariants needed — catches missing required fields, wrong types, and schema drift for free:
  ```python
  from venomqa.v1.invariants import OpenAPISchemaInvariant
  invariants = [
      OpenAPISchemaInvariant(spec_url="http://localhost:8000/openapi.json"),
      # or: OpenAPISchemaInvariant(spec_path="api-spec.yaml")
  ]
  ```
  Uses `jsonschema` for full validation if installed; falls back to structural checks (required fields + type) if not. Skips paths not in the spec and undocumented status codes.

- **`world.last_action_result`** — property exposing the `ActionResult` from the most recent `world.act()` call. Available inside invariant `check(world)` functions for HTTP-aware invariants.

## [0.4.4] - 2026-02-17

### Added

- **Violation deduplication** — `result.unique_violations` returns one violation per `(invariant, action)` root cause, keeping the shortest reproduction path. `ConsoleReporter` now prints `"N violations (M unique root causes — showing shortest path per cause)"` and annotates each with `(xN total)`. `JSONReporter` adds a `unique_violations` key alongside `violations`. Turns 49 near-identical violations into 1 actionable entry.

- **`World(teardown=fn)`** — mirror of `setup=`. Called after `Agent.explore()` completes (whether successful, truncated, or on violation). Use to delete test data created during the run. Same `(api, context)` signature as setup. Errors in teardown are swallowed so they don't mask exploration results.

- **`World(state_from_context=[...])`** — track state from context key values with no database adapter required. When any listed key changes between actions, VenomQA sees a new state — `states_visited > 1` works out of the box for pure HTTP APIs. Suppresses the "no systems registered" warning. This removes the biggest onboarding blocker.

- **`venomqa scaffold openapi <url>`** — scaffold command now accepts live HTTP/HTTPS URLs in addition to local files. FastAPI, Django Ninja, Flask-Smorest and others serve `/openapi.json` by default: `venomqa scaffold openapi http://localhost:8000/openapi.json -o qa/actions/generated.py`

- **`venomqa replay`** — re-run a violation's reproduction path step by step against a live API. Prints the full request/response at each step. `--interactive` pauses after each step for debugging:
  ```bash
  venomqa replay reports/run.json --violation 0 --base-url http://localhost:8000 --actions qa/actions/my_actions.py
  venomqa replay reports/run.json --violation 0 --base-url http://localhost:8000 --actions qa/actions/my_actions.py --interactive
  ```

## [0.4.3] - 2026-02-17

### Added

- **`World(clients={...})`** — register named `HttpClient` instances for multi-role / RBAC testing. Access in invariants as `world.clients["viewer"]`, access in actions as `context.get_client("viewer")`. Named clients survive checkpoint/rollback (they are test infrastructure, not application state). Example:
  ```python
  world = World(
      api=admin_api,
      clients={"viewer": viewer_api, "anon": HttpClient(base_url)},
  )

  def viewer_cannot_delete(world):
      result = world.clients["viewer"].delete("/resource/1")
      return result.response.status_code == 403
  ```

- **`venomqa scaffold openapi <spec.yaml>`** — generate a runnable VenomQA actions file from an OpenAPI 3.x spec. Produces one action function per endpoint with context wiring (path params → `context.get()`, `id` fields in responses → `context.set()`), expected statuses inferred from the spec, and a ready-to-run `Agent` setup at the bottom. Supports `.yaml`, `.yml`, and `.json`. Example:
  ```bash
  venomqa scaffold openapi api-spec.yaml -o qa/actions/generated.py --base-url http://localhost:8000
  ```

## [0.4.2] - 2026-02-17

### Added

- **`Agent(progress_every=N)`** — print a progress line every N steps: `step 100/3000 | states 12 | coverage 8% | violations 0`. Gives real-time feedback during long explorations. Pass `progress_every=100` to see updates every 100 steps.
- **`venomqa explore --verbose`** — enables `progress_every=100` from the CLI.
- **`explore(progress_every=N)`** — same parameter on the convenience function.

### Fixed

- **PostgresAdapter + BFS/CoverageGuided/Weighted crash** — `Agent.__init__()` now raises a clear `ValueError` immediately if a non-DFS strategy is paired with `PostgresAdapter`. PostgreSQL SAVEPOINTs are stack-based: `ROLLBACK TO S1` destroys all later savepoints, so BFS mid-run rollbacks crash with `InvalidSavepointSpecification`. The error message explains the problem and lists three fixes (use `DFS()`, use `SQLiteAdapter`, use `MockHTTPServer`).

## [0.4.1] - 2026-02-17

### Added

- **Runtime warnings for common LLM/user mistakes**:
  - `No systems registered in World` — warns when `world.systems` is empty, which causes all states to hash identically and `states_visited=1`.
  - `All N actions valid from initial state` — warns when every action is available from step 0, which usually means IDs were pre-seeded in context and exploration will be shallow.
- **String shorthand in `Action.preconditions`** — strings are automatically resolved to `precondition_action_ran()` calls. `preconditions=["create_connection"]` now works without importing `precondition_action_ran`.
- **`COMMON MISTAKES` section in `venomqa llm-docs`** — covers the 6 most common errors: no adapter, pre-seeded context, `expected_status` behaviour, returning `None`, string preconditions, and guard-vs-precondition patterns.

## [0.4.0] - 2026-02-17

### Added

- **`HttpClient.with_headers(headers)`** — returns a new `HttpClient` inheriting base URL and timeout but merging the given headers over defaults. Enables per-role auth tokens without a second full client: `viewer_api = api.with_headers({"Authorization": viewer_token})`.
- **`World(setup=fn)`** — optional `setup` function called by `Agent.explore()` before the initial checkpoint. Use for DB seeding, auth token bootstrap, or any one-time pre-exploration setup: `World(api=api, setup=bootstrap_auth)`.
- **`coverage_target` param on `Agent` and `explore()`** — stop exploration once action coverage reaches the given fraction (0.0–1.0). Exposed in CLI as `venomqa explore --coverage-target 0.8`.
- **`precondition_action_ran(*action_names)`** — gate an action on prior actions having fired at least once in the current exploration. Agent checks `_required_actions` against the set of used action names, enabling clean dependency ordering without guard logic inside action functions.
- **`Graph.used_action_names`** property — set of action names executed at least once. Used internally by context-aware precondition checking.
- **`src/` layout** — package source moved to `src/venomqa/` to prevent the local directory from shadowing an installed `venomqa` package. Root `conftest.py` adds `src/` to `sys.path` for test runs.

### Fixed

- **`HTMLTraceReporter` crash (`KeyError: 'coverage_percent'`)** — `ExplorationResult.summary()` now includes a `coverage_percent` alias key (mapped to `action_coverage_percent`) so the HTML reporter and any other consumers that reference `summary['coverage_percent']` no longer crash.
- **`expected_status=[404]` without `expect_failure=True` was ignored** — `ResponseAssertion.validate()` previously checked `response.ok` even when the status code was already explicitly accepted by `expected_status`. Now, if `expected_status` is set and the response status is in the list, the ok/fail check is skipped entirely. `Action(expected_status=[404])` alone now correctly passes on a 404 response.
- **`precondition_has_context` now enforces checks via Agent** — context-aware preconditions are evaluated with the live `Context` when filtering valid actions.

## [0.3.0] - 2026-02-17

### Added

- **MockHTTPServer** — abstract base class for in-process mock HTTP servers with real checkpoint/rollback (no HTTP round-trips). Subclass and implement `get_state_snapshot()`, `rollback_from_snapshot()`, `observe_from_state()` for instant branching exploration.
- **HTMLTraceReporter** — self-contained D3.js force-graph report. Nodes are states (colored by violation severity), edges are action transitions with HTTP status. Fully offline, zero external dependencies.
- **RequestRecorder + Journey codegen** — wrap any `HttpClient` with `RequestRecorder` to capture all HTTP traffic, then call `generate_journey_code()` to produce a runnable VenomQA Journey skeleton from real traffic.
- **`venomqa record` CLI command** — record HTTP traffic against a live API and generate a Journey file automatically.
- **`Violation.action_result`** — violations now carry the triggering `ActionResult` so reporters can display the full HTTP request/response payload.
- **ConsoleReporter HTTP payload** — when a violation occurs, the console reporter now prints the full HTTP request/response that triggered it.
- **Hypergraph system** — multi-dimensional state indexing with 6 built-in dimensions (auth status, user role, entity status, count class, usage class, plan type). Opt in with `Agent(hypergraph=True)`.
- **DimensionNoveltyStrategy** — exploration strategy that prioritises state/action pairs closest to unexplored dimension combinations.
- **DimensionCoverage + DimensionCoverageReporter** — per-dimension coverage metrics and tabular reporter.
- **Constraints** — `AnonHasNoRole`, `AuthHasRole`, `FreeCannotExceedUsage`, `LambdaConstraint` for encoding business rules as graph constraints.
- **`venomqa explore --strategy coverage|weighted|dimension`** — all five exploration strategies now accessible from the CLI.

### Fixed

- **PostgresAdapter now uses psycopg (v3)** instead of psycopg2. The dependency (`psycopg[binary]>=3.1.0`) and the import now match.
- **`precondition_has_context` now enforces context checks** — the Agent passes live context when filtering valid actions, so preconditions created with `precondition_has_context("key")` correctly gate action selection.

### Improved

- `Action.can_execute_with_context(state, context)` — new method that evaluates context-aware preconditions against the live Context.
- `Graph.get_valid_actions(state, context=None)` — accepts optional context for context-aware filtering.
- Combined mock adapter integration test (`tests/v1/test_adapters_integration.py`).

## [0.2.0] - 2026-02-15

### Added

- **State Graph Testing** - Model apps as state machines, explore all paths automatically
- **Invariant System** - Define rules that must always hold true
- **Journey Validation** - `journey.validate()` catches structural issues before runtime
- **Enhanced Error Messages** - Request/response details shown on failure
- **Preflight Smoke Tests** - `venomqa smoke-test` for quick API health checks
- **Demo Command** - `venomqa demo --explain` for instant experience
- **Doctor Command** - `venomqa doctor` for system diagnostics
- **Watch Mode** - Auto-rerun tests on file changes
- **Load Testing** - Built-in load testing with `venomqa load`
- **Security Scanning** - OWASP-style security tests
- **GraphQL Support** - Full GraphQL client and test generation
- **Multiple Reporters** - HTML, JSON, JUnit, Markdown, Slack, Discord, SARIF
- **Combinatorial Testing** - Generate test combinations from parameters

### Improved

- StateManager warnings when checkpoint/branch used without database
- Better import handling - no more sys.path hacks in generated code
- Comprehensive test suite (2400+ tests)

### Fixed

- Journey discovery now unified across CLI and plugins
- Checkpoint validation in branch structures

## [0.1.0] - 2024-01-15

### Added

- Core journey DSL with Journey, Step, Checkpoint, Branch, and Path models
- JourneyRunner for executing journeys with branching and rollback
- HTTP Client with retry logic and request history tracking
- AsyncClient for async HTTP operations
- ExecutionContext for sharing state between steps
- PostgreSQL state manager with SAVEPOINT support
- Docker Compose infrastructure manager
- Multiple reporter formats:
  - MarkdownReporter for human-readable reports
  - JSONReporter for structured output
  - JUnitReporter for CI/CD integration
- CLI commands:
  - `venomqa run` - Execute journeys
  - `venomqa list` - List available journeys
  - `venomqa report` - Generate reports
- Configuration via YAML file and environment variables
- Automatic issue capture with suggestions
- Parallel path execution support
- Request/response logging

### Documentation

- API reference documentation
- CLI usage guide
- Journey writing guide
- Database backend configuration
- Advanced usage patterns
- Real-world examples

### Dependencies

- httpx>=0.25.0 for HTTP client
- pydantic>=2.0.0 for data validation
- pydantic-settings>=2.0.0 for configuration
- click>=8.0.0 for CLI
- rich>=13.0.0 for output formatting
- pyyaml>=6.0 for configuration
- psycopg[binary]>=3.1.0 for PostgreSQL

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 0.4.3 | 2026-02-17 | src/ layout, scaffold openapi, multi-role clients |
| 0.4.2 | 2026-02-17 | Progress feedback, PostgresAdapter+BFS fix |
| 0.4.1 | 2026-02-17 | Runtime warnings, string preconditions |
| 0.4.0 | 2026-02-17 | with_headers, World setup, coverage_target |
| 0.3.0 | 2026-02-17 | MockHTTPServer, HTMLTraceReporter, hypergraph |
| 0.2.0 | 2026-02-15 | State graph testing, invariants, journey validation |
| 0.1.0 | 2024-01-15 | Initial release |

---

## Future Roadmap

### Planned for 0.2.0

- MySQL state backend support
- SQLite state backend for local testing
- WebSocket client for real-time testing
- Improved parallel execution with process pools
- Watch mode for re-running on file changes

### Planned for 0.3.0

- OpenAPI spec journey generation
- Hypothesis integration for property-based testing
- Failure clustering and analysis
- Distributed execution support

### Planned for 1.0.0

- Stable API guarantee
- Complete documentation
- Full test coverage
- Performance benchmarks
