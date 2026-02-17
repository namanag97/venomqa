"""
VenomQA – Real API QA

  Part 1: GitHub public API  (https://api.github.com)
  Part 2: Stripe mock server  (http://localhost:12111)

Exercises every new v1 feature:
  • ConsoleReporter with HTTP payload on violations
  • HTMLTraceReporter saved to /tmp/{github,stripe}_trace.html
  • RequestRecorder + generate_journey_code
  • Agent(hypergraph=True) + DimensionCoverageReporter
  • DimensionNoveltyStrategy

Run: python3 real_api_qa.py
"""

from __future__ import annotations

import sys
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

SEP  = "═" * 65
SEP2 = "─" * 65


# ─────────────────────────────────────────────────────────────────────────────
# Generic HTTP adapter (stateless, rollback no-op)
# ─────────────────────────────────────────────────────────────────────────────

class RestApi(Rollbackable):
    def __init__(self, base_url: str, headers: dict | None = None) -> None:
        self.base_url   = base_url
        self._client    = httpx.Client(timeout=15.0, headers=headers or {})
        self._last_status = 0
        self._last_count  = 0
        self._last_ok     = True
        self._resource    = "none"

    def _call(self, method: str, path: str, **kw) -> ActionResult:
        url = f"{self.base_url}{path}"
        t0  = time.perf_counter()
        try:
            r   = self._client.request(method, url, **kw)
            ms  = (time.perf_counter() - t0) * 1000
            ct  = r.headers.get("content-type", "")
            body = r.json() if "json" in ct else r.text
            self._last_status = r.status_code
            self._last_ok     = r.is_success
            if isinstance(body, list):
                self._last_count = len(body)
            elif isinstance(body, dict) and "data" in body and isinstance(body["data"], list):
                self._last_count = len(body["data"])
            else:
                self._last_count = 1 if body else 0
            return ActionResult.from_response(
                HTTPRequest(method, url, body=kw.get("json")),
                HTTPResponse(r.status_code, dict(r.headers), body),
                duration_ms=ms,
            )
        except Exception as e:
            return ActionResult.from_error(HTTPRequest(method, url), str(e))

    def get(self, path: str, **kw)         -> ActionResult: return self._call("GET",    path, **kw)
    def post(self, path: str, json=None)   -> ActionResult: return self._call("POST",   path, json=json)
    def put(self, path: str, json=None)    -> ActionResult: return self._call("PUT",    path, json=json)
    def delete(self, path: str)            -> ActionResult: return self._call("DELETE", path)

    # Rollbackable (stateless REST — nothing to save)
    def checkpoint(self, name: str) -> SystemCheckpoint: return {}
    def rollback(self, cp)          -> None: pass

    def observe(self) -> Observation:
        n = self._last_count
        count_cls = "zero" if n == 0 else "one" if n == 1 else "few" if n <= 10 else "many"
        return Observation(
            system="api",
            data={
                "status":        "active" if self._last_ok else "inactive",
                "count":         n,
                "authenticated": self._resource == "authed",
            },
        )


def run_section(title: str) -> None:
    print(f"\n{SEP2}\n  {title}\n{SEP2}\n")


def save_html(result, path: str) -> None:
    html = HTMLTraceReporter().report(result)
    Path(path).write_text(html)
    nodes = html.count('"is_initial"')
    has_viol = any(v.invariant_name in html for v in result.violations[:1])
    print(f"  Saved {len(html):,} bytes → {path}")
    print(f"  Nodes: {nodes}  |  Violations in HTML: {has_viol}")


