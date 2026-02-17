#!/usr/bin/env python3
"""
VenomQA v1 Comprehensive Smoke Test
====================================
Exercises every major feature in one fully in-memory run:

  1. Mock adapters (Queue, Mail, Storage, Time) in a World
  2. Agent exploration with invariants — Violation.action_result populated
  3. ConsoleReporter output (shows HTTP payload on violations)
  4. HTMLTraceReporter — generate /tmp/trace.html, verify nodes/links
  5. RequestRecorder + generate_journey_code
  6. Hypergraph (Agent with hypergraph=True) — dimension extraction, DimensionCoverage
  7. DimensionCoverageReporter output
  8. DimensionNoveltyStrategy as exploration strategy
"""

import json as _json
import re as _re
import sys
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Helper: section banners
# ─────────────────────────────────────────────────────────────────────────────

def banner(title: str) -> None:
    line = "=" * 70
    print(f"\n{line}")
    print(f"  {title}")
    print(f"{line}\n")


def sub_banner(title: str) -> None:
    print(f"\n  --- {title} ---\n")


# ─────────────────────────────────────────────────────────────────────────────
# Import everything from v1
# ─────────────────────────────────────────────────────────────────────────────

banner("IMPORTING VenomQA v1")

from venomqa.v1 import (
    # Core
    State, Observation, Action, ActionResult, HTTPRequest, HTTPResponse,
    Invariant, Violation, Severity, InvariantTiming,
    # World
    World,
    # Agent
    Agent, BFS, DimensionNoveltyStrategy,
    # Hypergraph
    AuthStatus, UserRole, CountClass,
    Hyperedge, Hypergraph,
    DimensionCoverage, DimensionCoverageReporter,
    # Recording
    RequestRecorder, RecordedRequest, generate_journey_code,
    # Reporters
    ConsoleReporter, HTMLTraceReporter,
    # DSL
    Journey, Step,
)
from venomqa.v1.adapters import MockQueue, MockMail, MockStorage, MockTime

print("  All imports successful.")
print(f"  Python {sys.version.split()[0]}")


# ─────────────────────────────────────────────────────────────────────────────
# Shared mock HTTP client used throughout the test
# ─────────────────────────────────────────────────────────────────────────────

class MockHttpClient:
    """Fake HTTP client — returns realistic mocked responses, no real network."""

    def __init__(self, label: str = "default"):
        self.label = label
        self.call_log: list[tuple[str, str]] = []
        self._step = 0

    def _respond(self, method: str, path: str, body: dict, status: int = 200) -> ActionResult:
        self.call_log.append((method, path))
        req  = HTTPRequest(method=method, url=f"http://mock{path}", body=body)
        resp = HTTPResponse(status_code=status, body=body)
        return ActionResult.from_response(req, resp, duration_ms=1.5)

    def get(self,    path: str, **kw) -> ActionResult:
        self._step += 1
        return self._respond("GET",    path, {"path": path, "ok": True, "step": self._step})

    def post(self,   path: str, **kw) -> ActionResult:
        self._step += 1
        payload = kw.get("json", {})
        if "/queue" in path:
            return self._respond("POST", path, {"queued": True, "job_id": self._step}, 202)
        if "/upload" in path:
            return self._respond("POST", path, {"stored": True, "file_id": self._step}, 201)
        if "/email" in path:
            return self._respond("POST", path, {"sent": True, "email_id": self._step}, 200)
        if "/time" in path:
            return self._respond("POST", path, {"advanced": True}, 200)
        if "/auth/login" in path:
            return self._respond("POST", path, {"authenticated": True, "role": payload.get("role", "user")}, 200)
        if "/auth/logout" in path:
            return self._respond("POST", path, {"authenticated": False}, 200)
        return self._respond("POST",   path, {"created": True, "id": self._step}, 201)

    def delete(self, path: str, **kw) -> ActionResult:
        self._step += 1
        return self._respond("DELETE", path, {"deleted": True, "step": self._step}, 200)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — Mock adapters in a World
# ─────────────────────────────────────────────────────────────────────────────

banner("SECTION 1 — Mock Adapters in a World")

queue   = MockQueue(name="jobs")
mail    = MockMail()
storage = MockStorage(bucket="uploads")
clock   = MockTime()
clock.freeze(datetime(2026, 1, 15, 9, 0, 0))

