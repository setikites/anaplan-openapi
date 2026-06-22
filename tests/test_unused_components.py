"""
Tests that every component defined under components/ is referenced at least once.
"""

import json
import pytest
from pathlib import Path
from check_unused_components import check_spec

REPO_ROOT = Path(__file__).parent.parent
SPEC_FILES = sorted(REPO_ROOT.glob("*/*-openapi.json"))


# ─── Unit tests ──────────────────────────────────────────────────────────────

def test_checker_passes_when_schema_is_referenced():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/items": {
                "get": {
                    "summary": "List",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Item"}
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {"schemas": {"Item": {"type": "object"}}},
    }
    assert check_spec(spec, "test") == []


def test_checker_fails_when_schema_is_unreferenced():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {},
        "components": {"schemas": {"Orphan": {"type": "object"}}},
    }
    violations = check_spec(spec, "test")
    assert violations
    assert any("Orphan" in v for v in violations)


def test_checker_passes_when_security_scheme_is_used():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "security": [{"BearerAuth": []}],
        "paths": {},
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer"}
            }
        },
    }
    assert check_spec(spec, "test") == []


def test_checker_fails_when_security_scheme_is_unused():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {},
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer"}
            }
        },
    }
    violations = check_spec(spec, "test")
    assert violations
    assert any("BearerAuth" in v for v in violations)


def test_checker_passes_for_inter_component_ref():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/items": {
                "get": {
                    "summary": "List",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Wrapper"}
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Wrapper": {
                    "type": "object",
                    "properties": {
                        "item": {"$ref": "#/components/schemas/Inner"}
                    },
                },
                "Inner": {"type": "object"},
            }
        },
    }
    assert check_spec(spec, "test") == []


def test_checker_skips_stub_schema():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {},
        "components": {"schemas": {"Stub": {"x-stub": True, "type": "object"}}},
    }
    assert check_spec(spec, "test") == []


def test_checker_returns_empty_when_no_components():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {},
    }
    assert check_spec(spec, "test") == []


# ─── Integration tests: all 9 specs must pass ────────────────────────────────

@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_spec_has_no_unused_components(spec_path):
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    violations = check_spec(spec, spec_path.parent.name)
    assert not violations, (
        f"{spec_path.parent.name}: {len(violations)} unused component(s):\n"
        + "\n".join(f"  {v}" for v in violations)
    )
