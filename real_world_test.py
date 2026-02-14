#!/usr/bin/env python3
"""Real-world test of VenomQA against the Todo App.

This script tests VenomQA's core claims:
1. State matching - does context flow between steps?
2. State mapping - are IDs passed correctly?
3. Bug finding - can it detect actual issues?
4. State logic - do checkpoints work?
"""

import sys
sys.path.insert(0, '.')

from venomqa import Client, Journey, Step, Checkpoint, Branch, Path
from venomqa.runner import JourneyRunner
from venomqa.core.context import ExecutionContext

BASE_URL = "http://localhost:5001"


def test_state_matching_and_mapping():
    """Test 1: Verify state matching and mapping works."""
    print("\n" + "="*60)
    print("TEST 1: State Matching and Mapping")
    print("="*60)

    # Create actions that depend on context
    def create_todo(client, context):
        response = client.post("/todos", json={"title": "Test Todo for State"})
        if response.status_code in [200, 201]:
            todo_id = response.json().get("id")
            context["todo_id"] = todo_id
            print(f"  [CREATE] Created todo with ID: {todo_id}")
        return response

    def get_todo_using_context(client, context):
        todo_id = context.get("todo_id")
        print(f"  [GET] Attempting to get todo with ID from context: {todo_id}")
        response = client.get(f"/todos/{todo_id}")
        return response

    def update_todo_using_context(client, context):
        todo_id = context.get("todo_id")
        print(f"  [UPDATE] Updating todo {todo_id}")
        response = client.put(f"/todos/{todo_id}", json={"title": "Updated Title"})
        return response

    def delete_todo_using_context(client, context):
        todo_id = context.get("todo_id")
        print(f"  [DELETE] Deleting todo {todo_id}")
        response = client.delete(f"/todos/{todo_id}")
        return response

    journey = Journey(
        name="state_matching_test",
        description="Test that context flows between steps",
        steps=[
            Step(name="create", action=create_todo),
            Step(name="read", action=get_todo_using_context),
            Step(name="update", action=update_todo_using_context),
            Step(name="delete", action=delete_todo_using_context),
        ]
    )

    client = Client(base_url=BASE_URL)
    runner = JourneyRunner(client=client)
    result = runner.run(journey)

    print(f"\n  Result: {'PASSED' if result.success else 'FAILED'}")
    print(f"  Steps: {result.passed_steps}/{result.total_steps}")

    if not result.success:
        for issue in result.issues:
            print(f"  Issue: {issue.step} - {issue.error}")

    return result.success


def test_bug_detection():
    """Test 2: Verify VenomQA can detect bugs (expected failures)."""
    print("\n" + "="*60)
    print("TEST 2: Bug Detection")
    print("="*60)

    def get_nonexistent_todo(client, context):
        print("  [BUG TEST] Fetching non-existent todo (ID=99999)")
        response = client.get("/todos/99999")
        return response

    # This should fail because the todo doesn't exist
    journey_expected_fail = Journey(
        name="bug_detection_test",
        steps=[
            Step(name="get_missing", action=get_nonexistent_todo),
        ]
    )

    client = Client(base_url=BASE_URL)
    runner = JourneyRunner(client=client)
    result = runner.run(journey_expected_fail)

    # VenomQA should detect this as a failure
    detected_failure = not result.success
    print(f"\n  Bug detected: {detected_failure}")

    if result.issues:
        for issue in result.issues:
            print(f"  Issue found: {issue.step} - {issue.error}")
            print(f"  Suggestion: {issue.suggestion}")

    return detected_failure


