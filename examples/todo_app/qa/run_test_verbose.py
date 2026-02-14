#!/usr/bin/env python3
"""Run todo app journeys manually with verbose output."""
import sys
import os

sys.path.insert(0, '/Users/namanagarwal/venomQA')
sys.path.insert(0, '/Users/namanagarwal/venomQA/examples/todo_app/qa')

from venomqa import Client, JourneyRunner

# Import crud_journey directly
from journeys.crud_journey import crud_journey

# Create client
client = Client(base_url="http://localhost:5001")

# Create runner
runner = JourneyRunner(client=client)

# Run the journey
print("Running CRUD Journey...")
print("=" * 60)
result = runner.run(crud_journey)

# Print results
print(f"\nJourney: {result.journey_name}")
print(f"Status: {'PASSED' if result.success else 'FAILED'}")
print(f"Steps: {result.passed_steps}/{result.total_steps} passed")
print(f"Duration: {result.duration_seconds:.2f}s")

print("\nStep details:")
for step in result.step_results:
    status = "✓" if step.success else "✗"
    msg = f"{status} {step.step_name} ({step.duration_seconds:.3f}s)"
    if not step.success:
        print(f"{msg} - FAILED")
        print(f"     Error: {step.error}")
        if hasattr(step, 'response') and step.response:
            print(f"     Status: {step.response.status_code}")
            try:
                print(f"     Response: {step.response.json()}")
            except:
                print(f"     Response: {step.response.text[:200]}")
    else:
        print(msg)
        if hasattr(step, 'response') and step.response:
            print(f"     Status: {step.response.status_code}")

sys.exit(0 if result.success else 1)
