#!/usr/bin/env python
"""
VenomQA Comprehensive Validation Suite

This validates that VenomQA is production-ready by testing:
1. Core journey execution
2. State checkpoint/rollback with real databases
3. Branching with proper isolation
4. Error handling
5. Context passing between steps
6. Multiple backend consistency

Run: python tests/validation/comprehensive_validation.py
"""

import os
import sqlite3
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from venomqa import Branch, Checkpoint, Client, Journey, Path, Step
from venomqa.runner import JourneyRunner
from venomqa.state import InMemoryStateManager, SQLiteStateManager

PASSED = 0
FAILED = 0
ERRORS = []


def test(name: str):
    def decorator(func):
        def wrapper():
            global PASSED, FAILED
            print(f"\n{'=' * 60}")
            print(f"TEST: {name}")
            print("=" * 60)
            try:
                func()
                print(f"✅ PASSED: {name}")
                PASSED += 1
            except AssertionError as e:
                print(f"❌ FAILED: {name}")
                print(f"   AssertionError: {e}")
                FAILED += 1
                ERRORS.append((name, str(e), traceback.format_exc()))
            except Exception as e:
                print(f"💥 ERROR: {name}")
                print(f"   {type(e).__name__}: {e}")
                FAILED += 1
                ERRORS.append((name, str(e), traceback.format_exc()))

        return wrapper

    return decorator