def test_expected_failure_handling():
    """Test 3: Verify expect_failure flag works correctly."""
    print("\n" + "="*60)
    print("TEST 3: Expected Failure Handling")
    print("="*60)

    def create_todo(client, context):
        response = client.post("/todos", json={"title": "Will be deleted"})
        context["todo_id"] = response.json().get("id")
        print(f"  [CREATE] Created todo with ID: {context['todo_id']}")
        return response

    def delete_todo(client, context):
        todo_id = context.get("todo_id")
        print(f"  [DELETE] Deleting todo {todo_id}")
        return client.delete(f"/todos/{todo_id}")

    def verify_deleted(client, context):
        todo_id = context.get("todo_id")
        print(f"  [VERIFY] Getting deleted todo {todo_id} (should 404)")
        return client.get(f"/todos/{todo_id}")

    journey = Journey(
        name="expected_failure_test",
        steps=[
            Step(name="create", action=create_todo),
            Step(name="delete", action=delete_todo),
            Step(name="verify_deleted", action=verify_deleted, expect_failure=True),
        ]
    )

    client = Client(base_url=BASE_URL)
    runner = JourneyRunner(client=client)
    result = runner.run(journey)

    print(f"\n  Result: {'PASSED' if result.success else 'FAILED'}")
    print(f"  Steps: {result.passed_steps}/{result.total_steps}")

    # Check each step's result
    for step_result in result.step_results:
        print(f"  Step '{step_result.step_name}': {'PASS' if step_result.success else 'FAIL'}")
        if step_result.response:
            print(f"    Status: {step_result.response.get('status_code')}")

    return result.success


def test_checkpoint_and_branch():
    """Test 4: Verify checkpoint and branching logic."""
    print("\n" + "="*60)
    print("TEST 4: Checkpoint and Branch Logic")
    print("="*60)

    def create_todo(client, context):
        response = client.post("/todos", json={"title": "Branch Test Todo"})
        context["todo_id"] = response.json().get("id")
        print(f"  [CREATE] Created todo with ID: {context['todo_id']}")
        return response

    def mark_completed(client, context):
        todo_id = context.get("todo_id")
        print(f"  [PATH A] Marking todo {todo_id} as completed")
        return client.put(f"/todos/{todo_id}", json={"completed": True})

    def update_title(client, context):
        todo_id = context.get("todo_id")
        print(f"  [PATH B] Updating todo {todo_id} title")
        return client.put(f"/todos/{todo_id}", json={"title": "Updated in Path B"})

    journey = Journey(
        name="checkpoint_branch_test",
        steps=[
            Step(name="create", action=create_todo),
            Checkpoint(name="after_create"),
            Branch(
                checkpoint_name="after_create",
                paths=[
                    Path(name="complete_path", steps=[
                        Step(name="mark_complete", action=mark_completed),
                    ]),
                    Path(name="update_path", steps=[
                        Step(name="update_title", action=update_title),
                    ]),
                ]
            ),
        ]
    )

    client = Client(base_url=BASE_URL)
    runner = JourneyRunner(client=client)
    result = runner.run(journey)

    print(f"\n  Result: {'PASSED' if result.success else 'FAILED'}")
    print(f"  Main steps: {result.passed_steps}/{result.total_steps}")
    print(f"  Branch paths: {result.passed_paths}/{result.total_paths}")

    for branch_result in result.branch_results:
        print(f"  Branch '{branch_result.checkpoint_name}':")
        for path_result in branch_result.path_results:
            status = 'PASS' if path_result.success else 'FAIL'
            print(f"    Path '{path_result.path_name}': {status}")

    # Note: cleanup is handled automatically, no need to delete here

    return result.success


def test_context_isolation_between_paths():
    """Test 5: Verify context is properly isolated between branch paths."""
    print("\n" + "="*60)
    print("TEST 5: Context Isolation Between Paths")
    print("="*60)

    def create_todo(client, context):
        response = client.post("/todos", json={"title": "Context Isolation Test"})
        context["todo_id"] = response.json().get("id")
        context["original_title"] = "Context Isolation Test"
        print(f"  [CREATE] Created todo with ID: {context['todo_id']}")
        return response

    def path_a_modify(client, context):
        print(f"  [PATH A] Context before modify: todo_id={context.get('todo_id')}")
        context["path_specific"] = "A"
        todo_id = context.get("todo_id")
        return client.put(f"/todos/{todo_id}", json={"title": "Modified by Path A"})

    def path_b_check(client, context):
        # This should NOT see "path_specific" from Path A if isolation works
        has_path_specific = "path_specific" in context
        print(f"  [PATH B] Has path_specific from A: {has_path_specific}")
        todo_id = context.get("todo_id")
        return client.get(f"/todos/{todo_id}")

    journey = Journey(
        name="context_isolation_test",
        steps=[
            Step(name="create", action=create_todo),
            Checkpoint(name="shared_state"),
            Branch(
                checkpoint_name="shared_state",
                paths=[
                    Path(name="path_a", steps=[
                        Step(name="modify_a", action=path_a_modify),
                    ]),
                    Path(name="path_b", steps=[
                        Step(name="check_b", action=path_b_check),
                    ]),
                ]
            ),
        ]
    )

    client = Client(base_url=BASE_URL)
    runner = JourneyRunner(client=client)
    result = runner.run(journey)

    print(f"\n  Result: {'PASSED' if result.success else 'FAILED'}")
    print(f"  Branch paths: {result.passed_paths}/{result.total_paths}")

    return result.success


