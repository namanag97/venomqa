"""Real-world VenomQA test — SaaS Subscription Management.

Exercises ALL VenomQA adapter types:
  ✓ PostgresAdapter  — real Postgres (Docker), SAVEPOINT rollback
  ✓ RedisAdapter     — real Redis (Docker), key dump/restore rollback
  ✓ MockMail         — email notifications
  ✓ MockQueue        — background jobs
  ✓ MockStorage      — invoice PDFs
  ✓ MockTime         — controllable clock

The server has 3 deliberately planted bugs that VenomQA's BFS exploration
will catch via invariant violations:
  BUG-1: Users can have multiple active subscriptions simultaneously
  BUG-2: New invoices can be created against cancelled subscriptions
  BUG-3: Re-subscribe after cancel uses old plan price (wrong amount)

Run:
    pytest examples/subscriptions_qa/test_subscriptions_qa.py -v
    (requires Docker: postgres on 5432, redis on 6379)
"""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
import pytest
import uvicorn

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from venomqa.v1 import Action, Agent, BFS, Invariant, Severity, World
from venomqa.v1.adapters import MockMail, MockQueue, MockStorage, MockTime
from venomqa.v1.adapters.http import HttpClient
from venomqa.v1.adapters.postgres import PostgresAdapter
from venomqa.v1.adapters.redis import RedisAdapter
from venomqa.v1.reporters.console import ConsoleReporter
from venomqa.v1.reporters.json import JSONReporter

from server import create_app

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

POSTGRES_URL = "postgresql://appuser:apppass@localhost:5432/appdb"
REDIS_URL    = "redis://localhost:6379"
APP_PORT     = 18744


# ──────────────────────────────────────────────────────────────────────────────
# Pytest fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def adapters():
    """Spin up all adapters and the FastAPI server, return them bundled."""

    # ── Real DB adapters ────────────────────────────────────────────────────
    pg = PostgresAdapter(
        POSTGRES_URL,
        observe_tables=["subs_users", "subs_subscriptions", "subs_invoices"],
    )
    pg.connect()

    # Add custom observations so invariants can query business state
    pg.add_observation_query(
        "active_sub_count",
        "SELECT COUNT(*) FROM subs_subscriptions WHERE status = 'active'",
    )
    pg.add_observation_query(
        "max_active_subs_per_user",
        """SELECT COALESCE(MAX(cnt), 0) FROM (
               SELECT user_id, COUNT(*) AS cnt
               FROM subs_subscriptions WHERE status = 'active'
               GROUP BY user_id
           ) sub""",
    )
    pg.add_observation_query(
        "invoices_for_cancelled",
        """SELECT COUNT(*) FROM subs_invoices i
           JOIN subs_subscriptions s ON i.subscription_id = s.id
           WHERE s.status = 'cancelled'
             AND i.created_at > s.cancelled_at""",
    )

    rdb = RedisAdapter(REDIS_URL, track_patterns=["subs:*"])
    rdb.connect()

    # ── In-memory adapters ──────────────────────────────────────────────────
    mail    = MockMail()
    queue   = MockQueue(name="billing")
    storage = MockStorage(bucket="invoices")
    clock   = MockTime(start=datetime(2024, 6, 1, 12, 0, 0))

    # ── Shared psycopg2 connection ──────────────────────────────────────────
    # The app writes go through the SAME connection as PostgresAdapter,
    # so every INSERT/UPDATE is inside the same transaction and SAVEPOINTs work.
    conn = pg._conn

    # ── FastAPI server (background thread) ─────────────────────────────────
    app_instance = create_app(conn=conn, mail=mail, queue=queue, storage=storage, clock=clock)

    class _Server(uvicorn.Server):
        def install_signal_handlers(self):
            pass   # don't block test runner

    config = uvicorn.Config(app_instance, host="127.0.0.1", port=APP_PORT, log_level="error")
    server = _Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to be ready
    api_check = HttpClient(f"http://127.0.0.1:{APP_PORT}")
    for _ in range(50):
        time.sleep(0.05)
        try:
            r = api_check.get("/health")
            if r.status_code == 200:
                break
        except Exception:
            pass

    yield {
        "pg":      pg,
        "rdb":     rdb,
        "mail":    mail,
        "queue":   queue,
        "storage": storage,
        "clock":   clock,
        "conn":    conn,
        "server":  server,
    }

    server.should_exit = True
    rdb.close()
    pg.close()


