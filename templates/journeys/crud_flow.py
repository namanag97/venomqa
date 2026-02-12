from typing import Any, Optional
from venomqa import Journey, Step, Checkpoint, Branch
from venomqa.clients import HTTPClient


class CRUDActions:
    def __init__(self, base_url: str, resource_path: str):
        self.client = HTTPClient(base_url=base_url)
        self.resource_path = resource_path.rstrip("/")

    def create(self, data: dict, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.post(f"{self.resource_path}", json=data, headers=headers)

    def list(
        self,
        page: int = 1,
        per_page: int = 20,
        filters: Optional[dict] = None,
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        params = {"page": page, "per_page": per_page}
        if filters:
            params.update(filters)
        return self.client.get(f"{self.resource_path}", params=params, headers=headers)

    def get(self, resource_id: int | str, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.get(f"{self.resource_path}/{resource_id}", headers=headers)

    def update(
        self,
        resource_id: int | str,
        data: dict,
        partial: bool = True,
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        method = self.client.patch if partial else self.client.put
        return method(f"{self.resource_path}/{resource_id}", json=data, headers=headers)

    def delete(self, resource_id: int | str, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.delete(f"{self.resource_path}/{resource_id}", headers=headers)

    def bulk_create(self, items: list[dict], token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.post(
            f"{self.resource_path}/bulk", json={"items": items}, headers=headers
        )

    def bulk_delete(self, ids: list[int | str], token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.delete(f"{self.resource_path}/bulk", json={"ids": ids}, headers=headers)


def login_and_get_token(client, context):
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "test@example.com"),
            "password": context.get("password", "testpassword123"),
        },
    )
    if response.status_code == 200:
        context["token"] = response.json().get("access_token")
    return response


def create_resource(client, context):
    crud = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    response = crud.create(
        data=context.get("create_data", {"name": "Test Item", "value": 100}),
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        context["created_id"] = response.json().get("id")
    return response


def list_resources(client, context):
    crud = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    return crud.list(
        page=context.get("page", 1),
        per_page=context.get("per_page", 20),
        filters=context.get("filters"),
        token=context.get("token"),
    )


def get_resource(client, context):
    crud = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    return crud.get(
        resource_id=context["created_id"],
        token=context.get("token"),
    )


def update_resource(client, context):
    crud = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    return crud.update(
        resource_id=context["created_id"],
        data=context.get("update_data", {"name": "Updated Item"}),
        partial=context.get("partial_update", True),
        token=context.get("token"),
    )


def delete_resource(client, context):
    crud = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    return crud.delete(
        resource_id=context["created_id"],
        token=context.get("token"),
    )


def verify_deleted(client, context):
    crud = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    response = crud.get(
        resource_id=context["created_id"],
        token=context.get("token"),
    )
    return response


crud_create_flow = Journey(
    name="crud_create",
    description="Create and verify new resource",
    steps=[
        Step(name="login", action=login_and_get_token),
        Checkpoint(name="authenticated"),
        Step(name="create_resource", action=create_resource),
        Step(name="verify_creation", action=get_resource),
    ],
)


crud_read_flow = Journey(
    name="crud_read",
    description="List and get individual resources",
    steps=[
        Step(name="login", action=login_and_get_token),
        Checkpoint(name="authenticated"),
        Step(name="create_test_resource", action=create_resource),
        Step(name="list_resources", action=list_resources),
        Step(name="get_individual_resource", action=get_resource),
        Step(name="cleanup", action=delete_resource),
    ],
)


crud_update_flow = Journey(
    name="crud_update",
    description="Update resource with partial and full updates",
    steps=[
        Step(name="login", action=login_and_get_token),
        Checkpoint(name="authenticated"),
        Step(name="create_resource", action=create_resource),
        Step(
            name="partial_update",
            action=update_resource,
            context_overrides={
                "partial_update": True,
                "update_data": {"name": "Partially Updated"},
            },
        ),
        Step(
            name="full_update",
            action=update_resource,
            context_overrides={
                "partial_update": False,
                "update_data": {"name": "Fully Updated", "value": 200},
            },
        ),
        Step(name="verify_update", action=get_resource),
        Step(name="cleanup", action=delete_resource),
    ],
)


crud_delete_flow = Journey(
    name="crud_delete",
    description="Delete resource and verify deletion",
    steps=[
        Step(name="login", action=login_and_get_token),
        Checkpoint(name="authenticated"),
        Step(name="create_resource", action=create_resource),
        Step(name="delete_resource", action=delete_resource),
        Step(name="verify_deletion", action=verify_deleted),
    ],
)


crud_full_cycle_flow = Journey(
    name="crud_full_cycle",
    description="Complete CRUD lifecycle: Create, Read, Update, Delete",
    steps=[
        Step(name="login", action=login_and_get_token),
        Checkpoint(name="authenticated"),
        Step(name="create", action=create_resource),
        Checkpoint(name="resource_created"),
        Step(name="read_created", action=get_resource),
        Step(
            name="update",
            action=update_resource,
            context_overrides={"update_data": {"name": "Modified Item", "value": 999}},
        ),
        Step(name="read_updated", action=get_resource),
        Step(name="delete", action=delete_resource),
        Checkpoint(name="resource_deleted"),
    ],
)


crud_pagination_flow = Journey(
    name="crud_pagination",
    description="Test pagination of list endpoints",
    steps=[
        Step(name="login", action=login_and_get_token),
        Checkpoint(name="authenticated"),
        Step(
            name="list_first_page",
            action=list_resources,
            context_overrides={"page": 1, "per_page": 10},
        ),
        Step(
            name="list_second_page",
            action=list_resources,
            context_overrides={"page": 2, "per_page": 10},
        ),
        Step(
            name="list_last_page",
            action=list_resources,
            context_overrides={"page": 100, "per_page": 10},
        ),
    ],
)
