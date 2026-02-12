"""Search actions for content management.

Reusable search actions.
"""


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

    def get_suggestions(self, query: str, limit: int = 5, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.search_client.get(
            "/api/search/suggestions", params={"q": query, "limit": limit}, headers=headers
        )

    def get_facets(self, query: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.search_client.get("/api/search/facets", params={"q": query}, headers=headers)

    def index_document(self, doc_id: str, content: dict, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.search_client.post(f"/api/search/index/{doc_id}", json=content, headers=headers)

    def delete_document(self, doc_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.search_client.delete(f"/api/search/index/{doc_id}", headers=headers)


def search(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    response = actions.search(
        query=context.get("query", ""),
        page=context.get("page", 1),
        per_page=context.get("per_page", 20),
        token=context.get("token"),
    )
    if response.status_code == 200:
        data = response.json()
        context["results"] = data.get("results", [])
        context["total"] = data.get("total", 0)
    return response


def search_with_filters(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    return actions.search_with_filters(
        query=context.get("query", ""),
        filters=context.get("filters", {}),
        token=context.get("token"),
    )


def get_suggestions(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    response = actions.get_suggestions(
        query=context.get("partial_query", ""),
        limit=context.get("suggestion_limit", 5),
        token=context.get("token"),
    )
    if response.status_code == 200:
        context["suggestions"] = response.json().get("suggestions", [])
    return response


def get_facets(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    response = actions.get_facets(query=context.get("query", ""), token=context.get("token"))
    if response.status_code == 200:
        context["facets"] = response.json().get("facets", {})
    return response


def index_document(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    response = actions.index_document(
        doc_id=context.get("doc_id"),
        content=context.get("doc_content", {}),
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        context["indexed_doc_id"] = context.get("doc_id")
    return response


def delete_document(client, context):
    actions = SearchActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        search_url=context.get("search_url"),
    )
    return actions.delete_document(doc_id=context.get("indexed_doc_id"), token=context.get("token"))
