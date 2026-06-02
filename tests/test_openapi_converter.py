import json
import yaml
import pytest
from openapi_spec_validator import validate
from converter import convert_openapi_spec, fetch_apiary, apiary_to_openapi_skeleton


# ─── Apiary fixtures (real jsapi.apiary.io format) ───────────────────────────

_MINIMAL_APIARY = {"name": "Test API", "resourceGroups": []}

_APIARY_DOC = {
    "name": "Test API",
    "resourceGroups": [
        {
            "name": "Tokens",
            "description": "",
            "resources": [
                {
                    "name": "Token Collection",
                    "uriTemplate": "/token/authenticate",
                    "actions": [
                        {
                            "name": "Create Token",
                            "method": "POST",
                            "description": "Generates a token.",
                            "examples": [
                                {
                                    "requests": [],
                                    "responses": [
                                        {"status": "201", "body": "", "schema": "", "description": "Created"},
                                        {"status": "401", "body": "", "schema": "", "description": "Unauthorized"},
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ],
}


def test_convert_dict_returns_dict():
    """Tracer bullet: function accepts dict and returns valid JSON-serializable dict."""
    input_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://example.com"}],
        "paths": {},
    }

    result = convert_openapi_spec(input_spec)

    assert isinstance(result, dict)
    assert result["openapi"] == "3.0.0"
    assert json.dumps(result)  # Should be JSON-serializable


def test_convert_yaml_string_to_dict():
    """Function accepts YAML string input and returns dict."""
    input_yaml = """
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
servers:
  - url: https://example.com
paths: {}
"""
    result = convert_openapi_spec(input_yaml)

    assert isinstance(result, dict)
    assert result["openapi"] == "3.0.0"
    assert result["info"]["title"] == "Test API"


def test_convert_json_string_to_dict():
    """Function accepts JSON string input and returns dict."""
    input_json = json.dumps({
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://example.com"}],
        "paths": {},
    })

    result = convert_openapi_spec(input_json)

    assert isinstance(result, dict)
    assert result["openapi"] == "3.0.0"


def test_output_passes_openapi_spec_validator():
    """Output is a valid OpenAPI 3.0.0 spec."""
    input_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://example.com"}],
        "paths": {
            "/test": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    }
                }
            }
        },
    }

    result = convert_openapi_spec(input_spec)

    validate(result)


def test_endpoint_missing_description_gets_added():
    """Enhancement: endpoint without description gets a default description."""
    input_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://example.com"}],
        "paths": {
            "/users": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    }
                }
            }
        },
    }

    result = convert_openapi_spec(input_spec)

    endpoint = result["paths"]["/users"]["get"]
    # Should have either original or enhanced description
    assert "description" in endpoint or "summary" in endpoint


def test_preserves_all_input_properties():
    """Function preserves all properties from input spec."""
    input_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://example.com"}],
        "paths": {
            "/resource": {
                "get": {
                    "tags": ["resources"],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Resource": {"type": "object", "properties": {"id": {"type": "string"}}}
            }
        },
    }

    result = convert_openapi_spec(input_spec)

    assert "/resource" in result["paths"]
    assert "Resource" in result["components"]["schemas"]
    assert result["paths"]["/resource"]["get"]["tags"] == ["resources"]


@pytest.mark.parametrize("spec_path", [
    "authentication/authentication-openapi.json",
    "oauth/oauth-openapi.json",
])
def test_validate_final_spec(spec_path):
    """Each completed *-openapi.json passes openapi-spec-validator without errors."""
    import pathlib

    spec_file = pathlib.Path(__file__).parent.parent / spec_path
    with open(spec_file, encoding="utf-8") as f:
        spec = json.load(f)

    validate(spec)


@pytest.mark.parametrize("spec_name", ["authentication/postman-spec.yaml"])
def test_convert_postman_spec(spec_name):
    """Integration test: convert postman-spec.yaml to valid OpenAPI JSON."""
    import pathlib

    spec_file = pathlib.Path(__file__).parent.parent / spec_name
    with open(spec_file, encoding="utf-8") as f:
        postman_spec = yaml.safe_load(f)

    result = convert_openapi_spec(postman_spec)

    # Verify structure
    assert result["openapi"] == "3.0.0"
    assert result["info"]["title"] is not None

    # Verify all paths from source YAML are present in result
    source_paths = postman_spec.get("paths", {}).keys()
    result_paths = result.get("paths", {}).keys()
    for path in source_paths:
        assert path in result_paths, f"Missing path: {path}"

    # Verify BearerAuth is present in security schemes
    assert "BearerAuth" in result.get("components", {}).get("securitySchemes", {}), "Missing BearerAuth scheme"

    # Verify output is valid OpenAPI
    validate(result)


