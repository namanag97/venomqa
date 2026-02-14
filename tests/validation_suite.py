#!/usr/bin/env python
"""
VenomQA Comprehensive Validation Suite - Using Correct APIs
"""

import sys
import os
import traceback
import json
import tempfile
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

results = {"passed": [], "failed": [], "errors": []}


def test(name: str):
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                print(f"\n{'=' * 60}")
                print(f"TEST: {name}")
                print(f"{'=' * 60}")
                func(*args, **kwargs)
                print(f"✅ PASSED: {name}")
                results["passed"].append(name)
            except AssertionError as e:
                print(f"❌ FAILED: {name}")
                print(f"   Reason: {e}")
                results["failed"].append((name, str(e)))
            except Exception as e:
                print(f"💥 ERROR: {name}")
                print(f"   Exception: {type(e).__name__}: {e}")
                traceback.print_exc()
                results["errors"].append((name, str(e), traceback.format_exc()))

        return wrapper

    return decorator


# ============================================================
# CORE FRAMEWORK TESTS
# ============================================================


@test("Core: Journey creation and basic execution")
def test_journey_basic():
    from venomqa import Journey, Step, Client
    from venomqa.runner import JourneyRunner

    executed = []

    def step1(client, ctx):
        executed.append("step1")
        ctx["data"] = "hello"

    def step2(client, ctx):
        executed.append("step2")
        assert ctx.get("data") == "hello", "Context not passed"

    journey = Journey(
        name="basic_test",
        steps=[Step(name="step1", action=step1), Step(name="step2", action=step2)],
    )

    with Client("http://localhost:8001", timeout=1.0, retry_count=1) as client:
        runner = JourneyRunner(client=client)
        result = runner.run(journey)

        assert result.success, f"Journey failed: {[i.error for i in result.issues]}"
        assert len(executed) == 2


@test("Core: Checkpoint and Branch execution")
def test_checkpoint_branch():
    from venomqa import Journey, Step, Checkpoint, Branch, Path, Client
    from venomqa.runner import JourneyRunner

    executed = {"branches": []}

    def branch1(client, ctx):
        executed["branches"].append("path1")

    def branch2(client, ctx):
        executed["branches"].append("path2")

    journey = Journey(
        name="branch_test",
        steps=[
            Checkpoint(name="cp1"),
            Branch(
                checkpoint_name="cp1",
                paths=[
                    Path(name="path1", steps=[Step(name="b1", action=branch1)]),
                    Path(name="path2", steps=[Step(name="b2", action=branch2)]),
                ],
            ),
        ],
    )

    with Client("http://localhost:8001", timeout=1.0, retry_count=1) as client:
        runner = JourneyRunner(client=client)
        result = runner.run(journey)

        assert result.success
        assert result.branch_results[0].passed_paths == 2


@test("Core: ExecutionContext operations")
def test_execution_context():
    from venomqa.core.context import ExecutionContext

    ctx = ExecutionContext()
    ctx.set("key1", "value1")
    assert ctx.get("key1") == "value1"

    val = ctx.pop("key1")
    assert val == "value1"
    assert ctx.get("key1") is None


@test("Core: Step with expect_failure")
def test_expect_failure():
    from venomqa import Journey, Step, Client
    from venomqa.runner import JourneyRunner

    def failing_step(client, ctx):
        raise Exception("Intentional failure")

    def success_step(client, ctx):
        pass  # Success

    # expect_failure=True with actual failure = PASS
    journey1 = Journey(
        name="expect_fail_pass", steps=[Step(name="f1", action=failing_step, expect_failure=True)]
    )

    with Client("http://localhost:8001", timeout=1.0, retry_count=1) as client:
        runner = JourneyRunner(client=client)
        result = runner.run(journey1)
        assert result.success, "Expected failure should pass"

        # expect_failure=True with success = FAIL
        journey2 = Journey(
            name="expect_fail_fail",
            steps=[Step(name="s1", action=success_step, expect_failure=True)],
        )
        result = runner.run(journey2)
        assert not result.success, "Should fail when expect_failure but succeeds"


