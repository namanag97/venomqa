#!/usr/bin/env python3
"""
Deep analysis of OpenAPI parsing issues discovered in prototype.

Issues to investigate:
1. Resource type inference quirks (e.g., "findByStatu" instead of proper names)
2. $ref resolution - what happens without it
3. Schema complexity (oneOf/anyOf/allOf)
4. Missing schemas for request/response bodies
"""

import json
import sys
from collections import Counter
from pathlib import Path
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from venomqa.v1.generators.openapi_actions import (
    parse_openapi_endpoints,
    _singularize,
    _parse_endpoint,
)
from venomqa.v1.adapters.resource_graph import schema_from_openapi, _parse_path_segments


def fetch_petstore():
    """Fetch the Petstore spec for analysis."""
    url = "https://petstore3.swagger.io/api/v3/openapi.json"
    req = Request(url, headers={"User-Agent": "VenomQA-Prototype/1.0"})
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def analyze_resource_inference():
    """Analyze why resource type inference produces odd results."""
    print("=" * 70)
    print("ANALYSIS: Resource Type Inference")
    print("=" * 70)

    spec = fetch_petstore()

    print("\nPaths in Petstore spec:")
    for path in spec["paths"]:
        segments = _parse_path_segments(path)
        print(f"  {path}")
        print(f"    Segments: {segments}")

        # What VenomQA infers as resource types
        for resource_name, param_name in segments:
            singular = _singularize(resource_name)
            print(f"    → '{resource_name}' → '{singular}'")

    print("\n" + "=" * 70)
    print("PROBLEM: Non-resource paths treated as resources")
    print("=" * 70)

    # These are problematic paths
    problematic = [
        "/pet/findByStatus",      # findByStatus is not a resource
        "/pet/findByTags",        # findByTags is not a resource
        "/pet/{petId}/uploadImage", # uploadImage is not a resource
        "/store/inventory",       # inventory is a query, not a resource
        "/user/login",            # login is an action, not a resource
        "/user/logout",           # logout is an action, not a resource
        "/user/createWithList",   # createWithList is an action, not a resource
    ]

    print("\nProblematic paths:")
    for path in problematic:
        segments = _parse_path_segments(path)
        print(f"  {path}")
        print(f"    Segments: {segments}")
        for resource_name, param_name in segments:
            singular = _singularize(resource_name)
            print(f"    → Incorrectly treated '{singular}' as resource type")


def analyze_crud_detection():
    """Analyze how CRUD operations are detected."""
    print("\n" + "=" * 70)
    print("ANALYSIS: CRUD Operation Detection")
    print("=" * 70)

    spec = fetch_petstore()

    print("\nEndpoint → Inferred Operation:")
    endpoints = parse_openapi_endpoints(spec)

    # Group by operation type
    by_operation = {}
    for ep in endpoints:
        if ep.operation not in by_operation:
            by_operation[ep.operation] = []
        by_operation[ep.operation].append(ep)

    for op_type, eps in by_operation.items():
        print(f"\n{op_type.upper()}:")
        for ep in eps:
            print(f"  {ep.method:6} {ep.path:40} (operationId: {ep.operation_id})")


def analyze_ref_usage():
    """Analyze how $ref is used in a spec."""
    print("\n" + "=" * 70)
    print("ANALYSIS: $ref Usage")
    print("=" * 70)

    spec = fetch_petstore()

    def find_refs(obj, path=""):
        """Recursively find all $ref usages."""
        refs = []
        if isinstance(obj, dict):
            if "$ref" in obj:
                refs.append((path, obj["$ref"]))
            for k, v in obj.items():
                refs.extend(find_refs(v, f"{path}.{k}"))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                refs.extend(find_refs(v, f"{path}[{i}]"))
        return refs

    refs = find_refs(spec)
    print(f"\nTotal $ref usages: {len(refs)}")

    # Categorize refs
    ref_targets = Counter()
    for path, target in refs:
        # Get the reference type (e.g., "#/components/schemas/Pet" → "schemas/Pet")
        if target.startswith("#/"):
            parts = target[2:].split("/")
            if len(parts) >= 2:
                ref_type = f"{parts[-2]}/{parts[-1]}"
            else:
                ref_type = target
        else:
            ref_type = "external"
        ref_targets[ref_type] += 1

    print("\n$ref targets:")
    for target, count in ref_targets.most_common(20):
        print(f"  {target}: {count}")


