from venomqa import Journey, Step, Action
from actions.items import create_item, get_item, update_item, delete_item
from actions.auth import login


crud_journey = Journey(
    name="crud_operations",
    description="Basic CRUD operations journey",
    steps=[
        Step(
            name="login",
            action=Action(func=login),
            checkpoint="authenticated",
        ),
        Step(
            name="create_item",
            action=Action(func=create_item, args={"name": "Test Item", "price": 99.99}),
            save_to="created_item",
        ),
        Step(
            name="get_item",
            action=Action(func=get_item, args={"item_id": "{created_item.id}"}),
            save_to="fetched_item",
            assert_that=lambda ctx: ctx["fetched_item"].status_code == 200,
        ),
        Step(
            name="update_item",
            action=Action(
                func=update_item,
                args={"item_id": "{created_item.id}", "name": "Updated Item", "price": 149.99},
            ),
            save_to="updated_item",
        ),
        Step(
            name="delete_item",
            action=Action(func=delete_item, args={"item_id": "{created_item.id}"}),
            expect_failure=False,
        ),
    ],
)
