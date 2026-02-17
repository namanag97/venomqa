#!/usr/bin/env python3
"""
Prototype: Test OpenAPI parsing against real-world specs.

This script fetches various public OpenAPI specs and tests VenomQA's
parsing capabilities to understand:
1. What we can extract successfully
2. What edge cases exist
3. Where parsing fails
"""

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from venomqa.v1.generators.openapi_actions import (
    parse_openapi_endpoints,
    generate_actions,
    EndpointInfo,
)
from venomqa.v1.adapters.resource_graph import schema_from_openapi, ResourceSchema


# ============================================================================
# Test Targets
# ============================================================================

SPECS = [
    {
        "name": "Swagger Petstore",
        "url": "https://petstore3.swagger.io/api/v3/openapi.json",
        "version": "3.0",
        "complexity": "simple",
        "format": "json",
    },
    {
        "name": "OpenAI API",
        "url": "https://raw.githubusercontent.com/openai/openai-openapi/master/openapi.yaml",
        "version": "3.0",
        "complexity": "complex",
        "format": "yaml",
    },
    {
        "name": "Stripe API",
        "url": "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.yaml",
        "version": "3.0",
        "complexity": "complex",
        "format": "yaml",
    },
    {
        "name": "GitHub REST API",
        "url": "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.yaml",
        "version": "3.0",
        "complexity": "complex",
        "format": "yaml",
    },
    {
        "name": "Kubernetes API",
        "url": "https://raw.githubusercontent.com/kubernetes/kubernetes/master/api/openapi-spec/swagger.json",
        "version": "2.0",
        "complexity": "complex",
        "format": "json",
    },
    {
        "name": "Slack Web API",
        "url": "https://raw.githubusercontent.com/slackapi/slack-api-specs/master/web-api/slack_web_openapi_v2.json",
        "version": "2.0",
        "complexity": "medium",
        "format": "json",
    },
    {
        "name": "Xero Accounting API",
        "url": "https://raw.githubusercontent.com/XeroAPI/Xero-OpenAPI/master/xero_accounting.yaml",
        "version": "3.0",
        "complexity": "medium",
        "format": "yaml",
    },
    {
        "name": "Discord API",
        "url": "https://raw.githubusercontent.com/discord/discord-api-spec/main/specs/openapi.json",
        "version": "3.1",
        "complexity": "complex",
        "format": "json",
    },
    {
        "name": "DigitalOcean API",
        "url": "https://api-engineering.nyc3.cdn.digitaloceanspaces.com/spec-ci/DigitalOcean-public.v2.yaml",
        "version": "3.0",
        "complexity": "complex",
        "format": "yaml",
    },
    {
        "name": "Asana API",
        "url": "https://raw.githubusercontent.com/Asana/openapi/main/defs/asana_oas.yaml",
        "version": "3.0",
        "complexity": "medium",
        "format": "yaml",
    },
]


# ============================================================================
# Parsing Logic
# ============================================================================

def fetch_spec(url: str, format: str) -> dict[str, Any] | None:
    """Fetch and parse an OpenAPI spec from URL."""
    try:
        req = Request(url, headers={"User-Agent": "VenomQA-Prototype/1.0"})
        with urlopen(req, timeout=30) as response:
            content = response.read().decode("utf-8")

        if format == "yaml":
            try:
                import yaml
                return yaml.safe_load(content)
            except ImportError:
                print("  [!] PyYAML not installed, skipping YAML spec")
                return None
        else:
            return json.loads(content)

    except HTTPError as e:
        print(f"  [!] HTTP Error {e.code}: {e.reason}")
        return None
    except URLError as e:
        print(f"  [!] URL Error: {e.reason}")
        return None
    except Exception as e:
        print(f"  [!] Error fetching spec: {e}")
        return None


@dataclass
class ParseResult:
    """Results of parsing an OpenAPI spec."""
    name: str
    success: bool
    error: str | None = None

    # Spec metadata
    openapi_version: str | None = None
    title: str | None = None

    # Extracted data
    paths_count: int = 0
    endpoints_count: int = 0
    actions_count: int = 0
    resource_types: list[str] | None = None

    # Operation breakdown
    operations: dict[str, int] | None = None  # create/read/update/delete/list/action counts

    # Edge cases found
    edge_cases: list[str] | None = None

    # Sample endpoints
    sample_endpoints: list[EndpointInfo] | None = None


