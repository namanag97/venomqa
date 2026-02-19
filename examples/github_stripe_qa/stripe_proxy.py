"""Picklable proxy for the Stripe HttpClient.

VenomQA's World.checkpoint() uses copy.deepcopy() on context data.
httpx.Client (inside HttpClient) contains threading.RLock objects that cannot
be deep-copied. This proxy wraps HttpClient and implements __deepcopy__ to
reconstruct from just the base_url, avoiding the unpicklable internals.
"""

from __future__ import annotations

from venomqa.adapters.http import HttpClient
from venomqa.core.action import ActionResult


class StripeProxy:
    """Thin, deepcopy-safe wrapper around HttpClient for Stripe."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self._client = HttpClient(base_url)

    # deepcopy just reconstructs with the same URL — no lock objects copied
    def __deepcopy__(self, memo: dict) -> "StripeProxy":
        clone = StripeProxy(self.base_url)
        memo[id(self)] = clone
        return clone

    # Pickle support (used by some serializers)
    def __getstate__(self) -> dict:
        return {"base_url": self.base_url}

    def __setstate__(self, state: dict) -> None:
        self.base_url = state["base_url"]
        self._client = HttpClient(self.base_url)

    # Delegate HTTP methods
    def post(self, path: str, **kwargs) -> ActionResult:  # type: ignore[no-untyped-def]
        return self._client.post(path, **kwargs)

    def get(self, path: str, **kwargs) -> ActionResult:  # type: ignore[no-untyped-def]
        return self._client.get(path, **kwargs)

    def put(self, path: str, **kwargs) -> ActionResult:  # type: ignore[no-untyped-def]
        return self._client.put(path, **kwargs)

    def patch(self, path: str, **kwargs) -> ActionResult:  # type: ignore[no-untyped-def]
        return self._client.patch(path, **kwargs)

    def delete(self, path: str, **kwargs) -> ActionResult:  # type: ignore[no-untyped-def]
        return self._client.delete(path, **kwargs)

    def close(self) -> None:
        self._client.close()
