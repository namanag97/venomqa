"""Tests for OpenAPIParser functionality."""

import json
import tempfile
from pathlib import Path

import pytest

from runtime_core import OpenAPIParser, ResourceSchema


@pytest.fixture
def parser() -> OpenAPIParser:
    """An OpenAPIParser instance."""
    return OpenAPIParser()


class TestParseSimpleResource:
    """Tests for parsing simple single-level resources."""

    def test_parse_single_collection(self, parser: OpenAPIParser) -> None:
        """Parses a single resource collection."""
        spec = {
            "paths": {
                "/workspaces": {},
                "/workspaces/{workspace_id}": {},
            }
        }

        schema = parser.parse(spec)

        assert "workspace" in schema.types
        ws_type = schema.types["workspace"]
        assert ws_type.name == "workspace"
        assert ws_type.parent is None
        assert ws_type.path_param == "workspace_id"

    def test_parse_multiple_root_resources(self, parser: OpenAPIParser) -> None:
        """Parses multiple independent root resources."""
        spec = {
            "paths": {
                "/workspaces": {},
                "/workspaces/{workspace_id}": {},
                "/users": {},
                "/users/{user_id}": {},
            }
        }

        schema = parser.parse(spec)

        assert "workspace" in schema.types
        assert "user" in schema.types
        assert schema.types["workspace"].parent is None
        assert schema.types["user"].parent is None

    def test_parse_collection_without_id_path(self, parser: OpenAPIParser) -> None:
        """Handles collection endpoint without ID path."""
        spec = {
            "paths": {
                "/metrics": {},  # No /{id} path
            }
        }

        schema = parser.parse(spec)

        assert "metric" in schema.types
        assert schema.types["metric"].path_param is None

    def test_parse_empty_spec(self, parser: OpenAPIParser) -> None:
        """Empty spec returns empty schema."""
        schema = parser.parse({"paths": {}})
        assert schema.types == {}

    def test_parse_no_paths_key(self, parser: OpenAPIParser) -> None:
        """Missing paths key returns empty schema."""
        schema = parser.parse({})
        assert schema.types == {}


class TestParseNestedResources:
    """Tests for parsing nested resource hierarchies."""

    def test_parse_two_level_nesting(self, parser: OpenAPIParser) -> None:
        """Parses parent -> child relationship."""
        spec = {
            "paths": {
                "/workspaces": {},
                "/workspaces/{workspace_id}": {},
                "/workspaces/{workspace_id}/uploads": {},
                "/workspaces/{workspace_id}/uploads/{upload_id}": {},
            }
        }

        schema = parser.parse(spec)

        assert "workspace" in schema.types
        assert "upload" in schema.types
        assert schema.types["upload"].parent == "workspace"
        assert schema.types["upload"].path_param == "upload_id"

    def test_parse_three_level_nesting(self, parser: OpenAPIParser) -> None:
        """Parses grandparent -> parent -> child relationship."""
        spec = {
            "paths": {
                "/orgs/{org_id}/workspaces/{workspace_id}/uploads/{upload_id}": {},
            }
        }

        schema = parser.parse(spec)

        assert "org" in schema.types
        assert "workspace" in schema.types
        assert "upload" in schema.types
        assert schema.types["org"].parent is None
        assert schema.types["workspace"].parent == "org"
        assert schema.types["upload"].parent == "workspace"

    def test_parse_multiple_children(self, parser: OpenAPIParser) -> None:
        """Parses parent with multiple child types."""
        spec = {
            "paths": {
                "/workspaces/{workspace_id}/uploads": {},
                "/workspaces/{workspace_id}/members": {},
                "/workspaces/{workspace_id}/settings": {},
            }
        }

        schema = parser.parse(spec)

        assert schema.types["upload"].parent == "workspace"
        assert schema.types["member"].parent == "workspace"
        assert schema.types["setting"].parent == "workspace"


class TestInferParentChild:
    """Tests for parent/child inference from URL patterns."""

    def test_infer_parent_from_path_param(self, parser: OpenAPIParser) -> None:
        """Parent is inferred from path parameter before child."""
        spec = {
            "paths": {
                "/projects/{project_id}/tasks": {},
            }
        }

        schema = parser.parse(spec)

        assert schema.types["task"].parent == "project"

    def test_infer_preserves_hierarchy_order(self, parser: OpenAPIParser) -> None:
        """Hierarchy is inferred in URL path order."""
        spec = {
            "paths": {
                "/a/{a_id}/b/{b_id}/c/{c_id}": {},
            }
        }

        schema = parser.parse(spec)

        assert schema.types["a"].parent is None
        assert schema.types["b"].parent == "a"
        assert schema.types["c"].parent == "b"

    def test_schema_get_ancestors(self, parser: OpenAPIParser) -> None:
        """Schema.get_ancestors returns full ancestor chain."""
        spec = {
            "paths": {
                "/orgs/{org_id}/teams/{team_id}/members/{member_id}": {},
            }
        }

        schema = parser.parse(spec)

        ancestors = schema.get_ancestors("member")
        assert ancestors == ["team", "org"]

    def test_schema_get_children(self, parser: OpenAPIParser) -> None:
        """Schema.get_children returns direct children."""
        spec = {
            "paths": {
                "/workspaces/{workspace_id}/uploads": {},
                "/workspaces/{workspace_id}/members": {},
                "/workspaces/{workspace_id}/uploads/{upload_id}/versions": {},
            }
        }

        schema = parser.parse(spec)

        children = schema.get_children("workspace")
        assert set(children) == {"upload", "member"}


