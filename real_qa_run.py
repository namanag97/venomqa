"""
Real QA run against https://jsonplaceholder.typicode.com

Exercises every new feature:
  - ConsoleReporter (violation with HTTP payload)
  - HTMLTraceReporter (saved to /tmp/real_trace.html)
  - RequestRecorder + generate_journey_code
  - Agent(hypergraph=True) + DimensionCoverageReporter
  - DimensionNoveltyStrategy
"""

from __future__ import annotations

import time
import httpx
from pathlib import Path

from venomqa.v1 import (
    Agent, BFS, World,
    Action, ActionResult, HTTPRequest, HTTPResponse,
    Invariant, Severity,
    ConsoleReporter, HTMLTraceReporter,
    DimensionCoverageReporter, DimensionNoveltyStrategy,
    Hypergraph,
)
from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import Rollbackable, SystemCheckpoint
from venomqa.v1.recording import RequestRecorder, generate_journey_code

BASE_URL = "https://jsonplaceholder.typicode.com"
SEP = "=" * 65


# ─────────────────────────────────────────────────────────────────────────────
# Real HTTP adapter (stateless, rollback is a no-op)
# ─────────────────────────────────────────────────────────────────────────────

class RealHttp(Rollbackable):
    """Thin httpx wrapper that also implements Rollbackable."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self._client = httpx.Client(timeout=15.0)
        # Track last observed state for dimension extraction
        self._last_status: int = 0
        self._last_count: int = 0
        self._last_ok: bool = True

    def _req(self, method: str, path: str, **kwargs) -> ActionResult:
        url = f"{self.base_url}{path}"
        t0 = time.perf_counter()
        try:
            resp = self._client.request(method, url, **kwargs)
            ms = (time.perf_counter() - t0) * 1000
            body = resp.json() if "json" in resp.headers.get("content-type", "") else resp.text
            self._last_status = resp.status_code
            self._last_ok = resp.is_success
            if isinstance(body, list):
                self._last_count = len(body)
            return ActionResult.from_response(
                HTTPRequest(method, url, body=kwargs.get("json")),
                HTTPResponse(resp.status_code, dict(resp.headers), body),
                duration_ms=ms,
            )
        except Exception as e:
            return ActionResult.from_error(HTTPRequest(method, url), str(e))

    def get(self, path: str) -> ActionResult:   return self._req("GET", path)
    def post(self, path: str, json=None) -> ActionResult: return self._req("POST", path, json=json)
    def put(self, path: str, json=None) -> ActionResult:  return self._req("PUT", path, json=json)
    def delete(self, path: str) -> ActionResult: return self._req("DELETE", path)

    # Rollbackable – stateless API, nothing to save/restore
    def checkpoint(self, name: str) -> SystemCheckpoint: return {}
    def rollback(self, cp: SystemCheckpoint) -> None: pass

    def observe(self) -> Observation:
        # Inject dimension-friendly keys so hyperedge extraction works
        count_class = (
            "zero" if self._last_count == 0 else
            "one"  if self._last_count == 1 else
            "few"  if self._last_count <= 10 else "many"
        )
        return Observation(
            system="api",
            data={
                "status":       "active" if self._last_ok else "inactive",
                "count":        self._last_count,
                "last_status":  self._last_status,
                "authenticated": False,   # JSONPlaceholder has no auth
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# Actions
# ─────────────────────────────────────────────────────────────────────────────

def make_actions(api: RealHttp) -> list[Action]:
    return [
        Action("list_posts",    lambda a: a.get("/posts"),                    description="GET /posts"),
        Action("get_post_1",    lambda a: a.get("/posts/1"),                  description="GET /posts/1"),
        Action("get_post_999",  lambda a: a.get("/posts/999"),                description="GET /posts/999 (should 404)"),
        Action("create_post",   lambda a: a.post("/posts", json={"title": "VenomQA", "body": "test", "userId": 1}),
               description="POST /posts"),
        Action("update_post",   lambda a: a.put("/posts/1", json={"title": "Updated by VenomQA"}),
               description="PUT /posts/1"),
        Action("delete_post",   lambda a: a.delete("/posts/1"),               description="DELETE /posts/1"),
        Action("list_users",    lambda a: a.get("/users"),                    description="GET /users"),
        Action("get_user_1",    lambda a: a.get("/users/1"),                  description="GET /users/1"),
        Action("list_comments", lambda a: a.get("/posts/1/comments"),         description="GET /posts/1/comments"),
        Action("list_todos",    lambda a: a.get("/todos?userId=1"),           description="GET /todos?userId=1"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Invariants
# ─────────────────────────────────────────────────────────────────────────────

def make_invariants(api: RealHttp) -> list[Invariant]:

    def posts_not_empty(world):
        r = api.get("/posts")
        return isinstance(r.response.body, list) and len(r.response.body) > 0

    def post_has_required_fields(world):
        r = api.get("/posts/1")
        if not r.response or not r.response.ok:
            return True  # skip if endpoint down
        body = r.response.body
        if not isinstance(body, dict):
            return False
        return all(k in body for k in ("id", "title", "body", "userId"))

    def users_not_empty(world):
        r = api.get("/users")
        return isinstance(r.response.body, list) and len(r.response.body) > 0

    # Deliberately-broken invariant so we get a rich violation output
    def post_999_must_exist(world):
        """This WILL fail — 404 is returned for posts/999."""
        r = api.get("/posts/999")
        return r.response is not None and r.response.status_code == 200

    return [
        Invariant("posts_not_empty",        posts_not_empty,        severity=Severity.HIGH,
                  message="GET /posts must return a non-empty list"),
        Invariant("post_has_required_fields", post_has_required_fields, severity=Severity.CRITICAL,
                  message="Post must have id, title, body, userId"),
        Invariant("users_not_empty",        users_not_empty,        severity=Severity.MEDIUM,
                  message="GET /users must return a non-empty list"),
        Invariant("post_999_must_exist",    post_999_must_exist,    severity=Severity.HIGH,
                  message="GET /posts/999 should return 200 (intentional failure)"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(SEP)
    print("  VENOMQA – REAL QA RUN")
    print(f"  Target: {BASE_URL}")
    print(SEP)

    api = RealHttp(BASE_URL)
    actions = make_actions(api)
    invariants = make_invariants(api)

    # ── Build the Hypergraph manually so DimensionNoveltyStrategy can use it
    hg = Hypergraph()
    strategy = DimensionNoveltyStrategy(hypergraph=hg)

    world = World(api=api, systems={"api": api})

    # ── SECTION 1: Exploration with DimensionNoveltyStrategy + hypergraph=True
    print(f"\n{'─'*65}")
    print("  SECTION 1 — Exploration (DimensionNoveltyStrategy, hypergraph=True)")
    print(f"{'─'*65}\n")

    agent = Agent(
        world=world,
        actions=actions,
        invariants=invariants,
        strategy=strategy,
        max_steps=15,
        hypergraph=True,
    )

    # Wire the agent's internal hypergraph into the strategy after construction
    # (so strategy uses the same instance the agent populates)
    agent._hypergraph = hg
    strategy._hypergraph = hg

    result = agent.explore()

    print(f"  States visited     : {result.states_visited}")
    print(f"  Transitions taken  : {result.transitions_taken}")
    print(f"  Coverage           : {result.coverage_percent:.1f}%")
    print(f"  Duration           : {result.duration_ms:.0f} ms")
    print(f"  Violations found   : {len(result.violations)}")

    # ── SECTION 2: ConsoleReporter (shows HTTP payload on violations)
    print(f"\n{'─'*65}")
    print("  SECTION 2 — ConsoleReporter (HTTP payload on violations)")
    print(f"{'─'*65}\n")
    ConsoleReporter().report(result)

    # ── SECTION 3: HTMLTraceReporter
    print(f"\n{'─'*65}")
    print("  SECTION 3 — HTMLTraceReporter → /tmp/real_trace.html")
    print(f"{'─'*65}\n")
    html = HTMLTraceReporter().report(result)
    Path("/tmp/real_trace.html").write_text(html)
    print(f"  Written {len(html):,} bytes")
    # Sanity checks
    assert '"nodes"' in html
    assert '"links"' in html
    node_count = html.count('"is_initial"')
    print(f"  Nodes embedded: {node_count}")
    print(f"  Violations in HTML: {'post_999_must_exist' in html}")

    # ── SECTION 4: DimensionCoverage + DimensionCoverageReporter
    print(f"\n{'─'*65}")
    print("  SECTION 4 — Dimension Coverage Report")
    print(f"{'─'*65}\n")
    cov = result.dimension_coverage
    if cov:
        DimensionCoverageReporter().report(cov)
        print("\n  — Markdown table —")
        print(DimensionCoverageReporter(color=False).report_markdown(cov))
        print(f"  Unexplored combos (top-2 dims): {cov.unexplored_combos}")
    else:
        print("  (no dimension_coverage — hypergraph may not have detected dimensions)")
        print(f"  Hypergraph node count: {hg.node_count}")
        print(f"  Dimensions seen: {hg.all_dimensions()}")
        raw_cov = __import__('venomqa.v1.core.coverage', fromlist=['DimensionCoverage']).DimensionCoverage.from_hypergraph(hg)
        DimensionCoverageReporter().report(raw_cov)

    # ── SECTION 5: RequestRecorder + Journey codegen (live traffic)
    print(f"\n{'─'*65}")
    print("  SECTION 5 — RequestRecorder + Journey codegen (live HTTP)")
    print(f"{'─'*65}\n")

    recorder = RequestRecorder(api)
    # Replay a mini sequence through the recorder
    recorder.get("/posts/1")
    recorder.get("/users/1")
    recorder.post("/posts", json={"title": "Recorded", "body": "...", "userId": 2})
    recorder.delete("/posts/1")

    print(f"  Captured {len(recorder.captured)} requests:")
    for r in recorder.captured:
        print(f"    {r.method:6} {r.url}  →  {r.status_code}  ({r.duration_ms:.0f} ms)")

    code = generate_journey_code(recorder.captured, journey_name="jsonplaceholder_recorded", base_url=BASE_URL)
    print(f"\n  Generated {len(code.splitlines())} lines of Journey code")
    print("\n  ── Generated Journey skeleton ──────────────────────────")
    print(code)

    # ── SECTION 6: Hypergraph dimension query
    print(f"{'─'*65}")
    print("  SECTION 6 — Hypergraph dimension queries")
    print(f"{'─'*65}\n")
    print(f"  Total nodes registered: {hg.node_count}")
    print(f"  Dimensions detected   : {sorted(hg.all_dimensions())}")
    for dim in sorted(hg.all_dimensions()):
        vals = hg.all_values(dim)
        print(f"    {dim}: {[v.value if hasattr(v,'value') else v for v in vals]}")

    print(f"\n{'─'*65}")
    print("  ALL DONE")
    print(f"{'─'*65}")
    print(f"  HTML trace: /tmp/real_trace.html")
    print(f"  Open in a browser to see the interactive exploration graph.")


if __name__ == "__main__":
    main()
