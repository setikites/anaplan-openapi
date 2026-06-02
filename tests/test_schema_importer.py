"""Tests for schema_importer.py — issue #22."""

import json
from pathlib import Path

import pytest

from schema_importer import load_object_schemas, validate_response_examples, wire_response_schema_refs


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _write_json(path: Path, data) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _object_schema_file(tmp_path: Path) -> Path:
    data = [
        {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "version": "1.0",
            "title": "workspace",
            "type": "object",
            "name": "workspaces",
            "order": [],
            "primaryKey": ["id"],
            "foreignKeys": [],
            "bulk": [],
            "properties": {
                "id":   {"description": "id",   "type": "string"},
                "name": {"description": "name", "type": "string"},
            },
        },
        {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "version": "1.0",
            "title": "dimension",
            "type": "object",
            "name": "dimensions",
            "order": [],
            "primaryKey": ["id"],
            "foreignKeys": [],
            "bulk": [],
            "properties": {
                "id":   {"description": "id",   "type": "string"},
            },
        },
        {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "version": "1.0",
            "title": "user",
            "type": "object",
            "name": "users",
            "order": [],
            "primaryKey": ["id"],
            "foreignKeys": [],
            "bulk": [],
            "properties": {
                "id":            {"description": "id",    "type": "string"},
                "lastLoginDate": {"description": "login", "type": "date-time"},
                "roles":         {"description": "roles", "type": "set"},
            },
        },
    ]
    return _write_json(tmp_path / "objectSchema.json", data)


def _model_schema_file(tmp_path: Path) -> Path:
    base = "https://api.anaplan.com/2/0/models/AABBCC/objects"
    data = [
        {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "description": "A dimension in an Anaplan model",
            "id": f"{base}/dimension#",
            "properties": {
                "code": {"type": "string"},
                "id":   {"type": "string"},
                "name": {"type": "string"},
            },
        },
        {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "description": "A period",
            "id": f"{base}/period#",
            "properties": {
                "date":       {"type": "string"},
                "periodText": {"type": "string"},
            },
        },
        {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "description": "A version",
            "id": f"{base}/version#",
            "properties": {
                "id":         {"type": "string"},
                "switchover": {"$ref": f"{base}/period#"},
            },
        },
    ]
    return _write_json(tmp_path / "modelObjectschema.json", data)


# ─── load_object_schemas ─────────────────────────────────────────────────────

def test_load_schemas_returns_workspace_with_id_property(tmp_path):
    """Tracer bullet: workspace schema from objectSchema.json lands in output with id property."""
    obj_path = _object_schema_file(tmp_path)
    mod_path = _model_schema_file(tmp_path)

    schemas = load_object_schemas(obj_path, mod_path)

    assert "Workspace" in schemas
    assert "id" in schemas["Workspace"]["properties"]


def test_model_schema_wins_on_overlap(tmp_path):
    """modelObjectschema.json takes precedence: Dimension has code+id+name (model), not just id (object)."""
    obj_path = _object_schema_file(tmp_path)
    mod_path = _model_schema_file(tmp_path)

    schemas = load_object_schemas(obj_path, mod_path)

    dim = schemas["Dimension"]
    assert "code" in dim["properties"]
    assert "name" in dim["properties"]


def test_json_schema_extras_stripped(tmp_path):
    """Draft-04 extras ($schema, foreignKeys, bulk, primaryKey, name, order) must not appear."""
    obj_path = _object_schema_file(tmp_path)
    mod_path = _model_schema_file(tmp_path)

    schemas = load_object_schemas(obj_path, mod_path)

    ws = schemas["Workspace"]
    for key in ("$schema", "foreignKeys", "bulk", "primaryKey", "name", "order", "id", "version"):
        assert key not in ws, f"extra key {key!r} not stripped from Workspace schema"


def test_set_type_remapped_to_array(tmp_path):
    """Property with type=set must be remapped to type=array."""
    obj_path = _object_schema_file(tmp_path)
    mod_path = _model_schema_file(tmp_path)

    schemas = load_object_schemas(obj_path, mod_path)

    assert schemas["User"]["properties"]["roles"]["type"] == "array"


def test_type_as_enum_object_unwrapped(tmp_path):
    """Property with type={enum:[...]} (draft-04) must become {enum:[...]} at top level."""
    data = [
        {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "model",
            "type": "object",
            "name": "models",
            "order": [], "primaryKey": [], "foreignKeys": [], "bulk": [],
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "description": "cat",
                                "type": {"enum": ["App", "Env"]},
                            }
                        },
                    },
                }
            },
        }
    ]
    obj_path = _write_json(tmp_path / "objectSchema.json", data)
    mod_path = _write_json(tmp_path / "modelObjectschema.json", [])

    schemas = load_object_schemas(obj_path, mod_path)

    cat = schemas["Model"]["properties"]["items"]["items"]["properties"]["category"]
    assert "type" not in cat or not isinstance(cat.get("type"), dict)
    assert cat.get("enum") == ["App", "Env"]


