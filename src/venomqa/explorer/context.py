"""Context extraction and path parameter substitution for state chain exploration."""

import builtins
import re
from typing import Any


class ExplorationContext:
    """Accumulates context (IDs, tokens) through exploration chain."""

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._extracted_keys: set[str] = set()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the context.

        Args:
            key: The key to look up
            default: Default value if key not found

        Returns:
            The value associated with the key, or default if not found
        """
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in the context.

        Args:
            key: The key to set
            value: The value to associate with the key
        """
        self._data[key] = value
        self._extracted_keys.add(key)

    def has(self, key: str) -> bool:
        """Check if a key exists in the context.

        Args:
            key: The key to check

        Returns:
            True if the key exists, False otherwise
        """
        return key in self._data

    def keys(self) -> builtins.set[str]:
        """Get all keys in the context.

        Returns:
            Set of all keys
        """
        return set(self._data.keys())

    def extracted_keys(self) -> builtins.set[str]:
        """Get all keys that were explicitly extracted (not inherited).

        Returns:
            Set of keys that were set via set()
        """
        return self._extracted_keys.copy()

    def copy(self) -> 'ExplorationContext':
        """Create a shallow copy of the context.

        Returns:
            A new ExplorationContext with the same data
        """
        new_ctx = ExplorationContext()
        new_ctx._data = self._data.copy()
        # Don't copy extracted_keys - new context starts fresh for tracking
        return new_ctx

    def to_dict(self) -> dict[str, Any]:
        """Convert context to a dictionary.

        Returns:
            Dictionary copy of the context data
        """
        return self._data.copy()

    def update(self, data: dict[str, Any]) -> None:
        """Update context with multiple key-value pairs.

        Args:
            data: Dictionary of key-value pairs to add
        """
        for key, value in data.items():
            self.set(key, value)

    def __repr__(self) -> str:
        return f"ExplorationContext({self._data})"

    def __len__(self) -> int:
        return len(self._data)


def _normalize_key(key: str) -> str:
    """Normalize a key to snake_case format.

    Converts camelCase to snake_case and ensures consistent formatting.

    Args:
        key: The key to normalize (e.g., 'todoId', 'user_id', 'ID')

    Returns:
        Normalized key in snake_case (e.g., 'todo_id', 'user_id', 'id')
    """
    # Handle all-caps like "ID" -> "id"
    if key.isupper():
        return key.lower()

    # Handle consecutive uppercase letters (e.g., "userID" -> "user_id", "APIKey" -> "api_key")
    # First, handle sequences of uppercase followed by lowercase (e.g., "APIKey" -> "API_Key")
    result = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', key)

    # Then handle lowercase followed by uppercase (e.g., "userId" -> "user_Id")
    result = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', result)

    # Lowercase everything
    result = result.lower()

    # Handle double underscores
    result = re.sub(r'_+', '_', result)

    # Remove leading/trailing underscores
    result = result.strip('_')

    return result


def _infer_context_key_from_endpoint(endpoint: str) -> str | None:
    """Infer the context key name from an endpoint path.

    Extracts the resource name from the endpoint and converts it to
    a singular form with _id suffix.

    Args:
        endpoint: The API endpoint (e.g., '/todos', '/api/v1/users')

    Returns:
        Inferred key name (e.g., 'todo_id', 'user_id') or None if cannot infer
    """
    # Remove query string if present
    endpoint = endpoint.split('?')[0]

    # Split into path segments and filter empty ones
    segments = [s for s in endpoint.split('/') if s and not s.startswith('{')]

    if not segments:
        return None

    # Get the last meaningful segment (ignore version prefixes like 'v1', 'api')
    resource = None
    for segment in reversed(segments):
        # Skip common prefixes
        if segment.lower() in ('api', 'v1', 'v2', 'v3'):
            continue
        resource = segment
        break

    if not resource:
        return None

    # Convert to snake_case
    resource = _normalize_key(resource)

    # Convert plural to singular (simple heuristic)
    if resource.endswith('ies'):
        resource = resource[:-3] + 'y'
    elif resource.endswith('ses'):
        resource = resource[:-2]
    elif resource.endswith('s') and not resource.endswith('ss'):
        resource = resource[:-1]

    # Ensure it ends with _id
    if not resource.endswith('_id'):
        resource = f"{resource}_id"

    return resource


