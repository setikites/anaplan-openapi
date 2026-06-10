"""
Contract tests for the Financial Consolidation API spec.

Verifies that the spec satisfies the domain invariants documented in the issue:
- Spec loads and parses without error
- All 18 required path+method combinations are present
- securitySchemes declares apiToken (apiKey, X_API_TOKEN header)
- Global security is set
- TenantHeader reusable parameter exists in components/parameters
- Operation counts per section:
    OData: 5   (GET/POST/PUT/DELETE /odata/{tableName} + POST /odata/batch/{tableName})
    Metadata: 3 GET operations
    Workflow: 3 operations (start, stop, get state)
    User management: 7 operations
"""
import json
from pathlib import Path

import pytest

SPEC_PATH = Path(__file__).parent.parent / "financial-consolidation" / "financial-consolidation-openapi.json"
_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})


def _load():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


# ── Spec loads ────────────────────────────────────────────────────────────────

def test_spec_loads_without_error():
    spec = _load()
    assert spec["openapi"].startswith("3.0")
    assert spec["info"]["title"].strip()
    assert spec["info"]["version"].strip()
    assert spec.get("paths"), "spec must have at least one path"


# ── Global security ───────────────────────────────────────────────────────────

def test_global_security_is_set():
    spec = _load()
    assert spec.get("security"), "global security[] must be non-empty"


# ── Security scheme ───────────────────────────────────────────────────────────

def test_api_token_scheme_declared():
    spec = _load()
    schemes = spec.get("components", {}).get("securitySchemes", {})
    assert "apiToken" in schemes, "securitySchemes must include apiToken"
    s = schemes["apiToken"]
    assert s.get("type") == "apiKey", "apiToken must be type: apiKey"
    assert s.get("in") == "header", "apiToken must be in: header"
    assert s.get("name") == "X_API_TOKEN", "apiToken header name must be X_API_TOKEN"


# ── TenantHeader parameter ────────────────────────────────────────────────────

def test_tenant_header_parameter_defined():
    spec = _load()
    params = spec.get("components", {}).get("parameters", {})
    assert "TenantHeader" in params, "components/parameters must define TenantHeader"
    t = params["TenantHeader"]
    assert t.get("in") == "header", "TenantHeader must be in: header"
    assert t.get("name") == "TENANT", "TenantHeader header name must be TENANT"
    assert t.get("required") is True, "TenantHeader must be required: true"


# ── Required operations ───────────────────────────────────────────────────────

_EXPECTED_OPERATIONS = [
    # OData (5)
    ("get",    "/odata/{tableName}"),
    ("post",   "/odata/{tableName}"),
    ("put",    "/odata/{tableName}"),
    ("delete", "/odata/{tableName}"),
    ("post",   "/odata/batch/{tableName}"),
    # Metadata (3)
    ("get", "/metadata/Dimensions"),
    ("get", "/metadata/models/{modelName}/Dimensions"),
    ("get", "/metadata/Dimensions/{dimensionName}"),
    # Workflow (3)
    ("post", "/process/start/{path}/{name_of_workflow}"),
    ("post", "/process/stop/{path}/{name_of_workflow}"),
    ("get",  "/process/state/{path}/{name_of_workflow}"),
    # User management (7)
    ("get",    "/users"),
    ("post",   "/users"),
    ("put",    "/users"),
    ("delete", "/users/{username}"),
    ("get",    "/user/{username}/roles"),
    ("put",    "/user/{username}/roles"),
    ("delete", "/user/{username}/roles"),
]


@pytest.mark.parametrize("method,path", _EXPECTED_OPERATIONS)
def test_required_operation_exists(method, path):
    spec = _load()
    paths = spec.get("paths", {})
    assert path in paths, f"spec must document path {path!r}"
    assert method in paths[path], f"spec must document {method.upper()} {path}"


# ── Operation counts per section ──────────────────────────────────────────────

def _count_ops(spec, prefix):
    return sum(
        1
        for path_str, item in spec.get("paths", {}).items()
        if path_str.startswith(prefix)
        for method in _HTTP_METHODS
        if method in item
    )


def test_odata_section_has_five_operations():
    spec = _load()
    count = _count_ops(spec, "/odata/")
    assert count == 5, f"OData section: expected 5 operations, got {count}"


def test_metadata_section_has_three_operations():
    spec = _load()
    count = _count_ops(spec, "/metadata/")
    assert count == 3, f"Metadata section: expected 3 operations, got {count}"


def test_workflow_section_has_three_operations():
    spec = _load()
    count = _count_ops(spec, "/process/")
    assert count == 3, f"Workflow section: expected 3 operations, got {count}"


def test_user_management_section_has_seven_operations():
    spec = _load()
    count = _count_ops(spec, "/user")
    assert count == 7, f"User management section: expected 7 operations, got {count}"
