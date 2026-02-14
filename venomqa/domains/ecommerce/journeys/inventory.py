"""E-commerce inventory management journeys.

Demonstrates:
- Stock tracking and updates
- Low stock alerts
- Inventory reconciliation
"""

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.client import Client


class InventoryActions:
    def __init__(self, base_url: str, inventory_url: str | None = None):
        self.client = Client(base_url=base_url)
        self.inventory_client = Client(base_url=inventory_url or base_url)

    def create_product(self, product_data: dict, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post("/api/products", json=product_data, headers=headers)

    def get_inventory(self, product_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.inventory_client.get(f"/api/inventory/{product_id}", headers=headers)

    def update_stock(
        self, product_id: str, quantity: int, operation: str = "set", token: str | None = None
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.inventory_client.patch(
            f"/api/inventory/{product_id}",
            json={"quantity": quantity, "operation": operation},
            headers=headers,
        )

    def reserve_stock(
        self, product_id: str, quantity: int, order_id: str, token: str | None = None
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.inventory_client.post(
            f"/api/inventory/{product_id}/reserve",
            json={"quantity": quantity, "order_id": order_id},
            headers=headers,
        )

    def release_reservation(self, product_id: str, order_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.inventory_client.post(
            f"/api/inventory/{product_id}/release",
            json={"order_id": order_id},
            headers=headers,
        )

    def get_low_stock_alerts(self, threshold: int = 10, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.inventory_client.get(
            f"/api/inventory/alerts?threshold={threshold}", headers=headers
        )

    def reconcile_inventory(self, product_id: str, actual_count: int, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.inventory_client.post(
            f"/api/inventory/{product_id}/reconcile",
            json={"actual_count": actual_count},
            headers=headers,
        )


def login_admin(client, context):
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "admin@example.com"),
            "password": context.get("password", "admin123"),
        },
    )
    if response.status_code == 200:
        context["token"] = response.json().get("access_token")
    return response


def create_product(client, context):
    actions = InventoryActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        inventory_url=context.get("inventory_url", "http://localhost:8002"),
    )
    response = actions.create_product(
        product_data={
            "name": context.get("product_name", "Test Product"),
            "sku": context.get("sku", "TEST-001"),
            "price": context.get("price", 19.99),
            "initial_stock": context.get("initial_stock", 100),
        },
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        context["product_id"] = response.json().get("id")
        context["initial_stock"] = context.get("initial_stock", 100)
    return response


def verify_inventory(client, context):
    actions = InventoryActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        inventory_url=context.get("inventory_url", "http://localhost:8002"),
    )
    response = actions.get_inventory(product_id=context["product_id"], token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        context["current_stock"] = data.get("quantity")
        assert data.get("quantity") >= 0, "Stock should not be negative"
    return response


def increase_stock(client, context):
    actions = InventoryActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        inventory_url=context.get("inventory_url", "http://localhost:8002"),
    )
    quantity = context.get("add_quantity", 50)
    response = actions.update_stock(
        product_id=context["product_id"],
        quantity=quantity,
        operation="add",
        token=context.get("token"),
    )
    if response.status_code == 200:
        context["current_stock"] = context.get("current_stock", 0) + quantity
    return response


def decrease_stock(client, context):
    actions = InventoryActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        inventory_url=context.get("inventory_url", "http://localhost:8002"),
    )
    quantity = context.get("remove_quantity", 30)
    response = actions.update_stock(
        product_id=context["product_id"],
        quantity=quantity,
        operation="subtract",
        token=context.get("token"),
    )
    if response.status_code == 200:
        context["current_stock"] = context.get("current_stock", 0) - quantity
    return response


def reserve_stock(client, context):
    actions = InventoryActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        inventory_url=context.get("inventory_url", "http://localhost:8002"),
    )
    quantity = context.get("reserve_quantity", 10)
    context["order_id"] = context.get("order_id", "order_test_123")
    response = actions.reserve_stock(
        product_id=context["product_id"],
        quantity=quantity,
        order_id=context["order_id"],
        token=context.get("token"),
    )
    if response.status_code == 200:
        context["reserved_quantity"] = quantity
    return response


def release_reservation(client, context):
    actions = InventoryActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        inventory_url=context.get("inventory_url", "http://localhost:8002"),
    )
    return actions.release_reservation(
        product_id=context["product_id"],
        order_id=context["order_id"],
        token=context.get("token"),
    )


def check_low_stock_alerts(client, context):
    actions = InventoryActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        inventory_url=context.get("inventory_url", "http://localhost:8002"),
    )
    threshold = context.get("alert_threshold", 10)
    response = actions.get_low_stock_alerts(threshold=threshold, token=context.get("token"))
    if response.status_code == 200:
        alerts = response.json().get("alerts", [])
        context["low_stock_products"] = [a.get("product_id") for a in alerts]
    return response


def deplete_stock(client, context):
    actions = InventoryActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        inventory_url=context.get("inventory_url", "http://localhost:8002"),
    )
    return actions.update_stock(
        product_id=context["product_id"],
        quantity=5,
        operation="set",
        token=context.get("token"),
    )


def reconcile_inventory(client, context):
    actions = InventoryActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        inventory_url=context.get("inventory_url", "http://localhost:8002"),
    )
    actual_count = context.get("actual_count", 95)
    response = actions.reconcile_inventory(
        product_id=context["product_id"],
        actual_count=actual_count,
        token=context.get("token"),
    )
    if response.status_code == 200:
        data = response.json()
        context["discrepancy"] = data.get("discrepancy")
        assert isinstance(data.get("discrepancy"), int), "Discrepancy should be an integer"
    return response


inventory_update_flow = Journey(
    name="ecommerce_inventory_update",
    description="Test inventory stock updates with reservations",
    steps=[
        Step(name="login_admin", action=login_admin),
        Checkpoint(name="authenticated"),
        Step(name="create_product", action=create_product),
        Step(name="verify_initial_stock", action=verify_inventory),
        Checkpoint(name="product_created"),
        Step(name="reserve_stock", action=reserve_stock),
        Step(name="verify_reservation", action=verify_inventory),
        Step(name="release_reservation", action=release_reservation),
        Step(name="verify_release", action=verify_inventory),
        Checkpoint(name="reservation_tested"),
        Branch(
            checkpoint_name="reservation_tested",
            paths=[
                Path(name="increase_path", steps=[Step(name="add_stock", action=increase_stock)]),
                Path(
                    name="decrease_path", steps=[Step(name="remove_stock", action=decrease_stock)]
                ),
            ],
        ),
    ],
)

stock_alert_flow = Journey(
    name="ecommerce_stock_alert",
    description="Test low stock alert generation",
    steps=[
        Step(name="login_admin", action=login_admin),
        Checkpoint(name="authenticated"),
        Step(name="create_product", action=create_product, args={"initial_stock": 100}),
        Step(name="deplete_stock", action=deplete_stock),
        Checkpoint(name="low_stock"),
        Step(name="check_alerts", action=check_low_stock_alerts),
    ],
)

inventory_reconciliation_flow = Journey(
    name="ecommerce_inventory_reconciliation",
    description="Test inventory count reconciliation",
    steps=[
        Step(name="login_admin", action=login_admin),
        Checkpoint(name="authenticated"),
        Step(name="create_product", action=create_product, args={"initial_stock": 100}),
        Step(name="verify_stock", action=verify_inventory),
        Checkpoint(name="stock_verified"),
        Step(name="reconcile", action=reconcile_inventory, args={"actual_count": 95}),
        Step(name="verify_reconciliation", action=verify_inventory),
    ],
)