@pytest.mark.parametrize("spec_name", ["authentication/postman-spec.yaml"])
def test_no_duplicate_inline_schemas(spec_name):
    """Complex reused schemas should be extracted to components/schemas, not duplicated inline."""
    import pathlib

    spec_file = pathlib.Path(__file__).parent.parent / spec_name
    with open(spec_file, encoding="utf-8") as f:
        postman_spec = yaml.safe_load(f)

    result = convert_openapi_spec(postman_spec)

    # Collect all complex inline schemas in paths (those with properties, oneOf, allOf)
    inline_schemas = []

    def collect_schemas(obj):
        if isinstance(obj, dict):
            if _is_complex_schema(obj):
                schema_key = json.dumps(obj, sort_keys=True)
                inline_schemas.append(schema_key)
            for value in obj.values():
                collect_schemas(value)
        elif isinstance(obj, list):
            for item in obj:
                collect_schemas(item)

    collect_schemas(result.get("paths", {}))

    # Check for duplicates: complex schemas that appear more than once should have been extracted
    schema_counts = {}
    for schema in inline_schemas:
        schema_counts[schema] = schema_counts.get(schema, 0) + 1

    duplicates = {schema: count for schema, count in schema_counts.items() if count > 1}
    assert not duplicates, f"Found duplicate complex inline schemas that should be in components/schemas: {len(duplicates)}"


# ─── apiary_to_openapi_skeleton ──────────────────────────────────────────────

def test_apiary_skeleton_returns_openapi_dict():
    """Tracer bullet: produces a dict with the three required OpenAPI 3.0.0 top-level fields."""
    result = apiary_to_openapi_skeleton(_MINIMAL_APIARY)
    assert result["openapi"] == "3.0.0"
    assert "info" in result
    assert "paths" in result


def test_apiary_skeleton_extracts_api_title():
    """API title comes from the top-level category's meta.title in the Refract tree."""
    result = apiary_to_openapi_skeleton(_APIARY_DOC)
    assert result["info"]["title"] == "Test API"


def test_apiary_skeleton_extracts_path_and_method():
    """Resource href and httpRequest method map to an OpenAPI path operation."""
    result = apiary_to_openapi_skeleton(_APIARY_DOC)
    assert "/token/authenticate" in result["paths"]
    assert "post" in result["paths"]["/token/authenticate"]


def test_apiary_skeleton_captures_operation_summary():
    """Transition meta.title becomes the OpenAPI operation summary."""
    result = apiary_to_openapi_skeleton(_APIARY_DOC)
    operation = result["paths"]["/token/authenticate"]["post"]
    assert operation["summary"] == "Create Token"


def test_apiary_skeleton_captures_response_status_codes():
    """All httpResponse status codes from the transaction appear as documented responses."""
    result = apiary_to_openapi_skeleton(_APIARY_DOC)
    responses = result["paths"]["/token/authenticate"]["post"]["responses"]
    assert "201" in responses
    assert "401" in responses


def test_apiary_skeleton_piped_through_converter():
    """Skeleton from apiary_to_openapi_skeleton is accepted by convert_openapi_spec without error."""
    skeleton = apiary_to_openapi_skeleton(
        _APIARY_DOC,
        servers=[{"url": "https://auth.anaplan.com"}],
    )
    result = convert_openapi_spec(skeleton)
    assert result["openapi"] == "3.0.0"
    assert "/token/authenticate" in result["paths"]


def test_apiary_skeleton_passes_through_servers():
    """Provided servers list appears verbatim in the skeleton output."""
    servers = [
        {"url": "https://auth.anaplan.com", "description": "Default"},
        {"url": "https://eu3.auth.anaplan.com", "description": "EU3"},
    ]
    result = apiary_to_openapi_skeleton(_MINIMAL_APIARY, servers=servers)
    assert result["servers"] == servers


@pytest.mark.live
def test_fetch_apiary_returns_dict_for_known_identifier():
    """fetch_apiary hits the Apiary JSON endpoint and returns a parsed dict."""
    result = fetch_apiary("anaplanoauth2service")
    assert isinstance(result, dict), "expected a JSON object from Apiary"
    assert result, "expected a non-empty response"


def _is_complex_schema(obj):
    """Check if object is a complex schema worth extracting (has properties, oneOf, or allOf)."""
    if not isinstance(obj, dict):
        return False
    if "$ref" in obj and len(obj) == 1:
        return False
    return "properties" in obj or "oneOf" in obj or "allOf" in obj
