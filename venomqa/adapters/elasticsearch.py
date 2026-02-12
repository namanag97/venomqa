"""Elasticsearch adapter for search testing.

Elasticsearch is a distributed search and analytics engine.

Installation:
    pip install elasticsearch

Example:
    >>> from venomqa.adapters import ElasticsearchAdapter
    >>> adapter = ElasticsearchAdapter(hosts=["http://localhost:9200"])
    >>> adapter.index_document("test", doc)
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from venomqa.ports.search import IndexedDocument, SearchIndex, SearchPort, SearchResult

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk

    ELASTICSEARCH_AVAILABLE = True
except ImportError:
    ELASTICSEARCH_AVAILABLE = False
    Elasticsearch = None


@dataclass
class ElasticsearchConfig:
    """Configuration for Elasticsearch adapter."""

    hosts: list[str] | None = None
    cloud_id: str | None = None
    api_key: str | None = None
    basic_auth: tuple[str, str] | None = None
    timeout: int = 30
    verify_certs: bool = True


class ElasticsearchAdapter(SearchPort):
    """Adapter for Elasticsearch search engine.

    This adapter provides integration with Elasticsearch for
    document indexing and search in test environments.

    Attributes:
        config: Configuration for the Elasticsearch connection.

    Example:
        >>> adapter = ElasticsearchAdapter(hosts=["http://localhost:9200"])
        >>> adapter.create_index("products")
        >>> adapter.index_document("products", doc)
        >>> results, total = adapter.search("products", "laptop")
    """

    def __init__(
        self,
        hosts: list[str] | None = None,
        cloud_id: str | None = None,
        api_key: str | None = None,
        basic_auth: tuple[str, str] | None = None,
        timeout: int = 30,
        verify_certs: bool = True,
    ) -> None:
        """Initialize the Elasticsearch adapter.

        Args:
            hosts: List of Elasticsearch hosts.
            cloud_id: Elastic Cloud ID.
            api_key: API key for authentication.
            basic_auth: (username, password) tuple.
            timeout: Request timeout in seconds.
            verify_certs: Whether to verify SSL certificates.

        Raises:
            ImportError: If elasticsearch is not installed.
        """
        if not ELASTICSEARCH_AVAILABLE:
            raise ImportError("elasticsearch is required. Install with: pip install elasticsearch")

        self.config = ElasticsearchConfig(
            hosts=hosts,
            cloud_id=cloud_id,
            api_key=api_key,
            basic_auth=basic_auth,
            timeout=timeout,
            verify_certs=verify_certs,
        )

        kwargs: dict[str, Any] = {"timeout": timeout}
        if hosts:
            kwargs["hosts"] = hosts
        if cloud_id:
            kwargs["cloud_id"] = cloud_id
        if api_key:
            kwargs["api_key"] = api_key
        if basic_auth:
            kwargs["basic_auth"] = basic_auth

        self._client = Elasticsearch(**kwargs)

    def _doc_to_indexed(self, hit: dict[str, Any]) -> IndexedDocument:
        """Convert an ES hit to IndexedDocument."""
        source = hit.get("_source", {})
        return IndexedDocument(
            id=hit.get("_id", ""),
            content=source.get("content", ""),
            title=source.get("title"),
            fields=source,
            tags=source.get("tags", []),
            timestamp=source.get("timestamp"),
        )

    def _hit_to_result(self, hit: dict[str, Any]) -> SearchResult:
        """Convert an ES hit to SearchResult."""
        highlight = hit.get("highlight", {})
        return SearchResult(
            id=hit.get("_id", ""),
            score=hit.get("_score", 0.0),
            document=self._doc_to_indexed(hit),
            highlights=highlight,
            fields=hit.get("_source", {}),
        )

    def index_document(
        self,
        index: str,
        document: IndexedDocument,
        refresh: bool = False,
    ) -> bool:
        """Index a document.

        Args:
            index: Index name.
            document: Document to index.
            refresh: Whether to refresh the index immediately.

        Returns:
            True if successful.
        """
        doc_body = {
            "content": document.content,
            "title": document.title,
            "tags": document.tags,
            "timestamp": document.timestamp,
            **document.fields,
        }

        self._client.index(
            index=index,
            id=document.id,
            document=doc_body,
            refresh=refresh,
        )
        return True

    def index_documents(
        self,
        index: str,
        documents: list[IndexedDocument],
        refresh: bool = False,
    ) -> int:
        """Index multiple documents in bulk.

        Args:
            index: Index name.
            documents: Documents to index.
            refresh: Whether to refresh the index immediately.

        Returns:
            Number of documents indexed.
        """
        actions = []
        for doc in documents:
            doc_body = {
                "content": doc.content,
                "title": doc.title,
                "tags": doc.tags,
                "timestamp": doc.timestamp,
                **doc.fields,
            }
            actions.append(
                {
                    "_index": index,
                    "_id": doc.id,
                    "_source": doc_body,
                }
            )

        success, _ = bulk(self._client, actions, refresh=refresh)
        return success

    def get_document(self, index: str, doc_id: str) -> IndexedDocument | None:
        """Get a document by ID.

        Args:
            index: Index name.
            doc_id: Document ID.

        Returns:
            The document or None if not found.
        """
        try:
            response = self._client.get(index=index, id=doc_id)
            return self._doc_to_indexed(response)
        except Exception:
            return None

    def delete_document(self, index: str, doc_id: str) -> bool:
        """Delete a document by ID.

        Args:
            index: Index name.
            doc_id: Document ID.

        Returns:
            True if deleted, False if not found.
        """
        try:
            self._client.delete(index=index, id=doc_id)
            return True
        except Exception:
            return False

    def search(
        self,
        index: str,
        query: str | dict[str, Any],
        fields: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        sort: list[str] | None = None,
        offset: int = 0,
        limit: int = 10,
    ) -> tuple[list[SearchResult], int]:
        """Search for documents.

        Args:
            index: Index name.
            query: Search query string or query DSL.
            fields: Fields to search in.
            filters: Filters to apply.
            sort: Sort criteria.
            offset: Result offset for pagination.
            limit: Maximum results to return.

        Returns:
            Tuple of (results, total_count).
        """
        if isinstance(query, str):
            if fields:
                query_dsl = {
                    "multi_match": {
                        "query": query,
                        "fields": fields,
                    }
                }
            else:
                query_dsl = {
                    "query_string": {
                        "query": query,
                    }
                }
        else:
            query_dsl = query

        body: dict[str, Any] = {"query": query_dsl}

        if filters:
            body["query"] = {
                "bool": {
                    "must": [query_dsl],
                    "filter": [{"term": {k: v}} for k, v in filters.items()],
                }
            }

        if sort:
            body["sort"] = [{s: "asc"} for s in sort]

        body["highlight"] = {
            "fields": {
                "content": {},
                "title": {},
            }
        }

        response = self._client.search(
            index=index,
            body=body,
            from_=offset,
            size=limit,
        )

        hits = response.get("hits", {})
        total = hits.get("total", {}).get("value", 0)
        results = [self._hit_to_result(hit) for hit in hits.get("hits", [])]

        return results, total

    def create_index(
        self,
        name: str,
        settings: dict[str, Any] | None = None,
        mappings: dict[str, Any] | None = None,
    ) -> bool:
        """Create a new index.

        Args:
            name: Index name.
            settings: Index settings.
            mappings: Field mappings.

        Returns:
            True if successful.
        """
        body: dict[str, Any] = {}
        if settings:
            body["settings"] = settings
        if mappings:
            body["mappings"] = mappings

        if body:
            self._client.indices.create(index=name, body=body)
        else:
            self._client.indices.create(index=name)
        return True

    def delete_index(self, name: str) -> bool:
        """Delete an index.

        Args:
            name: Index name.

        Returns:
            True if successful.
        """
        try:
            self._client.indices.delete(index=name)
            return True
        except Exception:
            return False

    def index_exists(self, name: str) -> bool:
        """Check if an index exists.

        Args:
            name: Index name.

        Returns:
            True if exists, False otherwise.
        """
        return self._client.indices.exists(index=name)

    def get_index(self, name: str) -> SearchIndex | None:
        """Get information about an index.

        Args:
            name: Index name.

        Returns:
            Index information or None if not found.
        """
        try:
            response = self._client.indices.get(index=name)
            info = response[name]
            settings = info.get("settings", {}).get("index", {})

            count_response = self._client.count(index=name)
            doc_count = count_response.get("count", 0)

            return SearchIndex(
                name=name,
                document_count=doc_count,
                size_bytes=int(settings.get("store", {}).get("size_in_bytes", 0)),
                created_at=datetime.fromisoformat(settings.get("creation_date"))
                if settings.get("creation_date")
                else None,
                settings=settings,
            )
        except Exception:
            return None

    def refresh_index(self, name: str) -> bool:
        """Refresh an index to make changes visible.

        Args:
            name: Index name.

        Returns:
            True if successful.
        """
        try:
            self._client.indices.refresh(index=name)
            return True
        except Exception:
            return False

    def clear_index(self, name: str) -> bool:
        """Clear all documents from an index.

        Args:
            name: Index name.

        Returns:
            True if successful.
        """
        try:
            self._client.delete_by_query(
                index=name,
                body={"query": {"match_all": {}}},
            )
            return True
        except Exception:
            return False

    def health_check(self) -> bool:
        """Check if the search service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            response = self._client.cluster.health()
            return response.get("status") in ("green", "yellow")
        except Exception:
            return False

    def get_cluster_health(self) -> dict[str, Any]:
        """Get cluster health information.

        Returns:
            Cluster health dictionary.
        """
        return self._client.cluster.health()

    def get_indices(self) -> list[str]:
        """Get list of all indices.

        Returns:
            List of index names.
        """
        response = self._client.indices.get_alias(index="*")
        return list(response.keys())

    def update_document(
        self,
        index: str,
        doc_id: str,
        doc: dict[str, Any],
        upsert: bool = False,
    ) -> bool:
        """Update a document.

        Args:
            index: Index name.
            doc_id: Document ID.
            doc: Document fields to update.
            upsert: Create if doesn't exist.

        Returns:
            True if successful.
        """
        try:
            body = {"doc": doc}
            if upsert:
                body["doc_as_upsert"] = True
            self._client.update(index=index, id=doc_id, body=body)
            return True
        except Exception:
            return False

    def mget(
        self,
        index: str,
        doc_ids: list[str],
    ) -> list[IndexedDocument]:
        """Get multiple documents by ID.

        Args:
            index: Index name.
            doc_ids: List of document IDs.

        Returns:
            List of documents found.
        """
        response = self._client.mget(index=index, body={"ids": doc_ids})
        documents = []
        for doc in response.get("docs", []):
            if doc.get("found"):
                documents.append(self._doc_to_indexed(doc))
        return documents

    def scroll_search(
        self,
        index: str,
        query: str | dict[str, Any],
        scroll: str = "2m",
        size: int = 100,
    ) -> Iterator[list[SearchResult]]:
        """Scroll through all search results.

        Args:
            index: Index name.
            query: Search query.
            scroll: Scroll duration.
            size: Batch size.

        Yields:
            Batches of search results.
        """
        query_dsl = query if isinstance(query, dict) else {"query_string": {"query": query}}

        response = self._client.search(
            index=index,
            body={"query": query_dsl},
            scroll=scroll,
            size=size,
        )

        scroll_id = response.get("_scroll_id")
        while scroll_id:
            hits = response.get("hits", {}).get("hits", [])
            if not hits:
                break

            yield [self._hit_to_result(hit) for hit in hits]

            response = self._client.scroll(scroll_id=scroll_id, scroll=scroll)
            scroll_id = response.get("_scroll_id")

        if scroll_id:
            self._client.clear_scroll(scroll_id=scroll_id)
