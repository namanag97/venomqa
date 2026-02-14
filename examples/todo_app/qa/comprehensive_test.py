#!/usr/bin/env python3
"""Comprehensive test runner for VenomQA todo app example."""
import sys
import os
from datetime import datetime

sys.path.insert(0, '/Users/namanagarwal/venomQA')
sys.path.insert(0, '/Users/namanagarwal/venomQA/examples/todo_app/qa')

from venomqa import Client, JourneyRunner

# Import all journeys
from journeys.crud_journey import crud_journey, crud_with_branches_journey
from journeys.file_upload_journey import file_upload_journey, multiple_uploads_journey
from journeys.error_handling_journey import (
    error_handling_journey,
    validation_errors_journey,
    pagination_journey,
)

def run_journey(client, journey, verbose=False):
    """Run a single journey and return results."""
    runner = JourneyRunner(client=client)
    
    print(f"\n{'='*70}")
    print(f"Running: {journey.name}")
    print(f"Description: {journey.description}")
    print(f"{'='*70}")
    
    result = runner.run(journey)
    
    # Print summary
    status_icon = "✅" if result.success else "❌"
    print(f"\n{status_icon} {journey.name}")
    print(f"   Status: {'PASSED' if result.success else 'FAILED'}")
    print(f"   Steps: {result.passed_steps}/{result.total_steps} passed")
    print(f"   Duration: {result.duration_seconds:.2f}s")
    
    if verbose or not result.success:
        print(f"\n   Step Details:")
        for step in result.step_results:
            status = "✓" if step.success else "✗"
            print(f"   {status} {step.step_name} ({step.duration_seconds:.3f}s)")
            if not step.success:
                print(f"      Error: {step.error}")
    
    return result

def main():
    """Run all journeys and generate report."""
    print("\n" + "="*70)
    print("VenomQA Todo App - Comprehensive Test Suite")
    print("="*70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL: http://localhost:5001")
    
    # Create client
    client = Client(base_url="http://localhost:5001")
    
    # List of all journeys to run
    journeys = [
        ("CRUD Operations", crud_journey),
        ("CRUD with Branches", crud_with_branches_journey),
        ("File Upload", file_upload_journey),
        ("Multiple Uploads", multiple_uploads_journey),
        ("Error Handling", error_handling_journey),
        ("Validation Errors", validation_errors_journey),
        ("Pagination", pagination_journey),
    ]
    
    results = []
    
    # Run each journey
    for name, journey in journeys:
        try:
            result = run_journey(client, journey, verbose=False)
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} - EXCEPTION: {e}")
            results.append((name, None))
    
    # Final summary
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, r in results if r and r.success)
    failed = sum(1 for _, r in results if r and not r.success)
    errored = sum(1 for _, r in results if r is None)
    total = len(results)
    
    print(f"\nTotal Journeys: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⚠️  Errors: {errored}")
    print(f"Success Rate: {passed/total*100:.1f}%")
    
    # List failures
    if failed > 0 or errored > 0:
        print("\n Failed/Errored Journeys:")
        for name, result in results:
            if result is None:
                print(f"   ⚠️  {name} - Exception")
            elif not result.success:
                print(f"   ❌ {name} - {result.passed_steps}/{result.total_steps} steps passed")
    
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    sys.exit(0 if (failed + errored) == 0 else 1)

if __name__ == "__main__":
    main()