print(f"  Queue  : MockQueue(name='jobs')         pending={queue.pending_count}")
print(f"  Mail   : MockMail()                     sent={mail.sent_count}")
print(f"  Storage: MockStorage(bucket='uploads')  files={storage.file_count}")
print(f"  Clock  : MockTime frozen at {clock.now.isoformat()}")

api1 = MockHttpClient(label="section1")
world1 = World(
    api=api1,
    systems={"queue": queue, "mail": mail, "storage": storage, "clock": clock},
)

state_before = world1.observe()
print(f"\n  world.observe() systems: {list(state_before.observations.keys())}")
for name, obs in state_before.observations.items():
    print(f"    [{obs.system}]  data={obs.data}")

sub_banner("Checkpoint / rollback test")
queue.push({"task": "initial_task"})
storage.put("seed.txt", b"hello")
mail.send("admin@example.com", "Boot", "World started")
clock.advance(hours=1)
cp_id = world1.checkpoint("after_setup")

queue.push({"task": "extra_task"})
storage.put("extra.txt", b"extra")
clock.advance(hours=5)
print(f"  Before rollback: queue pending={queue.pending_count}, storage files={storage.file_count}, clock={clock.now.isoformat()}")

world1.rollback(cp_id)
print(f"  After  rollback: queue pending={queue.pending_count}, storage files={storage.file_count}, clock={clock.now.isoformat()}")
assert queue.pending_count == 1,     "Queue should have 1 message after rollback"
assert storage.file_count  == 1,     "Storage should have 1 file after rollback"
assert clock.now.hour      == 10,    "Clock should be at 10:00 after rollback"
print("  Checkpoint/rollback PASSED.")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — Agent exploration with a failing invariant
# ─────────────────────────────────────────────────────────────────────────────

banner("SECTION 2 — Agent Exploration with Failing Invariant")

# Fresh adapters for exploration
q2   = MockQueue(name="jobs")
m2   = MockMail()
s2   = MockStorage(bucket="uploads")
t2   = MockTime()
t2.freeze(datetime(2026, 1, 15, 9, 0, 0))

# This client side-effects the adapters AND returns useful response bodies
class SideEffectClient(MockHttpClient):
    def __init__(self, q, m, s, t):
        super().__init__(label="exploration")
        self._q = q
        self._m = m
        self._s = s
        self._t = t

    def post(self, path: str, **kw) -> ActionResult:
        self._step += 1
        payload = kw.get("json", {})
        if "/queue" in path:
            self._q.push({"task": "job", "id": self._step})
            depth = self._q.pending_count
            return self._respond("POST", path, {
                "queued": True, "job_id": self._step,
                "queue_depth": depth, "payload": payload,
            }, 202)
        if "/upload" in path:
            fname = f"reports/file_{self._step}.txt"
            self._s.put(fname, f"content_{self._step}".encode())
            return self._respond("POST", path, {
                "stored": True, "file_id": self._step, "filename": fname,
            }, 201)
        if "/email" in path:
            self._m.send("user@example.com", f"Notif-{self._step}", "body")
            return self._respond("POST", path, {
                "sent": True, "email_id": self._step, "recipient": "user@example.com",
            }, 200)
        if "/time" in path:
            self._t.advance(hours=1)
            return self._respond("POST", path, {
                "advanced": True, "now": self._t.now.isoformat(),
            }, 200)
        return self._respond("POST", path, {"id": self._step, "payload": payload}, 201)


api2   = SideEffectClient(q2, m2, s2, t2)
world2 = World(api=api2, systems={"queue": q2, "mail": m2, "storage": s2, "clock": t2})

# ── Invariants ───────────────────────────────────────────────────────────────
#
# FAILING invariant: The last action result must never be a /queue response
# with job_id >= 3.  This is a contrived rule that will trigger as soon as
# the agent has pushed a 3rd job (which happens during exploration because
# the agent explores each action, and queue_push runs multiple times from
# different states as the graph grows).
#
# We check it via the action_result attached to the violation so we can see
# the HTTP payload rendered by ConsoleReporter.

_violation_action_results: list[ActionResult] = []

def failing_check(w: World) -> bool:
    # Check queue depth: fail when there are pending jobs in the queue
    # (after rollback the queue resets, but during a single step it can have items)
    obs = w.systems["queue"].observe()
    pending = obs.data["pending"]
    # This will fail as soon as ANY job is in the queue (pending > 0)
    # making it reliably trigger on the first push_job action.
    return pending == 0

