"""OpenAPI specification parser for inferring resource schemas.

This module extracts resource type hierarchies from OpenAPI specifications
by analyzing URL path patterns and response schemas.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .type_system import ResourceSchema, ResourceType


class OpenAPIParser:
    """Parser that extracts ResourceSchema from OpenAPI specifications.

    Analyzes API paths to infer resource types and their parent/child
    relationships based on URL nesting patterns.

    Example:
        >>> parser = OpenAPIParser()
        >>> schema = parser.parse({
        ...     "paths": {
        ...         "/workspaces": {},
        ...         "/workspaces/{workspace_id}": {},
        ...         "/workspaces/{workspace_id}/uploads": {},
        ...         "/workspaces/{workspace_id}/uploads/{upload_id}": {},
        ...     }
        ... })
        >>> schema.get_parent("upload")  # "workspace"
    """

    # Common singular/plural mappings that don't follow standard rules
    IRREGULAR_PLURALS: dict[str, str] = {
        "people": "person",
        "children": "child",
        "men": "man",
        "women": "woman",
        "feet": "foot",
        "teeth": "tooth",
        "geese": "goose",
        "mice": "mouse",
        "analyses": "analysis",
        "bases": "base",
        "crises": "crisis",
        "diagnoses": "diagnosis",
        "emphases": "emphasis",
        "hypotheses": "hypothesis",
        "oases": "oasis",
        "parentheses": "parenthesis",
        "synopses": "synopsis",
        "theses": "thesis",
        "criteria": "criterion",
        "phenomena": "phenomenon",
        "data": "datum",
        "media": "medium",
        "indices": "index",
        "appendices": "appendix",
        "matrices": "matrix",
        "vertices": "vertex",
    }

    def parse(self, spec: dict[str, Any] | str | Path) -> ResourceSchema:
        """Parse an OpenAPI spec into a ResourceSchema.

        Args:
            spec: OpenAPI specification as a dict, file path string, or Path

        Returns:
            ResourceSchema with inferred resource types

        Raises:
            ValueError: If spec cannot be parsed
            FileNotFoundError: If file path doesn't exist
        """
        # Load spec if it's a path
        if isinstance(spec, (str, Path)):
            spec_path = Path(spec)
            if not spec_path.exists():
                raise FileNotFoundError(f"OpenAPI spec not found: {spec_path}")

            content = spec_path.read_text()

            # Try JSON first, then YAML
            try:
                spec = json.loads(content)
            except json.JSONDecodeError:
                try:
                    import yaml
                    spec = yaml.safe_load(content)
                except ImportError:
                    raise ValueError(
                        "YAML spec requires pyyaml: pip install pyyaml"
                    )
                except Exception as e:
                    raise ValueError(f"Failed to parse spec: {e}")

        if not isinstance(spec, dict):
            raise ValueError("Spec must be a dictionary")

        paths = spec.get("paths", {})
        if not paths:
            return ResourceSchema(types={})

        # Extract resource types from paths
        types: dict[str, ResourceType] = {}

        for path in paths:
            parsed = self._parse_path(path)
            self._add_types_from_parsed_path(parsed, types, spec)

        return ResourceSchema(types=types)

    def _parse_path(self, path: str) -> list[tuple[str, str | None]]:
        """Parse a URL path into resource segments.

        Args:
            path: URL path like "/workspaces/{workspace_id}/uploads"

        Returns:
            List of (resource_type, path_param) tuples.
            path_param is None for collection endpoints.

        Example:
            >>> parser._parse_path("/workspaces/{workspace_id}/uploads")
            [("workspace", "workspace_id"), ("upload", None)]
        """
        segments: list[tuple[str, str | None]] = []
        parts = [p for p in path.split("/") if p]

        i = 0
        while i < len(parts):
            part = parts[i]

            # Skip path parameters on their own
            if part.startswith("{") and part.endswith("}"):
                i += 1
                continue

            # Resource collection (e.g., "workspaces")
            resource_type = self._singularize(part)

            # Check if next part is a path parameter
            path_param: str | None = None
            if i + 1 < len(parts):
                next_part = parts[i + 1]
                if next_part.startswith("{") and next_part.endswith("}"):
                    path_param = next_part[1:-1]  # Remove braces
                    i += 1  # Skip the param in next iteration

            segments.append((resource_type, path_param))
            i += 1

        return segments

    def _add_types_from_parsed_path(
        self,
        parsed: list[tuple[str, str | None]],
        types: dict[str, ResourceType],
        spec: dict[str, Any],
    ) -> None:
        """Add resource types from a parsed path to the types dict.

        Args:
            parsed: Parsed path segments from _parse_path
            types: Dict to update with new types
            spec: Full OpenAPI spec for schema lookups
        """
        parent_type: str | None = None

        for resource_type, path_param in parsed:
            if resource_type not in types:
                # Try to find id_field from response schema
                id_field = self._find_id_field(resource_type, spec)

                types[resource_type] = ResourceType(
                    name=resource_type,
                    parent=parent_type,
                    id_field=id_field,
                    path_param=path_param,
                )
            elif parent_type and types[resource_type].parent is None:
                # Update parent if we find a more specific path
                types[resource_type] = ResourceType(
                    name=resource_type,
                    parent=parent_type,
                    id_field=types[resource_type].id_field,
                    path_param=path_param or types[resource_type].path_param,
                )

            # Only set parent for next type if this one has an ID param
            # (i.e., it's a specific resource, not just a collection)
            if path_param:
                parent_type = resource_type
            else:
                # Reset parent for collection endpoints without ID
                parent_type = parent_type  # Keep existing parent

    def _find_id_field(self, resource_type: str, spec: dict[str, Any]) -> str:
        """Find the ID field name from response schemas.

        Args:
            resource_type: The resource type to look up
            spec: Full OpenAPI spec

        Returns:
            The ID field name (defaults to "id" if not found)
        """
        # Try to find in components/schemas
        schemas = spec.get("components", {}).get("schemas", {})

        # Try various name patterns
        type_names = [
            resource_type,
            resource_type.capitalize(),
            resource_type.title(),
            resource_type.upper(),
        ]

        for name in type_names:
            if name in schemas:
                schema = schemas[name]
                properties = schema.get("properties", {})

                # Look for common ID field patterns
                for field_name in ["id", f"{resource_type}_id", "uuid", "key"]:
                    if field_name in properties:
                        return field_name

        return "id"  # Default

    def _singularize(self, word: str) -> str:
        """Convert a plural word to singular form.

        Args:
            word: Potentially plural word (e.g., "workspaces")

        Returns:
            Singular form (e.g., "workspace")
        """
        # Handle lowercase comparison
        lower_word = word.lower()

        # Check irregular plurals
        if lower_word in self.IRREGULAR_PLURALS:
            return self.IRREGULAR_PLURALS[lower_word]

        # Handle common patterns
        if lower_word.endswith("ies") and len(lower_word) > 3:
            # policies -> policy, categories -> category
            return lower_word[:-3] + "y"

        if lower_word.endswith("ves"):
            # leaves -> leaf, shelves -> shelf
            return lower_word[:-3] + "f"

        if lower_word.endswith("oes"):
            # heroes -> hero, potatoes -> potato
            return lower_word[:-2]

        if lower_word.endswith("ses") and not lower_word.endswith("sses"):
            # buses -> bus (but not classes -> class)
            return lower_word[:-2]

        if lower_word.endswith("xes") or lower_word.endswith("ches") or \
           lower_word.endswith("shes") or lower_word.endswith("sses"):
            # boxes -> box, batches -> batch, dishes -> dish, classes -> class
            return lower_word[:-2]

        if lower_word.endswith("s") and not lower_word.endswith("ss"):
            # Regular plural: workspaces -> workspace
            return lower_word[:-1]

        return word

    def parse_multiple(
        self,
        specs: list[dict[str, Any] | str | Path],
    ) -> ResourceSchema:
        """Parse multiple OpenAPI specs and merge into one schema.

        Args:
            specs: List of OpenAPI specifications

        Returns:
            Merged ResourceSchema
        """
        merged_types: dict[str, ResourceType] = {}

        for spec in specs:
            schema = self.parse(spec)
            for name, rt in schema.types.items():
                if name not in merged_types:
                    merged_types[name] = rt
                # If already exists, keep the one with more info (parent set)
                elif rt.parent and not merged_types[name].parent:
                    merged_types[name] = rt

        return ResourceSchema(types=merged_types)
