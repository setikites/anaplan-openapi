"""
Tests that OpenAPI spec field ordering conforms to ADR 0002.
See docs/adr/0002-canonical-element-ordering.md
"""

import json
import pytest
from pathlib import Path
from check_ordering import check_spec_ordering

REPO_ROOT = Path(__file__).parent.parent
SPEC_FILES = sorted(REPO_ROOT.glob("*/*-openapi.json"))

_ADR = "docs/adr/0002-canonical-element-ordering.md"


# ─── Tracer bullet: document-level ordering ───────────────────────────────

def test_checker_passes_spec_with_canonical_document_order():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {},
    }
    assert check_spec_ordering(spec, "test") == []


def test_checker_fails_when_document_keys_are_out_of_order():
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "https://api.example.com"}],
        "info": {"title": "T", "version": "1"},  # info after servers — wrong
        "paths": {},
    }
    violations = check_spec_ordering(spec, "test")
    assert violations
    assert any(_ADR in v for v in violations)


# ─── Operation-level ordering ─────────────────────────────────────────────

def test_checker_passes_spec_with_canonical_operation_order():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/items": {
                "get": {
                    "summary": "List",
                    "description": "List items",
                    "operationId": "listItems",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    assert check_spec_ordering(spec, "test") == []


def test_checker_fails_when_operation_keys_are_out_of_order():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/items": {
                "get": {
                    "summary": "List",
                    "responses": {"200": {"description": "OK"}},
                    "operationId": "listItems",  # operationId after responses — wrong
                }
            }
        },
    }
    violations = check_spec_ordering(spec, "test")
    assert violations
    assert any("GET /items" in v for v in violations)
    assert any(_ADR in v for v in violations)


def test_checker_passes_when_optional_operation_fields_are_absent():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/items": {
                "get": {
                    "summary": "Get",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    assert check_spec_ordering(spec, "test") == []


# ─── Parameter array ordering ─────────────────────────────────────────────

def test_checker_passes_when_path_param_precedes_query_param():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/items/{id}": {
                "get": {
                    "summary": "Get item",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "filter", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    assert check_spec_ordering(spec, "test") == []


def test_checker_fails_when_required_param_follows_optional():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/items": {
                "get": {
                    "summary": "Get",
                    "parameters": [
                        {"name": "filter", "in": "query", "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": True, "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    violations = check_spec_ordering(spec, "test")
    assert violations
    assert any("parameters array" in v for v in violations)


def test_checker_skips_array_ordering_when_ref_params_present():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/items": {
                "get": {
                    "summary": "Get",
                    "parameters": [
                        {"$ref": "#/components/parameters/TenantHeader"},
                        {"name": "filter", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    # $ref params can't be resolved here; array ordering check is skipped
    assert check_spec_ordering(spec, "test") == []


# ─── Integration tests: all 9 specs must conform ──────────────────────────

@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_spec_conforms_to_element_ordering_standard(spec_path):
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    violations = check_spec_ordering(spec, spec_path.parent.name)
    assert not violations, (
        f"{spec_path.parent.name}: {len(violations)} ordering violation(s):\n"
        + "\n".join(f"  {v}" for v in violations)
    )