failing_invariant = Invariant(
    name="queue_must_be_empty",
    check=failing_check,
    message="Queue must always be empty (strict invariant) — pending jobs found",
    severity=Severity.HIGH,
)

# PASSING invariant
def passing_check(w: World) -> bool:
    obs = w.systems["storage"].observe()
    files = obs.data.get("files", [])
    # All files must start with 'reports/' or be named 'seed*'
    return all(f.startswith("reports/") or f.startswith("seed") for f in files)

passing_invariant = Invariant(
    name="storage_prefix_valid",
    check=passing_check,
    message="All storage files must be under reports/ or seed*",
    severity=Severity.MEDIUM,
)

# ── Actions ───────────────────────────────────────────────────────────────────

def act_push_job(api):
    return api.post("/queue/push", json={"task": "process", "priority": "normal"})

def act_send_email(api):
    return api.post("/email/send", json={"to": "user@example.com", "subject": "Hello"})

def act_upload_file(api):
    return api.post("/upload", json={"filename": "report.txt", "size": 1024})

def act_advance_time(api):
    return api.post("/time/advance", json={"hours": 1})

def act_get_status(api):
    return api.get("/status")

actions2 = [
    Action(name="push_job",      execute=act_push_job),
    Action(name="send_email",    execute=act_send_email),
    Action(name="upload_file",   execute=act_upload_file),
    Action(name="advance_time",  execute=act_advance_time),
    Action(name="get_status",    execute=act_get_status),
]

print(f"  Actions: {[a.name for a in actions2]}")
print(f"  Invariants:")
print(f"    - {failing_invariant.name}  [EXPECTED TO FAIL]")
print(f"    - {passing_invariant.name}  [expected to pass]")

agent2 = Agent(
    world=world2,
    actions=actions2,
    invariants=[failing_invariant, passing_invariant],
    strategy=BFS(),
    max_steps=20,
)

result2 = agent2.explore()

print(f"\n  Steps taken:       {agent2.step_count}")
print(f"  States visited:    {result2.states_visited}")
print(f"  Transitions taken: {result2.transitions_taken}")
print(f"  Violations:        {len(result2.violations)}")

sub_banner("Verifying Violation.action_result is populated")
for i, v in enumerate(result2.violations):
    print(f"  Violation #{i+1}: [{v.severity.value.upper()}] {v.invariant_name}")
    print(f"    message:       {v.message!r}")
    print(f"    action:        {v.action.name if v.action else 'None'}")
    has_ar = v.action_result is not None
    print(f"    action_result: {'present' if has_ar else 'MISSING'}")
    if has_ar:
        ar = v.action_result
        print(f"      request:    {ar.request.method} {ar.request.url}")
        if ar.request.body:
            print(f"      req body:   {ar.request.body}")
        if ar.response:
            print(f"      response:   HTTP {ar.response.status_code}")
            if ar.response.body:
                print(f"      res body:   {ar.response.body}")
    if v.reproduction_path:
        path_str = " -> ".join(t.action_name for t in v.reproduction_path)
        print(f"    repro path:    {path_str}")
    print()

violations_with_ar = [v for v in result2.violations if v.action_result is not None]
print(f"  Violations with action_result populated: {len(violations_with_ar)} / {len(result2.violations)}")
assert len(result2.violations) > 0, "Expected at least one violation (queue_must_be_empty should fail)"
assert len(violations_with_ar) > 0, "Expected at least one violation with action_result"
print("  ASSERTION PASSED: violations found and action_result populated.")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — ConsoleReporter (shows HTTP payload on violations)
# ─────────────────────────────────────────────────────────────────────────────

banner("SECTION 3 — ConsoleReporter Output (with HTTP payloads)")

print("  [ConsoleReporter output follows]\n")
console = ConsoleReporter(color=False)   # no ANSI for clean capture
console.report(result2)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — HTMLTraceReporter → /tmp/trace.html
# ─────────────────────────────────────────────────────────────────────────────

banner("SECTION 4 — HTMLTraceReporter → /tmp/trace.html")

html_reporter = HTMLTraceReporter()
html_content  = html_reporter.report(result2)

trace_path = Path("/tmp/trace.html")
trace_path.write_text(html_content, encoding="utf-8")
file_size = trace_path.stat().st_size

print(f"  Written to: {trace_path}  ({file_size:,} bytes)")
assert file_size > 1000, f"HTML file too small: {file_size} bytes"