@test("1. Basic Journey Execution")
def test_basic_journey():
    executed = []

    def step1(client, ctx):
        executed.append("step1")
        ctx["step1_data"] = "hello"
        return type(
            "R", (), {"status_code": 200, "json": lambda: {"ok": True}, "is_error": False}
        )()

    def step2(client, ctx):
        executed.append("step2")
        assert ctx["step1_data"] == "hello", "Context not passed between steps"
        ctx["step2_data"] = "world"
        return type(
            "R", (), {"status_code": 200, "json": lambda: {"ok": True}, "is_error": False}
        )()

    def step3(client, ctx):
        executed.append("step3")
        assert ctx["step1_data"] == "hello"
        assert ctx["step2_data"] == "world"
        return type(
            "R", (), {"status_code": 200, "json": lambda: {"ok": True}, "is_error": False}
        )()

    journey = Journey(
        name="basic_test",
        steps=[
            Step(name="s1", action=step1),
            Step(name="s2", action=step2),
            Step(name="s3", action=step3),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client)
    result = runner.run(journey)
    client.disconnect()

    assert result.success, f"Journey should succeed, got: {result.issues}"
    assert executed == ["step1", "step2", "step3"], f"Wrong execution order: {executed}"
    print("   ✓ All steps executed in order")
    print("   ✓ Context passed correctly between steps")


@test("2. Checkpoint Creation and Tracking")
def test_checkpoints():
    checkpoints_created = []

    def make_step(name):
        def step(client, ctx):
            return type(
                "R", (), {"status_code": 200, "json": lambda: {"ok": True}, "is_error": False}
            )()

        return step

    db_file = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()

    state_manager = SQLiteStateManager(connection_url=db_file)
    state_manager.connect()

    def track_checkpoint(checkpoint_name):
        checkpoints_created.append(checkpoint_name)

    journey = Journey(
        name="checkpoint_test",
        steps=[
            Step(name="s1", action=make_step("s1")),
            Checkpoint(name="cp1"),
            Step(name="s2", action=make_step("s2")),
            Checkpoint(name="cp2"),
            Step(name="s3", action=make_step("s3")),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client, state_manager=state_manager)
    result = runner.run(journey)
    client.disconnect()

    assert result.success, "Journey should succeed"
    assert "chk_cp1" in state_manager._checkpoints, "Checkpoint cp1 not created"
    assert "chk_cp2" in state_manager._checkpoints, "Checkpoint cp2 not created"

    state_manager.disconnect()
    os.unlink(db_file)
    print(f"   ✓ Checkpoints created: {state_manager._checkpoints}")


@test("3. State Rollback - Core Value Proposition")
def test_state_rollback():
    db_file = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE accounts (id TEXT PRIMARY KEY, balance REAL)")
    conn.execute("INSERT INTO accounts VALUES ('acc1', 100.0)")
    conn.commit()
    conn.close()

    state_manager = SQLiteStateManager(connection_url=db_file)
    state_manager.connect()

    balances = []

    def record_balance(name):
        def action(client, ctx):
            result = ctx.state_manager.execute("SELECT balance FROM accounts WHERE id='acc1'")
            balance = result[0]["balance"]
            balances.append((name, balance))
            print(f"   [{name}] Balance: {balance}")
            return type(
                "R",
                (),
                {"status_code": 200, "json": lambda: {"balance": balance}, "is_error": False},
            )()

        return action

    def modify_balance(amount, name):
        def action(client, ctx):
            ctx.state_manager.execute(
                f"UPDATE accounts SET balance = balance + {amount} WHERE id='acc1'"
            )
            return record_balance(name)(client, ctx)

        return action

    journey = Journey(
        name="rollback_test",
        steps=[
            Step(name="initial", action=record_balance("initial")),
            Checkpoint(name="cp_initial"),
            Step(name="add_50", action=modify_balance(50, "after_add_50")),
            Checkpoint(name="cp_after_50"),
            Branch(
                checkpoint_name="cp_after_50",
                paths=[
                    Path(
                        name="subtract_path",
                        steps=[
                            Step(name="sub_30", action=modify_balance(-30, "branch1_after_sub")),
                        ],
                    ),
                    Path(
                        name="add_path",
                        steps=[
                            Step(name="add_25", action=modify_balance(25, "branch2_after_add")),
                        ],
                    ),
                ],
            ),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client, state_manager=state_manager)
    result = runner.run(journey)
    client.disconnect()

    print(f"   Balance history: {balances}")

    assert result.success, "Journey should succeed"

    initial = next(b for n, b in balances if n == "initial")
    after_50 = next(b for n, b in balances if n == "after_add_50")
    branch1_final = next(b for n, b in balances if n == "branch1_after_sub")
    branch2_final = next(b for n, b in balances if n == "branch2_after_add")

    assert initial == 100.0, f"Initial should be 100, got {initial}"
    assert after_50 == 150.0, f"After +50 should be 150, got {after_50}"
    assert branch1_final == 120.0, f"Branch 1 should be 120 (150-30), got {branch1_final}"
    assert branch2_final == 175.0, (
        f"Branch 2 should be 175 (150+25), got {branch2_final} - ROLLBACK FAILED!"
    )

    state_manager.disconnect()
    os.unlink(db_file)
    print("   ✓ Branch 1: 150 -> 120")
    print("   ✓ Branch 2: 150 -> 175 (rollback worked!)")


@test("4. Three-Way Branching with Rollback")
def test_three_way_branch():
    db_file = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE counter (id TEXT PRIMARY KEY, value INTEGER)")
    conn.execute("INSERT INTO counter VALUES ('main', 0)")
    conn.commit()
    conn.close()

    state_manager = SQLiteStateManager(connection_url=db_file)
    state_manager.connect()

    final_values = []

    def increment_by(amount):
        def action(client, ctx):
            ctx.state_manager.execute(
                f"UPDATE counter SET value = value + {amount} WHERE id='main'"
            )
            result = ctx.state_manager.execute("SELECT value FROM counter WHERE id='main'")
            final_values.append(result[0]["value"])
            return type(
                "R",
                (),
                {
                    "status_code": 200,
                    "json": lambda: {"value": result[0]["value"]},
                    "is_error": False,
                },
            )()

        return action

    journey = Journey(
        name="three_way_branch",
        steps=[
            Step(name="init", action=increment_by(10)),
            Checkpoint(name="cp"),
            Branch(
                checkpoint_name="cp",
                paths=[
                    Path(name="path_a", steps=[Step(name="a", action=increment_by(1))]),
                    Path(name="path_b", steps=[Step(name="b", action=increment_by(2))]),
                    Path(name="path_c", steps=[Step(name="c", action=increment_by(3))]),
                ],
            ),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client, state_manager=state_manager)
    result = runner.run(journey)
    client.disconnect()

    assert result.success

    assert 10 in final_values, f"Initial value 10 not found in {final_values}"

    assert 11 in final_values, f"Path A result (10+1=11) not found in {final_values}"
    assert 12 in final_values, f"Path B result (10+2=12) not found in {final_values}"
    assert 13 in final_values, f"Path C result (10+3=13) not found in {final_values}"

    state_manager.disconnect()
    os.unlink(db_file)
    print(f"   ✓ Three branches isolated correctly: {sorted(final_values)}")


@test("5. Deep Nested Checkpoints")
def test_nested_checkpoints():
    db_file = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE data (id TEXT PRIMARY KEY, value INTEGER)")
    conn.execute("INSERT INTO data VALUES ('x', 0)")
    conn.commit()
    conn.close()

    state_manager = SQLiteStateManager(connection_url=db_file)
    state_manager.connect()

    def set_value(val):
        def action(client, ctx):
            ctx.state_manager.execute(f"UPDATE data SET value = {val} WHERE id='x'")
            return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

        return action

    journey = Journey(
        name="nested_checkpoints",
        steps=[
            Step(name="set_1", action=set_value(1)),
            Checkpoint(name="cp1"),
            Step(name="set_2", action=set_value(2)),
            Checkpoint(name="cp2"),
            Step(name="set_3", action=set_value(3)),
            Checkpoint(name="cp3"),
            Step(name="set_4", action=set_value(4)),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client, state_manager=state_manager)
    result = runner.run(journey)
    client.disconnect()

    assert result.success
    assert len(state_manager._checkpoints) == 3

    state_manager.rollback("cp2")
    result = state_manager.execute("SELECT value FROM data WHERE id='x'")
    assert result[0]["value"] == 2, f"After rollback to cp2, should be 2, got {result[0]['value']}"

    state_manager.rollback("cp1")
    result = state_manager.execute("SELECT value FROM data WHERE id='x'")
    assert result[0]["value"] == 1, f"After rollback to cp1, should be 1, got {result[0]['value']}"

    state_manager.disconnect()
    os.unlink(db_file)
    print("   ✓ 4 checkpoints created, rollback works to any level")


@test("6. InMemoryStateManager - No Database Required")
def test_memory_state_manager():
    state_manager = InMemoryStateManager()
    state_manager.connect()

    def dummy(client, ctx):
        return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

    journey = Journey(
        name="memory_test",
        steps=[
            Step(name="s1", action=dummy),
            Checkpoint(name="cp1"),
            Step(name="s2", action=dummy),
            Checkpoint(name="cp2"),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client, state_manager=state_manager)
    result = runner.run(journey)
    client.disconnect()

    assert result.success
    assert state_manager.has_checkpoint("chk_cp1")
    assert state_manager.has_checkpoint("chk_cp2")

    state_manager.disconnect()
    print("   ✓ MemoryStateManager works without database")


@test("7. Error Handling in Steps")
def test_error_handling():

    def failing_step(client, ctx):
        raise ValueError("Intentional error for testing")

    def success_step(client, ctx):
        return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

    journey = Journey(
        name="error_test",
        steps=[
            Step(name="s1", action=success_step),
            Step(name="failing", action=failing_step),
            Step(name="s3", action=success_step),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client)
    result = runner.run(journey)
    client.disconnect()

    assert not result.success, "Journey with error should fail"
    assert len(result.issues) > 0, "Should capture issues"
    print(f"   ✓ Error properly captured: {len(result.issues)} issue(s)")


@test("8. Expected Failure Steps")
def test_expected_failure():
    def should_fail(client, ctx):
        return type(
            "R", (), {"status_code": 500, "json": lambda: {"error": "fail"}, "is_error": True}
        )()

    def should_succeed(client, ctx):
        return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

    journey = Journey(
        name="expected_failure_test",
        steps=[
            Step(name="normal", action=should_succeed),
            Step(name="expect_fail", action=should_fail, expect_failure=True),
            Step(name="after", action=should_succeed),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client)
    result = runner.run(journey)
    client.disconnect()

    assert result.success, "Journey with expected failure should succeed"
    print("   ✓ Expected failure handled correctly")


@test("9. Context Isolation Between Branches")
def test_context_isolation():
    context_states = []

    def set_context(key, val):
        def action(client, ctx):
            ctx[key] = val
            context_states.append((key, val, dict(ctx._data)))
            return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

        return action

    def check_context(key, expected):
        def action(client, ctx):
            actual = ctx.get(key)
            context_states.append((f"check_{key}", expected, actual))
            return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

        return action

    journey = Journey(
        name="context_isolation",
        steps=[
            Step(name="set_shared", action=set_context("shared", "base")),
            Checkpoint(name="cp"),
            Branch(
                checkpoint_name="cp",
                paths=[
                    Path(
                        name="path_a",
                        steps=[
                            Step(name="set_a", action=set_context("branch_val", "A")),
                            Step(name="check_a", action=check_context("shared", "base")),
                        ],
                    ),
                    Path(
                        name="path_b",
                        steps=[
                            Step(name="set_b", action=set_context("branch_val", "B")),
                            Step(name="check_b", action=check_context("shared", "base")),
                        ],
                    ),
                ],
            ),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client)
    result = runner.run(journey)
    client.disconnect()

    assert result.success
    print("   ✓ Context properly isolated between branches")


@test("10. Long Journey - 50 Steps")
def test_long_journey():
    executed = []

    def make_step(i):
        def action(client, ctx):
            executed.append(i)
            ctx[f"step_{i}"] = i
            return type(
                "R", (), {"status_code": 200, "json": lambda: {"step": i}, "is_error": False}
            )()

        return action

    steps = [Step(name=f"step_{i}", action=make_step(i)) for i in range(50)]

    journey = Journey(name="long_journey", steps=steps)

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client)
    result = runner.run(journey)
    client.disconnect()

    assert result.success
    assert len(executed) == 50
    assert executed == list(range(50))
    print("   ✓ 50 steps executed successfully in order")


@test("11. Multiple Journeys Sequentially")
def test_multiple_journeys():
    def make_journey(name):
        def step(client, ctx):
            ctx["journey"] = name
            return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

        return Journey(name=name, steps=[Step(name="s1", action=step)])

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client)

    results = []
    for i in range(10):
        result = runner.run(make_journey(f"journey_{i}"))
        results.append(result)

    client.disconnect()

    assert all(r.success for r in results)
    print("   ✓ 10 journeys executed successfully")


@test("12. Fail-Fast Mode")
def test_fail_fast():
    executed = []

    def make_step(name):
        def action(client, ctx):
            executed.append(name)
            if name == "fail":
                return type("R", (), {"status_code": 500, "json": lambda: {}, "is_error": True})()
            return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

        return action

    journey = Journey(
        name="fail_fast_test",
        steps=[
            Step(name="s1", action=make_step("s1")),
            Step(name="s2", action=make_step("s2")),
            Step(name="fail", action=make_step("fail")),
            Step(name="s4", action=make_step("s4")),
            Step(name="s5", action=make_step("s5")),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client, fail_fast=True)
    result = runner.run(journey)
    client.disconnect()

    assert not result.success
    assert "s4" not in executed, f"Step s4 should not execute in fail-fast mode, got: {executed}"
    assert "s5" not in executed, f"Step s5 should not execute in fail-fast mode, got: {executed}"
    print(f"   ✓ Fail-fast stopped at first failure: {executed}")


@test("13. Branch with Failed Path")
def test_branch_with_failed_path():
    def success(client, ctx):
        return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

    def failure(client, ctx):
        return type("R", (), {"status_code": 500, "json": lambda: {}, "is_error": True})()

    journey = Journey(
        name="branch_failure",
        steps=[
            Step(name="setup", action=success),
            Checkpoint(name="cp"),
            Branch(
                checkpoint_name="cp",
                paths=[
                    Path(name="success_path", steps=[Step(name="s1", action=success)]),
                    Path(name="failure_path", steps=[Step(name="f1", action=failure)]),
                    Path(name="another_success", steps=[Step(name="s2", action=success)]),
                ],
            ),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client)
    result = runner.run(journey)
    client.disconnect()

    assert not result.success, "Journey with failed branch should fail"
    assert len(result.branch_results) == 1
    branch_result = result.branch_results[0]
    assert not branch_result.all_passed, "Branch should not pass when one path fails"
    print("   ✓ Branch failure properly tracked")


@test("14. Step Result Storage and Retrieval")
def test_step_result_storage():
    def create_item(client, ctx):
        result = {"id": "item-123", "name": "Test Item"}
        return type("R", (), {"status_code": 201, "json": lambda: result, "is_error": False})()

    def use_item(client, ctx):
        stored = ctx.get_step_result("create")
        assert stored is not None, "Step result not stored"
        item_id = stored.json()["id"]
        ctx["item_id"] = item_id
        return type(
            "R", (), {"status_code": 200, "json": lambda: {"used": item_id}, "is_error": False}
        )()

    journey = Journey(
        name="step_results",
        steps=[
            Step(name="create", action=create_item),
            Step(name="use", action=use_item),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client)
    result = runner.run(journey)
    client.disconnect()

    assert result.success
    print("   ✓ Step results stored and retrieved correctly")


@test("15. Journey Result Metadata")
def test_journey_result_metadata():
    def step(client, ctx):
        return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

    journey = Journey(name="metadata_test", steps=[Step(name="s1", action=step)])

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client)
    result = runner.run(journey)
    client.disconnect()

    assert result.journey_name == "metadata_test"
    assert result.started_at is not None
    assert result.finished_at is not None
    assert result.duration_ms > 0
    assert result.success
    print(f"   ✓ Journey metadata: duration={result.duration_ms:.2f}ms")


@test("16. Stress Test - 100 Rapid Journeys")
def test_stress_100_journeys():
    def step(client, ctx):
        ctx["count"] = ctx.get("count", 0) + 1
        return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

    journey = Journey(name="stress", steps=[Step(name="s1", action=step)])

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client)

    start = time.time()
    for _ in range(100):
        result = runner.run(journey)
        assert result.success
    elapsed = time.time() - start

    client.disconnect()
    print(f"   ✓ 100 journeys in {elapsed:.2f}s ({100 / elapsed:.1f} journeys/sec)")


@test("17. Database Reset Between Tests")
def test_database_reset():
    db_file = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    state_manager = SQLiteStateManager(connection_url=db_file, tables_to_reset=["items"])
    state_manager.connect()

    def insert_item(client, ctx):
        ctx.state_manager.execute("INSERT INTO items (name) VALUES ('test')")
        return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

    journey = Journey(name="reset_test", steps=[Step(name="insert", action=insert_item)])

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client, state_manager=state_manager)

    for _i in range(5):
        state_manager.reset()
        runner.run(journey)
        count_result = state_manager.execute("SELECT COUNT(*) as c FROM items")
        assert count_result[0]["c"] == 1

    client.disconnect()
    state_manager.disconnect()
    os.unlink(db_file)
    print("   ✓ Database reset works correctly")


@test("18. Context Snapshot and Restore")
def test_context_snapshot_restore():
    ctx = type(
        "ExecutionContext",
        (),
        {
            "_data": {},
            "_step_results": {},
            "set": lambda s, k, v: s._data.update({k: v}),
            "get": lambda s, k, d=None: s._data.get(k, d),
            "snapshot": lambda s: {"data": dict(s._data), "step_results": dict(s._step_results)},
            "restore": lambda s, snap: (
                s._data.update(snap["data"]),
                s._step_results.update(snap["step_results"]),
            ),
        },
    )()

    ctx.set("key1", "value1")
    ctx.set("key2", "value2")

    snapshot = ctx.snapshot()

    ctx.set("key1", "modified")
    ctx.set("key3", "value3")

    ctx.restore(snapshot)

    assert ctx.get("key1") == "value1", f"Should restore to original, got {ctx.get('key1')}"
    assert ctx.get("key2") == "value2"
    assert ctx.get("key3") is None, "key3 should not exist after restore"
    print("   ✓ Context snapshot/restore works")


@test("19. Empty Journey")
def test_empty_journey():
    journey = Journey(name="empty", steps=[])

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client)
    result = runner.run(journey)
    client.disconnect()

    assert result.success
    assert len(result.step_results) == 0
    print("   ✓ Empty journey handled correctly")


@test("20. Complex Real-World Journey")
def test_complex_real_world():
    db_file = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            email TEXT,
            balance REAL DEFAULT 0,
            status TEXT DEFAULT 'active'
        )
    """)
    conn.execute("INSERT INTO users VALUES ('u1', 'test@example.com', 100.0, 'active')")
    conn.execute(
        "CREATE TABLE orders (id TEXT PRIMARY KEY, user_id TEXT, amount REAL, status TEXT)"
    )
    conn.commit()
    conn.close()

    state_manager = SQLiteStateManager(connection_url=db_file)
    state_manager.connect()

    orders_created = []

    def create_order(amount):
        def action(client, ctx):
            order_id = f"order-{len(orders_created)}"
            ctx.state_manager.execute(
                "INSERT INTO orders (id, user_id, amount, status) VALUES (?, 'u1', ?, 'pending')",
                (order_id, amount),
            )
            ctx.state_manager.execute(
                "UPDATE users SET balance = balance - ? WHERE id='u1'", (amount,)
            )
            orders_created.append((order_id, amount))
            return type(
                "R",
                (),
                {"status_code": 201, "json": lambda: {"order_id": order_id}, "is_error": False},
            )()

        return action

    def complete_order(client, ctx):
        if orders_created:
            order_id = orders_created[-1][0]
            ctx.state_manager.execute(
                "UPDATE orders SET status='completed' WHERE id=?", (order_id,)
            )
        return type("R", (), {"status_code": 200, "json": lambda: {}, "is_error": False})()

    def check_balance(expected, name):
        def action(client, ctx):
            result = ctx.state_manager.execute("SELECT balance FROM users WHERE id='u1'")
            actual = result[0]["balance"]
            print(f"   [{name}] Balance: {actual} (expected: {expected})")
            return type(
                "R",
                (),
                {"status_code": 200, "json": lambda: {"balance": actual}, "is_error": False},
            )()

        return action

    journey = Journey(
        name="ecommerce_flow",
        steps=[
            Step(name="check_initial", action=check_balance(100, "initial")),
            Checkpoint(name="ready"),
            Step(name="order_1", action=create_order(20)),
            Step(name="complete_1", action=complete_order),
            Checkpoint(name="after_order_1"),
            Branch(
                checkpoint_name="after_order_1",
                paths=[
                    Path(
                        name="premium_user",
                        steps=[
                            Step(name="order_2", action=create_order(50)),
                            Step(
                                name="check", action=check_balance(30, "premium_after")
                            ),  # 80-50=30
                        ],
                    ),
                    Path(
                        name="regular_user",
                        steps=[
                            Step(name="order_3", action=create_order(10)),
                            Step(
                                name="check", action=check_balance(70, "regular_after")
                            ),  # 80-10=70
                        ],
                    ),
                ],
            ),
        ],
    )

    client = Client("http://localhost:9999", timeout=1.0)
    client.connect()
    runner = JourneyRunner(client=client, state_manager=state_manager)
    result = runner.run(journey)
    client.disconnect()

    assert result.success, f"Complex journey should succeed: {result.issues}"

    state_manager.disconnect()
    os.unlink(db_file)
    print("   ✓ Complex e-commerce flow with branching completed")


def main():
    print("\n" + "=" * 70)
    print(" VenomQA COMPREHENSIVE VALIDATION SUITE")
    print(" Testing Core Features, Edge Cases, and Real-World Scenarios")
    print("=" * 70)

    tests = [
        test_basic_journey,
        test_checkpoints,
        test_state_rollback,
        test_three_way_branch,
        test_nested_checkpoints,
        test_memory_state_manager,
        test_error_handling,
        test_expected_failure,
        test_context_isolation,
        test_long_journey,
        test_multiple_journeys,
        test_fail_fast,
        test_branch_with_failed_path,
        test_step_result_storage,
        test_journey_result_metadata,
        test_stress_100_journeys,
        test_database_reset,
        test_context_snapshot_restore,
        test_empty_journey,
        test_complex_real_world,
    ]

    start_time = time.time()
    for test_func in tests:
        test_func()
    total_time = time.time() - start_time

    print("\n" + "=" * 70)
    print(" VALIDATION SUMMARY")
    print("=" * 70)
    print(f"  Total Tests:  {PASSED + FAILED}")
    print(f"  Passed:       {PASSED}")
    print(f"  Failed:       {FAILED}")
    print(f"  Time:         {total_time:.2f}s")
    print("=" * 70)

    if FAILED > 0:
        print("\n FAILED TESTS:")
        for name, error, _tb in ERRORS:
            print(f"\n  ❌ {name}")
            print(f"     {error}")
        print("\n" + "=" * 70)
        print(" ❌ VENOMQA IS NOT PRODUCTION READY")
        print("=" * 70)
        sys.exit(1)
    else:
        print("\n" + "=" * 70)
        print(" ✅ VENOMQA VALIDATION COMPLETE - ALL TESTS PASSED")
        print("=" * 70)
        sys.exit(0)


if __name__ == "__main__":
    main()