def _flatten_dict(
    data: dict[str, Any],
    prefix: str = "",
    separator: str = "."
) -> list[tuple[str, Any]]:
    """Flatten a nested dictionary into a list of (key_path, value) tuples.

    Args:
        data: The dictionary to flatten
        prefix: Prefix for keys (used in recursion)
        separator: Separator for nested keys

    Returns:
        List of (key_path, value) tuples
    """
    items: list[tuple[str, Any]] = []

    for key, value in data.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key

        if isinstance(value, dict):
            # Recurse into nested dictionaries
            items.extend(_flatten_dict(value, new_key, separator))
        elif isinstance(value, list):
            # Process list items
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    items.extend(_flatten_dict(item, f"{new_key}[{i}]", separator))
        else:
            items.append((new_key, value))

    return items


def extract_context_from_response(
    response_data: dict[str, Any],
    endpoint: str,
    context: ExplorationContext
) -> ExplorationContext:
    """
    Extract IDs, tokens, and references from API response.

    Rules:
    - "id" field -> infer key from endpoint (e.g., /todos -> todo_id)
    - Fields ending in "_id" or "Id" -> use as-is (normalized to snake_case)
    - Token fields -> auth_token, access_token, etc.
    - Nested objects -> recurse
    - Status fields -> capture state information

    Args:
        response_data: The JSON response data to extract from
        endpoint: The API endpoint that produced this response
        context: The existing context to update

    Returns:
        Updated ExplorationContext with extracted values
    """
    if not isinstance(response_data, dict):
        return context

    # Flatten the response to process nested structures
    flat_items = _flatten_dict(response_data)

    for key_path, value in flat_items:
        # Get the immediate key (last part of path)
        key_parts = key_path.replace('[', '.').replace(']', '').split('.')
        immediate_key = key_parts[-1]

        # Skip None values
        if value is None:
            continue

        # Rule 1: "id" field -> infer from endpoint
        if immediate_key == "id":
            context_key = _infer_context_key_from_endpoint(endpoint)
            if context_key:
                context.set(context_key, value)
            # Also set a generic 'id' if it's at the root level
            if '.' not in key_path and '[' not in key_path:
                context.set("id", value)

        # Rule 2: Fields ending in "_id" or "Id"
        elif immediate_key.endswith("_id") or immediate_key.endswith("Id"):
            normalized_key = _normalize_key(immediate_key)
            context.set(normalized_key, value)

        # Rule 3: Token fields
        elif immediate_key in ("token", "access_token", "auth_token", "refresh_token", "api_key"):
            # Normalize token field names
            if immediate_key == "token":
                context.set("auth_token", value)
            else:
                context.set(_normalize_key(immediate_key), value)

        # Rule 4: Status/state fields (for state naming)
        elif immediate_key in ("status", "state", "completed", "active", "verified"):
            context.set(immediate_key, value)

    # Handle top-level ID separately if present (common case)
    if "id" in response_data and response_data["id"] is not None:
        context_key = _infer_context_key_from_endpoint(endpoint)
        if context_key:
            context.set(context_key, response_data["id"])

    return context