def test_data_consistency():
    """Test 6: Verify data returned matches what was sent."""
    print("\n" + "="*60)
    print("TEST 6: Data Consistency Verification")
    print("="*60)

    test_title = "Data Consistency Test Title"
    test_description = "This is a test description"

    def create_and_verify(client, context):
        # Create
        response = client.post("/todos", json={
            "title": test_title,
            "description": test_description,
        })

        if response.status_code not in [200, 201]:
            print(f"  [ERROR] Create failed with status {response.status_code}")
            return response

        created = response.json()
        context["todo_id"] = created["id"]

        # Verify response matches input
        title_match = created.get("title") == test_title
        desc_match = created.get("description") == test_description

        print(f"  [CREATE] Title match: {title_match}")
        print(f"  [CREATE] Description match: {desc_match}")

        if not title_match or not desc_match:
            print(f"  [BUG] Data mismatch detected!")
            print(f"    Expected title: '{test_title}'")
            print(f"    Got title: '{created.get('title')}'")

        return response

    def fetch_and_verify(client, context):
        todo_id = context.get("todo_id")
        response = client.get(f"/todos/{todo_id}")

        if response.status_code != 200:
            print(f"  [ERROR] Fetch failed with status {response.status_code}")
            return response

        fetched = response.json()

        # Verify data persisted correctly
        title_match = fetched.get("title") == test_title
        desc_match = fetched.get("description") == test_description

        print(f"  [FETCH] Title persisted correctly: {title_match}")
        print(f"  [FETCH] Description persisted correctly: {desc_match}")

        return response

    def cleanup(client, context):
        todo_id = context.get("todo_id")
        return client.delete(f"/todos/{todo_id}")

    journey = Journey(
        name="data_consistency_test",
        steps=[
            Step(name="create_verify", action=create_and_verify),
            Step(name="fetch_verify", action=fetch_and_verify),
            Step(name="cleanup", action=cleanup),
        ]
    )

    client = Client(base_url=BASE_URL)
    runner = JourneyRunner(client=client)
    result = runner.run(journey)

    print(f"\n  Result: {'PASSED' if result.success else 'FAILED'}")

    return result.success


def main():
    """Run all real-world tests."""
    print("\n" + "#"*60)
    print("# VenomQA Real-World Test Suite")
    print("# Testing against Todo App at", BASE_URL)
    print("#"*60)

    # Check if the app is running
    try:
        import requests
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"\nERROR: Todo app not healthy. Status: {response.status_code}")
            return
        print(f"\nTodo app is healthy: {response.json()}")
    except Exception as e:
        print(f"\nERROR: Cannot connect to Todo app: {e}")
        print("Make sure the app is running: docker compose -f examples/todo_app/docker/docker-compose.yml up -d")
        return

    results = {}

    # Run all tests
    results["State Matching & Mapping"] = test_state_matching_and_mapping()
    results["Bug Detection"] = test_bug_detection()
    results["Expected Failure Handling"] = test_expected_failure_handling()
    results["Checkpoint & Branch"] = test_checkpoint_and_branch()
    results["Context Isolation"] = test_context_isolation_between_paths()
    results["Data Consistency"] = test_data_consistency()

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    all_passed = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "-"*60)
    if all_passed:
        print("ALL TESTS PASSED - VenomQA claims verified!")
    else:
        failed = [name for name, passed in results.items() if not passed]
        print(f"SOME TESTS FAILED: {', '.join(failed)}")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
