"""Domain-specific journey templates for VenomQA.

This module provides pre-built journey templates for common domains:
- ecommerce: Shopping carts, checkout, payments, inventory
- auth: Registration, OAuth, password management
- content: File uploads, search functionality
- realtime: Chat, notifications, WebSocket testing
- api: CRUD operations, rate limiting, versioning
- security: Vulnerability scanning, injection testing, OWASP checks
"""

from venomqa.domains import api, auth, content, ecommerce, realtime, security

__all__ = ["ecommerce", "auth", "content", "realtime", "api", "security"]
