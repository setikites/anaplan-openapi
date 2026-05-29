import json
import yaml
import pytest
from openapi_spec_validator import validate
from converter import convert_openapi_spec


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


def test_convert_authentication_postman_spec():
    """Integration test: convert authentication/postman-spec.yaml to valid OpenAPI JSON."""
    import pathlib

    spec_file = pathlib.Path(__file__).parent.parent / "authentication" / "postman-spec.yaml"
    with open(spec_file, encoding="utf-8") as f:
        postman_spec = yaml.safe_load(f)

    result = convert_openapi_spec(postman_spec)

    # Verify structure
    assert result["openapi"] == "3.0.0"
    assert result["info"]["title"] is not None

    # Verify all 4 endpoints are present
    expected_endpoints = ["/token/authenticate", "/token/refresh", "/token/validate", "/token/logout"]
    for endpoint in expected_endpoints:
        assert endpoint in result["paths"], f"Missing endpoint: {endpoint}"

    # Verify security schemes are present
    assert "BasicAuth" in result["components"]["securitySchemes"], "Missing BasicAuth scheme"

    # Verify output is valid OpenAPI
    validate(result)
