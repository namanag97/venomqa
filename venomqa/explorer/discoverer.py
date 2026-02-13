"""
API Discoverer for the VenomQA State Explorer module.

This module provides the APIDiscoverer class which is responsible for
discovering API endpoints from various sources including OpenAPI/Swagger
specifications, HTML pages, and dynamic crawling.

The discoverer identifies available endpoints, their methods, parameters,
and authentication requirements.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import yaml

from venomqa.explorer.models import Action, ExplorationConfig


class APIDiscoverer:
    """
    Discovers API endpoints from various sources.

    The APIDiscoverer is responsible for finding all available API endpoints
    that can be explored. It supports multiple discovery strategies:

    - OpenAPI/Swagger specification parsing
    - HTML link crawling
    - Dynamic endpoint discovery from responses
    - HAR file analysis

    Attributes:
        base_url: The base URL of the API to discover
        config: Exploration configuration
        discovered_actions: Set of discovered actions
        discovered_endpoints: Set of discovered endpoint patterns
        _spec_components: Cached components section for $ref resolution

    Example:
        discoverer = APIDiscoverer(base_url="http://api.example.com")
        actions = await discoverer.discover()
        for action in actions:
            print(f"{action.method} {action.endpoint}")
    """

    def __init__(
        self,
        base_url: str,
        config: Optional[ExplorationConfig] = None,
    ) -> None:
        """
        Initialize the API discoverer.

        Args:
            base_url: The base URL of the API to discover
            config: Optional exploration configuration
        """
        self.base_url = base_url.rstrip("/")
        self.config = config or ExplorationConfig()
        self.discovered_actions: Set[Action] = set()
        self.discovered_endpoints: Set[str] = set()
        self._spec_components: Dict[str, Any] = {}
        self._spec_security_schemes: Dict[str, Any] = {}

    async def discover(self) -> List[Action]:
        """
        Discover all available API endpoints.

        This method orchestrates the discovery process, trying multiple
        strategies to find endpoints.

        Returns:
            List of discovered Action objects

        Raises:
            DiscoveryError: If discovery fails completely
        """
        # TODO: Implement discovery orchestration
        # 1. Try to fetch OpenAPI/Swagger spec
        # 2. Fall back to HTML crawling if no spec found
        # 3. Use configured seed endpoints
        # 4. Filter by include/exclude patterns
        raise NotImplementedError("discover() not yet implemented")

    async def discover_from_openapi(
        self,
        spec_url: Optional[str] = None,
    ) -> List[Action]:
        """
        Discover endpoints from an OpenAPI/Swagger specification.

        Args:
            spec_url: URL to the OpenAPI spec. If None, common paths are tried.

        Returns:
            List of discovered Action objects
        """
        import httpx

        # Try to fetch spec from URL
        spec_urls_to_try = []
        if spec_url:
            spec_urls_to_try.append(spec_url)
        else:
            # Try common OpenAPI spec paths
            spec_urls_to_try = [
                f"{self.base_url}/openapi.json",
                f"{self.base_url}/swagger.json",
                f"{self.base_url}/api/openapi.json",
                f"{self.base_url}/api/swagger.json",
                f"{self.base_url}/v1/openapi.json",
                f"{self.base_url}/docs/openapi.json",
            ]

        spec_data: Optional[Dict[str, Any]] = None
        async with httpx.AsyncClient(
            timeout=self.config.request_timeout_seconds,
            verify=self.config.verify_ssl,
            follow_redirects=self.config.follow_redirects,
        ) as client:
            for url in spec_urls_to_try:
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        spec_data = response.json()
                        break
                except (httpx.RequestError, json.JSONDecodeError):
                    continue

        if not spec_data:
            raise ValueError(
                f"Could not fetch OpenAPI spec from any of: {spec_urls_to_try}"
            )

        return self.parse_openapi_spec(spec_data)

    def from_openapi(self, spec_path: str) -> List[Action]:
        """
        Parse an OpenAPI specification from a file path and extract API actions.

        This is a convenience method that loads an OpenAPI 3.0.x/3.1.x spec
        from a file (JSON or YAML) and returns all discovered actions.

        Args:
            spec_path: Path to the OpenAPI specification file (.json, .yaml, .yml)

        Returns:
            List of Action objects representing all API endpoints

        Raises:
            FileNotFoundError: If the spec file does not exist
            ValueError: If the spec is invalid or cannot be parsed

        Example:
            discoverer = APIDiscoverer(base_url="http://api.example.com")
            actions = discoverer.from_openapi("./openapi.yaml")
            for action in actions:
                print(f"{action.method} {action.endpoint}")
                if action.body:
                    print(f"  Body: {action.body}")
        """
        path = Path(spec_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenAPI spec file not found: {spec_path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {spec_path}")

        return self.parse_openapi_spec(path)

    def parse_openapi_spec(
        self,
        spec: Union[Dict[str, Any], str, Path],
    ) -> List[Action]:
        """
        Parse an OpenAPI specification and extract endpoints as Action objects.

        This method supports OpenAPI 3.0.x and 3.1.x specifications.

        Args:
            spec: OpenAPI spec as a dict, JSON/YAML string, or file path

        Returns:
            List of discovered Action objects

        Raises:
            ValueError: If the spec is invalid or cannot be parsed
        """
        # Load spec from various formats
        spec_dict = self._load_spec(spec)

        # Validate it looks like an OpenAPI spec
        if not isinstance(spec_dict, dict):
            raise ValueError("OpenAPI spec must be a dictionary")

        # Check for OpenAPI version
        openapi_version = spec_dict.get("openapi", spec_dict.get("swagger", ""))
        if not openapi_version:
            raise ValueError("Invalid OpenAPI spec: missing 'openapi' or 'swagger' field")

        # Cache components for $ref resolution
        self._spec_components = spec_dict.get("components", {})
        self._spec_security_schemes = self._spec_components.get("securitySchemes", {})

        # Extract paths
        paths = spec_dict.get("paths", {})
        if not paths:
            return []

        # Extract global security requirements
        global_security = spec_dict.get("security", [])

        # Parse each path and operation
        actions: List[Action] = []
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            # Normalize path (ensure leading slash)
            normalized_path = self._normalize_endpoint(path)

            # Check include/exclude patterns
            if not self._should_include_endpoint(normalized_path):
                continue

            # Get path-level parameters
            path_params = path_item.get("parameters", [])

            # Process each HTTP method
            http_methods = ["get", "post", "put", "delete", "patch", "head", "options"]
            for method in http_methods:
                operation = path_item.get(method)
                if not operation or not isinstance(operation, dict):
                    continue

                action = self._parse_operation(
                    method=method.upper(),
                    path=normalized_path,
                    operation=operation,
                    path_params=path_params,
                    global_security=global_security,
                )

                if action:
                    actions.append(action)
                    self.discovered_actions.add(action)
                    self.discovered_endpoints.add(normalized_path)

        return actions

    def _load_spec(
        self,
        spec: Union[Dict[str, Any], str, Path],
    ) -> Dict[str, Any]:
        """
        Load OpenAPI spec from various formats.

        Args:
            spec: OpenAPI spec as dict, JSON/YAML string, or file path

        Returns:
            Parsed spec as dictionary
        """
        if isinstance(spec, dict):
            return spec

        if isinstance(spec, Path):
            spec = str(spec)

        # Check if it's a file path
        if isinstance(spec, str):
            path = Path(spec)
            if path.exists() and path.is_file():
                content = path.read_text()
                if path.suffix.lower() in (".yaml", ".yml"):
                    return yaml.safe_load(content)
                else:
                    return json.loads(content)

            # Try to parse as JSON/YAML string
            try:
                return json.loads(spec)
            except json.JSONDecodeError:
                try:
                    return yaml.safe_load(spec)
                except yaml.YAMLError:
                    raise ValueError(f"Could not parse spec: not valid JSON or YAML")

        raise ValueError(f"Invalid spec type: {type(spec)}")

    def _parse_operation(
        self,
        method: str,
        path: str,
        operation: Dict[str, Any],
        path_params: List[Dict[str, Any]],
        global_security: List[Dict[str, List[str]]],
    ) -> Optional[Action]:
        """
        Parse an OpenAPI operation into an Action.

        Args:
            method: HTTP method
            path: Endpoint path
            operation: Operation object from spec
            path_params: Path-level parameters
            global_security: Global security requirements

        Returns:
            Action object or None if operation should be skipped
        """
        # Get operation description
        description = operation.get("summary") or operation.get("description")
        if description and len(description) > 200:
            description = description[:197] + "..."

        # Combine path-level and operation-level parameters
        all_params = list(path_params) + operation.get("parameters", [])

        # Extract query parameters
        query_params: Dict[str, Any] = {}
        for param in all_params:
            if not isinstance(param, dict):
                continue
            if param.get("in") == "query":
                param_name = param.get("name", "")
                if param_name:
                    # Use example value if available, otherwise use placeholder
                    example = param.get("example")
                    schema = param.get("schema", {})
                    if example is not None:
                        query_params[param_name] = example
                    elif schema.get("default") is not None:
                        query_params[param_name] = schema.get("default")
                    elif schema.get("example") is not None:
                        query_params[param_name] = schema.get("example")

        # Extract request body schema (for POST, PUT, PATCH)
        body: Optional[Dict[str, Any]] = None
        request_body = operation.get("requestBody", {})
        if request_body and method in ("POST", "PUT", "PATCH"):
            body = self._extract_request_body_example(request_body)

        # Determine if authentication is required
        operation_security = operation.get("security", global_security)
        requires_auth = bool(operation_security)

        # Build headers from parameters
        headers: Dict[str, str] = {}
        for param in all_params:
            if not isinstance(param, dict):
                continue
            if param.get("in") == "header":
                param_name = param.get("name", "")
                if param_name and param_name.lower() not in ("authorization", "content-type"):
                    example = param.get("example", param.get("schema", {}).get("example"))
                    if example:
                        headers[param_name] = str(example)

        return Action(
            method=method,
            endpoint=path,
            params=query_params if query_params else None,
            body=body,
            headers=headers if headers else None,
            description=description,
            requires_auth=requires_auth,
        )

    def _extract_request_body_example(
        self,
        request_body: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Extract an example request body from OpenAPI requestBody.

        Args:
            request_body: OpenAPI requestBody object

        Returns:
            Example body dictionary or None
        """
        content = request_body.get("content", {})

        # Prefer application/json
        json_content = content.get("application/json", {})
        if json_content:
            # Check for direct example
            if "example" in json_content:
                return json_content["example"]

            # Check for examples (multiple)
            examples = json_content.get("examples", {})
            if examples:
                first_example = next(iter(examples.values()), {})
                if "value" in first_example:
                    return first_example["value"]

            # Try to build from schema
            schema = json_content.get("schema", {})
            if schema:
                return self._build_example_from_schema(schema)

        return None

    def _build_example_from_schema(
        self,
        schema: Dict[str, Any],
        visited: Optional[Set[str]] = None,
    ) -> Any:
        """
        Build an example value from an OpenAPI schema.

        Args:
            schema: OpenAPI schema object
            visited: Set of visited $ref paths to prevent infinite recursion

        Returns:
            Example value based on schema
        """
        if visited is None:
            visited = set()

        # Check for direct example
        if "example" in schema:
            return schema["example"]

        # Handle $ref (we don't resolve refs, just return placeholder)
        if "$ref" in schema:
            ref = schema["$ref"]
            if ref in visited:
                return {}
            visited.add(ref)
            return {}

        schema_type = schema.get("type", "object")

        if schema_type == "object":
            result = {}
            properties = schema.get("properties", {})
            for prop_name, prop_schema in properties.items():
                if isinstance(prop_schema, dict):
                    result[prop_name] = self._build_example_from_schema(prop_schema, visited)
            return result

        elif schema_type == "array":
            items = schema.get("items", {})
            if items:
                return [self._build_example_from_schema(items, visited)]
            return []

        elif schema_type == "string":
            format_type = schema.get("format", "")
            enum = schema.get("enum")
            if enum:
                return enum[0]
            if format_type == "email":
                return "user@example.com"
            if format_type == "date":
                return "2024-01-01"
            if format_type == "date-time":
                return "2024-01-01T00:00:00Z"
            if format_type == "uuid":
                return "123e4567-e89b-12d3-a456-426614174000"
            if format_type == "uri":
                return "https://example.com"
            return "string"

        elif schema_type == "integer":
            minimum = schema.get("minimum", 0)
            return int(minimum) if minimum else 0

        elif schema_type == "number":
            minimum = schema.get("minimum", 0.0)
            return float(minimum) if minimum else 0.0

        elif schema_type == "boolean":
            return True

        return None

    async def discover_from_html(
        self,
        start_url: Optional[str] = None,
    ) -> List[Action]:
        """
        Discover endpoints by crawling HTML pages.

        Args:
            start_url: URL to start crawling from. Defaults to base_url.

        Returns:
            List of discovered Action objects
        """
        # TODO: Implement HTML crawling
        # 1. Fetch the start page
        # 2. Parse for links and forms
        # 3. Extract API endpoints from links
        # 4. Build Action objects from forms
        # 5. Recursively crawl discovered pages
        raise NotImplementedError("discover_from_html() not yet implemented")

    async def discover_from_response(
        self,
        response: Dict[str, Any],
    ) -> List[Action]:
        """
        Discover endpoints from API response data (HATEOAS links).

        Args:
            response: API response containing potential links

        Returns:
            List of newly discovered Action objects
        """
        # TODO: Implement response-based discovery
        # 1. Look for _links, links, href fields
        # 2. Parse HAL, JSON:API, or other hypermedia formats
        # 3. Extract endpoint URLs and methods
        # 4. Build Action objects for new endpoints
        raise NotImplementedError("discover_from_response() not yet implemented")

    async def discover_from_har(
        self,
        har_path: str,
    ) -> List[Action]:
        """
        Discover endpoints from a HAR (HTTP Archive) file.

        Args:
            har_path: Path to the HAR file

        Returns:
            List of discovered Action objects
        """
        # TODO: Implement HAR file parsing
        # 1. Load and parse HAR file
        # 2. Extract unique request patterns
        # 3. Build Action objects for each pattern
        raise NotImplementedError("discover_from_har() not yet implemented")

    def add_seed_endpoints(
        self,
        endpoints: List[Tuple[str, str]],
    ) -> None:
        """
        Add seed endpoints for discovery.

        Args:
            endpoints: List of (method, path) tuples to use as seeds
        """
        valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}

        for method, path in endpoints:
            # Validate method
            method_upper = method.upper()
            if method_upper not in valid_methods:
                continue

            # Normalize path
            normalized_path = self._normalize_endpoint(path)

            # Check include/exclude patterns
            if not self._should_include_endpoint(normalized_path):
                continue

            # Create Action
            action = Action(
                method=method_upper,
                endpoint=normalized_path,
            )

            self.discovered_actions.add(action)
            self.discovered_endpoints.add(normalized_path)

    def _should_include_endpoint(self, endpoint: str) -> bool:
        """
        Check if an endpoint should be included based on patterns.

        Args:
            endpoint: The endpoint path to check

        Returns:
            True if the endpoint should be included
        """
        # Check exclude patterns first
        for pattern in self.config.exclude_patterns:
            if re.match(pattern, endpoint):
                return False

        # If include patterns are specified, endpoint must match at least one
        if self.config.include_patterns:
            for pattern in self.config.include_patterns:
                if re.match(pattern, endpoint):
                    return True
            return False

        return True

    def _normalize_endpoint(self, endpoint: str) -> str:
        """
        Normalize an endpoint path.

        Args:
            endpoint: The endpoint path to normalize

        Returns:
            Normalized endpoint path
        """
        # Remove base URL if present
        if endpoint.startswith(self.base_url):
            endpoint = endpoint[len(self.base_url) :]

        # Handle query parameters - strip them
        if "?" in endpoint:
            endpoint = endpoint.split("?")[0]

        # Ensure leading slash
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint

        # Remove trailing slash (except for root)
        if endpoint != "/" and endpoint.endswith("/"):
            endpoint = endpoint.rstrip("/")

        return endpoint

    def _extract_path_params(self, endpoint: str) -> List[str]:
        """
        Extract path parameter names from an endpoint.

        Args:
            endpoint: The endpoint path

        Returns:
            List of parameter names
        """
        # Find {param} patterns in the path
        pattern = r"\{([^}]+)\}"
        matches = re.findall(pattern, endpoint)
        return matches

    def get_discovered_actions(self) -> List[Action]:
        """
        Get all currently discovered actions.

        Returns:
            List of discovered Action objects
        """
        return list(self.discovered_actions)

    def get_endpoint_count(self) -> int:
        """
        Get the count of unique discovered endpoints.

        Returns:
            Number of unique endpoints
        """
        return len(self.discovered_endpoints)

    def clear(self) -> None:
        """Clear all discovered endpoints and actions."""
        self.discovered_actions.clear()
        self.discovered_endpoints.clear()
