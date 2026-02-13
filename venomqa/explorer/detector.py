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
from typing import Any, Callable, Dict, List, Optional, Set

from venomqa.explorer.models import Action, State, StateID


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

        # TODO: Initialize default extractors
        # TODO: Set up common state detection patterns

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

        # Create and cache the state
        from datetime import datetime
        state = State(
            id=state_id,
            name=state_name,
            properties=properties,
            available_actions=available_actions,
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

        return actions

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
            for rel, link_data in response["_links"].items():
                if isinstance(link_data, dict) and "href" in link_data:
                    method = link_data.get("method", "GET").upper()
                    actions.append(Action(
                        method=method,
                        endpoint=link_data["href"],
                        description=rel,
                    ))

        # Look for links array (JSON:API format)
        if "links" in response and isinstance(response["links"], list):
            for link in response["links"]:
                if isinstance(link, dict) and "href" in link:
                    method = link.get("method", "GET").upper()
                    actions.append(Action(
                        method=method,
                        endpoint=link["href"],
                        description=link.get("rel", ""),
                    ))

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
