"""Search journeys for content management.

Demonstrates:
- Basic and filtered search
- Search suggestions
- Pagination
"""


from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.clients import HTTPClient


class SearchActions:
    def __init__(self, base_url: str, search_url: str | None = None):
        self.client = HTTPClient(base_url=base_url)
        self.search_client = HTTPClient(base_url=search_url or base_url)

    def search(self, query: str, page: int = 1, per_page: int = 20, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.search_client.get(
            "/api/search",
            params={"q": query, "page": page, "per_page": per_page},
            headers=headers,
        )

    def search_with_filters(self, query: str, filters: dict, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        params = {"q": query}
        params.update(filters)
        return self.search_client.get("/api/search", params=params, headers=headers)

    def get_suggestions(self, query: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.search_client.get(
            "/api/search/suggestions", params={"q": query}, headers=headers
        )

    def index_document(self, doc_id: str, content: dict, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.search_client.post(f"/api/search/index/{doc_id}", json=content, headers=headers)

    def delete_from_index(self, doc_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.search_client.delete(f"/api/search/index/{doc_id}", headers=headers)


def login_user(client, context):
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "user@example.com"),
            "password": context.get("password", "password123"),
        },
    )
    if response.status_code == 200:
        context["token"] = response.json().get("access_token")
    return response


def index_test_document(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    doc_id = context.get("doc_id", "doc_test_123")
    response = actions.index_document(
        doc_id=doc_id,
        content={
            "title": context.get("doc_title", "Test Document"),
            "body": context.get("doc_body", "This is test content for search"),
        },
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        context["indexed_doc_id"] = doc_id
    return response


def basic_search(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    query = context.get("search_query", "test")
    response = actions.search(query=query, token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        context["search_results"] = data.get("results", [])
        context["total_results"] = data.get("total", 0)
        assert isinstance(data.get("results"), list), "Results should be a list"
    return response


def filtered_search(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    query = context.get("search_query", "test")
    filters = context.get("search_filters", {"category": "documents", "date_from": "2024-01-01"})
    response = actions.search_with_filters(query=query, filters=filters, token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        context["filtered_results"] = data.get("results", [])
    return response


def get_search_suggestions(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    query = context.get("partial_query", "te")
    response = actions.get_suggestions(query=query, token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        context["suggestions"] = data.get("suggestions", [])
        assert isinstance(data.get("suggestions"), list), "Suggestions should be a list"
    return response


def search_first_page(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    return actions.search(
        query=context.get("search_query", "test"), page=1, per_page=10, token=context.get("token")
    )


def search_second_page(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    return actions.search(
        query=context.get("search_query", "test"), page=2, per_page=10, token=context.get("token")
    )


def delete_indexed_document(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    return actions.delete_from_index(
        doc_id=context.get("indexed_doc_id", "doc_test_123"), token=context.get("token")
    )


basic_search_flow = Journey(
    name="basic_search",
    description="Basic search with results retrieval",
    steps=[
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="index_document", action=index_test_document),
        Checkpoint(name="document_indexed"),
        Step(name="search", action=basic_search),
        Step(name="cleanup", action=delete_indexed_document),
    ],
)

filtered_search_flow = Journey(
    name="filtered_search",
    description="Search with various filter combinations",
    steps=[
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="index_document", action=index_test_document),
        Checkpoint(name="document_indexed"),
        Branch(
            checkpoint_name="document_indexed",
            paths=[
                Path(
                    name="category_filter",
                    steps=[
                        Step(
                            name="search_by_category",
                            action=filtered_search,
                            context_overrides={"search_filters": {"category": "documents"}},
                        ),
                    ],
                ),
                Path(
                    name="date_filter",
                    steps=[
                        Step(
                            name="search_by_date",
                            action=filtered_search,
                            context_overrides={
                                "search_filters": {
                                    "date_from": "2024-01-01",
                                    "date_to": "2024-12-31",
                                }
                            },
                        ),
                    ],
                ),
            ],
        ),
        Step(name="cleanup", action=delete_indexed_document),
    ],
)

search_suggestions_flow = Journey(
    name="search_suggestions",
    description="Get search suggestions based on partial input",
    steps=[
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="index_document", action=index_test_document),
        Checkpoint(name="document_indexed"),
        Step(name="get_suggestions", action=get_search_suggestions),
        Step(name="cleanup", action=delete_indexed_document),
    ],
)
