"""RefResolver - Resolves $ref pointers in OpenAPI specifications."""

from __future__ import annotations

from typing import Any


class RefResolver:
    """Resolves JSON $ref pointers within an OpenAPI specification.

    Supports internal references (starting with "#/") to:
    - #/components/schemas/...
    - #/components/parameters/...
    - #/components/requestBodies/...
    - #/components/responses/...

    The resolver caches resolved references to avoid redundant traversals.

    Example::

        resolver = RefResolver(spec)
        schema = resolver.resolve("#/components/schemas/User")
        # Returns the User schema dict

    Args:
        spec: The full OpenAPI specification dictionary.
    """

    def __init__(self, spec: dict[str, Any]) -> None:
        self._spec = spec
        self._cache: dict[str, dict[str, Any]] = {}

    def resolve(self, ref: str) -> dict[str, Any]:
        """Resolve a $ref pointer to its target.

        Args:
            ref: The $ref string (e.g., "#/components/schemas/User").

        Returns:
            The resolved schema/parameter/etc. dictionary.
            Returns empty dict if the reference cannot be resolved.
        """
        if ref in self._cache:
            return self._cache[ref]

        if not ref.startswith("#/"):
            # External refs not supported
            return {}

        # Navigate the spec using the reference path
        parts = ref[2:].split("/")  # Remove "#/" prefix and split
        current: Any = self._spec
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                self._cache[ref] = {}
                return {}

        result = current if isinstance(current, dict) else {}
        self._cache[ref] = result
        return result

    def resolve_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Resolve a schema that may contain a $ref.

        If the schema has a $ref, resolves it. Otherwise returns the
        schema as-is. Also handles allOf/oneOf/anyOf compositions.

        Args:
            schema: A JSON Schema object, possibly with $ref.

        Returns:
            The resolved schema.
        """
        if "$ref" in schema:
            return self.resolve(schema["$ref"])

        # Handle allOf - merge all schemas
        if "allOf" in schema:
            merged: dict[str, Any] = {}
            merged_props: dict[str, Any] = {}
            merged_required: list[str] = []
            for sub in schema["allOf"]:
                resolved = self.resolve_schema(sub)
                merged_props.update(resolved.get("properties", {}))
                merged_required.extend(resolved.get("required", []))
                # Copy non-property fields from last schema
                for k, v in resolved.items():
                    if k not in ("properties", "required"):
                        merged[k] = v
            if merged_props:
                merged["properties"] = merged_props
            if merged_required:
                merged["required"] = merged_required
            return merged

        # Handle oneOf/anyOf - use first option
        if "oneOf" in schema and schema["oneOf"]:
            return self.resolve_schema(schema["oneOf"][0])
        if "anyOf" in schema and schema["anyOf"]:
            return self.resolve_schema(schema["anyOf"][0])

        return schema


__all__ = ["RefResolver"]