def analyze_schema_complexity():
    """Analyze complex schema patterns."""
    print("\n" + "=" * 70)
    print("ANALYSIS: Schema Complexity Patterns")
    print("=" * 70)

    spec = fetch_petstore()

    components = spec.get("components", {})
    schemas = components.get("schemas", {})

    print(f"\nTotal schemas: {len(schemas)}")

    for schema_name, schema_def in schemas.items():
        complexity = []

        if "oneOf" in schema_def:
            complexity.append(f"oneOf({len(schema_def['oneOf'])} variants)")
        if "anyOf" in schema_def:
            complexity.append(f"anyOf({len(schema_def['anyOf'])} variants)")
        if "allOf" in schema_def:
            complexity.append(f"allOf({len(schema_def['allOf'])} parts)")
        if "discriminator" in schema_def:
            complexity.append(f"discriminator={schema_def['discriminator'].get('propertyName')}")

        if complexity:
            print(f"\n{schema_name}:")
            for c in complexity:
                print(f"  - {c}")

        # Check for nested complexity
        props = schema_def.get("properties", {})
        for prop_name, prop_def in props.items():
            if isinstance(prop_def, dict):
                if "$ref" in prop_def:
                    pass  # Normal
                elif "type" in prop_def and prop_def["type"] == "array":
                    items = prop_def.get("items", {})
                    if "$ref" in items:
                        pass  # Normal
                    elif "oneOf" in items or "anyOf" in items:
                        print(f"  - {prop_name}: array with oneOf/anyOf items")


def analyze_what_we_cant_generate():
    """Show what invariants/behaviors we can't automatically generate."""
    print("\n" + "=" * 70)
    print("ANALYSIS: What We Can't Auto-Generate")
    print("=" * 70)

    print("""
Things NOT in OpenAPI that VenomQA needs:

1. BUSINESS INVARIANTS
   - "balance >= 0" (no concept of balance semantics)
   - "order.total == sum(order.items.price)" (no relationship rules)
   - "deleted user can't place orders" (no cross-entity rules)

2. SIDE EFFECTS
   - "POST /orders sends confirmation email"
   - "DELETE /user cancels all subscriptions"
   - Webhooks exist in 3.1 but don't describe effects

3. TEMPORAL CONSTRAINTS
   - "subscription.end_date > subscription.start_date"
   - "can't cancel order after shipping"

4. IDEMPOTENCY
   - "DELETE /users/{id} is idempotent" (not standardized)
   - "POST /payments is NOT idempotent"

5. STATE DEPENDENCIES
   - "must create workspace before upload" (only implicit in URL)
   - "payment requires valid payment_method" (not expressed)

6. RATE LIMITS / QUOTAS
   - "max 100 requests/minute" (sometimes in x-ratelimit headers)
   - "max 10 users per free plan"

What VenomQA CAN infer from OpenAPI:

✓ CRUD semantics from HTTP methods
✓ Resource hierarchy from URL structure
✓ Required fields from schema
✓ Valid value ranges (minimum/maximum)
✓ Enum constraints
✓ Response structure (for schema validation)
✓ Authentication requirements (security)
✓ Path parameter dependencies
""")


def suggest_improvements():
    """Suggest concrete improvements to VenomQA's OpenAPI handling."""
    print("\n" + "=" * 70)
    print("SUGGESTED IMPROVEMENTS")
    print("=" * 70)

    print("""
1. IMPROVE RESOURCE TYPE INFERENCE
   Current: Treats every path segment as a potential resource
   Better: Detect action-like paths vs. resource paths

   Heuristics:
   - If segment starts with verb (find, get, create, login) → NOT a resource
   - If segment matches method (POST /users → "users" is resource)
   - If segment comes after {id} without {id} → likely sub-action

2. ADD $ref RESOLUTION
   Current: Ignores $ref, schemas appear empty
   Better: Resolve references before processing

   Options:
   - Use jsonschema library with RefResolver
   - Simple recursive resolution for #/ refs

3. HANDLE COMPLEX SCHEMAS
   Current: Ignores oneOf/anyOf/allOf
   Better: Generate multiple test cases

   For oneOf: Generate one test per variant
   For anyOf: Generate combinations
   For allOf: Merge schemas

4. GENERATE AUTO-INVARIANTS FROM SCHEMA
   Current: Only generates actions
   Better: Generate invariants too

   From schema:
   - Required fields → "response must have field X"
   - Enum constraints → "field X must be one of [...]"
   - min/max → "field X in range [min, max]"

5. GENERATE CRUD INVARIANTS AUTOMATICALLY
   From method + path:
   - POST /resources → expect 201
   - GET /resources/{id} after POST → expect 200
   - GET /resources/{id} after DELETE → expect 404
   - DELETE /resources/{id} twice → second returns 404

6. BETTER REQUEST BODY GENERATION
   Current: Uses context.get("_request_body")
   Better: Generate from schema using hypothesis-jsonschema

   From schema constraints:
   - type: string → random string (or specific if format)
   - type: integer, minimum: 0 → non-negative int
   - enum → pick from values
""")


def main():
    analyze_resource_inference()
    analyze_crud_detection()
    analyze_ref_usage()
    analyze_schema_complexity()
    analyze_what_we_cant_generate()
    suggest_improvements()


if __name__ == "__main__":
    main()
