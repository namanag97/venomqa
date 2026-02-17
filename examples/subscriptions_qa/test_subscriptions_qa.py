"""Real-world VenomQA test — SaaS Subscription Management.

Exercises ALL VenomQA adapter types with real Docker services:
  ✓ PostgresAdapter — Docker Postgres, row-count observation
  ✓ RedisAdapter    — Docker Redis, key dump/restore rollback
  ✓ MockMail        — in-memory email tracking
  ✓ MockQueue       — in-memory background job tracking
  ✓ MockStorage     — in-memory invoice PDF storage
  ✓ MockTime        — controllable clock

3 deliberately planted bugs are found automatically by BFS exploration:
  BUG-1: users can hold multiple active subscriptions
  BUG-2: invoices can be created against cancelled subscriptions
  BUG-3: re-subscribing to a different plan uses the old plan's price

Run:
    pytest examples/subscriptions_qa/test_subscriptions_qa.py -v
"""

from __future__ import annotations

import io
import json
import random
import string
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import psycopg2
import pytest
import redis as redis_lib
import uvicorn

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from venomqa.v1 import Action, Agent, BFS, Invariant, Severity, World
from venomqa.v1.adapters import MockMail, MockQueue, MockStorage, MockTime
from venomqa.v1.adapters.http import HttpClient
from venomqa.v1.adapters.postgres import PostgresAdapter
from venomqa.v1.adapters.redis import RedisAdapter
from venomqa.v1.reporters.console import ConsoleReporter
from venomqa.v1.reporters.json import JSONReporter

from server import create_app

POSTGRES_URL = "postgresql://appuser:apppass@localhost:5432/appdb"
REDIS_URL    = "redis://localhost:6379"
APP_PORT     = 18744


# ──────────────────────────────────────────────────────────────────────────────
# Module-scoped fixtures — server + adapters started once
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def mail():
    return MockMail()

@pytest.fixture(scope="module")
def queue():
    return MockQueue(name="billing")

@pytest.fixture(scope="module")
def storage():
    return MockStorage(bucket="invoices")

@pytest.fixture(scope="module")
def clock():
    return MockTime(start=datetime(2024, 6, 1, 12, 0, 0))

@pytest.fixture(scope="module")
def server(mail, queue, storage, clock):
    """Start FastAPI in background thread."""
    app_instance = create_app(mail=mail, queue=queue, storage=storage, clock=clock)

    class _Server(uvicorn.Server):
        def install_signal_handlers(self): pass

    cfg = uvicorn.Config(app_instance, host="127.0.0.1", port=APP_PORT, log_level="error")
    srv = _Server(cfg)
    t   = threading.Thread(target=srv.run, daemon=True)
    t.start()

    # Wait for readiness
    for _ in range(60):
        time.sleep(0.05)
        try:
            r = HttpClient(f"http://127.0.0.1:{APP_PORT}").get("/health")
            if r.status_code == 200:
                break
        except Exception:
            pass

    yield f"http://127.0.0.1:{APP_PORT}"
    srv.should_exit = True


@pytest.fixture(scope="module")
def pg():
    """PostgresAdapter with a dedicated connection for observation."""
    adapter = PostgresAdapter(
        POSTGRES_URL,
        observe_tables=["subs_users", "subs_subscriptions", "subs_invoices"],
    )
    adapter.connect()
    adapter.add_observation_query(
        "active_sub_count",
        "SELECT COUNT(*) FROM subs_subscriptions WHERE status='active'",
    )
    adapter.add_observation_query(
        "max_active_per_user",
        """SELECT COALESCE(MAX(c),0) FROM (
               SELECT user_id, COUNT(*) c FROM subs_subscriptions
               WHERE status='active' GROUP BY user_id) t""",
    )
    yield adapter
    adapter.close()


@pytest.fixture(scope="module")
def rdb():
    """RedisAdapter for session cache."""
    adapter = RedisAdapter(REDIS_URL, track_patterns=["subs:*"])
    adapter.connect()
    yield adapter
    adapter.close()


@pytest.fixture(autouse=True)
def reset_between_tests(server, mail, queue, storage, clock):
    """Before each test: wipe DB and reset all in-memory adapters."""
    HttpClient(server).delete("/reset")
    mail._messages = []
    queue._messages = []
    queue._message_counter = 0
    storage._files = {}
    clock.set(datetime(2024, 6, 1, 12, 0, 0))
    yield


