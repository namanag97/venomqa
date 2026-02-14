#!/usr/bin/env python
"""
VenomQA REAL State Machine Journey Test

Tests against a REAL database with REAL checkpoints and rollback.
This validates the core value proposition of VenomQA.

IMPORTANT: Step actions MUST use context.state_manager.execute()
for database operations so that SAVEPOINTs work correctly.
"""

import sys
import os
import sqlite3
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from venomqa import Journey, Step, Checkpoint, Branch, Path, Client
from venomqa.runner import JourneyRunner
from venomqa.state import SQLiteStateManager

print("=" * 60)
print("VenomQA REAL State Machine Journey Test")
print("=" * 60)

db_file = tempfile.mktemp(suffix=".db")
print(f"\n1. Creating real SQLite database: {db_file}")

conn = sqlite3.connect(db_file)
conn.execute("""
    CREATE TABLE users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        name TEXT,
        balance REAL DEFAULT 0.0,
        created_at TEXT
    )
""")
conn.commit()
conn.execute(
    "INSERT INTO users (id, email, name, balance) VALUES (?, ?, ?, ?)",
    ("user-1", "test@example.com", "Test User", 100.0),
)
conn.commit()
conn.close()
print("   ✓ Tables created")
print("   ✓ Test user inserted with balance=100")


print("\n2. Initializing SQLiteStateManager...")
state_manager = SQLiteStateManager(connection_url=db_file)
state_manager.connect()
print("   ✓ StateManager connected")


balances = []


def get_balance_via_state_manager(sm):
    result = sm.execute("SELECT balance FROM users WHERE id = ?", ("user-1",))
    return result[0]["balance"] if result else 0


def track_balance(msg, sm):
    bal = get_balance_via_state_manager(sm)
    balances.append((msg, bal))
    print(f"   [{msg}] Balance: {bal}")
    return bal


def get_initial_balance(client, ctx):
    sm = ctx.state_manager
    bal = track_balance("get_initial", sm)
    ctx["initial"] = bal
    return type(
        "R", (), {"status_code": 200, "json": lambda: {"balance": bal}, "is_error": False}
    )()


def deposit_50(client, ctx):
    sm = ctx.state_manager
    sm.execute("UPDATE users SET balance = balance + 50 WHERE id = ?", ("user-1",))
    bal = track_balance("deposit_50", sm)
    ctx["after_deposit"] = bal
    return type(
        "R", (), {"status_code": 200, "json": lambda: {"balance": bal}, "is_error": False}
    )()


def withdraw_30(client, ctx):
    sm = ctx.state_manager
    sm.execute("UPDATE users SET balance = balance - 30 WHERE id = ?", ("user-1",))
    bal = track_balance("withdraw_30", sm)
    return type(
        "R", (), {"status_code": 200, "json": lambda: {"balance": bal}, "is_error": False}
    )()


def deposit_25(client, ctx):
    sm = ctx.state_manager
    sm.execute("UPDATE users SET balance = balance + 25 WHERE id = ?", ("user-1",))
    bal = track_balance("deposit_25", sm)
    return type(
        "R", (), {"status_code": 200, "json": lambda: {"balance": bal}, "is_error": False}
    )()


def verify_final(client, ctx):
    sm = ctx.state_manager
    bal = track_balance("verify_final", sm)
    ctx["final"] = bal
    return type(
        "R", (), {"status_code": 200, "json": lambda: {"balance": bal}, "is_error": False}
    )()


print("\n3. Creating stateful journey with BRANCHING...")
print("   This tests that each branch starts from the checkpoint state!")

journey = Journey(
    name="rollback_test_journey",
    description="Test that branching restores checkpoint state",
    steps=[
        Step(name="get_initial", action=get_initial_balance),
        Checkpoint(name="before_changes"),
        Step(name="deposit_50", action=deposit_50),
        Checkpoint(name="after_deposit"),
        Branch(
            checkpoint_name="after_deposit",
            paths=[
                Path(
                    name="withdraw_path",
                    steps=[
                        Step(name="withdraw_30", action=withdraw_30),
                        Step(name="verify", action=verify_final),
                    ],
                ),
                Path(
                    name="another_deposit_path",
                    steps=[
                        Step(name="deposit_25", action=deposit_25),
                        Step(name="verify", action=verify_final),
                    ],
                ),
            ],
        ),
    ],
)
print("   ✓ Journey created")
print("   Expected flow:")
print("     1. Initial: 100")
print("     2. After deposit: 150")
print("     3. Branch 1 (withdraw): 150 -> 120")
print("     4. Branch 2 (deposit): 150 -> 175 (ROLLBACK from 120!)")


print("\n4. Running journey with StateManager...")

client = Client("http://localhost:8001", timeout=1.0, retry_count=1)
client.connect()

runner = JourneyRunner(client=client, state_manager=state_manager)
result = runner.run(journey)

client.disconnect()


print("\n" + "=" * 60)
print("RESULTS ANALYSIS")
print("=" * 60)

print(f"\nJourney Success: {result.success}")
print(f"Steps Passed: {result.passed_steps}/{result.total_steps}")

print("\nBalance tracking:")
for msg, bal in balances:
    print(f"   {msg}: {bal}")

print("\n" + "=" * 60)
print("VALIDATION")
print("=" * 60)

initial_balance = 100.0
after_first_deposit = 150.0
after_withdraw = 120.0
after_second_deposit_with_rollback = 175.0
after_second_deposit_without_rollback = 145.0

withdraw_final = None
deposit_final = None

for i, (msg, bal) in enumerate(balances):
    if msg == "verify_final":
        if withdraw_final is None:
            withdraw_final = bal
        else:
            deposit_final = bal

print(f"\nBranch 1 (withdraw) final: {withdraw_final}")
print(f"Branch 2 (deposit) final: {deposit_final}")

if withdraw_final == after_withdraw:
    print("✓ Branch 1 correct: 150 -> 120")
else:
    print(f"✗ Branch 1 wrong: expected 120, got {withdraw_final}")

if deposit_final == after_second_deposit_with_rollback:
    print("✓ Branch 2 correct: 150 -> 175 (ROLLBACK WORKED!)")
    rollback_worked = True
elif deposit_final == after_second_deposit_without_rollback:
    print("✗ Branch 2 shows NO rollback: 120 -> 145")
    print("   This means rollback is NOT working!")
    rollback_worked = False
else:
    print(f"? Branch 2 unexpected: {deposit_final}")
    rollback_worked = False


print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

if result.success:
    print("✅ Journey executed successfully")
else:
    print("❌ Journey had failures")

if rollback_worked:
    print("✅ STATE ROLLBACK IS WORKING!")
    print("   Each branch correctly starts from checkpoint state")
else:
    print("❌ STATE ROLLBACK NOT WORKING")
    print("   Branches are NOT isolated - state carries over")

state_manager.disconnect()
os.unlink(db_file)
print("\n" + "=" * 60)