# Extract and verify embedded DATA JSON
data_match = _re.search(r'const DATA = (\{.*?\});', html_content, _re.DOTALL)
assert data_match, "Could not find DATA JSON in HTML"
graph_data = _json.loads(data_match.group(1))

node_count = len(graph_data.get("nodes", []))
link_count = len(graph_data.get("links", []))

print(f"  Nodes in graph:   {node_count}")
print(f"  Links in graph:   {link_count}")
print(f"  Summary embedded: {graph_data.get('summary', {})}")

violated_nodes = [n for n in graph_data["nodes"] if n.get("has_violation")]
print(f"  Nodes with violations flagged: {len(violated_nodes)}")

print("\n  HTML structure checks:")
for keyword in [
    "<!DOCTYPE html>", "d3.forceSimulation", "VenomQA Exploration Trace",
    "violation-card", "stat-grid", "queue_must_be_empty",
]:
    present = keyword in html_content
    status  = "FOUND" if present else "MISSING"
    mark    = "" if present else " <-- PROBLEM"
    print(f"    [{status}]  {keyword!r}{mark}")
    assert present, f"Expected {keyword!r} in HTML output"

assert node_count > 0, "HTML trace must have at least one node"
assert link_count > 0, "HTML trace must have at least one link"
assert len(violated_nodes) > 0, "HTML trace must flag violation nodes"
print("\n  HTMLTraceReporter PASSED.")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — RequestRecorder + generate_journey_code
# ─────────────────────────────────────────────────────────────────────────────

banner("SECTION 5 — RequestRecorder + generate_journey_code")

api_raw  = MockHttpClient(label="recorder")
recorder = RequestRecorder(api_raw)

sub_banner("Recording a sequence of requests via recorder")
recorder.post("/users",    json={"name": "Alice", "role": "admin"})
recorder.post("/users",    json={"name": "Bob",   "role": "user"})
recorder.get("/users")
recorder.post("/orders",   json={"user_id": 1, "items": ["widget"]})
recorder.get("/orders/1")
recorder.delete("/orders/1")

print(f"  Captured {len(recorder)} requests:")
for r in recorder.captured:
    print(f"    {r.method:6}  {r.url:35}  HTTP {r.status_code}  ({r.duration_ms:.2f}ms)")

sub_banner("Generated Journey code")
journey_code = generate_journey_code(
    recorder.captured,
    journey_name="user_order_flow",
    base_url="http://mock",
)
print(journey_code)

# Verify it's syntactically valid Python
try:
    compile(journey_code, "<generated>", "exec")
    print("  [COMPILE OK] Valid Python syntax.")
except SyntaxError as exc:
    print(f"  [COMPILE FAIL] {exc}")
    raise

# Verify key content that we know will be present based on generated names
assert "from venomqa.v1 import"          in journey_code, "Import missing"
assert "journey = Journey("              in journey_code, "Journey object missing"
assert "post_http_mock_users"            in journey_code, "POST /users action missing"
assert "get_http_mock_users"             in journey_code, "GET /users action missing"
assert "delete_http_mock_orders"         in journey_code, "DELETE /orders action missing"
assert 'expected_status=[201]'           in journey_code, "expected_status missing"
print("  Content assertions PASSED.")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — Hypergraph (Agent with hypergraph=True) + DimensionCoverage
# ─────────────────────────────────────────────────────────────────────────────

banner("SECTION 6 — Hypergraph Mode + Dimension Extraction")

# Adapters that return dimension-rich observation data so Hyperedge.from_state()
# can infer AuthStatus, UserRole, and CountClass dimensions.

class DimQueue(MockQueue):
    """Exposes 'count' so CountClass dimension is inferred."""
    def observe(self) -> Observation:
        obs = super().observe()
        return Observation(
            system=obs.system,
            data={**obs.data, "count": obs.data["total"]},
        )


class DimMail(MockMail):
    """Exposes 'authenticated' and 'role' so AuthStatus/UserRole are inferred."""
    def __init__(self):
        super().__init__()
        self.authenticated = False
        self.role = "none"

    def observe(self) -> Observation:
        obs = super().observe()
        return Observation(
            system=obs.system,
            data={**obs.data, "authenticated": self.authenticated, "role": self.role},
        )


hq      = DimQueue(name="hg_jobs")
hm      = DimMail()
hs      = MockStorage(bucket="hg")
hclock  = MockTime()
hclock.freeze(datetime(2026, 1, 15, 9, 0, 0))
h_api   = MockHttpClient(label="hypergraph")
h_world = World(api=h_api, systems={"queue": hq, "mail": hm, "storage": hs})