def analyze_spec(name: str, spec: dict[str, Any]) -> ParseResult:
    """Analyze an OpenAPI spec and extract VenomQA artifacts."""
    result = ParseResult(name=name, success=False)
    edge_cases = []

    try:
        # Extract metadata
        result.openapi_version = spec.get("openapi") or spec.get("swagger")
        info = spec.get("info", {})
        result.title = info.get("title")

        # Count paths
        paths = spec.get("paths", {})
        result.paths_count = len(paths)

        if result.paths_count == 0:
            edge_cases.append("NO_PATHS: Spec has no paths defined")

        # Parse endpoints using VenomQA's parser
        endpoints = parse_openapi_endpoints(spec)
        result.endpoints_count = len(endpoints)

        # Count operations by type
        ops = {"create": 0, "read": 0, "update": 0, "delete": 0, "list": 0, "action": 0}
        for ep in endpoints:
            ops[ep.operation] += 1
        result.operations = ops

        # Generate actions
        actions = generate_actions(spec)
        result.actions_count = len(actions)

        # Extract resource schema
        schema = schema_from_openapi(spec)
        result.resource_types = list(schema.types.keys())

        # Sample some endpoints for inspection
        result.sample_endpoints = endpoints[:5]

        # Detect edge cases
        for ep in endpoints:
            # No operation ID
            if not ep.operation_id:
                if "NO_OPERATION_ID" not in [e.split(":")[0] for e in edge_cases]:
                    edge_cases.append(f"NO_OPERATION_ID: {ep.method} {ep.path}")

            # Complex path params
            if len(ep.path_params) > 3:
                edge_cases.append(f"DEEP_NESTING: {ep.path} has {len(ep.path_params)} path params")

            # No request body schema for POST/PUT
            if ep.method in ("POST", "PUT") and not ep.request_body_schema:
                if "NO_REQUEST_SCHEMA" not in [e.split(":")[0] for e in edge_cases]:
                    edge_cases.append(f"NO_REQUEST_SCHEMA: {ep.method} {ep.path}")

            # No response schema
            if not ep.response_schema:
                if "NO_RESPONSE_SCHEMA" not in [e.split(":")[0] for e in edge_cases]:
                    edge_cases.append(f"NO_RESPONSE_SCHEMA: {ep.method} {ep.path}")

        # Check for $ref usage (we can't fully resolve these)
        spec_str = json.dumps(spec)
        if '"$ref"' in spec_str:
            ref_count = spec_str.count('"$ref"')
            edge_cases.append(f"USES_REFS: {ref_count} $ref references found")

        # Check for complex schemas
        components = spec.get("components", {}) or spec.get("definitions", {})
        schemas = components.get("schemas", {}) if isinstance(components, dict) else {}

        for schema_name, schema_def in schemas.items():
            if isinstance(schema_def, dict):
                if "oneOf" in schema_def:
                    edge_cases.append(f"ONEOF_SCHEMA: {schema_name}")
                if "anyOf" in schema_def:
                    edge_cases.append(f"ANYOF_SCHEMA: {schema_name}")
                if "allOf" in schema_def:
                    edge_cases.append(f"ALLOF_SCHEMA: {schema_name}")

        result.edge_cases = edge_cases[:20]  # Limit to first 20
        result.success = True

    except Exception as e:
        result.error = str(e)
        result.edge_cases = edge_cases

    return result


def print_result(result: ParseResult):
    """Print parsing result in a readable format."""
    status = "✓" if result.success else "✗"
    print(f"\n{'='*70}")
    print(f"{status} {result.name}")
    print(f"{'='*70}")

    if result.error:
        print(f"  ERROR: {result.error}")
        return

    print(f"  OpenAPI Version: {result.openapi_version}")
    print(f"  Title: {result.title}")
    print(f"  Paths: {result.paths_count}")
    print(f"  Endpoints: {result.endpoints_count}")
    print(f"  Actions Generated: {result.actions_count}")
    print(f"  Resource Types: {len(result.resource_types or [])} - {result.resource_types[:10] if result.resource_types else 'None'}...")

    if result.operations:
        print(f"  Operations:")
        for op, count in result.operations.items():
            if count > 0:
                print(f"    {op}: {count}")

    if result.sample_endpoints:
        print(f"  Sample Endpoints:")
        for ep in result.sample_endpoints[:3]:
            print(f"    {ep.method:6} {ep.path[:50]:50} → {ep.operation} ({ep.operation_id or 'no id'})")

    if result.edge_cases:
        print(f"  Edge Cases ({len(result.edge_cases)}):")
        for case in result.edge_cases[:10]:
            print(f"    - {case}")
        if len(result.edge_cases) > 10:
            print(f"    ... and {len(result.edge_cases) - 10} more")


def main():
    print("="*70)
    print("VenomQA OpenAPI Parsing Prototype")
    print("="*70)
    print(f"Testing {len(SPECS)} OpenAPI specifications...\n")

    results = []

    for spec_info in SPECS:
        print(f"\n→ Fetching {spec_info['name']}...")

        spec = fetch_spec(spec_info["url"], spec_info["format"])
        if spec is None:
            results.append(ParseResult(
                name=spec_info["name"],
                success=False,
                error="Failed to fetch spec"
            ))
            continue

        print(f"  Parsing...")
        result = analyze_spec(spec_info["name"], spec)
        results.append(result)
        print_result(result)

        # Small delay to be nice to servers
        time.sleep(0.5)

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    print(f"\nSuccessful: {len(successful)}/{len(results)}")
    print(f"Failed: {len(failed)}/{len(results)}")

    if failed:
        print("\nFailed specs:")
        for r in failed:
            print(f"  - {r.name}: {r.error}")

    # Aggregate edge cases
    all_edge_cases = {}
    for r in successful:
        for case in (r.edge_cases or []):
            case_type = case.split(":")[0]
            all_edge_cases[case_type] = all_edge_cases.get(case_type, 0) + 1

    print("\nEdge Case Summary:")
    for case_type, count in sorted(all_edge_cases.items(), key=lambda x: -x[1]):
        print(f"  {case_type}: {count} occurrences")

    # Total stats
    total_endpoints = sum(r.endpoints_count for r in successful)
    total_actions = sum(r.actions_count for r in successful)
    total_resources = sum(len(r.resource_types or []) for r in successful)

    print(f"\nTotals across all specs:")
    print(f"  Endpoints parsed: {total_endpoints}")
    print(f"  Actions generated: {total_actions}")
    print(f"  Resource types inferred: {total_resources}")


if __name__ == "__main__":
    main()
