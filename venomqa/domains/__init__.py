"""Domain-specific journey templates for VenomQA.

This module provides pre-built journey templates for common domains:
- ecommerce: Shopping carts, checkout, payments, inventory
- auth: Registration, OAuth, password management
- content: File uploads, search functionality
- realtime: Chat, notifications, WebSocket testing
- api: CRUD operations, rate limiting, versioning
"""

from venomqa.domains import api, auth, content, ecommerce, realtime

__all__ = ["ecommerce", "auth", "content", "realtime", "api"]