def h_login_admin(api, context):
    hm.authenticated = True
    hm.role = "admin"
    context.set("role", "admin")
    return api.post("/auth/login", json={"role": "admin"})

def h_login_user(api, context):
    hm.authenticated = True
    hm.role = "user"
    context.set("role", "user")
    return api.post("/auth/login", json={"role": "user"})

def h_logout(api, context):
    hm.authenticated = False
    hm.role = "none"
    context.delete("role")
    return api.post("/auth/logout")

def h_push_job(api):
    hq.push({"task": "hg_job"})
    return api.post("/queue/push", json={"task": "hg_job"})

def h_get_status(api):
    return api.get("/status")

h_actions = [
    Action(name="login_admin",  execute=h_login_admin),
    Action(name="login_user",   execute=h_login_user),
    Action(name="logout",       execute=h_logout),
    Action(name="push_job",     execute=h_push_job),
    Action(name="get_status",   execute=h_get_status),
]

print(f"  Actions: {[a.name for a in h_actions]}")

# Create agent with hypergraph=True first (to get the Hypergraph instance),
# then wire the DimensionNoveltyStrategy to it.
h_agent = Agent(
    world=h_world,
    actions=h_actions,
    strategy=BFS(),         # placeholder; will replace below
    max_steps=25,
    hypergraph=True,
)
# Wire hypergraph into the DimensionNoveltyStrategy
h_agent.strategy = DimensionNoveltyStrategy(hypergraph=h_agent.hypergraph)
print(f"  Strategy: DimensionNoveltyStrategy (wired to agent's hypergraph)")

h_result = h_agent.explore()

print(f"\n  Steps:          {h_agent.step_count}")
print(f"  States visited: {h_result.states_visited}")
print(f"  Transitions:    {h_result.transitions_taken}")

sub_banner("Hypergraph nodes & inferred dimensions")
hg = h_agent.hypergraph
assert hg is not None, "Hypergraph must be set when hypergraph=True"
print(f"  Hypergraph node count: {hg.node_count}")
print(f"  Dimensions found:      {sorted(hg.all_dimensions())}")
for dim in sorted(hg.all_dimensions()):
    values   = hg.all_values(dim)
    vals_str = ", ".join(sorted(str(v) for v in values))
    count    = len(values)
    print(f"    {dim:<18}  {count} value(s):  [{vals_str}]")

# Query hypergraph
auth_states = hg.query_by_dimension(auth=AuthStatus.AUTH) if "auth" in hg.all_dimensions() else []
anon_states = hg.query_by_dimension(auth=AuthStatus.ANON) if "auth" in hg.all_dimensions() else []
print(f"\n  Authenticated states: {len(auth_states)}")
print(f"  Anonymous states:     {len(anon_states)}")

sub_banner("DimensionCoverage.from_hypergraph()")
cov = DimensionCoverage.from_hypergraph(hg)
print(f"  total_states:      {cov.total_states}")
print(f"  unexplored_combos: {cov.unexplored_combos}")
print(f"  axes:              {list(cov.axes.keys())}")

assert h_result.dimension_coverage is not None, "dimension_coverage must be attached to ExplorationResult"
print(f"\n  result.dimension_coverage attached: True")

cov_summary = cov.summary()
print(f"\n  Coverage summary (JSON):\n{_json.dumps(cov_summary, indent=4, default=str)}")

assert hg.node_count > 0, "Hypergraph must have at least one node"
print("\n  Hypergraph mode PASSED.")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — DimensionCoverageReporter output
# ─────────────────────────────────────────────────────────────────────────────

banner("SECTION 7 — DimensionCoverageReporter Output")

print("  [DimensionCoverageReporter.report() output follows]\n")
dim_reporter = DimensionCoverageReporter(color=False)
dim_reporter.report(cov)

sub_banner("DimensionCoverageReporter.report_markdown()")
md = dim_reporter.report_markdown(cov)
print(md)

assert "## Dimension Coverage Report" in md, "Markdown header missing"
assert "| Dimension |"               in md, "Markdown table header missing"
print("  Markdown assertions PASSED.")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — DimensionNoveltyStrategy standalone run
# ─────────────────────────────────────────────────────────────────────────────

banner("SECTION 8 — DimensionNoveltyStrategy (standalone dedicated run)")