def record_and_codegen(api: RestApi, calls: list[tuple], journey_name: str) -> None:
    rec = RequestRecorder(api)
    for method, path, *rest in calls:
        getattr(rec, method.lower())(path, **(rest[0] if rest else {}))
    print(f"  Captured {len(rec.captured)} requests:")
    for r in rec.captured:
        print(f"    {r.method:7} {r.url:60}  {r.status_code}  {r.duration_ms:.0f}ms")
    code = generate_journey_code(rec.captured, journey_name=journey_name, base_url=api.base_url)
    lines = code.splitlines()
    print(f"\n  Generated {len(lines)} lines. First 30:\n")
    print("\n".join(f"    {l}" for l in lines[:30]))
    if len(lines) > 30:
        print(f"    ... ({len(lines)-30} more lines)")


def dim_report(result, hg: Hypergraph) -> None:
    cov = result.dimension_coverage
    if not cov:
        from venomqa.v1.core.coverage import DimensionCoverage
        cov = DimensionCoverage.from_hypergraph(hg)
    DimensionCoverageReporter().report(cov)
    print(DimensionCoverageReporter(color=False).report_markdown(cov))


# ═════════════════════════════════════════════════════════════════════════════
# PART 1 — GitHub Public API
# ═════════════════════════════════════════════════════════════════════════════

def run_github():
    print(f"\n{SEP}")
    print("  PART 1 — GitHub Public API  (https://api.github.com)")
    print(SEP)

    REPO  = "anthropics/anthropic-sdk-python"
    USER  = "anthropics"
    api   = RestApi("https://api.github.com",
                    headers={"Accept": "application/vnd.github+json",
                             "User-Agent": "VenomQA-RealQA/1.0"})

    # ── Actions ──────────────────────────────────────────────────────────────
    actions = [
        Action("rate_limit",       lambda a: a.get("/rate_limit"),
               description="GET /rate_limit"),
        Action("get_repo",         lambda a: a.get(f"/repos/{REPO}"),
               description=f"GET /repos/{REPO}"),
        Action("list_issues",      lambda a: a.get(f"/repos/{REPO}/issues?state=open&per_page=5"),
               description="GET issues (open)"),
        Action("list_closed",      lambda a: a.get(f"/repos/{REPO}/issues?state=closed&per_page=5"),
               description="GET issues (closed)"),
        Action("get_user",         lambda a: a.get(f"/users/{USER}"),
               description=f"GET /users/{USER}"),
        Action("list_contributors",lambda a: a.get(f"/repos/{REPO}/contributors?per_page=5"),
               description="GET contributors"),
        Action("list_tags",        lambda a: a.get(f"/repos/{REPO}/tags?per_page=5"),
               description="GET tags"),
        Action("get_nonexistent",  lambda a: a.get("/repos/doesnotexist999/nope"),
               description="GET non-existent repo (should 404)"),
    ]

    # ── Invariants ───────────────────────────────────────────────────────────
    def repo_exists(world):
        r = api.get(f"/repos/{REPO}")
        return r.response and r.response.ok and isinstance(r.response.body, dict)

    def repo_has_required_fields(world):
        r = api.get(f"/repos/{REPO}")
        if not (r.response and r.response.ok): return True
        body = r.response.body
        return all(k in body for k in ("id", "name", "full_name", "stargazers_count", "open_issues_count"))

    def rate_limit_not_exhausted(world):
        r = api.get("/rate_limit")
        if not (r.response and r.response.ok): return True
        remaining = r.response.body.get("rate", {}).get("remaining", 1)
        return remaining > 0

    def nonexistent_is_404(world):
        r = api.get("/repos/doesnotexist999/nope")
        return r.response is not None and r.response.status_code == 404

    # Intentional failure — assert nonexistent repo returns 200
    def nonexistent_should_be_200(world):
        r = api.get("/repos/doesnotexist999/nope")
        return r.response is not None and r.response.status_code == 200

    invariants = [
        Invariant("repo_exists",          repo_exists,          severity=Severity.CRITICAL,
                  message=f"{REPO} must be accessible"),
        Invariant("repo_has_fields",      repo_has_required_fields, severity=Severity.HIGH,
                  message="Repo must have id, name, full_name, stargazers_count, open_issues_count"),
        Invariant("rate_limit_ok",        rate_limit_not_exhausted, severity=Severity.MEDIUM,
                  message="Rate limit must not be exhausted"),
        Invariant("404_on_missing",       nonexistent_is_404,   severity=Severity.HIGH,
                  message="Non-existent repo must return 404"),
        Invariant("intentional_failure",  nonexistent_should_be_200, severity=Severity.HIGH,
                  message="INTENTIONAL: expects 200 on 404 — will fire violation"),
    ]

    # ── Explore ───────────────────────────────────────────────────────────────
    hg       = Hypergraph()
    strategy = DimensionNoveltyStrategy(hypergraph=hg)
    world    = World(api=api, systems={"api": api})

    agent = Agent(world=world, actions=actions, invariants=invariants,
                  strategy=strategy, max_steps=8, hypergraph=True)
    agent._hypergraph = hg
    strategy._hypergraph = hg

    result = agent.explore()

    print(f"  States: {result.states_visited}  |  Transitions: {result.transitions_taken}"
          f"  |  Coverage: {result.coverage_percent:.1f}%"
          f"  |  Duration: {result.duration_ms:.0f}ms"
          f"  |  Violations: {len(result.violations)}")

    # ── Console reporter ───────────────────────────────────────────────────────
    run_section("GitHub — ConsoleReporter (violations with HTTP payload)")
    ConsoleReporter().report(result)

    # ── HTML trace ─────────────────────────────────────────────────────────────
    run_section("GitHub — HTMLTraceReporter")
    save_html(result, "/tmp/github_trace.html")

    # ── Dimension coverage ────────────────────────────────────────────────────
    run_section("GitHub — Dimension Coverage")
    dim_report(result, hg)

    # ── Record + codegen ──────────────────────────────────────────────────────
    run_section("GitHub — RequestRecorder + Journey codegen")
    record_and_codegen(api, [
        ("GET",  f"/repos/{REPO}"),
        ("GET",  f"/repos/{REPO}/issues?state=open&per_page=3"),
        ("GET",  f"/users/{USER}"),
    ], journey_name="github_journey")

    return result


