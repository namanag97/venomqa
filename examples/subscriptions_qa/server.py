"""SaaS Subscription Management server — with 3 deliberately planted bugs.

This server uses its own psycopg2 connection (not shared with VenomQA's
PostgresAdapter, so Agent BFS can run without savepoint conflicts).

VenomQA observes state via:
  - PostgresAdapter (separate read-only connection) — row counts
  - MockMail    — email notifications
  - MockQueue   — background jobs
  - MockStorage — invoice PDFs
  - MockTime    — controllable clock
  - RedisAdapter — session cache

Planted bugs:
  BUG-1: POST /subscriptions allows a user to have multiple active subs
  BUG-2: POST /subscriptions/{id}/invoice doesn't reject cancelled subs
  BUG-3: Re-subscribe after cancel copies old amount instead of new plan price
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

PLANS = {
    "basic":      {"price": 10.00, "name": "Basic"},
    "pro":        {"price": 49.00, "name": "Pro"},
    "enterprise": {"price": 199.00, "name": "Enterprise"},
}

POSTGRES_URL = "postgresql://appuser:apppass@localhost:5432/appdb"


def create_app(mail: Any, queue: Any, storage: Any, clock: Any) -> FastAPI:
    """Create the FastAPI app with injected side-effect adapters.

    Uses its own psycopg2 connection — isolated from VenomQA's PostgresAdapter.
    """
    app = FastAPI(title="Subscription Management Service")

    # Own connection — autocommit so writes are immediately visible
    _conn = psycopg2.connect(POSTGRES_URL)
    _conn.autocommit = True

    def db_exec(sql: str, params: tuple = ()) -> list[dict]:
        cur = _conn.cursor()
        cur.execute(sql, params)
        if cur.description:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        return []

    def db_one(sql: str, params: tuple = ()) -> dict | None:
        rows = db_exec(sql, params)
        return rows[0] if rows else None

    # Bootstrap tables
    cur = _conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subs_users (
            id         SERIAL PRIMARY KEY,
            email      TEXT UNIQUE NOT NULL,
            name       TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subs_subscriptions (
            id           SERIAL PRIMARY KEY,
            user_id      INT NOT NULL REFERENCES subs_users(id),
            plan         TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'active',
            amount       NUMERIC(10,2) NOT NULL,
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            cancelled_at TIMESTAMPTZ
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subs_invoices (
            id              SERIAL PRIMARY KEY,
            subscription_id INT NOT NULL REFERENCES subs_subscriptions(id),
            amount          NUMERIC(10,2) NOT NULL,
            reason          TEXT NOT NULL,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    @app.post("/users", status_code=201)
    def create_user(body: dict):
        email = body.get("email", "").strip()
        name  = body.get("name",  "").strip()
        if not email or not name:
            raise HTTPException(400, "email and name required")
        if db_one("SELECT id FROM subs_users WHERE email = %s", (email,)):
            raise HTTPException(409, f"User {email} already exists")

        row = db_one(
            "INSERT INTO subs_users (email, name) VALUES (%s, %s) RETURNING *",
            (email, name),
        )
        mail.send(email, "Welcome to SaaS App!", f"Hi {name}, welcome aboard!")
        queue.push({"type": "onboarding_job", "user_id": row["id"]})
        return row

    @app.get("/users/{user_id}")
    def get_user(user_id: int):
        u = db_one("SELECT * FROM subs_users WHERE id = %s", (user_id,))
        if not u:
            raise HTTPException(404, "User not found")
        return u

    @app.post("/subscriptions", status_code=201)
    def create_subscription(body: dict):
        user_id = body.get("user_id")
        plan    = body.get("plan", "basic")
        if plan not in PLANS:
            raise HTTPException(400, f"Unknown plan: {plan}")
        u = db_one("SELECT * FROM subs_users WHERE id = %s", (user_id,))
        if not u:
            raise HTTPException(404, "User not found")

        # ══════════════════════════════════
        # BUG-1: no uniqueness check here
        # ══════════════════════════════════

        # BUG-3: copy amount from previous sub instead of using plan price
        prev = db_one(
            "SELECT amount FROM subs_subscriptions WHERE user_id = %s ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        amount = float(prev["amount"]) if prev else PLANS[plan]["price"]

        sub = db_one(
            "INSERT INTO subs_subscriptions (user_id, plan, amount) VALUES (%s, %s, %s) RETURNING *",
            (user_id, plan, amount),
        )
        db_exec(
            "INSERT INTO subs_invoices (subscription_id, amount, reason) VALUES (%s, %s, %s)",
            (sub["id"], amount, "subscription_start"),
        )
        mail.send(u["email"], f"Subscribed to {plan}!", f"Your {plan} plan is now active.")
        queue.push({"type": "billing_job", "subscription_id": sub["id"], "amount": amount})
        storage.put(
            f"invoice_{sub['id']}.pdf",
            f"Invoice for sub {sub['id']}: ${amount:.2f}".encode(),
        )
        return sub

    @app.get("/subscriptions/{user_id}")
    def list_subscriptions(user_id: int):
        return db_exec(
            "SELECT * FROM subs_subscriptions WHERE user_id = %s ORDER BY id",
            (user_id,),
        )

    @app.delete("/subscriptions/{sub_id}", status_code=200)
    def cancel_subscription(sub_id: int):
        s = db_one("SELECT * FROM subs_subscriptions WHERE id = %s", (sub_id,))
        if not s:
            raise HTTPException(404, "Subscription not found")
        if s["status"] == "cancelled":
            raise HTTPException(409, "Already cancelled")
        db_exec(
            "UPDATE subs_subscriptions SET status='cancelled', cancelled_at=%s WHERE id=%s",
            (clock.now, sub_id),
        )
        u = db_one("SELECT * FROM subs_users WHERE id = %s", (s["user_id"],))
        mail.send(u["email"], "Subscription cancelled", "Your subscription has been cancelled.")
        queue.push({"type": "cancel_job", "subscription_id": sub_id})
        return {"cancelled": sub_id}

    @app.post("/subscriptions/{sub_id}/invoice", status_code=201)
    def create_invoice(sub_id: int, body: dict):
        s = db_one("SELECT * FROM subs_subscriptions WHERE id = %s", (sub_id,))
        if not s:
            raise HTTPException(404, "Subscription not found")

        # ══════════════════════════════════
        # BUG-2: no guard for cancelled subs
        # ══════════════════════════════════

        reason = body.get("reason", "manual")
        amount = float(s["amount"])
        row = db_one(
            "INSERT INTO subs_invoices (subscription_id, amount, reason) VALUES (%s, %s, %s) RETURNING *",
            (sub_id, amount, reason),
        )
        storage.put(
            f"invoice_{sub_id}_{row['id']}.pdf",
            f"Invoice {row['id']}: ${amount:.2f} ({reason})".encode(),
        )
        return row

    @app.get("/invoices/{sub_id}")
    def list_invoices(sub_id: int):
        return db_exec(
            "SELECT * FROM subs_invoices WHERE subscription_id = %s ORDER BY id",
            (sub_id,),
        )

    @app.delete("/reset", status_code=200)
    def reset_db():
        """Test-only endpoint: wipe all subscription tables."""
        db_exec("DELETE FROM subs_invoices")
        db_exec("DELETE FROM subs_subscriptions")
        db_exec("DELETE FROM subs_users")
        return {"reset": True}

    @app.get("/health")
    def health():
        return {"status": "ok", "time": clock.now.isoformat()}

    return app