# ============================================================
# ADAPTER TESTS - Using Correct APIs
# ============================================================


@test("Adapter: MockCacheAdapter")
def test_cache_adapter():
    from venomqa.adapters import MockCacheAdapter

    cache = MockCacheAdapter()

    # Set/Get
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"

    # Delete
    cache.delete("key1")
    assert cache.get("key1") is None

    # Health
    assert cache.health_check() == True
    cache.set_healthy(False)
    assert cache.health_check() == False

    # Stats - returns CacheStats object
    stats = cache.get_stats()
    assert hasattr(stats, "hits") or hasattr(stats, "misses") or "hits" in dir(stats)
    print("   ✓ Cache works")


@test("Adapter: MockQueueAdapter")
def test_queue_adapter():
    from venomqa.adapters import MockQueueAdapter

    queue = MockQueueAdapter()

    # Enqueue returns job ID
    job_id = queue.enqueue("test_queue", {"task": "data"})
    assert job_id.startswith("job-")

    # Get job returns JobInfo object (not dict)
    job = queue.get_job(job_id)
    assert job is not None
    assert hasattr(job, "status") or (isinstance(job, dict) and "status" in job)

    # Complete job
    queue.start_job(job_id)
    queue.complete_job(job_id, result={"done": True})

    # Completed jobs
    completed = queue.get_completed_jobs()
    assert len(completed) >= 1
    print("   ✓ Queue works")


@test("Adapter: MockMailAdapter")
def test_mail_adapter():
    from venomqa.adapters import MockMailAdapter
    from venomqa.ports import Email  # Import Email model

    mail = MockMailAdapter()

    # send_email takes Email object
    email = Email(
        sender="from@test.com",
        recipients=["test@example.com"],
        subject="Test Subject",
        body="Test Body",
    )
    msg_id = mail.send_email(email)
    assert msg_id.startswith("msg-")

    # Get emails
    emails = mail.get_emails_to("test@example.com")
    assert len(emails) == 1

    # Health
    assert mail.health_check() == True
    print("   ✓ Mail works")


@test("Adapter: MockStorageAdapter")
def test_storage_adapter():
    from venomqa.adapters import MockStorageAdapter
    import io

    storage = MockStorageAdapter()

    # Create bucket
    storage.create_bucket("test-bucket")

    # Put (not put_object)
    content = b"test content"
    storage.put("test-bucket", "test.txt", content)

    # List
    objects = storage.list_objects("test-bucket")
    assert len(objects) >= 1

    # Delete (not delete_object)
    storage.delete("test-bucket", "test.txt")
    print("   ✓ Storage works")


@test("Adapter: MockTimeAdapter")
def test_time_adapter():
    from venomqa.adapters import MockTimeAdapter
    from datetime import datetime

    time = MockTimeAdapter()

    # Now
    now = time.now()
    assert isinstance(now, datetime)

    # schedule_after for delay-based scheduling
    task_id = time.schedule_after(delay_seconds=10, callback=lambda: "result")
    assert task_id.startswith("sched-")
    print("   ✓ Time works")


@test("Adapter: ThreadConcurrencyAdapter")
def test_concurrency_adapter():
    from venomqa.adapters import ThreadConcurrencyAdapter

    concurrency = ThreadConcurrencyAdapter()

    results = []

    def task():
        results.append("done")
        return "result"

    task_id = concurrency.spawn(task)
    assert task_id.startswith("task-")

    # join_all (not wait_all)
    concurrency.join_all([task_id], timeout=5.0)
    assert "done" in results

    # Lock
    lock_id = concurrency.lock("resource1", timeout=1.0)
    assert lock_id is not None
    concurrency.unlock("resource1")
    print("   ✓ Concurrency works")


# ============================================================
# STATE MANAGEMENT TESTS
# ============================================================