class TestSingularization:
    """Tests for the _singularize method."""

    def test_regular_plurals(self, parser: OpenAPIParser) -> None:
        """Handles regular -s plurals."""
        assert parser._singularize("workspaces") == "workspace"
        assert parser._singularize("users") == "user"
        assert parser._singularize("uploads") == "upload"

    def test_ies_plurals(self, parser: OpenAPIParser) -> None:
        """Handles -ies -> -y plurals."""
        assert parser._singularize("categories") == "category"
        assert parser._singularize("policies") == "policy"
        assert parser._singularize("stories") == "story"

    def test_es_plurals(self, parser: OpenAPIParser) -> None:
        """Handles -es plurals."""
        assert parser._singularize("boxes") == "box"
        assert parser._singularize("batches") == "batch"
        assert parser._singularize("dishes") == "dish"
        assert parser._singularize("classes") == "class"

    def test_irregular_plurals(self, parser: OpenAPIParser) -> None:
        """Handles irregular plurals."""
        assert parser._singularize("people") == "person"
        assert parser._singularize("children") == "child"
        assert parser._singularize("data") == "datum"

    def test_already_singular(self, parser: OpenAPIParser) -> None:
        """Already singular words pass through."""
        assert parser._singularize("status") == "statu"  # Edge case
        assert parser._singularize("analysis") == "analysis"


class TestParseFromFile:
    """Tests for parsing specs from file paths."""

    def test_parse_json_file(self, parser: OpenAPIParser) -> None:
        """Parses JSON spec file."""
        spec = {
            "paths": {
                "/items": {},
                "/items/{item_id}": {},
            }
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(spec, f)
            f.flush()

            schema = parser.parse(f.name)

        assert "item" in schema.types

    def test_parse_path_object(self, parser: OpenAPIParser) -> None:
        """Parses from Path object."""
        spec = {"paths": {"/widgets": {}}}

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(spec, f)
            f.flush()

            schema = parser.parse(Path(f.name))

        assert "widget" in schema.types

    def test_parse_nonexistent_file_raises(self, parser: OpenAPIParser) -> None:
        """Nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/path.json")


class TestIdFieldExtraction:
    """Tests for extracting id_field from response schemas."""

    def test_default_id_field(self, parser: OpenAPIParser) -> None:
        """Default id_field is 'id'."""
        spec = {"paths": {"/items": {}}}

        schema = parser.parse(spec)

        assert schema.types["item"].id_field == "id"

    def test_extracts_id_from_schema(self, parser: OpenAPIParser) -> None:
        """Extracts id_field from component schema."""
        spec = {
            "paths": {"/items": {}},
            "components": {
                "schemas": {
                    "item": {
                        "properties": {
                            "item_id": {"type": "string"},
                            "name": {"type": "string"},
                        }
                    }
                }
            },
        }

        schema = parser.parse(spec)

        assert schema.types["item"].id_field == "item_id"

    def test_extracts_uuid_field(self, parser: OpenAPIParser) -> None:
        """Extracts 'uuid' as id_field if present."""
        spec = {
            "paths": {"/items": {}},
            "components": {
                "schemas": {
                    "item": {
                        "properties": {
                            "uuid": {"type": "string"},
                        }
                    }
                }
            },
        }

        schema = parser.parse(spec)

        assert schema.types["item"].id_field == "uuid"


class TestParseMultiple:
    """Tests for merging multiple specs."""

    def test_merge_disjoint_specs(self, parser: OpenAPIParser) -> None:
        """Merges specs with different resources."""
        spec1 = {"paths": {"/users": {}}}
        spec2 = {"paths": {"/products": {}}}

        schema = parser.parse_multiple([spec1, spec2])

        assert "user" in schema.types
        assert "product" in schema.types

    def test_merge_overlapping_specs(self, parser: OpenAPIParser) -> None:
        """Merges specs with overlapping resources."""
        spec1 = {"paths": {"/items": {}}}
        spec2 = {
            "paths": {
                "/categories/{cat_id}/items": {},
            }
        }

        schema = parser.parse_multiple([spec1, spec2])

        # Second spec provides parent info
        assert schema.types["item"].parent == "category"