def test_date_time_type_remapped(tmp_path):
    """Property with type=date-time must become {type: string, format: date-time}."""
    obj_path = _object_schema_file(tmp_path)
    mod_path = _model_schema_file(tmp_path)

    schemas = load_object_schemas(obj_path, mod_path)

    login = schemas["User"]["properties"]["lastLoginDate"]
    assert login["type"] == "string"
    assert login["format"] == "date-time"


def test_absolute_ref_converted_to_internal_ref(tmp_path):
    """Absolute $ref URL in model schema is converted to #/components/schemas/{PascalCase}."""
    obj_path = _object_schema_file(tmp_path)
    mod_path = _model_schema_file(tmp_path)

    schemas = load_object_schemas(obj_path, mod_path)

    switchover_ref = schemas["Version"]["properties"]["switchover"]
    assert switchover_ref == {"$ref": "#/components/schemas/Period"}


# ─── wire_response_schema_refs ───────────────────────────────────────────────

def _spec_with_list_response():
    return {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "components": {
            "schemas": {
                "Workspace": {"type": "object", "properties": {"id": {"type": "string"}}},
            }
        },
        "paths": {
            "/workspaces": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "meta": {"schema": "https://api.anaplan.com/2/0/objects/workspace"},
                                        "status": {"code": 200, "message": "Success"},
                                        "workspaces": [{"id": "abc", "name": "FP&A"}],
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }


def test_wire_adds_array_schema_for_list_response():
    """Response example with list item key gets schema with type:array items:$ref."""
    spec = _spec_with_list_response()
    result = wire_response_schema_refs(spec)

    media = result["paths"]["/workspaces"]["get"]["responses"]["200"]["content"]["application/json"]
    assert "schema" in media
    ws_prop = media["schema"]["properties"]["workspaces"]
    assert ws_prop["type"] == "array"
    assert ws_prop["items"] == {"$ref": "#/components/schemas/Workspace"}


def test_wire_adds_direct_ref_for_singleton_response():
    """Response example with single-object item key gets schema with direct $ref."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "components": {
            "schemas": {
                "Workspace": {"type": "object"},
            }
        },
        "paths": {
            "/workspaces/{id}": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "meta": {"schema": "https://api.anaplan.com/2/0/objects/workspace"},
                                        "status": {"code": 200},
                                        "workspace": {"id": "abc", "name": "FP&A"},
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }
    result = wire_response_schema_refs(spec)

    media = result["paths"]["/workspaces/{id}"]["get"]["responses"]["200"]["content"]["application/json"]
    ws_prop = media["schema"]["properties"]["workspace"]
    assert ws_prop == {"$ref": "#/components/schemas/Workspace"}


def test_wire_skips_when_schema_name_not_in_components():
    """Response with unresolvable meta.schema URL is left unchanged."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "components": {"schemas": {}},
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "meta": {"schema": "https://api.anaplan.com/2/0/objects/unknownThing"},
                                        "status": {"code": 200},
                                        "items": [],
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }
    result = wire_response_schema_refs(spec)

    media = result["paths"]["/items"]["get"]["responses"]["200"]["content"]["application/json"]
    assert "schema" not in media


def test_wire_preserves_example_unchanged():
    """wire_response_schema_refs must not modify the example object."""
    spec = _spec_with_list_response()
    original_example = spec["paths"]["/workspaces"]["get"]["responses"]["200"]["content"]["application/json"]["example"]
    import copy
    original_example_copy = copy.deepcopy(original_example)

    result = wire_response_schema_refs(spec)
    result_example = result["paths"]["/workspaces"]["get"]["responses"]["200"]["content"]["application/json"]["example"]

    assert result_example == original_example_copy


def test_wire_is_idempotent():
    """Calling wire_response_schema_refs twice produces the same result."""
    spec = _spec_with_list_response()
    once = wire_response_schema_refs(spec)
    twice = wire_response_schema_refs(once)
    assert once == twice


# ─── validate_response_examples ──────────────────────────────────────────────

def _spec_with_schema_and_example(example, item_schema):
    return {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "components": {
            "schemas": {"Item": item_schema},
        },
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "items": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/Item"},
                                            }
                                        },
                                    },
                                    "example": example,
                                }
                            },
                        }
                    }
                }
            }
        },
    }


def test_validate_returns_empty_for_valid_example():
    """Valid example that matches the schema produces no warnings."""
    item_schema = {"type": "object", "properties": {"id": {"type": "string"}}}
    example = {"items": [{"id": "abc"}]}

    spec = _spec_with_schema_and_example(example, item_schema)
    warnings = validate_response_examples(spec)

    assert warnings == []


def test_validate_returns_warning_for_invalid_example():
    """Example that violates the schema produces a warning string."""
    item_schema = {
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    }
    example = {"items": [{"name": "no-id-here"}]}  # missing required "id"

    spec = _spec_with_schema_and_example(example, item_schema)
    warnings = validate_response_examples(spec)

    assert len(warnings) >= 1
    assert any("GET /items" in w or "/items" in w for w in warnings)