nq     = DimQueue(name="nov_jobs")
nm     = DimMail()
n_api  = MockHttpClient(label="novelty")
n_world = World(api=n_api, systems={"queue": nq, "mail": nm})

def nv_login_admin(api, context):
    nm.authenticated = True
    nm.role = "admin"
    return api.post("/auth/login", json={"role": "admin"})

def nv_login_user(api, context):
    nm.authenticated = True
    nm.role = "user"
    return api.post("/auth/login", json={"role": "user"})

def nv_logout(api, context):
    nm.authenticated = False
    nm.role = "none"
    return api.post("/auth/logout")

def nv_enqueue(api):
    nq.push({"job": "novelty"})
    return api.post("/queue/push", json={"job": "novelty"})

def nv_status(api):
    return api.get("/status")

n_actions = [
    Action(name="nv_login_admin", execute=nv_login_admin),
    Action(name="nv_login_user",  execute=nv_login_user),
    Action(name="nv_logout",      execute=nv_logout),
    Action(name="nv_enqueue",     execute=nv_enqueue),
    Action(name="nv_status",      execute=nv_status),
]

n_agent = Agent(
    world=n_world,
    actions=n_actions,
    strategy=BFS(),       # placeholder
    max_steps=20,
    hypergraph=True,
)
# Wire DimensionNoveltyStrategy after construction so it shares the hypergraph
n_agent.strategy = DimensionNoveltyStrategy(hypergraph=n_agent.hypergraph)

n_result = n_agent.explore()

print(f"  Strategy class:   {type(n_agent.strategy).__name__}")
print(f"  Steps taken:      {n_agent.step_count}")
print(f"  States visited:   {n_result.states_visited}")
print(f"  Transitions:      {n_result.transitions_taken}")
print(f"  Violations:       {len(n_result.violations)}")

n_hg  = n_agent.hypergraph
n_cov = DimensionCoverage.from_hypergraph(n_hg)
print(f"\n  Dimensions seen:  {sorted(n_hg.all_dimensions())}")
print(f"\n  DimensionCoverageReporter output for this run:\n")
dim_reporter.report(n_cov)

assert n_result.transitions_taken > 0, "DimensionNoveltyStrategy must produce transitions"
assert n_hg.node_count             > 0, "Hypergraph must have nodes"
print("  DimensionNoveltyStrategy PASSED.")


# ─────────────────────────────────────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

banner("FINAL SUMMARY")

_violations_with_ar = [v for v in result2.violations if v.action_result is not None]

checks = [
    ("MockQueue checkpoint/rollback",                   queue.pending_count == 1),
    ("MockStorage checkpoint/rollback",                 storage.file_count == 1),
    ("MockTime checkpoint/rollback",                    clock.now.hour == 10),
    ("MockMail checkpoint/rollback",                    mail.sent_count == 1),
    ("Agent exploration runs (states>1)",               result2.states_visited > 1),
    ("Failing invariant triggered",                     len(result2.violations) > 0),
    ("Violation.action_result populated",               len(_violations_with_ar) > 0),
    ("ConsoleReporter ran without error",               True),
    ("HTMLTraceReporter → /tmp/trace.html non-empty",   file_size > 1000),
    ("HTML has nodes",                                  node_count > 0),
    ("HTML has links",                                  link_count > 0),
    ("HTML flags violation nodes",                      len(violated_nodes) > 0),
    ("RequestRecorder captured 6 requests",             len(recorder) == 6),
    ("generate_journey_code produces valid Python",     True),
    ("Agent hypergraph=True (node_count>0)",            hg.node_count > 0),
    ("Dimensions inferred from observations",           len(hg.all_dimensions()) > 0),
    ("DimensionCoverage.from_hypergraph() works",       cov.total_states > 0),
    ("result.dimension_coverage attached",              h_result.dimension_coverage is not None),
    ("DimensionCoverageReporter text output",           True),
    ("DimensionCoverageReporter markdown output",       len(md) > 50),
    ("DimensionNoveltyStrategy transitions>0",          n_result.transitions_taken > 0),
]

all_passed = True
for label, status in checks:
    icon = "PASS" if status else "FAIL"
    print(f"  [{icon}]  {label}")
    if not status:
        all_passed = False

print()
if all_passed:
    print("  ALL CHECKS PASSED — VenomQA v1 smoke test complete.")
else:
    print("  SOME CHECKS FAILED — see items marked [FAIL] above.")
    sys.exit(1)

print(f"\n  HTML trace saved to: {trace_path}  ({file_size:,} bytes)")