# ──────────────────────────────────────────────────────────────────────────────
# Actions  (functions that return ActionResult)
# ──────────────────────────────────────────────────────────────────────────────

def _rand_suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=6))


def create_user(api, context):
    s = _rand_suffix()
    resp = api.post("/users", json={"email": f"u_{s}@example.com", "name": f"User {s}"})
    if resp.status_code == 201:
        context.set("user_id",    resp.json()["id"])
        context.set("user_email", resp.json()["email"])
    return resp


def subscribe_basic(api, context):
    uid = context.get("user_id")
    if uid is None:
        return api.get("/health")
    resp = api.post("/subscriptions", json={"user_id": uid, "plan": "basic"})
    if resp.status_code == 201:
        context.set("sub_id",     resp.json()["id"])
        context.set("sub_plan",   "basic")
        context.set("sub_amount", float(resp.json()["amount"]))
    return resp


def subscribe_pro(api, context):
    uid = context.get("user_id")
    if uid is None:
        return api.get("/health")
    resp = api.post("/subscriptions", json={"user_id": uid, "plan": "pro"})
    if resp.status_code == 201:
        context.set("sub_id",     resp.json()["id"])
        context.set("sub_plan",   "pro")
        context.set("sub_amount", float(resp.json()["amount"]))
    return resp


def cancel_subscription(api, context):
    sid = context.get("sub_id")
    if sid is None:
        return api.get("/health")
    resp = api.delete(f"/subscriptions/{sid}")
    if resp.ok:
        context.set("sub_cancelled", True)
    return resp


def create_invoice(api, context):
    sid = context.get("sub_id")
    if sid is None:
        return api.get("/health")
    return api.post(f"/subscriptions/{sid}/invoice", json={"reason": "renewal"})


def list_subscriptions(api, context):
    uid = context.get("user_id")
    if uid is None:
        return api.get("/health")
    resp = api.get(f"/subscriptions/{uid}")
    context.set("subscriptions", resp.json())
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# Invariants
# ──────────────────────────────────────────────────────────────────────────────

def no_double_active_subscription(world):
    """BUG-1: each user must have ≤ 1 active subscription."""
    subs = world.context.get("subscriptions") or []
    active = [s for s in subs if isinstance(s, dict) and s.get("status") == "active"]
    return len(active) <= 1


def no_invoice_on_cancelled_sub(world):
    """BUG-2: after cancel, new invoice requests must be rejected."""
    cancelled = world.context.get("sub_cancelled", False)
    invoice_created = world.context.get("invoice_created_after_cancel", False)
    return not invoice_created


def invoice_amount_matches_plan(world):
    """BUG-3: active subscription amount must equal the plan's listed price."""
    plan   = world.context.get("sub_plan")
    amount = world.context.get("sub_amount")
    if plan is None or amount is None:
        return True
    prices = {"basic": 10.00, "pro": 49.00, "enterprise": 199.00}
    expected = prices.get(plan)
    if expected is None:
        return True
    return abs(float(amount) - expected) < 0.01


def mail_sent_on_subscription(world):
    """Email sent whenever a subscription is created."""
    mail     = world.systems["mail"]
    sub_plan = world.context.get("sub_plan")
    if sub_plan is None:
        return True
    # At least 1 subscription email must have been sent
    sent = mail.get_sent()
    return any("Subscribed" in m.get("subject", "") for m in sent)


def storage_has_invoice_pdf(world):
    """Invoice PDF must be stored whenever a subscription is created."""
    storage = world.systems["storage"]
    sub_id  = world.context.get("sub_id")
    if sub_id is None:
        return True
    return storage.get(f"invoice_{sub_id}.pdf") is not None


# ──────────────────────────────────────────────────────────────────────────────
# Bug detection tests (using Agent BFS exploration)
# ──────────────────────────────────────────────────────────────────────────────

