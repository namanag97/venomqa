"""Hello Journey - VenomQA Quickstart Example.

This journey demonstrates a complete CRUD workflow:
1. Check API health
2. List existing items
3. Create a new item
4. Checkpoint (save state)
5. Branch: Update OR Delete the item
6. Verify final state

This showcases VenomQA's key features:
- Sequential step execution
- State management with checkpoints
- Branching paths for comprehensive testing
"""

import sys
from pathlib import Path

# Add the qa directory to the path for action imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from venomqa import Journey, Step, Checkpoint, Branch, Path as JourneyPath

from actions.hello_actions import (
    check_health,
    create_item,
    delete_item,
    get_item,
    list_items,
    update_item,
)


# Define the journey
journey = Journey(
    name="hello_journey",
    description="Quickstart CRUD journey demonstrating VenomQA basics",
    steps=[
        # Step 1: Health check
        Step(
            name="check_health",
            action=check_health,
            description="Verify API is healthy",
            expected_status=200,
        ),

        # Step 2: List items (should be empty initially)
        Step(
            name="list_items_initial",
            action=list_items,
            description="List items before creating any",
            expected_status=200,
        ),

        # Step 3: Create an item
        Step(
            name="create_item",
            action=create_item,
            args={"name": "Hello VenomQA", "description": "My first item", "price": 19.99},
            description="Create a new item",
            expected_status=201,
        ),

        # Step 4: Verify item was created
        Step(
            name="get_created_item",
            action=get_item,
            description="Fetch the created item",
            expected_status=200,
        ),

        # Checkpoint: Save state here for branching
        Checkpoint(
            name="item_created",
            description="Item has been created, ready for update or delete",
        ),

        # Branch: Test both update and delete paths
        Branch(
            checkpoint_name="item_created",
            paths=[
                # Path 1: Update the item
                JourneyPath(
                    name="update_path",
                    description="Update the item and verify",
                    steps=[
                        Step(
                            name="update_item",
                            action=update_item,
                            args={"name": "Updated VenomQA Item", "price": 29.99},
                            description="Update the item",
                            expected_status=200,
                        ),
                        Step(
                            name="verify_update",
                            action=get_item,
                            description="Verify the update",
                            expected_status=200,
                        ),
                    ],
                ),

                # Path 2: Delete the item
                JourneyPath(
                    name="delete_path",
                    description="Delete the item and verify",
                    steps=[
                        Step(
                            name="delete_item",
                            action=delete_item,
                            description="Delete the item",
                            expected_status=204,
                        ),
                        Step(
                            name="verify_delete",
                            action=get_item,
                            description="Verify item is deleted (expect 404)",
                            expected_status=404,
                        ),
                    ],
                ),
            ],
        ),

        # Final step: List items again
        Step(
            name="list_items_final",
            action=list_items,
            description="List items after operations",
            expected_status=200,
        ),
    ],
)


# For testing directly
if __name__ == "__main__":
    print(f"Journey: {journey.name}")
    print(f"Description: {journey.description}")
    print(f"Steps: {len(journey.steps)}")