def substitute_path_params(
    endpoint: str,
    context: ExplorationContext
) -> str | None:
    """
    Replace {param} placeholders with actual context values.

    Returns None if any placeholder can't be resolved.

    The function tries multiple variations to find a matching context value:
    1. Exact match (e.g., {todoId} -> context['todoId'])
    2. Snake_case conversion (e.g., {todoId} -> context['todo_id'])
    3. With _id suffix (e.g., {todo} -> context['todo_id'])
    4. CamelCase to snake_case with _id (e.g., {fileId} -> context['file_id'])

    Args:
        endpoint: The endpoint with {param} placeholders
        context: The context containing substitution values

    Returns:
        The endpoint with all placeholders resolved, or None if any
        placeholder cannot be resolved

    Examples:
        - /todos/{todoId} + todo_id=42 -> /todos/42
        - /todos/{todoId}/attachments/{fileId} + todo_id=42, file_id=abc -> /todos/42/attachments/abc
    """
    result = endpoint

    # Find all placeholders in the endpoint
    placeholders = re.findall(r'\{(\w+)\}', endpoint)

    for placeholder in placeholders:
        value = None

        # Try 1: Exact match
        if context.has(placeholder):
            value = context.get(placeholder)

        # Try 2: Snake_case conversion (e.g., todoId -> todo_id)
        elif context.has(_normalize_key(placeholder)):
            value = context.get(_normalize_key(placeholder))

        # Try 3: With _id suffix (e.g., todo -> todo_id)
        elif not placeholder.endswith('Id') and not placeholder.endswith('_id'):
            key_with_id = f"{_normalize_key(placeholder)}_id"
            if context.has(key_with_id):
                value = context.get(key_with_id)

        # Try 4: Remove 'Id' suffix and add '_id' (e.g., todoId -> todo_id already covered by normalize)
        # This is already handled by _normalize_key

        # Try 5: Check for the generic 'id' if placeholder suggests it
        if value is None and placeholder.lower() == 'id':
            if context.has('id'):
                value = context.get('id')

        # If we still haven't found a value, return None
        if value is None:
            return None

        # Substitute the placeholder
        result = result.replace(f'{{{placeholder}}}', str(value))

    return result


def generate_state_name(
    context: ExplorationContext,
    response_data: dict[str, Any]
) -> str:
    """
    Generate human-readable state name from context.

    Creates a descriptive state name based on authentication status,
    resource IDs, and current state flags.

    Args:
        context: The current exploration context
        response_data: The response data that led to this state

    Returns:
        A human-readable state name

    Examples:
        - "Anonymous"
        - "Anonymous | Todo:42"
        - "Authenticated | User:5 | Todo:42 | Completed"
    """
    parts: list[str] = []

    # Authentication status
    if context.get("auth_token") or context.get("access_token"):
        parts.append("Authenticated")
    else:
        parts.append("Anonymous")

    # User identification
    user_id = context.get("user_id")
    if user_id is not None:
        parts.append(f"User:{user_id}")

    # Common resource IDs (in logical order)
    id_fields = [
        ("order_id", "Order"),
        ("todo_id", "Todo"),
        ("item_id", "Item"),
        ("product_id", "Product"),
        ("cart_id", "Cart"),
        ("attachment_id", "Attachment"),
        ("file_id", "File"),
        ("comment_id", "Comment"),
        ("post_id", "Post"),
    ]

    for key, label in id_fields:
        value = context.get(key)
        if value is not None:
            parts.append(f"{label}:{value}")

    # Status indicators from response or context
    status_fields = [
        ("completed", "Completed", True),
        ("active", "Active", True),
        ("verified", "Verified", True),
        ("deleted", "Deleted", True),
        ("pending", "Pending", True),
    ]

    for field, label, expected_value in status_fields:
        # Check both response_data and context
        value = response_data.get(field) if response_data else None
        if value is None:
            value = context.get(field)

        if value == expected_value:
            parts.append(label)

    # Handle status/state string fields
    status = response_data.get("status") if response_data else context.get("status")
    if status and isinstance(status, str):
        # Capitalize the status for display
        parts.append(status.capitalize())

    # If we only have "Anonymous" or "Authenticated", that's the state
    if len(parts) == 1:
        return parts[0]

    return " | ".join(parts)


def has_unresolved_placeholders(endpoint: str) -> bool:
    """Check if an endpoint still has unresolved {param} placeholders.

    Args:
        endpoint: The endpoint to check

    Returns:
        True if there are unresolved placeholders, False otherwise
    """
    return bool(re.search(r'\{[^}]+\}', endpoint))


def get_required_placeholders(endpoint: str) -> list[str]:
    """Get list of placeholder names required by an endpoint.

    Args:
        endpoint: The endpoint with placeholders

    Returns:
        List of placeholder names (without braces)
    """
    return re.findall(r'\{(\w+)\}', endpoint)


def can_resolve_endpoint(endpoint: str, context: ExplorationContext) -> bool:
    """Check if all placeholders in an endpoint can be resolved.

    Args:
        endpoint: The endpoint with placeholders
        context: The context to check against

    Returns:
        True if all placeholders can be resolved, False otherwise
    """
    return substitute_path_params(endpoint, context) is not None
