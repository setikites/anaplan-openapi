import json
import yaml
import pytest
from openapi_spec_validator import validate
from converter import convert_openapi_spec, fetch_apiary, apiary_to_openapi_skeleton, extract_op_response_details, hoist_version_prefix


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


def test_operation_with_empty_responses_gets_placeholder():
    """Operation with responses: {} gets a 200 placeholder so openapi-spec-validator accepts it."""
    input_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://example.com"}],
        "paths": {
            "/items": {
                "get": {"responses": {}},
                "post": {"responses": {}},
            }
        },
    }

    result = convert_openapi_spec(input_spec)

    validate(result)
    assert result["paths"]["/items"]["get"]["responses"]
    assert result["paths"]["/items"]["post"]["responses"]


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


@pytest.mark.parametrize("spec_name", ["sources/postman-spec.yaml"])
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

    # Verify security schemes are carried through from the collection
    security_schemes = result.get("components", {}).get("securitySchemes", {})
    assert security_schemes, "Expected at least one security scheme in converted output"

    # Verify output is valid OpenAPI
    validate(result)


@pytest.mark.parametrize("spec_name", ["sources/postman-spec.yaml"])
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


# ─── extract_op_response_details ─────────────────────────────────────────────

def test_extract_response_body_from_application_json_heading():
    """### Response 200 (application/json) + fenced JSON → responses.200.content example, section stripped."""
    operation = {
        "responses": {},
        "description": 'Narrative.\n\n### Response 200 (application/json)\n\n```\n{"status": "ok"}\n```\n',
    }
    result = extract_op_response_details(operation)
    assert result["responses"]["200"]["content"]["application/json"]["example"] == {"status": "ok"}
    assert "### Response 200" not in result.get("description", "")
    assert "Narrative" in result["description"]


def test_extract_response_body_from_body_heading():
    """### Response 200 body variant promotes to the same responses.200.content target."""
    operation = {
        "responses": {},
        "description": 'Prose.\n\n### Response 200 body\n\n```\n{"items": []}\n```\n',
    }
    result = extract_op_response_details(operation)
    assert result["responses"]["200"]["content"]["application/json"]["example"] == {"items": []}
    assert "### Response 200 body" not in result.get("description", "")


def test_extract_multiple_response_codes():
    """Different ### Response N sections each land in the correct responses slot."""
    operation = {
        "responses": {},
        "description": (
            "Intro.\n\n"
            '### Response 200 (application/json)\n\n```\n{"ok": true}\n```\n\n'
            '### Response 404 body\n\n```\n{"error": "not found"}\n```\n'
        ),
    }
    result = extract_op_response_details(operation)
    assert result["responses"]["200"]["content"]["application/json"]["example"] == {"ok": True}
    assert result["responses"]["404"]["content"]["application/json"]["example"] == {"error": "not found"}
    assert "### Response" not in result.get("description", "")


def test_extract_response_headers():
    """### Response headers + `Header: Value` → responses.200.headers[Header], section stripped."""
    operation = {
        "responses": {},
        "description": "Prose.\n\n### Response headers\n\n`Content-Type: application/json`\n",
    }
    result = extract_op_response_details(operation)
    headers = result["responses"]["200"]["headers"]
    assert "Content-Type" in headers
    assert headers["Content-Type"]["example"] == "application/json"
    assert "### Response headers" not in result.get("description", "")


def test_extract_prose_status_code_callout():
    """Backtick-quoted HTTP status code in prose → responses.{code} with generic description."""
    operation = {
        "responses": {},
        "description": "Returns a `404` if workspace does not exist.",
    }
    result = extract_op_response_details(operation)
    assert "404" in result["responses"]
    assert result["responses"]["404"]["description"] == "more detail in path description"
    assert "404" in result.get("description", "")