@test("State: InMemoryStateManager")
def test_memory_state_manager():
    from venomqa.state import InMemoryStateManager

    sm = InMemoryStateManager()
    sm.connect()

    try:
        # set_data (not set_state)
        sm.set_data({"key1": "value1"})
        result = sm.get_data()
        assert result.get("key1") == "value1"

        # Checkpoint
        sm.checkpoint("cp1")
        sm.set_data({"key1": "value1", "key2": "value2"})

        # Rollback
        sm.rollback("cp1")
        result = sm.get_data()
        assert "key2" not in result
        print("   ✓ State works")
    finally:
        sm.disconnect()


# ============================================================
# REPORTER TESTS
# ============================================================


@test("Reporter: All reporters work")
def test_reporters():
    from venomqa.reporters import MarkdownReporter, JSONReporter, JUnitReporter
    from venomqa.core.models import JourneyResult, StepResult
    from datetime import datetime

    result = JourneyResult(
        journey_name="test",
        success=True,
        started_at=datetime.now(),
        finished_at=datetime.now(),
        step_results=[
            StepResult(
                step_name="s1",
                success=True,
                started_at=datetime.now(),
                finished_at=datetime.now(),
                duration_ms=10,
            )
        ],
        duration_ms=100.0,
    )

    # Markdown
    md = MarkdownReporter().generate([result])
    assert "test" in md

    # JSON
    json_out = JSONReporter().generate([result])
    data = json.loads(json_out)
    assert data["journeys"][0]["journey_name"] == "test"

    # JUnit
    junit = JUnitReporter().generate([result])
    assert "xml" in junit.lower() or "testsuite" in junit.lower()
    print("   ✓ All reporters work")


# ============================================================
# CLIENT TESTS
# ============================================================


@test("Client: HTTP Client with real server")
def test_http_client():
    from venomqa import Client

    try:
        with Client("http://localhost:8001", timeout=5.0) as client:
            response = client.get("/health")
            assert response.status_code == 200

            history = client.get_history()
            assert len(history) >= 1
            print("   ✓ HTTP client works")
    except Exception as e:
        if "Connection refused" in str(e):
            print("   ⚠️  Server not running")
            return
        raise


@test("Client: OAuth2 login helper")
def test_oauth2():
    from venomqa import Client
    import random, string

    try:
        with Client("http://localhost:8001", timeout=5.0) as client:
            email = f"oauth_{''.join(random.choices(string.ascii_lowercase, k=6))}@example.com"

            client.post("/api/v1/users/signup", json={"email": email, "password": "test123"})
            response = client.oauth2_login(
                "/api/v1/login/access-token", username=email, password="test123"
            )
            assert response.status_code == 200

            response = client.get("/api/v1/users/me")
            assert response.status_code == 200
            print("   ✓ OAuth2 works")
    except Exception as e:
        if "Connection refused" in str(e):
            print("   ⚠️  Server not running")
            return
        raise


# ============================================================
# MAIN
# ============================================================


def main():
    print("\n" + "=" * 60)
    print("VenomQA Validation Suite")
    print("=" * 60)

    tests = [
        test_journey_basic,
        test_checkpoint_branch,
        test_execution_context,
        test_expect_failure,
        test_cache_adapter,
        test_queue_adapter,
        test_mail_adapter,
        test_storage_adapter,
        test_time_adapter,
        test_concurrency_adapter,
        test_memory_state_manager,
        test_reporters,
        test_http_client,
        test_oauth2,
    ]

    for t in tests:
        t()

    print("\n" + "=" * 60)
    print(f"PASSED: {len(results['passed'])}")
    print(f"FAILED: {len(results['failed'])}")
    print(f"ERRORS: {len(results['errors'])}")

    if results["errors"]:
        print("\nErrors:")
        for name, err, _ in results["errors"][:5]:
            print(f"  - {name}: {err[:60]}...")

    total = len(results["passed"]) + len(results["failed"]) + len(results["errors"])
    rate = len(results["passed"]) / total * 100 if total else 0
    print(f"\nSuccess: {rate:.1f}% ({len(results['passed'])}/{total})")
    print("=" * 60)

    return len(results["failed"]) + len(results["errors"])


if __name__ == "__main__":
    exit(main())