# ═════════════════════════════════════════════════════════════════════════════
# PART 2 — Stripe Mock  (http://localhost:12111)
# ═════════════════════════════════════════════════════════════════════════════

def run_stripe():
    print(f"\n{SEP}")
    print("  PART 2 — Stripe Mock  (http://localhost:12111)")
    print(SEP)

    STRIPE_KEY = "sk_test_123"
    api = RestApi("http://localhost:12111",
                  headers={"Authorization": f"Bearer {STRIPE_KEY}",
                           "Stripe-Version": "2020-08-27",
                           "Content-Type": "application/json"})

    # ── Actions ──────────────────────────────────────────────────────────────
    actions = [
        Action("list_customers",
               lambda a: a.get("/v1/customers"),
               description="GET /v1/customers"),
        Action("create_customer",
               lambda a: a.post("/v1/customers",
                                json={"email": "venomqa@test.com", "name": "VenomQA Test"}),
               description="POST /v1/customers"),
        Action("list_charges",
               lambda a: a.get("/v1/charges"),
               description="GET /v1/charges"),
        Action("list_products",
               lambda a: a.get("/v1/products"),
               description="GET /v1/products"),
        Action("list_invoices",
               lambda a: a.get("/v1/invoices"),
               description="GET /v1/invoices"),
        Action("list_subscriptions",
               lambda a: a.get("/v1/subscriptions"),
               description="GET /v1/subscriptions"),
        Action("list_payment_intents",
               lambda a: a.get("/v1/payment_intents"),
               description="GET /v1/payment_intents"),
        Action("create_charge_no_source",
               lambda a: a.post("/v1/charges",
                                json={"amount": 1000, "currency": "usd"}),
               description="POST /v1/charges without source (expect error)"),
    ]

    # ── Invariants ────────────────────────────────────────────────────────────
    def list_has_object_field(world):
        r = api.get("/v1/customers")
        return r.response and r.response.ok and \
               isinstance(r.response.body, dict) and r.response.body.get("object") == "list"

    def list_has_data_array(world):
        r = api.get("/v1/customers")
        if not (r.response and r.response.ok): return True
        return "data" in r.response.body and isinstance(r.response.body["data"], list)

    def create_customer_returns_201_or_200(world):
        r = api.post("/v1/customers", json={"email": "check@test.com"})
        return r.response and r.response.status_code in (200, 201)

    def charge_without_source_is_error(world):
        r = api.post("/v1/charges", json={"amount": 500, "currency": "usd"})
        # stripe-mock returns 402 or 400 when no source provided
        return r.response and not r.response.ok

    # Intentional violation: assert all list endpoints return 201 (wrong)
    def all_lists_return_201(world):
        r = api.get("/v1/charges")
        return r.response and r.response.status_code == 201

    invariants = [
        Invariant("list_object_field",       list_has_object_field,       severity=Severity.CRITICAL,
                  message="List responses must have object='list'"),
        Invariant("list_data_array",         list_has_data_array,         severity=Severity.HIGH,
                  message="List responses must have a data array"),
        Invariant("create_customer_ok",      create_customer_returns_201_or_200, severity=Severity.HIGH,
                  message="POST /v1/customers must succeed"),
        Invariant("charge_error_no_source",  charge_without_source_is_error, severity=Severity.MEDIUM,
                  message="Charge without source must fail"),
        Invariant("lists_return_201",        all_lists_return_201,        severity=Severity.HIGH,
                  message="INTENTIONAL: expects 201 on list — will fire violation"),
    ]

    # ── Explore ───────────────────────────────────────────────────────────────
    hg       = Hypergraph()
    strategy = DimensionNoveltyStrategy(hypergraph=hg)
    world    = World(api=api, systems={"api": api})

    agent = Agent(world=world, actions=actions, invariants=invariants,
                  strategy=strategy, max_steps=12, hypergraph=True)
    agent._hypergraph = hg
    strategy._hypergraph = hg

    result = agent.explore()

    print(f"  States: {result.states_visited}  |  Transitions: {result.transitions_taken}"
          f"  |  Coverage: {result.coverage_percent:.1f}%"
          f"  |  Duration: {result.duration_ms:.0f}ms"
          f"  |  Violations: {len(result.violations)}")

    # ── Console reporter ──────────────────────────────────────────────────────
    run_section("Stripe — ConsoleReporter")
    ConsoleReporter().report(result)

    # ── HTML trace ─────────────────────────────────────────────────────────────
    run_section("Stripe — HTMLTraceReporter")
    save_html(result, "/tmp/stripe_trace.html")

    # ── Dimension coverage ─────────────────────────────────────────────────────
    run_section("Stripe — Dimension Coverage")
    dim_report(result, hg)

    # ── Record + codegen ───────────────────────────────────────────────────────
    run_section("Stripe — RequestRecorder + Journey codegen")
    record_and_codegen(api, [
        ("GET",  "/v1/customers"),
        ("POST", "/v1/customers", {"json": {"email": "rec@test.com", "name": "Recorded"}}),
        ("GET",  "/v1/charges"),
        ("GET",  "/v1/products"),
    ], journey_name="stripe_journey")

    return result


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    github_result = run_github()
    stripe_result = run_stripe()

    print(f"\n{SEP}")
    print("  FINAL SUMMARY")
    print(SEP)
    for name, r in [("GitHub", github_result), ("Stripe", stripe_result)]:
        status = "PASS ✓" if r.success else f"FAIL ✗ ({len(r.violations)} violations)"
        print(f"  {name:8}  states={r.states_visited}  transitions={r.transitions_taken}"
              f"  coverage={r.coverage_percent:.0f}%  {status}")
    print(f"\n  HTML traces: /tmp/github_trace.html  /tmp/stripe_trace.html")