def test_prose_callout_does_not_overwrite_existing_response():
    """Prose `404` callout is skipped when responses.404 is already documented."""
    operation = {
        "responses": {"404": {"description": "Not Found"}},
        "description": "Returns a `404` if workspace does not exist.",
    }
    result = extract_op_response_details(operation)
    assert result["responses"]["404"]["description"] == "Not Found"


def test_extract_response_details_is_idempotent():
    """Calling extract_op_response_details twice returns an identical result."""
    operation = {
        "responses": {},
        "description": (
            "Intro.\n\n"
            '### Response 200 (application/json)\n\n```\n{"id": 1}\n```\n\n'
            "Returns `404` if not found."
        ),
    }
    once = extract_op_response_details(operation)
    twice = extract_op_response_details(once)
    assert once == twice


def test_convert_openapi_spec_promotes_response_descriptions():
    """convert_openapi_spec runs extraction so ### Response sections appear in responses object."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test", "version": "1.0.0"},
        "paths": {
            "/items": {
                "get": {
                    "responses": {},
                    "description": 'List items.\n\n### Response 200 (application/json)\n\n```\n{"items": []}\n```\n',
                }
            }
        },
    }
    result = convert_openapi_spec(spec)
    operation = result["paths"]["/items"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["example"] == {"items": []}
    assert "### Response 200" not in operation.get("description", "")


# ─── hoist_version_prefix ────────────────────────────────────────────────────

def test_hoist_moves_common_version_prefix_to_servers():
    """Tracer bullet: /2/0 common to all paths is stripped from paths and appended to every server URL."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/2/0/integrations": {},
            "/2/0/integrations/{id}": {},
        },
    }
    result = hoist_version_prefix(spec)
    assert "/integrations" in result["paths"]
    assert "/integrations/{id}" in result["paths"]
    assert "/2/0/integrations" not in result["paths"]
    assert result["servers"][0]["url"] == "https://api.example.com/2/0"


def test_hoist_single_segment_v_prefix():
    """/v1 prefix (single version segment) is also hoisted."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {"/v1/users": {}, "/v1/orders": {}},
    }
    result = hoist_version_prefix(spec)
    assert "/users" in result["paths"]
    assert "/orders" in result["paths"]
    assert result["servers"][0]["url"] == "https://api.example.com/v1"


def test_hoist_no_common_prefix_leaves_spec_unchanged():
    """Paths with no shared prefix are returned as-is."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {"/users": {}, "/orders": {}},
    }
    result = hoist_version_prefix(spec)
    assert result["paths"] == spec["paths"]
    assert result["servers"] == spec["servers"]


def test_hoist_non_version_common_prefix_leaves_spec_unchanged():
    """/api common prefix is not a version token — spec left unchanged."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {"/api/users": {}, "/api/orders": {}},
    }
    result = hoist_version_prefix(spec)
    assert "/api/users" in result["paths"]
    assert result["servers"][0]["url"] == "https://api.example.com"


def test_hoist_empty_paths_leaves_spec_unchanged():
    """Spec with no paths is returned unchanged."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {},
    }
    result = hoist_version_prefix(spec)
    assert result["servers"] == spec["servers"]
    assert result["paths"] == {}


def test_hoist_appends_prefix_to_all_servers():
    """When multiple servers are present, the prefix is appended to each one."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "servers": [
            {"url": "https://api.example.com", "description": "Default"},
            {"url": "https://eu.api.example.com", "description": "EU"},
        ],
        "paths": {"/2/0/items": {}, "/2/0/items/{id}": {}},
    }
    result = hoist_version_prefix(spec)
    urls = [s["url"] for s in result["servers"]]
    assert urls == ["https://api.example.com/2/0", "https://eu.api.example.com/2/0"]


def test_hoist_partial_prefix_match_leaves_spec_unchanged():
    """If one path lacks the version prefix, no hoisting occurs."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {"/2/0/integrations": {}, "/health": {}},
    }
    result = hoist_version_prefix(spec)
    assert "/2/0/integrations" in result["paths"]
    assert result["servers"][0]["url"] == "https://api.example.com"
