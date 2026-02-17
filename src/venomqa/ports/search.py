"""Search Port interface for VenomQA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class IndexedDocument:
    """Represents a document to be indexed."""

    id: str
    content: str
    title: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    timestamp: datetime | None = None


@dataclass
class SearchResult:
    """Represents a search result."""

    id: str
    score: float
    document: IndexedDocument | None = None
    highlights: dict[str, list[str]] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchIndex:
    """Information about a search index."""

    name: str
    document_count: int = 0
    size_bytes: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    settings: dict[str, Any] = field(default_factory=dict)


class SearchPort(ABC):
    """Abstract port for search engine operations in QA testing.

    This port defines the interface for search engines like
    Elasticsearch, Solr, etc. Implementations should support
    indexing, searching, and index management.
    """

    @abstractmethod
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
        ...

    @abstractmethod
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
        ...

    @abstractmethod
    def get_document(self, index: str, doc_id: str) -> IndexedDocument | None:
        """Get a document by ID.

        Args:
            index: Index name.
            doc_id: Document ID.

        Returns:
            The document or None if not found.
        """
        ...

    @abstractmethod
    def delete_document(self, index: str, doc_id: str) -> bool:
        """Delete a document by ID.

        Args:
            index: Index name.
            doc_id: Document ID.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
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
        ...

    @abstractmethod
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
        ...

    @abstractmethod
    def delete_index(self, name: str) -> bool:
        """Delete an index.

        Args:
            name: Index name.

        Returns:
            True if successful.
        """
        ...

    @abstractmethod
    def index_exists(self, name: str) -> bool:
        """Check if an index exists.

        Args:
            name: Index name.

        Returns:
            True if exists, False otherwise.
        """
        ...

    @abstractmethod
    def get_index(self, name: str) -> SearchIndex | None:
        """Get information about an index.

        Args:
            name: Index name.

        Returns:
            Index information or None if not found.
        """
        ...

    @abstractmethod
    def refresh_index(self, name: str) -> bool:
        """Refresh an index to make changes visible.

        Args:
            name: Index name.

        Returns:
            True if successful.
        """
        ...

    @abstractmethod
    def clear_index(self, name: str) -> bool:
        """Clear all documents from an index.

        Args:
            name: Index name.

        Returns:
            True if successful.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the search service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        ...