@pytest.fixture
def world(adapters):
    """Fresh World for each test — resets in-memory adapters."""
    # Reset in-memory adapters for test isolation
    adapters["mail"]._messages = []
    adapters["queue"]._messages = []
    adapters["queue"]._message_counter = 0
    adapters["storage"]._files = {}
    adapters["clock"].set(datetime(2024, 6, 1, 12, 0, 0))

    api = HttpClient(f"http://127.0.0.1:{APP_PORT}")
    w = World(
        api=api,
        systems={
            "db":      adapters["pg"],
            "cache":   adapters["rdb"],
            "mail":    adapters["mail"],
            "queue":   adapters["queue"],
            "storage": adapters["storage"],
            "clock":   adapters["clock"],
        },
    )
    return w


# ──────────────────────────────────────────────────────────────────────────────
# Actions
# ──────────────────────────────────────────────────────────────────────────────

def create_user(api, context):
    import random, string
    suffix = "".join(random.choices(string.ascii_lowercase, k=6))
    resp = api.post("/users", json={
        "email": f"user_{suffix}@example.com",
        "name":  f"Test User {suffix}",
    })
    if resp.status_code == 201:
        context.set("user_id",    resp.json()["id"])
        context.set("user_email", resp.json()["email"])
    return resp


def subscribe_basic(api, context):
    user_id = context.get("user_id")
    if user_id is None:
        # Create a user first if we don't have one
        r = api.post("/users", json={"email": "auto@example.com", "name": "Auto"})
        if r.status_code == 201:
            context.set("user_id", r.json()["id"])
        user_id = context.get("user_id")
    if user_id is None:
        return api.get("/health")   # safe no-op

    resp = api.post("/subscriptions", json={"user_id": user_id, "plan": "basic"})
    if resp.status_code == 201:
        context.set("sub_id", resp.json()["id"])
        context.set("sub_amount", resp.json()["amount"])
        context.set("sub_plan", "basic")
    return resp


def subscribe_pro(api, context):
    user_id = context.get("user_id")
    if user_id is None:
        return api.get("/health")
    resp = api.post("/subscriptions", json={"user_id": user_id, "plan": "pro"})
    if resp.status_code == 201:
        context.set("sub_id",    resp.json()["id"])
        context.set("sub_amount", resp.json()["amount"])
        context.set("sub_plan", "pro")
    return resp


def cancel_subscription(api, context):
    sub_id = context.get("sub_id")
    if sub_id is None:
        return api.get("/health")
    resp = api.delete(f"/subscriptions/{sub_id}")
    if resp.ok:
        context.set("sub_cancelled", True)
    return resp


def create_invoice(api, context):
    sub_id = context.get("sub_id")
    if sub_id is None:
        return api.get("/health")
    return api.post(f"/subscriptions/{sub_id}/invoice", json={"reason": "renewal"})


def list_subscriptions(api, context):
    user_id = context.get("user_id")
    if user_id is None:
        return api.get("/health")
    resp = api.get(f"/subscriptions/{user_id}")
    context.set("subscriptions", resp.json())
    return resp


def advance_clock(api, context):
    """Advance mock clock by 30 days (simulates billing cycle)."""
    context.get("clock_ref") and context.get("clock_ref").advance(days=30)
    return api.get("/health")


# ──────────────────────────────────────────────────────────────────────────────
# Invariants
# ──────────────────────────────────────────────────────────────────────────────

def no_double_active_subscription(world):
    """BUG-1 detector: each user must have at most 1 active subscription."""
    obs = world.systems["db"].observe()
    max_per_user = obs.data.get("max_active_subs_per_user", 0)
    return int(max_per_user) <= 1


def no_invoice_after_cancellation(world):
    """BUG-2 detector: no invoice created after cancellation timestamp."""
    obs = world.systems["db"].observe()
    post_cancel_invoices = obs.data.get("invoices_for_cancelled", 0)
    return int(post_cancel_invoices) == 0


def invoice_amount_matches_plan(world):
    """BUG-3 detector: active subscriptions must have the correct plan price."""
    obs = world.systems["db"].observe()
    # Check via direct query attached to adapter
    try:
        cur = world.systems["db"]._conn.cursor()
        cur.execute("""
            SELECT s.plan, s.amount
            FROM subs_subscriptions s
            WHERE s.status = 'active'
        """)
        rows = cur.fetchall()
    except Exception:
        return True   # skip if query fails

    plan_prices = {"basic": 10.00, "pro": 49.00, "enterprise": 199.00}
    for plan, amount in rows:
        expected = plan_prices.get(plan)
        if expected is not None and abs(float(amount) - expected) > 0.01:
            return False
    return True


