"""Results persistence for journey execution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.core.models import Journey, JourneyResult
    from venomqa.storage import ResultsRepository

logger = logging.getLogger(__name__)


class ResultsPersister:
    """Persists journey results to storage.

    This class handles:
    - Saving journey results to a repository
    - Managing tags and metadata
    - Lazy initialization of the repository
    """

    def __init__(
        self,
        repository: ResultsRepository | None = None,
        enabled: bool = False,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the results persister.

        Args:
            repository: The results repository implementation.
            enabled: Whether persistence is enabled.
            tags: Default tags to apply to all results.
            metadata: Default metadata to include with results.
        """
        self.repository = repository
        self.enabled = enabled or repository is not None
        self.tags = tags or []
        self.metadata = metadata or {}

    def persist(
        self,
        result: JourneyResult,
        journey: Journey,
        extra_metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Persist a journey result to storage.

        Args:
            result: The JourneyResult to persist.
            journey: The Journey that was executed.
            extra_metadata: Additional metadata to include.

        Returns:
            The run ID if persisted, None otherwise.
        """
        if not self.enabled:
            return None

        try:
            # Lazy import to avoid circular imports
            if self.repository is None:
                from venomqa.storage import ResultsRepository

                self.repository = ResultsRepository()
                self.repository.initialize()

            # Merge journey tags with configured tags
            tags = list(set(self.tags + getattr(journey, "tags", [])))

            # Build metadata
            metadata = {
                **self.metadata,
                "journey_description": getattr(journey, "description", ""),
                **(extra_metadata or {}),
            }

            run_id = self.repository.save_journey_result(
                result,
                tags=tags,
                metadata=metadata,
            )

            logger.info(f"Persisted journey result: {result.journey_name} (run_id: {run_id})")
            return run_id

        except Exception as e:
            logger.warning(f"Failed to persist journey result: {e}")
            return None

    def close(self) -> None:
        """Close the repository connection."""
        if self.repository:
            self.repository.close()
