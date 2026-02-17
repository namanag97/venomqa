"""SaaS Subscription Management server — with 3 deliberately planted bugs.

This server is intentionally broken in specific ways so VenomQA can find them.

Planted bugs:
  BUG-1 (double-subscribe): POST /subscriptions doesn't check for an existing
         active subscription, so a user can have multiple active subscriptions.

  BUG-2 (invoice after cancel): POST /subscriptions/{id}/invoice creates a new
         invoice even when the subscription is already cancelled.

  BUG-3 (wrong plan amount): When a user resubscribes after cancelling, the
         invoice amount is copied from the previous subscription instead of
         using the new plan's price.

This server shares a psycopg2 connection with VenomQA's PostgresAdapter so
that SAVEPOINT rollback covers all database writes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Plans catalogue
# ---------------------------------------------------------------------------

PLANS = {
    "basic":      {"price": 10.00, "name": "Basic"},
    "pro":        {"price": 49.00, "name": "Pro"},
    "enterprise": {"price": 199.00, "name": "Enterprise"},
}


def create_app(conn: Any, mail: Any, queue: Any, storage: Any, clock: Any) -> FastAPI:
    """Create the FastAPI app, injecting shared dependencies.

    conn:    psycopg2 connection shared with PostgresAdapter
    mail:    MockMail instance
    queue:   MockQueue instance
    storage: MockStorage instance
    clock:   MockTime instance
    """
    app = FastAPI(title="Subscription Management Service")

    # ── Database helpers ────────────────────────────────────────────────────

    def db_exec(sql: str, params: tuple = ()) -> list[dict]:
        cur = conn.cursor()
        cur.execute(sql, params)
        if cur.description:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        return []

    def db_one(sql: str, params: tuple = ()) -> dict | None:
        rows = db_exec(sql, params)
        return rows[0] if rows else None

    # ── Schema bootstrap ────────────────────────────────────────────────────

    def _create_tables() -> None:
        cur = conn.cursor()
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
                id         SERIAL PRIMARY KEY,
                user_id    INT NOT NULL REFERENCES subs_users(id),
                plan       TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'active',
                amount     NUMERIC(10,2) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
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
        conn.commit()

    _create_tables()

    # ── Routes ──────────────────────────────────────────────────────────────

    @app.post("/users", status_code=201)
    def create_user(body: dict):
        email = body.get("email", "").strip()
        name  = body.get("name", "").strip()
        if not email or not name:
            raise HTTPException(400, "email and name required")

        existing = db_one("SELECT id FROM subs_users WHERE email = %s", (email,))
        if existing:
            raise HTTPException(409, f"User {email} already exists")

        row = db_one(
            "INSERT INTO subs_users (email, name) VALUES (%s, %s) RETURNING *",
            (email, name),
        )

        # Side effects — tracked by adapters
        mail.send(email, "Welcome to SaaS App!", f"Hi {name}, welcome aboard!")
        queue.push({"type": "onboarding_job", "user_id": row["id"]})

        return row

    @app.get("/users/{user_id}")
    def get_user(user_id: int):
        user = db_one("SELECT * FROM subs_users WHERE id = %s", (user_id,))
        if not user:
            raise HTTPException(404, "User not found")
        return user

    @app.post("/subscriptions", status_code=201)
    def create_subscription(body: dict):
        user_id = body.get("user_id")
        plan    = body.get("plan", "basic")

        if plan not in PLANS:
            raise HTTPException(400, f"Unknown plan: {plan}")

        user = db_one("SELECT * FROM subs_users WHERE id = %s", (user_id,))
        if not user:
            raise HTTPException(404, "User not found")

        # ══════════════════════════════════════════════════════════════════
        # BUG-1: Missing uniqueness check — this should reject if the user
        # already has an active subscription, but it doesn't.
        # ══════════════════════════════════════════════════════════════════

        # BUG-3: When there's a previous (cancelled) subscription for this
        # user, we accidentally copy its amount instead of using the new plan.
        prev = db_one(
            "SELECT amount FROM subs_subscriptions WHERE user_id = %s ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        if prev:
            amount = float(prev["amount"])   # BUG-3: should be PLANS[plan]["price"]
        else:
            amount = PLANS[plan]["price"]

        sub = db_one(
            """INSERT INTO subs_subscriptions (user_id, plan, amount)
               VALUES (%s, %s, %s) RETURNING *""",
            (user_id, plan, amount),
        )

        # Create initial invoice
        db_exec(
            "INSERT INTO subs_invoices (subscription_id, amount, reason) VALUES (%s, %s, %s)",
            (sub["id"], amount, "subscription_start"),
        )

        # Side effects
        mail.send(user["email"], f"Subscribed to {plan}!", f"Your {plan} plan is now active.")
        queue.push({"type": "billing_job", "subscription_id": sub["id"], "amount": amount})
        storage.put(
            f"invoice_{sub['id']}.pdf",
            f"Invoice for subscription {sub['id']}: ${amount:.2f}".encode(),
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
        sub = db_one("SELECT * FROM subs_subscriptions WHERE id = %s", (sub_id,))
        if not sub:
            raise HTTPException(404, "Subscription not found")
        if sub["status"] == "cancelled":
            raise HTTPException(409, "Already cancelled")

        db_exec(
            "UPDATE subs_subscriptions SET status = 'cancelled', cancelled_at = %s WHERE id = %s",
            (clock.now, sub_id),
        )

        user = db_one("SELECT * FROM subs_users WHERE id = %s", (sub["user_id"],))
        mail.send(user["email"], "Subscription cancelled", "Your subscription has been cancelled.")
        queue.push({"type": "cancel_job", "subscription_id": sub_id})

        return {"cancelled": sub_id}

    @app.post("/subscriptions/{sub_id}/invoice", status_code=201)
    def create_invoice(sub_id: int, body: dict):
        sub = db_one("SELECT * FROM subs_subscriptions WHERE id = %s", (sub_id,))
        if not sub:
            raise HTTPException(404, "Subscription not found")

        # ══════════════════════════════════════════════════════════════════
        # BUG-2: Should reject if subscription is cancelled, but doesn't.
        # ══════════════════════════════════════════════════════════════════

        reason = body.get("reason", "manual")
        amount = float(sub["amount"])

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

    @app.get("/health")
    def health():
        now = clock.now
        return {"status": "ok", "time": now.isoformat()}

    return app