class TestBugDetection:

    def test_bug1_double_subscribe_detected(self, server, mail, queue, storage, clock):
        """BFS finds BUG-1: user can hold >1 active subscription."""

        def subscribe_and_list(api, context):
            """Subscribe, then immediately list subs to observe double-active state."""
            uid = context.get("user_id")
            if uid is None:
                return api.get("/health")
            resp = api.post("/subscriptions", json={"user_id": uid, "plan": "basic"})
            if resp.status_code == 201:
                context.set("sub_id",   resp.json()["id"])
                context.set("sub_plan", "basic")
                context.set("sub_amount", float(resp.json()["amount"]))
            # Always refresh subscriptions for invariant check
            lr = api.get(f"/subscriptions/{uid}")
            context.set("subscriptions", lr.json())
            return resp if resp.status_code == 201 else lr

        world = World(
            api=HttpClient(server),
            systems={"mail": mail, "queue": queue, "storage": storage, "clock": clock},
        )
        agent = Agent(
            world=world,
            actions=[
                Action(name="create_user",         execute=create_user,         expected_status=[201, 409]),
                Action(name="subscribe_and_list",  execute=subscribe_and_list,  expected_status=[201, 200]),
                Action(name="subscribe_pro",       execute=subscribe_pro,       expected_status=[201]),
                Action(name="list_subs",           execute=list_subscriptions,  expected_status=[200]),
            ],
            invariants=[
                Invariant(
                    name="no_double_active_subscription",
                    check=no_double_active_subscription,
                    message="A user has more than 1 active subscription at the same time",
                    severity=Severity.CRITICAL,
                ),
            ],
            strategy=BFS(),
            max_steps=60,
        )

        result = agent.explore()
        _print_result(result)

        assert "no_double_active_subscription" in [v.invariant_name for v in result.violations], (
            "BUG-1 not detected"
        )

    def test_bug2_invoice_after_cancel_detected(self, server, mail, queue, storage, clock):
        """BFS finds BUG-2: invoice created against cancelled subscription."""

        def create_invoice_tracking(api, context):
            """Create invoice and mark if sub was cancelled first."""
            sid = context.get("sub_id")
            if sid is None:
                return api.get("/health")
            was_cancelled = context.get("sub_cancelled", False)
            resp = api.post(f"/subscriptions/{sid}/invoice", json={"reason": "renewal"})
            if resp.status_code == 201 and was_cancelled:
                context.set("invoice_created_after_cancel", True)
            return resp

        world = World(
            api=HttpClient(server),
            systems={"mail": mail, "queue": queue, "storage": storage, "clock": clock},
        )
        agent = Agent(
            world=world,
            actions=[
                Action(name="create_user",     execute=create_user,               expected_status=[201, 409]),
                Action(name="subscribe_basic", execute=subscribe_basic,           expected_status=[201]),
                Action(name="cancel_sub",      execute=cancel_subscription,       expected_status=[200, 409]),
                Action(name="create_invoice",  execute=create_invoice_tracking,   expected_status=[201, 404]),
            ],
            invariants=[
                Invariant(
                    name="no_invoice_on_cancelled_sub",
                    check=no_invoice_on_cancelled_sub,
                    message="Invoice was created after subscription was cancelled",
                    severity=Severity.CRITICAL,
                ),
            ],
            strategy=BFS(),
            max_steps=60,
        )

        result = agent.explore()
        _print_result(result)

        assert "no_invoice_on_cancelled_sub" in [v.invariant_name for v in result.violations], (
            "BUG-2 not detected"
        )

    def test_bug3_wrong_amount_on_resubscribe_detected(self, server, mail, queue, storage, clock):
        """BFS finds BUG-3: re-subscribing to different plan uses wrong price."""
        world = World(
            api=HttpClient(server),
            systems={"mail": mail, "queue": queue, "storage": storage, "clock": clock},
        )
        agent = Agent(
            world=world,
            actions=[
                Action(name="create_user",     execute=create_user,         expected_status=[201, 409]),
                Action(name="subscribe_basic", execute=subscribe_basic,     expected_status=[201]),
                Action(name="cancel_sub",      execute=cancel_subscription, expected_status=[200, 409]),
                Action(name="subscribe_pro",   execute=subscribe_pro,       expected_status=[201]),
                Action(name="list_subs",       execute=list_subscriptions,  expected_status=[200]),
            ],
            invariants=[
                Invariant(
                    name="invoice_amount_matches_plan",
                    check=invoice_amount_matches_plan,
                    message="Active subscription amount doesn't match plan price (basic=$10, pro=$49)",
                    severity=Severity.HIGH,
                ),
            ],
            strategy=BFS(),
            max_steps=80,
        )

        result = agent.explore()
        _print_result(result)

        assert "invoice_amount_matches_plan" in [v.invariant_name for v in result.violations], (
            "BUG-3 not detected"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Adapter-specific tests (direct, no Agent)
# ──────────────────────────────────────────────────────────────────────────────

class TestAdapters:

    def test_postgres_observes_row_counts(self, server, pg):
        """PostgresAdapter observes real DB state after API operations."""
        api = HttpClient(server)

        obs_before = pg.observe()
        users_before = int(obs_before.data["subs_users"])

        # Create user + subscription via API
        r = api.post("/users", json={"email": "pg_test@example.com", "name": "PG"})
        assert r.status_code == 201
        uid = r.json()["id"]
        r2  = api.post("/subscriptions", json={"user_id": uid, "plan": "pro"})
        assert r2.status_code == 201

        obs_after = pg.observe()
        assert int(obs_after.data["subs_users"]) == users_before + 1
        assert int(obs_after.data["subs_subscriptions"]) >= 1
        assert int(obs_after.data["subs_invoices"]) >= 1
        assert int(obs_after.data["active_sub_count"]) >= 1

    def test_postgres_savepoint_rollback(self, pg):
        """PostgresAdapter SAVEPOINT rollback undoes writes on its own connection."""
        pg_conn = pg._conn
        # Create a test table scoped to this test
        cur = pg_conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS pg_rollback_test (val TEXT)")
        pg_conn.commit()

        sp = pg.checkpoint("rollback_test")
        cur.execute("INSERT INTO pg_rollback_test VALUES ('before_rollback')")

        pg.rollback(sp)

        cur.execute("SELECT COUNT(*) FROM pg_rollback_test WHERE val='before_rollback'")
        count = cur.fetchone()[0]
        assert count == 0, "Postgres SAVEPOINT rollback failed — row still exists"

        cur.execute("DROP TABLE IF EXISTS pg_rollback_test")
        pg_conn.commit()

    def test_redis_adapter_checkpoint_rollback(self, rdb):
        """RedisAdapter snapshots and restores keys correctly."""
        r = redis_lib.Redis.from_url(REDIS_URL)
        r.set("subs:session_abc", "active", ex=300)

        snap = rdb.checkpoint("before_test")
        r.set("subs:session_abc", "modified")
        r.set("subs:new_key",     "should_disappear")

        rdb.rollback(snap)

        assert not r.exists("subs:new_key"), "New key should be gone after Redis rollback"
        val = r.get("subs:session_abc")
        assert val == b"active", f"Redis rollback failed — got {val!r}"
        r.delete("subs:session_abc")

    def test_mock_mail_tracks_all_emails(self, server, mail):
        """All three lifecycle emails (welcome, subscribe, cancel) are sent."""
        api = HttpClient(server)

        r  = api.post("/users", json={"email": "mail_test@example.com", "name": "Mail"})
        r2 = api.post("/subscriptions", json={"user_id": r.json()["id"], "plan": "basic"})
        r3 = api.delete(f"/subscriptions/{r2.json()['id']}")

        assert r.status_code  == 201
        assert r2.status_code == 201
        assert r3.status_code == 200

        sent     = mail.get_sent()
        subjects = [m["subject"] for m in sent]

        assert any("Welcome"    in s for s in subjects), f"No welcome email in {subjects}"
        assert any("Subscribed" in s for s in subjects), f"No subscription email in {subjects}"
        assert any("cancelled"  in s.lower() for s in subjects), f"No cancellation email in {subjects}"
        assert mail.sent_count >= 3

    def test_mock_queue_tracks_all_jobs(self, server, queue):
        """Background jobs are enqueued for user creation, subscription, and cancel."""
        api = HttpClient(server)

        r  = api.post("/users", json={"email": "q_test@example.com", "name": "Q"})
        r2 = api.post("/subscriptions", json={"user_id": r.json()["id"], "plan": "pro"})
        r3 = api.delete(f"/subscriptions/{r2.json()['id']}")

        msgs      = queue._messages
        job_types = [m.payload["type"] for m in msgs]

        assert "onboarding_job" in job_types, f"No onboarding_job in {job_types}"
        assert "billing_job"    in job_types, f"No billing_job in {job_types}"
        assert "cancel_job"     in job_types, f"No cancel_job in {job_types}"

        # Verify Message structure
        first = msgs[0]
        assert first.id.startswith("msg_")
        assert isinstance(first.payload, dict)
        assert first.processed is False   # not consumed yet

    def test_mock_storage_holds_invoice_pdfs(self, server, storage):
        """Invoice PDFs are stored for each subscription."""
        api = HttpClient(server)

        r  = api.post("/users", json={"email": "storage_test@example.com", "name": "S"})
        r2 = api.post("/subscriptions", json={"user_id": r.json()["id"], "plan": "enterprise"})
        sub_id = r2.json()["id"]

        pdf = storage.get(f"invoice_{sub_id}.pdf")
        assert pdf is not None, "Invoice PDF was not stored"
        assert b"199.00" in pdf, f"Enterprise invoice should be $199, content: {pdf}"
        assert storage.file_count >= 1

    def test_mock_time_drives_time_sensitive_ops(self, server, clock):
        """MockTime controls the server clock — cancellation timestamp uses it."""
        api = HttpClient(server)

        r   = api.post("/users", json={"email": "time_test@example.com", "name": "T"})
        uid = r.json()["id"]
        r2  = api.post("/subscriptions", json={"user_id": uid, "plan": "basic"})
        sid = r2.json()["id"]

        # Advance to day 30 of billing cycle
        clock.advance(days=30)
        assert clock.now.day == 1   # June 1 + 30 days = July 1

        # Health check reflects the mocked time
        h = api.get("/health")
        assert "2024-07" in h.json()["time"], f"Expected July 2024 in {h.json()['time']}"

        # Cancel — server stamps cancelled_at with mocked time
        r3 = api.delete(f"/subscriptions/{sid}")
        assert r3.status_code == 200

    def test_all_adapters_in_world_together(self, server, pg, rdb, mail, queue, storage, clock):
        """Smoke test: World with all 6 adapters observes consistent state."""
        world = World(
            api=HttpClient(server),
            systems={
                "db":      pg,
                "cache":   rdb,
                "mail":    mail,
                "queue":   queue,
                "storage": storage,
                "clock":   clock,
            },
        )

        # All systems should be observable
        for name, system in world.systems.items():
            obs = system.observe()
            assert obs is not None, f"System {name!r} returned None from observe()"
            assert hasattr(obs, "data"), f"Observation from {name!r} has no data"


# ──────────────────────────────────────────────────────────────────────────────
# Reporter tests
# ──────────────────────────────────────────────────────────────────────────────

class TestReporters:

    def test_json_reporter_has_all_fields(self, server, mail, queue, storage, clock):
        """JSONReporter output includes action_coverage_percent and truncated flag."""
        world = World(
            api=HttpClient(server),
            systems={"mail": mail, "queue": queue, "storage": storage, "clock": clock},
        )
        agent = Agent(
            world=world,
            actions=[
                Action(name="create_user",     execute=create_user,     expected_status=[201, 409]),
                Action(name="subscribe_basic", execute=subscribe_basic, expected_status=[201]),
                Action(name="list_subs",       execute=list_subscriptions),
            ],
            strategy=BFS(),
            max_steps=15,
        )
        result  = agent.explore()
        data    = json.loads(JSONReporter().report(result))
        summary = data["summary"]

        for key in ("states_visited", "transitions_taken", "action_coverage_percent",
                    "truncated_by_max_steps", "success"):
            assert key in summary, f"JSONReporter missing key: {key}"

        assert isinstance(summary["action_coverage_percent"], float)
        assert isinstance(summary["truncated_by_max_steps"], bool)

    def test_console_reporter_shows_truncation_warning(self, server, mail, queue, storage, clock):
        """ConsoleReporter shows a warning when max_steps is hit."""
        world = World(
            api=HttpClient(server),
            systems={"mail": mail, "queue": queue, "storage": storage, "clock": clock},
        )
        agent = Agent(
            world=world,
            actions=[
                Action(name="create_user",     execute=create_user,     expected_status=[201, 409]),
                Action(name="subscribe_basic", execute=subscribe_basic, expected_status=[201]),
                Action(name="cancel_sub",      execute=cancel_subscription),
            ],
            strategy=BFS(),
            max_steps=3,
        )
        result = agent.explore()
        assert result.truncated_by_max_steps

        buf = io.StringIO()
        ConsoleReporter(file=buf, color=False).report(result)
        assert "truncated" in buf.getvalue().lower()


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def _print_result(result) -> None:
    buf = io.StringIO()
    ConsoleReporter(file=buf, color=False).report(result)
    print(buf.getvalue())
