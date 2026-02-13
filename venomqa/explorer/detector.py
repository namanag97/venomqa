"""
State Detector for the VenomQA State Explorer module.

This module provides the StateDetector class which infers application
state from API responses. It analyzes response data to determine the
current state of the application and what actions are available.

State detection is crucial for building an accurate state graph and
understanding application behavior.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import re
from venomqa.explorer.models import Action, State, StateID


# Common authentication-related field names
AUTH_TOKEN_FIELDS = {
    "token",
    "access_token",
    "accessToken",
    "auth_token",
    "authToken",
    "jwt",
    "bearer",
    "id_token",
    "idToken",
    "refresh_token",
    "refreshToken",
    "session_token",
    "sessionToken",
    "api_key",
    "apiKey",
}

# Common user/identity field names
USER_FIELDS = {
    "user",
    "user_id",
    "userId",
    "username",
    "email",
    "name",
    "displayName",
    "display_name",
    "account",
    "profile",
    "identity",
    "sub",  # JWT subject claim
    "uid",
}

# Common entity identifier field names
ENTITY_ID_FIELDS = {
    "id",
    "_id",
    "uuid",
    "guid",
    "pk",
    "key",
    "slug",
}

# Common status/state field names
STATUS_FIELDS = {
    "status",
    "state",
    "phase",
    "stage",
    "condition",
    "lifecycle",
}


class AuthState:
    """Represents detected authentication state."""

    def __init__(
        self,
        is_authenticated: bool = False,
        has_token: bool = False,
        token_type: Optional[str] = None,
        user_info: Optional[Dict[str, Any]] = None,
        roles: Optional[List[str]] = None,
        permissions: Optional[List[str]] = None,
    ) -> None:
        self.is_authenticated = is_authenticated
        self.has_token = has_token
        self.token_type = token_type
        self.user_info = user_info or {}
        self.roles = roles or []
        self.permissions = permissions or []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "is_authenticated": self.is_authenticated,
            "has_token": self.has_token,
            "token_type": self.token_type,
            "user_info": self.user_info,
            "roles": self.roles,
            "permissions": self.permissions,
        }


class EntityState:
    """Represents detected entity state."""

    def __init__(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        status: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.status = status
        self.properties = properties or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "status": self.status,
            "properties": self.properties,
        }


class StateDetector:
    """
    Infers application state from API responses.

    The StateDetector analyzes API responses to determine:
    - The current state of the application
    - What actions are available from this state
    - State properties and metadata

    It uses various strategies for state inference:
    - Response structure analysis
    - Field presence/absence detection
    - Value-based state detection
    - Custom state extractors

    Attributes:
        state_extractors: Custom functions for extracting state
        action_extractors: Custom functions for extracting available actions
        known_states: Cache of previously detected states
        state_key_fields: Fields used to identify unique states

    Example:
        detector = StateDetector()
        detector.add_state_key_field("status")
        state = detector.detect_state(response_data)
        print(f"Current state: {state.name}")
    """

    def __init__(self) -> None:
        """Initialize the state detector."""
        self.state_extractors: List[Callable[[Dict[str, Any]], Optional[State]]] = []
        self.action_extractors: List[Callable[[Dict[str, Any]], List[Action]]] = []
        self.known_states: Dict[StateID, State] = {}
        self.state_key_fields: List[str] = []
        self._state_hashes: Dict[str, StateID] = {}

        # Initialize default state key fields
        self.state_key_fields = ["status", "state", "phase"]

    def detect_state(
        self,
        response: Dict[str, Any],
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
    ) -> State:
        """
        Detect the current state from an API response.

        Args:
            response: The API response data
            endpoint: The endpoint that was called (for context)
            method: The HTTP method used (for context)

        Returns:
            The detected State object
        """
        # Try custom state extractors first
        for extractor in self.state_extractors:
            extracted_state = extractor(response)
            if extracted_state is not None:
                self.known_states[extracted_state.id] = extracted_state
                return extracted_state

        # Fall back to automatic detection
        state_id = self._generate_state_id(response, endpoint)

        # Check if we already know this state
        if state_id in self.known_states:
            return self.known_states[state_id]

        # Extract state properties
        properties = self._extract_state_properties(response)

        # Detect available actions
        available_actions = self.detect_available_actions(response)

        # Infer state name
        state_name = self._infer_state_name(response, endpoint)

        # Build metadata
        metadata: Dict[str, Any] = {}
        if endpoint:
            metadata["endpoint"] = endpoint
        if method:
            metadata["method"] = method

        # Detect auth state and add to metadata
        auth_state = self.detect_auth_state(response)
        if auth_state.is_authenticated:
            metadata["auth_state"] = auth_state.to_dict()

        # Detect entity state and add to metadata
        entity_state = self.detect_entity_state(response, endpoint)
        if entity_state.entity_type or entity_state.entity_id:
            metadata["entity_state"] = entity_state.to_dict()

        # Create and cache the state
        state = State(
            id=state_id,
            name=state_name,
            properties=properties,
            available_actions=available_actions,
            metadata=metadata,
            discovered_at=datetime.now(),
        )

        self.known_states[state_id] = state
        return state

    def detect_available_actions(
        self,
        response: Dict[str, Any],
        current_state: Optional[State] = None,
    ) -> List[Action]:
        """
        Detect available actions from an API response.

        Args:
            response: The API response data
            current_state: The current state (for context)

        Returns:
            List of available Action objects
        """
        actions: List[Action] = []

        # Try custom action extractors first
        for extractor in self.action_extractors:
            extracted_actions = extractor(response)
            actions.extend(extracted_actions)

        # Look for HATEOAS links
        hateoas_actions = self._extract_links(response)
        actions.extend(hateoas_actions)

        # Deduplicate actions
        seen: Set[Tuple[str, str]] = set()
        unique_actions: List[Action] = []
        for action in actions:
            key = (action.method, action.endpoint)
            if key not in seen:
                seen.add(key)
                unique_actions.append(action)

        return unique_actions

    def detect_auth_state(self, response: Dict[str, Any]) -> AuthState:
        """
        Detect authentication state from response.

        Args:
            response: The API response data

        Returns:
            AuthState object with detected auth information
        """
        auth_state = AuthState()

        # Check for tokens in response
        token_type = None
        for field in AUTH_TOKEN_FIELDS:
            if field in response:
                auth_state.has_token = True
                if "access" in field.lower():
                    token_type = "access_token"
                elif "refresh" in field.lower():
                    token_type = "refresh_token"
                elif "jwt" in field.lower() or "bearer" in field.lower():
                    token_type = "jwt"
                else:
                    token_type = "token"
                break

            # Check nested data
            if "data" in response and isinstance(response["data"], dict):
                if field in response["data"]:
                    auth_state.has_token = True
                    token_type = "token"
                    break

        auth_state.token_type = token_type

        # Check for user info
        user_info: Dict[str, Any] = {}
        for field in USER_FIELDS:
            if field in response:
                value = response[field]
                if isinstance(value, dict):
                    user_info.update(value)
                else:
                    user_info[field] = value

            # Check nested data
            if "data" in response and isinstance(response["data"], dict):
                if field in response["data"]:
                    value = response["data"][field]
                    if isinstance(value, dict):
                        user_info.update(value)
                    else:
                        user_info[field] = value

        auth_state.user_info = user_info

        # Determine if authenticated
        auth_state.is_authenticated = auth_state.has_token or bool(user_info)

        # Extract roles/permissions if present
        if "roles" in response:
            roles = response["roles"]
            if isinstance(roles, list):
                auth_state.roles = roles
        if "permissions" in response:
            perms = response["permissions"]
            if isinstance(perms, list):
                auth_state.permissions = perms

        # Check user object for roles
        if "user" in response and isinstance(response["user"], dict):
            user = response["user"]
            if "roles" in user and isinstance(user["roles"], list):
                auth_state.roles = user["roles"]
            if "permissions" in user and isinstance(user["permissions"], list):
                auth_state.permissions = user["permissions"]

        return auth_state

    def detect_entity_state(
        self,
        response: Dict[str, Any],
        endpoint: Optional[str] = None,
    ) -> EntityState:
        """
        Detect entity state from response.

        Args:
            response: The API response data
            endpoint: The endpoint for context

        Returns:
            EntityState object with detected entity information
        """
        entity_state = EntityState()

        # Try to infer entity type from endpoint
        if endpoint:
            entity_type = self._infer_entity_type_from_endpoint(endpoint)
            if entity_type:
                entity_state.entity_type = entity_type

        # Look for entity ID
        for field in ENTITY_ID_FIELDS:
            if field in response:
                entity_state.entity_id = str(response[field])
                break
            # Check nested data
            if "data" in response and isinstance(response["data"], dict):
                if field in response["data"]:
                    entity_state.entity_id = str(response["data"][field])
                    break

        # Look for status
        for field in STATUS_FIELDS:
            if field in response:
                entity_state.status = str(response[field])
                break
            # Check nested data
            if "data" in response and isinstance(response["data"], dict):
                if field in response["data"]:
                    entity_state.status = str(response["data"][field])
                    break

        # Extract other properties (exclude known fields)
        excluded = AUTH_TOKEN_FIELDS | USER_FIELDS | ENTITY_ID_FIELDS | STATUS_FIELDS
        properties: Dict[str, Any] = {}
        for key, value in response.items():
            if key not in excluded and not key.startswith("_"):
                # Only include simple types for properties
                if isinstance(value, (str, int, float, bool)):
                    properties[key] = value
                elif isinstance(value, list) and len(value) > 0:
                    # Store list length as a property
                    properties[f"{key}_count"] = len(value)

        entity_state.properties = properties

        return entity_state

    def fingerprint(self, response: Dict[str, Any]) -> str:
        """
        Create a unique fingerprint for a response.

        This creates a hash-based signature that can identify
        equivalent states across different API calls.

        Args:
            response: The API response data

        Returns:
            A hex string fingerprint
        """
        # Extract key fields for fingerprinting
        fingerprint_data: Dict[str, Any] = {}

        # Include state key fields
        for field in self.state_key_fields:
            if field in response:
                fingerprint_data[field] = response[field]
            elif "data" in response and isinstance(response["data"], dict):
                if field in response["data"]:
                    fingerprint_data[field] = response["data"][field]

        # Include entity identifiers
        for field in ENTITY_ID_FIELDS:
            if field in response:
                fingerprint_data[f"_id_{field}"] = response[field]
                break

        # Include auth presence (but not actual tokens)
        has_auth = any(field in response for field in AUTH_TOKEN_FIELDS)
        fingerprint_data["_has_auth"] = has_auth

        # Include response structure signature
        structure = self._get_structure_signature(response)
        fingerprint_data["_structure"] = structure

        # Create hash
        canonical = json.dumps(fingerprint_data, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def _infer_entity_type_from_endpoint(self, endpoint: str) -> Optional[str]:
        """
        Infer entity type from endpoint path.

        Args:
            endpoint: The API endpoint

        Returns:
            Inferred entity type or None
        """
        # Remove leading slash and split
        path = endpoint.lstrip("/")
        segments = path.split("/")

        # Skip common prefixes
        skip_prefixes = {"api", "v1", "v2", "v3", "rest", "graphql"}

        for segment in segments:
            # Skip version numbers and common prefixes
            if segment.lower() in skip_prefixes:
                continue
            if re.match(r"^v\d+$", segment.lower()):
                continue

            # Skip IDs (numeric or UUID-like)
            if re.match(r"^\d+$", segment):
                continue
            if re.match(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                segment.lower()
            ):
                continue

            # Found a likely entity type
            # Singularize if ends with 's'
            if segment.endswith("s") and len(segment) > 2:
                return segment[:-1]
            return segment

        return None

    def _get_structure_signature(self, response: Dict[str, Any]) -> str:
        """
        Get a signature representing the structure of the response.

        Args:
            response: The API response data

        Returns:
            A string signature of the response structure
        """
        def get_type_sig(value: Any, depth: int = 0) -> str:
            if depth > 3:  # Limit depth
                return "..."
            if isinstance(value, dict):
                keys = sorted(value.keys())[:10]  # Limit keys
                return "{" + ",".join(keys) + "}"
            elif isinstance(value, list):
                if len(value) > 0:
                    return "[" + get_type_sig(value[0], depth + 1) + "]"
                return "[]"
            elif isinstance(value, str):
                return "str"
            elif isinstance(value, bool):
                return "bool"
            elif isinstance(value, int):
                return "int"
            elif isinstance(value, float):
                return "float"
            elif value is None:
                return "null"
            return "?"

        return get_type_sig(response)

    def add_state_extractor(
        self,
        extractor: Callable[[Dict[str, Any]], Optional[State]],
    ) -> None:
        """
        Add a custom state extraction function.

        Args:
            extractor: Function that takes response data and returns a State or None
        """
        self.state_extractors.append(extractor)

    def add_action_extractor(
        self,
        extractor: Callable[[Dict[str, Any]], List[Action]],
    ) -> None:
        """
        Add a custom action extraction function.

        Args:
            extractor: Function that takes response data and returns list of Actions
        """
        self.action_extractors.append(extractor)

    def add_state_key_field(self, field: str) -> None:
        """
        Add a field to use for state identification.

        State key fields are used to determine if two responses
        represent the same application state.

        Args:
            field: The field name to use as a state key
        """
        if field not in self.state_key_fields:
            self.state_key_fields.append(field)

    def set_state_key_fields(self, fields: List[str]) -> None:
        """
        Set the fields to use for state identification.

        Args:
            fields: List of field names to use as state keys
        """
        self.state_key_fields = fields.copy()

    def _generate_state_id(
        self,
        response: Dict[str, Any],
        endpoint: Optional[str] = None,
    ) -> StateID:
        """
        Generate a unique state ID from response data.

        Args:
            response: The API response data
            endpoint: The endpoint context

        Returns:
            A unique state identifier
        """
        # Extract relevant fields based on state_key_fields
        key_values = {}
        if self.state_key_fields:
            for field in self.state_key_fields:
                if field in response:
                    key_values[field] = response[field]
        else:
            # Use the whole response for hashing if no key fields defined
            key_values = response

        # Create a canonical representation
        canonical = json.dumps(key_values, sort_keys=True, default=str)

        # Add endpoint context if provided
        if endpoint:
            canonical = f"{endpoint}:{canonical}"

        # Generate a hash-based ID
        hash_id = hashlib.sha256(canonical.encode()).hexdigest()[:16]

        # Handle deduplication via hash lookup
        if canonical in self._state_hashes:
            return self._state_hashes[canonical]

        state_id = f"state_{hash_id}"
        self._state_hashes[canonical] = state_id
        return state_id

    def _extract_state_properties(
        self,
        response: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract state-relevant properties from response data.

        Args:
            response: The API response data

        Returns:
            Dictionary of state properties
        """
        # Filter out transient/non-relevant fields
        transient_fields = {
            "timestamp", "created_at", "updated_at", "request_id",
            "_links", "links", "meta", "_meta"
        }

        properties: Dict[str, Any] = {}
        for key, value in response.items():
            # Skip transient fields
            if key.lower() in transient_fields:
                continue
            # Include scalar values and small lists/dicts
            if isinstance(value, (str, int, float, bool, type(None))):
                properties[key] = value
            elif isinstance(value, (list, dict)) and len(str(value)) < 500:
                properties[key] = value

        return properties

    def _extract_links(
        self,
        response: Dict[str, Any],
    ) -> List[Action]:
        """
        Extract HATEOAS-style links from response data.

        Args:
            response: The API response data

        Returns:
            List of Action objects from discovered links
        """
        actions: List[Action] = []

        # Look for _links (HAL format)
        if "_links" in response and isinstance(response["_links"], dict):
            actions.extend(self._parse_hal_links(response["_links"]))

        # Look for links array
        if "links" in response and isinstance(response["links"], list):
            actions.extend(self._parse_links_array(response["links"]))

        # Look for links dict (JSON:API format)
        if "links" in response and isinstance(response["links"], dict):
            actions.extend(self._parse_jsonapi_links(response["links"]))

        # Look for actions/operations array
        if "actions" in response and isinstance(response["actions"], list):
            actions.extend(self._parse_actions_array(response["actions"]))
        if "operations" in response and isinstance(response["operations"], list):
            actions.extend(self._parse_actions_array(response["operations"]))

        return actions

    def _parse_hal_links(self, links: Dict[str, Any]) -> List[Action]:
        """Parse HAL-style _links object."""
        actions: List[Action] = []

        for rel, link_data in links.items():
            if rel == "self":
                continue  # Skip self link

            if isinstance(link_data, dict):
                href = link_data.get("href")
                method = link_data.get("method", "GET").upper()
                title = link_data.get("title") or link_data.get("name") or rel

                if href:
                    actions.append(
                        Action(
                            method=method,
                            endpoint=href,
                            description=title,
                        )
                    )
            elif isinstance(link_data, list):
                # Multiple links for same rel
                for item in link_data:
                    if isinstance(item, dict):
                        href = item.get("href")
                        method = item.get("method", "GET").upper()
                        if href:
                            actions.append(
                                Action(
                                    method=method,
                                    endpoint=href,
                                    description=rel,
                                )
                            )

        return actions

    def _parse_links_array(self, links: List[Any]) -> List[Action]:
        """Parse links array format."""
        actions: List[Action] = []

        for link in links:
            if not isinstance(link, dict):
                continue

            href = link.get("href") or link.get("url") or link.get("uri")
            rel = link.get("rel") or link.get("relation") or link.get("name")
            method = link.get("method", "GET").upper()

            if href and rel != "self":
                actions.append(
                    Action(
                        method=method,
                        endpoint=href,
                        description=rel,
                    )
                )

        return actions

    def _parse_jsonapi_links(self, links: Dict[str, Any]) -> List[Action]:
        """Parse JSON:API style links object."""
        actions: List[Action] = []

        for rel, link in links.items():
            if rel == "self":
                continue

            href = None
            if isinstance(link, str):
                href = link
            elif isinstance(link, dict):
                href = link.get("href")

            if href:
                # Infer method from rel name
                method = "GET"
                if rel in ("create", "add", "new"):
                    method = "POST"
                elif rel in ("update", "edit", "modify"):
                    method = "PUT"
                elif rel in ("delete", "remove", "destroy"):
                    method = "DELETE"

                actions.append(
                    Action(
                        method=method,
                        endpoint=href,
                        description=rel,
                    )
                )

        return actions

    def _parse_actions_array(self, actions_data: List[Any]) -> List[Action]:
        """Parse actions/operations array."""
        actions: List[Action] = []

        for action_item in actions_data:
            if not isinstance(action_item, dict):
                continue

            # Various ways to specify action
            href = (
                action_item.get("href")
                or action_item.get("url")
                or action_item.get("uri")
                or action_item.get("endpoint")
            )
            method = (
                action_item.get("method")
                or action_item.get("type")
                or "GET"
            ).upper()
            name = (
                action_item.get("name")
                or action_item.get("title")
                or action_item.get("description")
                or action_item.get("action")
            )

            if href:
                actions.append(
                    Action(
                        method=method,
                        endpoint=href,
                        description=name,
                    )
                )

        return actions

    def _infer_state_name(
        self,
        response: Dict[str, Any],
        endpoint: Optional[str] = None,
    ) -> str:
        """
        Infer a human-readable state name.

        Args:
            response: The API response data
            endpoint: The endpoint context

        Returns:
            A human-readable state name
        """
        # Use status/state fields if present
        for field in ["status", "state", "phase", "stage"]:
            if field in response:
                value = response[field]
                if isinstance(value, str):
                    return value.replace("_", " ").title()

        # Use endpoint context
        if endpoint:
            # Clean up endpoint to make a name
            name = endpoint.strip("/").replace("/", "_").replace("{", "").replace("}", "")
            return f"State_{name}" if name else "State_Root"

        # Generate from response structure
        if "type" in response:
            return f"State_{response['type']}"

        return "Unknown_State"

    def is_same_state(self, state1: State, state2: State) -> bool:
        """
        Check if two states represent the same application state.

        Args:
            state1: First state to compare
            state2: Second state to compare

        Returns:
            True if states are equivalent
        """
        # Compare state IDs first
        if state1.id == state2.id:
            return True

        # If different IDs, compare key properties
        if self.state_key_fields:
            for field in self.state_key_fields:
                val1 = state1.properties.get(field)
                val2 = state2.properties.get(field)
                if val1 != val2:
                    return False
            return True

        # If no key fields, states with different IDs are different
        return False

    def get_known_state(self, state_id: StateID) -> Optional[State]:
        """
        Get a previously detected state by ID.

        Args:
            state_id: The state ID to look up

        Returns:
            The State object if known, None otherwise
        """
        return self.known_states.get(state_id)

    def clear_cache(self) -> None:
        """Clear the known states cache."""
        self.known_states.clear()
        self._state_hashes.clear()

    def get_known_states(self) -> List[State]:
        """
        Get all known states.

        Returns:
            List of all cached State objects
        """
        return list(self.known_states.values())
