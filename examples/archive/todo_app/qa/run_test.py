#!/usr/bin/env python3
"""Run todo app journeys manually."""
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
        # Print available attributes for debugging
        print(f"{msg} - FAILED")
        print(f"     Error: {step.error}")
    else:
        print(msg)

sys.exit(0 if result.success else 1)
