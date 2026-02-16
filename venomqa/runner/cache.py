"""Response caching for journey execution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.performance import ResponseCache

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages HTTP response caching for journey execution.

    This class handles:
    - Checking cache for existing responses
    - Storing new responses in cache
    - Tracking cache hit/miss statistics
    """

    def __init__(
        self,
        cache: ResponseCache | None = None,
        enabled: bool = False,
        ttl: float = 300.0,
        cacheable_methods: set[str] | None = None,
    ) -> None:
        """Initialize the cache manager.

        Args:
            cache: The response cache implementation.
            enabled: Whether caching is enabled.
            ttl: Time-to-live for cached responses in seconds.
            cacheable_methods: HTTP methods that can be cached.
        """
        self.cache = cache
        self.enabled = enabled and cache is not None
        self.ttl = ttl
        self.cacheable_methods = cacheable_methods or {"GET", "HEAD", "OPTIONS"}
        self._hits = 0
        self._misses = 0

    def try_get_cached_response(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        body: Any,
    ) -> Any | None:
        """Try to get a cached response for the request.

        Args:
            method: HTTP method.
            url: Request URL.
            headers: Request headers.
            body: Request body.

        Returns:
            Cached response if available, None otherwise.
        """
        if not self.enabled or not self.cache:
            return None

        if method.upper() not in self.cacheable_methods:
            return None

        key = self.cache.compute_key(method, url, headers, body)
        cached = self.cache.get(key)

        if cached is not None:
            self._hits += 1
            logger.debug(f"Cache hit for {method} {url}")
            from venomqa.performance.cache import CachedResponse

            if isinstance(cached, dict):
                return CachedResponse(
                    status_code=cached.get("status_code", 200),
                    headers=cached.get("headers", {}),
                    body=cached.get("body"),
                    from_cache=True,
                )
            return cached

        self._misses += 1
        return None

    def cache_response(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        body: Any,
        response: Any,
    ) -> None:
        """Cache a response if caching is enabled and method is cacheable.

        Args:
            method: HTTP method.
            url: Request URL.
            headers: Request headers.
            body: Request body.
            response: Response to cache.
        """
        if not self.enabled or not self.cache:
            return

        if method.upper() not in self.cacheable_methods:
            return

        if hasattr(response, "status_code") and response.status_code >= 400:
            return

        key = self.cache.compute_key(method, url, headers, body)

        cached_data = {
            "status_code": getattr(response, "status_code", 200),
            "headers": dict(getattr(response, "headers", {})),
            "body": self._safe_json(response),
        }

        self.cache.set(key, cached_data, ttl=self.ttl)
        logger.debug(f"Cached response for {method} {url}")

    def _safe_json(self, response: Any) -> Any:
        """Safely extract JSON from response."""
        try:
            if hasattr(response, "json"):
                return response.json()
        except Exception:
            pass
        if hasattr(response, "text"):
            return response.text
        return str(response)

    def get_stats(self) -> dict[str, Any]:
        """Get caching statistics.

        Returns:
            Dictionary with cache statistics.
        """
        if not self.cache:
            return {"enabled": False}

        stats = self.cache.get_stats()
        return {
            "enabled": True,
            "hits": self._hits,
            "misses": self._misses,
            **stats.to_dict(),
        }

    def clear(self) -> None:
        """Clear the cache."""
        if self.cache:
            self.cache.clear()
        self._hits = 0
        self._misses = 0