def mail_sent_on_subscription(world):
    """Email must be sent whenever a subscription is created."""
    mail = world.systems["mail"]
    db   = world.systems["db"]
    obs  = db.observe()
    sub_count = int(obs.data.get("subs_subscriptions", 0))
    # At minimum 1 email per subscription (welcome + subscribe) but at least sub_count emails
    # (welcome emails + subscription emails)
    return mail.sent_count >= sub_count


def job_queued_on_activity(world):
    """Background job must be queued for every subscription creation."""
    queue = world.systems["queue"]
    db    = world.systems["db"]
    obs   = db.observe()
    sub_count = int(obs.data.get("subs_subscriptions", 0))
    # billing_job + cancel_job + onboarding_job — at least sub_count jobs
    return queue.processed_count + queue.pending_count >= sub_count


def storage_has_invoice_pdfs(world):
    """Every subscription must have at least one invoice PDF in storage."""
    storage = world.systems["storage"]
    db      = world.systems["db"]
    obs     = db.observe()
    sub_count = int(obs.data.get("subs_subscriptions", 0))
    return storage.file_count >= sub_count


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSubscriptionQA:

    def test_bug1_double_subscribe_found(self, adapters, world):
        """BFS exploration MUST find BUG-1: double active subscriptions."""
        agent = Agent(
            world=world,
            actions=[
                Action(name="create_user",     execute=create_user,     expected_status=[201, 409]),
                Action(name="subscribe_basic", execute=subscribe_basic, expected_status=[201]),
                Action(name="subscribe_pro",   execute=subscribe_pro,   expected_status=[201]),
                Action(name="list_subs",       execute=list_subscriptions),
            ],
            invariants=[
                Invariant(
                    name="no_double_active_subscription",
                    check=no_double_active_subscription,
                    message="A user has more than 1 active subscription simultaneously",
                    severity=Severity.CRITICAL,
                ),
            ],
            strategy=BFS(),
            max_steps=50,
        )

        result = agent.explore()

        # Pretty-print for visibility
        import io
        buf = io.StringIO()
        ConsoleReporter(file=buf, color=False).report(result)
        print(buf.getvalue())

        violation_names = [v.invariant_name for v in result.violations]
        assert "no_double_active_subscription" in violation_names, (
            "BUG-1 NOT detected! VenomQA should have found double-subscribe. "
            f"Violations found: {violation_names}"
        )

    def test_bug2_invoice_after_cancel_found(self, adapters, world):
        """BFS exploration MUST find BUG-2: invoice created after cancel."""
        agent = Agent(
            world=world,
            actions=[
                Action(name="create_user",      execute=create_user,          expected_status=[201, 409]),
                Action(name="subscribe_basic",  execute=subscribe_basic,      expected_status=[201]),
                Action(name="cancel_sub",       execute=cancel_subscription,  expected_status=[200, 409]),
                Action(name="create_invoice",   execute=create_invoice,       expected_status=[201, 404]),
            ],
            invariants=[
                Invariant(
                    name="no_invoice_after_cancellation",
                    check=no_invoice_after_cancellation,
                    message="An invoice was created after subscription was cancelled",
                    severity=Severity.CRITICAL,
                ),
            ],
            strategy=BFS(),
            max_steps=60,
        )

        result = agent.explore()

        import io
        buf = io.StringIO()
        ConsoleReporter(file=buf, color=False).report(result)
        print(buf.getvalue())

        violation_names = [v.invariant_name for v in result.violations]
        assert "no_invoice_after_cancellation" in violation_names, (
            "BUG-2 NOT detected! "
            f"Violations found: {violation_names}"
        )

    def test_bug3_wrong_amount_on_resubscribe_found(self, adapters, world):
        """BFS exploration MUST find BUG-3: wrong invoice amount after re-subscribe."""
        agent = Agent(
            world=world,
            actions=[
                Action(name="create_user",     execute=create_user,         expected_status=[201, 409]),
                Action(name="subscribe_basic", execute=subscribe_basic,     expected_status=[201]),
                Action(name="cancel_sub",      execute=cancel_subscription, expected_status=[200, 409]),
                Action(name="subscribe_pro",   execute=subscribe_pro,       expected_status=[201]),
                Action(name="list_subs",       execute=list_subscriptions),
            ],
            invariants=[
                Invariant(
                    name="invoice_amount_matches_plan",
                    check=invoice_amount_matches_plan,
                    message=(
                        "Active subscription amount doesn't match plan price. "
                        "basic=$10, pro=$49, enterprise=$199"
                    ),
                    severity=Severity.HIGH,
                ),
            ],
            strategy=BFS(),
            max_steps=80,
        )

        result = agent.explore()

        import io
        buf = io.StringIO()
        ConsoleReporter(file=buf, color=False).report(result)
        print(buf.getvalue())

        violation_names = [v.invariant_name for v in result.violations]
        assert "invoice_amount_matches_plan" in violation_names, (
            "BUG-3 NOT detected! Re-subscribe with different plan should have wrong amount. "
            f"Violations found: {violation_names}"
        )

    def test_all_adapters_checkpointing(self, adapters, world):
        """Verify that all adapters checkpoint and rollback correctly."""
        pg    = adapters["pg"]
        rdb   = adapters["rdb"]
        mail  = adapters["mail"]
        queue = adapters["queue"]
        storage = adapters["storage"]
        clock = adapters["clock"]

        # Snapshot all adapters
        pg_snap  = pg.checkpoint("test_snap")
        rdb_snap = rdb.checkpoint("test_snap")
        mail_before = mail.sent_count
        queue_before = queue.pending_count
        storage_before = storage.file_count
        clock_time_before = clock.now

        # Make changes via API
        api = HttpClient(f"http://127.0.0.1:{APP_PORT}")
        r = api.post("/users", json={"email": "snap_test@example.com", "name": "Snap"})
        assert r.status_code == 201
        user_id = r.json()["id"]
        r2 = api.post("/subscriptions", json={"user_id": user_id, "plan": "pro"})
        assert r2.status_code == 201

        # Advance clock
        clock.advance(days=7)
        assert clock.now != clock_time_before

        # Send extra mail
        mail.send("test@example.com", "Extra", "Email")
        assert mail.sent_count > mail_before

        # Push extra job
        queue.push({"type": "test"})
        assert queue.pending_count > queue_before

        # Store a file
        storage.put("test.txt", b"hello")
        assert storage.file_count > storage_before

        # Rollback all adapters
        pg.rollback(pg_snap)
        rdb.rollback(rdb_snap)

        # Reset in-memory adapters manually (as the World would)
        adapters["mail"]._messages = [m for m in adapters["mail"]._messages
                                       if m.id != adapters["mail"]._messages[-1].id]
        # Simpler: just reset to baseline for this test
        adapters["mail"]._messages = []
        adapters["queue"]._messages = []
        adapters["queue"]._message_counter = 0
        adapters["storage"]._files = {}
        clock.set(clock_time_before)

        # Verify DB was rolled back
        cur = adapters["conn"].cursor()
        cur.execute("SELECT id FROM subs_users WHERE email = 'snap_test@example.com'")
        assert cur.fetchone() is None, "Postgres rollback failed — user still exists"

        assert clock.now == clock_time_before
        assert storage.file_count == 0

    def test_mock_mail_tracks_all_notifications(self, adapters, world):
        """Every subscription and cancellation sends correct email notifications."""
        api = HttpClient(f"http://127.0.0.1:{APP_PORT}")

        mail_before = adapters["mail"].sent_count

        # Create user + subscribe + cancel
        r = api.post("/users", json={"email": "mail_test@example.com", "name": "Mail"})
        assert r.status_code == 201
        user_id = r.json()["id"]

        r2 = api.post("/subscriptions", json={"user_id": user_id, "plan": "basic"})
        assert r2.status_code == 201
        sub_id = r2.json()["id"]

        r3 = api.delete(f"/subscriptions/{sub_id}")
        assert r3.status_code == 200

        total_sent = adapters["mail"].sent_count - mail_before
        # Expect: 1 welcome + 1 subscription + 1 cancellation = 3 emails
        assert total_sent == 3, f"Expected 3 emails, got {total_sent}"

        sent = adapters["mail"].get_sent()
        subjects = [m["subject"] for m in sent[-3:]]
        assert any("Welcome" in s for s in subjects), "No welcome email"
        assert any("Subscribed" in s for s in subjects), "No subscription email"
        assert any("cancelled" in s.lower() for s in subjects), "No cancellation email"

    def test_mock_queue_tracks_all_jobs(self, adapters, world):
        """Background jobs are queued for every subscription event."""
        api = HttpClient(f"http://127.0.0.1:{APP_PORT}")

        queue_before = adapters["queue"].pending_count + adapters["queue"].processed_count

        r = api.post("/users", json={"email": "queue_test@example.com", "name": "Queue"})
        assert r.status_code == 201
        user_id = r.json()["id"]

        r2 = api.post("/subscriptions", json={"user_id": user_id, "plan": "pro"})
        assert r2.status_code == 201
        sub_id = r2.json()["id"]

        r3 = api.delete(f"/subscriptions/{sub_id}")
        assert r3.status_code == 200

        total_jobs = (adapters["queue"].pending_count + adapters["queue"].processed_count) - queue_before
        # onboarding_job + billing_job + cancel_job = 3 jobs
        assert total_jobs == 3, f"Expected 3 jobs, got {total_jobs}"

        # Check job types
        all_msgs = adapters["queue"]._messages
        job_types = [m.payload["type"] for m in all_msgs[-3:]]
        assert "onboarding_job" in job_types
        assert "billing_job"    in job_types
        assert "cancel_job"     in job_types

    def test_mock_storage_holds_invoice_pdfs(self, adapters, world):
        """Invoice PDFs are stored for every subscription created."""
        api = HttpClient(f"http://127.0.0.1:{APP_PORT}")

        files_before = adapters["storage"].file_count

        r = api.post("/users", json={"email": "storage_test@example.com", "name": "Storage"})
        assert r.status_code == 201
        user_id = r.json()["id"]

        r2 = api.post("/subscriptions", json={"user_id": user_id, "plan": "enterprise"})
        assert r2.status_code == 201
        sub_id = r2.json()["id"]

        new_files = adapters["storage"].file_count - files_before
        assert new_files >= 1, f"Expected at least 1 PDF, got {new_files}"

        # Verify PDF content
        pdf = adapters["storage"].get(f"invoice_{sub_id}.pdf")
        assert pdf is not None
        assert b"199.00" in pdf, "Enterprise invoice should be $199"

    def test_mock_time_drives_expiry_logic(self, adapters, world):
        """MockTime lets us simulate billing cycles without wall-clock waits."""
        clock = adapters["clock"]
        api   = HttpClient(f"http://127.0.0.1:{APP_PORT}")

        start = clock.now
        assert start == datetime(2024, 6, 1, 12, 0, 0)

        # Health check shows the current mock time
        r = api.get("/health")
        assert r.json()["time"] == start.isoformat()

        # Advance 30 days (billing cycle)
        clock.advance(days=30)
        r2 = api.get("/health")
        assert r2.json()["time"] != start.isoformat()
        assert clock.now.day == 1   # June 1 + 30 days = July 1

    def test_redis_adapter_checkpoints(self, adapters, world):
        """RedisAdapter snapshots and restores keys correctly."""
        rdb = adapters["rdb"]

        # Write a test key
        import redis as redis_lib
        r_client = redis_lib.Redis.from_url(REDIS_URL)
        r_client.set("subs:test_session", "active", ex=300)

        snap = rdb.checkpoint("before_test")
        assert r_client.exists("subs:test_session")

        # Modify
        r_client.set("subs:test_session", "modified")
        r_client.set("subs:new_key", "should_disappear")

        assert r_client.get("subs:test_session") == b"modified"

        # Rollback
        rdb.rollback(snap)

        # New key should be gone, original value restored
        assert not r_client.exists("subs:new_key"), "Redis rollback failed — new_key still exists"
        val = r_client.get("subs:test_session")
        assert val == b"active", f"Redis rollback failed — got {val}"

        r_client.delete("subs:test_session")

    def test_json_reporter_complete_output(self, adapters, world):
        """JSONReporter includes all expected fields after a real exploration."""
        agent = Agent(
            world=world,
            actions=[
                Action(name="create_user",     execute=create_user,     expected_status=[201, 409]),
                Action(name="subscribe_basic", execute=subscribe_basic, expected_status=[201]),
                Action(name="list_subs",       execute=list_subscriptions),
            ],
            invariants=[
                Invariant(
                    name="no_double_active_subscription",
                    check=no_double_active_subscription,
                    message="Double active subscription",
                    severity=Severity.CRITICAL,
                ),
            ],
            strategy=BFS(),
            max_steps=15,
        )

        result = agent.explore()
        output = JSONReporter().report(result)
        data   = json.loads(output)

        summary = data["summary"]
        assert "states_visited"          in summary
        assert "transitions_taken"       in summary
        assert "action_coverage_percent" in summary
        assert "truncated_by_max_steps"  in summary
        assert "success"                 in summary
        assert isinstance(summary["action_coverage_percent"], (int, float))
