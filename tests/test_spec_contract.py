"""
Contract tests verifying OpenAPI 3.0 spec files against domain invariants
from CONTEXT.md. These tests run without network access.

Invariants checked:
  Universal   — version, info, servers[], paths, responses, refs, security
  Cross-spec  — no path appears in more than one spec file
  Server URLs — each API family must use its correct host pattern
  Auth API    — BasicAuth + AnaplanAuthToken schemes; core endpoints present
  OAuth API   — core endpoints present; TokenResponse schema complete
  Integration — AnaplanAuthToken scheme declared (skipped until spec exists)
  SCIM        — BearerAuth scheme declared (skipped until spec exists)
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SPEC_FILES = sorted(REPO_ROOT.glob("*/*-openapi.json"))

# From CONTEXT.md: expected server URL host fragment per API directory.
# auth.anaplan.com  → Authentication API (token generation)
# app.anaplan.com   → OAuth 2.0 API
# api.anaplan.com   → all other data-plane APIs
SERVER_URL_PATTERNS: dict[str, str] = {
    "authentication":          "auth.anaplan.com",
    "oauth":                   "app.anaplan.com",
    "integration":             "api.anaplan.com",
    "scim":                    "api.anaplan.com",
    "alm":                     "api.anaplan.com",
    "audit":                   "api.anaplan.com",
    "cloudworks":              "api.anaplan.com",
    "financial-consolidation": "api.anaplan.com",
    "exception":               "api.anaplan.com",
}

# Host fragments that must NOT appear in a spec of each family.
# Catches copy-paste where e.g. a data-plane spec accidentally carries app.anaplan.com URLs.
_WRONG_URL_FRAGMENTS: dict[str, list[str]] = {
    "auth.anaplan.com": ["api.anaplan.com"],
    "app.anaplan.com":  ["auth.anaplan.com", "api.anaplan.com"],
    "api.anaplan.com":  ["auth.anaplan.com", "app.anaplan.com"],
}

_HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_operations(spec: dict):
    """Yield (path_str, method, operation) for every operation in spec."""
    for path_str, path_item in spec.get("paths", {}).items():
        for method in _HTTP_METHODS:
            if method in path_item:
                yield path_str, method, path_item[method]


def _collect_local_refs(obj, refs: set | None = None) -> set:
    """Recursively collect all internal $ref strings (starting with '#/')."""
    if refs is None:
        refs = set()
    if isinstance(obj, dict):
        if "$ref" in obj and isinstance(obj["$ref"], str):
            refs.add(obj["$ref"])
        for v in obj.values():
            _collect_local_refs(v, refs)
    elif isinstance(obj, list):
        for item in obj:
            _collect_local_refs(item, refs)
    return refs


def _specs_with_known_pattern() -> list[Path]:
    return [p for p in SPEC_FILES if p.parent.name in SERVER_URL_PATTERNS]


# ─── Universal invariants — run on every spec file found ──────────────────

@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_openapi_version_is_3_0(spec_path):
    spec = _load(spec_path)
    assert "openapi" in spec
    assert spec["openapi"].startswith("3.0"), (
        f"expected OpenAPI 3.0.x, got {spec['openapi']!r}"
    )


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_info_has_title_and_version(spec_path):
    spec = _load(spec_path)
    info = spec.get("info", {})
    assert info.get("title", "").strip(), "info.title is missing or empty"
    assert info.get("version", "").strip(), "info.version is missing or empty"


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_servers_list_is_nonempty(spec_path):
    spec = _load(spec_path)
    servers = spec.get("servers", [])
    assert servers, "servers[] must contain at least one entry"
    for server in servers:
        url = server.get("url", "")
        assert url.startswith("https://"), (
            f"server URL {url!r} must use https"
        )


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_paths_is_nonempty(spec_path):
    spec = _load(spec_path)
    assert spec.get("paths"), "paths must contain at least one endpoint"


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_every_operation_has_at_least_one_response(spec_path):
    spec = _load(spec_path)
    for path_str, method, operation in _all_operations(spec):
        assert operation.get("responses"), (
            f"{method.upper()} {path_str}: no responses documented"
        )


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_every_operation_has_summary_or_description(spec_path):
    spec = _load(spec_path)
    for path_str, method, operation in _all_operations(spec):
        has_summary = bool(operation.get("summary", "").strip())
        has_description = bool(operation.get("description", "").strip())
        assert has_summary or has_description, (
            f"{method.upper()} {path_str}: has neither summary nor description"
        )


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_internal_refs_resolve(spec_path):
    """Every #/components/... $ref must point to a component that actually exists."""
    spec = _load(spec_path)
    components = spec.get("components", {})
    for ref in _collect_local_refs(spec):
        if not ref.startswith("#/components/"):
            continue
        parts = ref.lstrip("#/").split("/")
        if len(parts) < 3:
            continue
        section, name = parts[1], parts[2]
        assert name in components.get(section, {}), (
            f"$ref {ref!r} points to a component that does not exist"
        )


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_security_requirements_reference_declared_schemes(spec_path):
    """Security requirements (global and per-operation) must name declared securitySchemes."""
    spec = _load(spec_path)
    declared = set(spec.get("components", {}).get("securitySchemes", {}).keys())

    for sec_req in spec.get("security", []):
        for scheme_name in sec_req:
            assert scheme_name in declared, (
                f"global security references undeclared scheme {scheme_name!r}"
            )

    for path_str, method, operation in _all_operations(spec):
        for sec_req in operation.get("security", []):
            for scheme_name in sec_req:
                assert scheme_name in declared, (
                    f"{method.upper()} {path_str}: security references "
                    f"undeclared scheme {scheme_name!r}"
                )


# ─── Cross-spec invariants ────────────────────────────────────────────────

def test_no_path_appears_in_more_than_one_spec():
    """Each URL path must be documented in exactly one spec file.

    Paths duplicated across specs cause client-generator confusion and drift
    when the two copies fall out of sync.
    """
    seen: dict[str, str] = {}  # path → first spec that defines it
    duplicates: list[str] = []

    for spec_path in SPEC_FILES:
        spec = _load(spec_path)
        api_name = spec_path.parent.name
        for path in spec.get("paths", {}):
            if path in seen:
                duplicates.append(
                    f"{path!r}: defined in both {seen[path]!r} and {api_name!r}"
                )
            else:
                seen[path] = api_name

    assert not duplicates, (
        "The following paths appear in more than one spec:\n"
        + "\n".join(f"  {d}" for d in duplicates)
    )


# ─── Server URL pattern invariants ────────────────────────────────────────

@pytest.mark.parametrize(
    "spec_path", _specs_with_known_pattern(), ids=lambda p: p.parent.name
)
def test_server_urls_match_api_family(spec_path):
    """At least one server URL must contain the host fragment for this API family."""
    api_dir = spec_path.parent.name
    expected = SERVER_URL_PATTERNS[api_dir]
    spec = _load(spec_path)
    urls = [s.get("url", "") for s in spec.get("servers", [])]
    assert any(expected in url for url in urls), (
        f"{api_dir}: no server URL contains {expected!r}. Got: {urls}"
    )


@pytest.mark.parametrize(
    "spec_path", _specs_with_known_pattern(), ids=lambda p: p.parent.name
)
def test_server_urls_dont_use_wrong_base(spec_path):
    """Server URLs must not use a host pattern that belongs to a different API family."""
    api_dir = spec_path.parent.name
    expected = SERVER_URL_PATTERNS[api_dir]
    forbidden = _WRONG_URL_FRAGMENTS.get(expected, [])
    spec = _load(spec_path)

    for server in spec.get("servers", []):
        url = server.get("url", "")
        for fragment in forbidden:
            assert fragment not in url, (
                f"{api_dir}: server URL {url!r} contains {fragment!r}, "
                f"which belongs to a different API family "
                f"(expected URLs containing {expected!r})"
            )


# ─── Authentication API ────────────────────────────────────────────────────
# Auth API uses HTTP Basic for token generation and AnaplanAuthToken for
# refresh/validate/logout. Both schemes must be declared.

_AUTH_SPEC = REPO_ROOT / "authentication" / "authentication-openapi.json"
_skip_auth = pytest.mark.skipif(
    not _AUTH_SPEC.exists(), reason="authentication spec not yet written"
)


@_skip_auth
def test_auth_spec_declares_basic_auth_scheme():
    """HTTP Basic is the primary mechanism for generating AnaplanAuthTokens."""
    spec = _load(_AUTH_SPEC)
    schemes = spec.get("components", {}).get("securitySchemes", {})
    basic = [
        name for name, d in schemes.items()
        if d.get("type") == "http" and d.get("scheme") == "basic"
    ]
    assert basic, (
        "authentication spec must declare an HTTP Basic scheme "
        "(type: http, scheme: basic)"
    )


@_skip_auth
def test_auth_spec_declares_anaplan_token_scheme():
    """Refresh, validate, and logout endpoints authenticate with AnaplanAuthToken."""
    spec = _load(_AUTH_SPEC)
    schemes = spec.get("components", {}).get("securitySchemes", {})
    # AnaplanAuthToken arrives in the Authorization header as an apiKey
    anaplan = [
        name for name, d in schemes.items()
        if (
            d.get("type") == "apiKey"
            and d.get("in") == "header"
            and d.get("name") == "Authorization"
        )
    ]
    assert anaplan, (
        "authentication spec must declare an AnaplanAuthToken-style scheme "
        "(type: apiKey, in: header, name: Authorization)"
    )


@_skip_auth
def test_auth_spec_has_token_authenticate_endpoint():
    spec = _load(_AUTH_SPEC)
    paths = spec.get("paths", {})
    assert "/token/authenticate" in paths, (
        "authentication spec must document /token/authenticate"
    )
    assert "post" in paths["/token/authenticate"], (
        "authentication spec must document POST /token/authenticate"
    )


@_skip_auth
def test_auth_spec_authenticate_endpoint_requires_security():
    """Token generation must not be an open endpoint — a security requirement is required."""
    spec = _load(_AUTH_SPEC)
    operation = (
        spec.get("paths", {})
        .get("/token/authenticate", {})
        .get("post", {})
    )
    assert operation.get("security"), (
        "POST /token/authenticate must declare a non-empty security requirement"
    )


# ─── OAuth API ─────────────────────────────────────────────────────────────
# OAuth API supports Authorization Code Grant and Device Authorization Grant.
# Core endpoints and the TokenResponse schema are required.

_OAUTH_SPEC = REPO_ROOT / "oauth" / "oauth-openapi.json"
_skip_oauth = pytest.mark.skipif(
    not _OAUTH_SPEC.exists(), reason="oauth spec not yet written"
)


@_skip_oauth
def test_oauth_spec_has_token_endpoint():
    """/oauth/token is the core token issuance endpoint for both grant types."""
    spec = _load(_OAUTH_SPEC)
    paths = spec.get("paths", {})
    assert "/oauth/token" in paths, "oauth spec must document /oauth/token"
    assert "post" in paths["/oauth/token"], (
        "oauth spec must document POST /oauth/token"
    )


@_skip_oauth
def test_oauth_spec_has_device_code_endpoint():
    """/oauth/device/code starts the Device Authorization Grant flow."""
    spec = _load(_OAUTH_SPEC)
    assert "/oauth/device/code" in spec.get("paths", {}), (
        "oauth spec must document /oauth/device/code"
    )


@_skip_oauth
def test_oauth_spec_has_authorize_endpoint():
    """/auth/authorize starts the Authorization Code Grant flow."""
    spec = _load(_OAUTH_SPEC)
    assert "/auth/authorize" in spec.get("paths", {}), (
        "oauth spec must document /auth/authorize"
    )


@_skip_oauth
def test_oauth_token_response_has_expires_in():
    """Clients use expires_in to manage the 35-minute token lifetime — must be in the schema."""
    spec = _load(_OAUTH_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    token_response = schemas.get("TokenResponse", {})
    assert "expires_in" in token_response.get("properties", {}), (
        "oauth TokenResponse schema must include 'expires_in' property"
    )


@_skip_oauth
def test_oauth_error_schema_has_rfc_6749_fields():
    """OAuth error responses require 'error' and 'error_description' per RFC 6749."""
    spec = _load(_OAUTH_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    error_schema = next(
        (s for name, s in schemas.items() if "error" in name.lower()),
        None,
    )
    assert error_schema is not None, "oauth spec must define an error response schema"
    props = error_schema.get("properties", {})
    assert "error" in props, (
        "oauth error schema must have 'error' field (RFC 6749 §5.2)"
    )
    assert "error_description" in props, (
        "oauth error schema must have 'error_description' field (RFC 6749 §5.2)"
    )


# ─── Integration API ───────────────────────────────────────────────────────
# Integration API accepts Bearer token OR AnaplanAuthToken (both must be declared).

_INTEGRATION_SPEC = REPO_ROOT / "integration" / "integration-openapi.json"
_skip_integration = pytest.mark.skipif(
    not _INTEGRATION_SPEC.exists(), reason="integration spec not yet written"
)


@_skip_integration
def test_integration_spec_declares_anaplan_token_scheme():
    """Integration API uses AnaplanAuthToken — must be declared as a securityScheme."""
    spec = _load(_INTEGRATION_SPEC)
    schemes = spec.get("components", {}).get("securitySchemes", {})
    # AnaplanAuthToken arrives as an apiKey in Authorization or its own header
    anaplan = [
        name for name, d in schemes.items()
        if (
            d.get("type") == "apiKey"
            and d.get("in") == "header"
            and d.get("name") in ("Authorization", "AnaplanAuthToken")
        )
    ]
    assert anaplan, (
        "integration spec must declare an AnaplanAuthToken security scheme "
        "(type: apiKey, in: header)"
    )


@_skip_integration
def test_integration_spec_declares_bearer_auth():
    """Integration API also accepts standard Bearer tokens — BearerAuth must be declared."""
    spec = _load(_INTEGRATION_SPEC)
    schemes = spec.get("components", {}).get("securitySchemes", {})
    bearer = [
        name for name, d in schemes.items()
        if d.get("type") == "http" and d.get("scheme") == "bearer"
    ]
    assert bearer, (
        "integration spec must declare a BearerAuth scheme (type: http, scheme: bearer)"
    )


@_skip_integration
def test_integration_spec_has_component_schemas():
    """Object schemas from the live /objects/ endpoints must appear in components/schemas."""
    spec = _load(_INTEGRATION_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    for expected in ("Workspace", "Model", "User", "Dimension", "Module"):
        assert expected in schemas, (
            f"integration spec must include {expected!r} in components/schemas"
        )


@_skip_integration
def test_integration_response_examples_match_schemas():
    """Every response example that has a sibling schema must validate against it."""
    from schema_importer import validate_response_examples
    spec = _load(_INTEGRATION_SPEC)
    warnings = validate_response_examples(spec)
    assert not warnings, (
        f"{len(warnings)} example/schema mismatch(es):\n"
        + "\n".join(f"  {w}" for w in warnings)
    )


# ─── Integration query parameter declarations ─────────────────────────────


def _all_params(spec, path_str, method):
    """Return combined path-level + operation-level parameters for an operation."""
    path_item = spec.get("paths", {}).get(path_str, {})
    return path_item.get("parameters", []) + path_item.get(method, {}).get("parameters", [])


@_skip_integration
def test_integration_current_period_put_declares_date_query_param():
    """PUT /models/{modelId}/currentPeriod must declare date as a query parameter.

    Live testing confirmed the API accepts date as either a query param or
    a request body field (but not both simultaneously).
    """
    spec = _load(_INTEGRATION_SPEC)
    params = _all_params(spec, "/models/{modelId}/currentPeriod", "put")
    names = {p["name"] for p in params if "name" in p}
    assert "date" in names, (
        "PUT /models/{modelId}/currentPeriod is missing date query parameter"
    )
    p = next(p for p in params if p.get("name") == "date")
    assert p.get("in") == "query"
    assert p.get("schema", {}).get("type") == "string"


@_skip_integration
def test_integration_current_period_put_declares_400_response():
    """PUT /models/{modelId}/currentPeriod must declare a 400 response."""
    spec = _load(_INTEGRATION_SPEC)
    responses = spec["paths"]["/models/{modelId}/currentPeriod"]["put"].get(
        "responses", {}
    )
    assert "400" in responses, (
        "PUT /models/{modelId}/currentPeriod is missing 400 response"
    )


@_skip_integration
def test_integration_view_data_declares_pages_param():
    """GET /models/{modelId}/views/{viewId}/data must declare the pages query parameter."""
    spec = _load(_INTEGRATION_SPEC)
    params = _all_params(spec, "/models/{modelId}/views/{viewId}/data", "get")
    names = {p["name"] for p in params if "name" in p}
    assert "pages" in names, (
        "GET /models/{modelId}/views/{viewId}/data is missing pages query parameter"
    )
    p = next(p for p in params if p.get("name") == "pages")
    assert p.get("in") == "query"


# Add entries here to extend sort contract coverage to additional list endpoints.
# sort_example must match the `example:` value declared in the spec for that path.
_SORT_PATHS = [
    # Task list endpoints
    pytest.param("/workspaces/{workspaceId}/models/{modelId}/imports/{importId}/tasks",    "-creationDate", id="import-tasks"),
    pytest.param("/workspaces/{workspaceId}/models/{modelId}/exports/{exportId}/tasks",    "-creationDate", id="export-tasks"),
    pytest.param("/workspaces/{workspaceId}/models/{modelId}/processes/{processId}/tasks", "-creationDate", id="process-tasks"),
    pytest.param("/workspaces/{workspaceId}/models/{modelId}/actions/{actionId}/tasks",    "-creationDate", id="action-tasks"),
    # Model-scoped list endpoints
    pytest.param("/models/{modelId}/files",                                                "+name",         id="files"),
    pytest.param("/workspaces/{workspaceId}/models/{modelId}/actions",                     "+name",         id="actions"),
    pytest.param("/workspaces/{workspaceId}/models/{modelId}/processes",                   "+name",         id="processes"),
    pytest.param("/workspaces/{workspaceId}/models/{modelId}/imports/",                    "+name",         id="imports"),
    pytest.param("/workspaces/{workspaceId}/models/{modelId}/exports",                     "+name",         id="exports"),
]


@_skip_integration
@pytest.mark.parametrize("path,sort_example", _SORT_PATHS)
def test_integration_list_declares_sort_only_param(path, sort_example):
    """List endpoints with sort-only support must declare sort (type: string, in: query)."""
    spec = _load(_INTEGRATION_SPEC)
    params = _all_params(spec, path, "get")
    names = {p["name"] for p in params if "name" in p}
    assert "sort" in names, f"GET {path} is missing sort query parameter"
    p = next(p for p in params if p.get("name") == "sort")
    assert p.get("in") == "query"
    assert p.get("schema", {}).get("type") == "string"
    assert p.get("example") == sort_example, (
        f"GET {path} sort example: expected {sort_example!r}, got {p.get('example')!r}"
    )
    assert "ascending" in p.get("description", "").lower()


@_skip_integration
def test_integration_models_list_declares_model_details():
    """GET /models must declare the modelDetails query parameter."""
    spec = _load(_INTEGRATION_SPEC)
    params = _all_params(spec, "/models", "get")
    names = {p["name"] for p in params if "name" in p}
    assert "modelDetails" in names, (
        "GET /models is missing modelDetails query parameter"
    )
    md = next(p for p in params if p.get("name") == "modelDetails")
    assert md.get("in") == "query"
    assert md.get("schema", {}).get("type") == "boolean"


# Add entries here to extend s/sort contract coverage to additional list endpoints.
# sort_example must match the `example:` value declared in the spec for that path.
_LIST_SEARCH_SORT = [
    pytest.param("/workspaces", "+name",      id="workspaces"),
    pytest.param("/models",     "+name",      id="models"),
    pytest.param("/users",      "+firstName", id="users"),
]


@_skip_integration
@pytest.mark.parametrize("path,sort_example", _LIST_SEARCH_SORT)
def test_integration_list_declares_s_param(path, sort_example):
    """List endpoints with search support must declare s (type: string, description: 'Search string')."""
    spec = _load(_INTEGRATION_SPEC)
    params = _all_params(spec, path, "get")
    names = {p["name"] for p in params if "name" in p}
    assert "s" in names, f"GET {path} is missing s query parameter"
    p = next(p for p in params if p.get("name") == "s")
    assert p.get("in") == "query"
    assert p.get("schema", {}).get("type") == "string"
    assert p.get("description") == "Search string"


@_skip_integration
@pytest.mark.parametrize("path,sort_example", _LIST_SEARCH_SORT)
def test_integration_list_declares_sort_param(path, sort_example):
    """List endpoints with sort support must declare sort with the correct example and description."""
    spec = _load(_INTEGRATION_SPEC)
    params = _all_params(spec, path, "get")
    names = {p["name"] for p in params if "name" in p}
    assert "sort" in names, f"GET {path} is missing sort query parameter"
    p = next(p for p in params if p.get("name") == "sort")
    assert p.get("in") == "query"
    assert p.get("schema", {}).get("type") == "string"
    assert p.get("example") == sort_example, (
        f"GET {path} sort example: expected {sort_example!r}, got {p.get('example')!r}"
    )
    assert "ascending" in p.get("description", "").lower()


@_skip_integration
def test_integration_workspace_views_declares_include_subsidiary_views():
    """GET /workspaces/{workspaceId}/models/{modelId}/views must declare includesubsidiaryviews."""
    spec = _load(_INTEGRATION_SPEC)
    params = _all_params(
        spec, "/workspaces/{workspaceId}/models/{modelId}/views", "get"
    )
    names = {p["name"] for p in params if "name" in p}
    assert "includesubsidiaryviews" in names, (
        "GET /workspaces/{workspaceId}/models/{modelId}/views is missing "
        "includesubsidiaryviews query parameter"
    )
    p = next(p for p in params if p.get("name") == "includesubsidiaryviews")
    assert p.get("in") == "query"


@_skip_integration
def test_integration_processes_declares_show_import_data_source():
    """GET /models/{modelId}/processes/{processId} must declare showImportDataSource."""
    spec = _load(_INTEGRATION_SPEC)
    params = _all_params(
        spec, "/models/{modelId}/processes/{processId}", "get"
    )
    names = {p["name"] for p in params if "name" in p}
    assert "showImportDataSource" in names, (
        "GET /models/{modelId}/processes/{processId} is missing "
        "showImportDataSource query parameter"
    )
    p = next(p for p in params if p.get("name") == "showImportDataSource")
    assert p.get("in") == "query"


# ─── Integration envelope schemas (Meta / Paging / Status) ───────────────


@_skip_integration
def test_integration_has_status_component_schema():
    """components/schemas/Status must exist with integer code and string message."""
    spec = _load(_INTEGRATION_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    assert "Status" in schemas, "components/schemas/Status is missing"
    props = schemas["Status"].get("properties", {})
    assert props.get("code", {}).get("type") == "integer", "Status.code must be type integer"
    assert props.get("message", {}).get("type") == "string", "Status.message must be type string"


@_skip_integration
def test_integration_has_paging_component_schema():
    """components/schemas/Paging must exist with three required integer fields."""
    spec = _load(_INTEGRATION_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    assert "Paging" in schemas, "components/schemas/Paging is missing"
    s = schemas["Paging"]
    props = s.get("properties", {})
    for field in ("currentPageSize", "totalSize", "offset"):
        assert props.get(field, {}).get("type") == "integer", (
            f"Paging.{field} must be type integer"
        )
    assert set(s.get("required", [])) >= {"currentPageSize", "totalSize", "offset"}, (
        "Paging must mark currentPageSize, totalSize, and offset as required"
    )


@_skip_integration
def test_integration_has_meta_component_schema():
    """components/schemas/Meta must exist with a required string schema field and optional $ref Paging."""
    spec = _load(_INTEGRATION_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    assert "Meta" in schemas, "components/schemas/Meta is missing"
    s = schemas["Meta"]
    props = s.get("properties", {})
    assert props.get("schema", {}).get("type") == "string", "Meta.schema must be type string"
    assert "schema" in s.get("required", []), "Meta.schema must be required"
    paging_prop = props.get("paging", {})
    assert paging_prop.get("$ref") == "#/components/schemas/Paging", (
        "Meta.paging must $ref #/components/schemas/Paging"
    )


@_skip_integration
def test_integration_response_meta_status_use_refs():
    """Every response schema with meta/status properties must use $ref, not bare type: object."""
    spec = _load(_INTEGRATION_SPEC)
    violations = []
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if not isinstance(op, dict):
                continue
            for code, resp in op.get("responses", {}).items():
                if not isinstance(resp, dict):
                    continue
                for ct, media in resp.get("content", {}).items():
                    props = media.get("schema", {}).get("properties", {})
                    for field in ("meta", "status"):
                        if field in props:
                            val = props[field]
                            if val == {"type": "object"} or "$ref" not in val:
                                violations.append(
                                    f"{method.upper()} {path} {code}: "
                                    f"{field} uses bare schema instead of $ref"
                                )
    assert not violations, "\n".join(violations)


# ─── Description cleanliness ──────────────────────────────────────────────


def _all_description_strings(spec: dict):
    """Yield every string value stored under a 'description' key anywhere in spec."""
    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "description" and isinstance(v, str):
                    yield v
                else:
                    yield from _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                yield from _walk(item)
    yield from _walk(spec)


# HTML tags that are noise outside of Markdown table cells.
# <br> inside a GFM table cell (line starting with |) is the standard way to
# add line breaks within cells -- those are kept. All other known HTML tags are noise.
_KNOWN_HTML_TAGS = re.compile(
    r"</?("
    r"p|strong|b|em|i|u|s|code|pre|a|ul|ol|li"
    r"|table|thead|tbody|tr|th|td|blockquote|hr|h[1-6]|span|div"
    r")(\s[^>]*)?>",
    re.IGNORECASE,
)
_BR_OUTSIDE_TABLE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _has_html_noise(description: str) -> bool:
    """Return True if description contains known HTML tags that should be Markdown."""
    if _KNOWN_HTML_TAGS.search(description):
        return True
    # <br> is acceptable inside table cell lines (lines starting with |);
    # flag it only when it appears outside of table cells.
    for line in description.splitlines():
        if not line.lstrip().startswith("|") and _BR_OUTSIDE_TABLE.search(line):
            return True
    return False


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_descriptions_have_no_nbsp(spec_path):
    """Non-breaking spaces are invisible noise; all descriptions must use regular spaces."""
    spec = _load(spec_path)
    violations = [
        repr(d[:120]) for d in _all_description_strings(spec) if "\xa0" in d
    ]
    assert not violations, (
        "{}: {} description(s) contain NBSP (\\u00a0):\n".format(
            spec_path.parent.name, len(violations)
        )
        + "\n".join("  " + v for v in violations[:3])
    )


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_descriptions_have_no_html_tags(spec_path):
    """Known HTML tags outside table cells must be converted to Markdown equivalents."""
    spec = _load(spec_path)
    violations = [
        repr(d[:120])
        for d in _all_description_strings(spec)
        if _has_html_noise(d)
    ]
    assert not violations, (
        "{}: {} description(s) contain raw HTML tags:\n".format(
            spec_path.parent.name, len(violations)
        )
        + "\n".join("  " + v for v in violations[:3])
    )

# ─── SCIM API ──────────────────────────────────────────────────────────────
# SCIM is a standard (RFC 7644). Anaplan implements Users + entitlements only.
# Auth: AnaplanAuthToken + BearerAuth (pending live-test validation — see issue #44).

_SCIM_SPEC = REPO_ROOT / "scim" / "scim-openapi.json"
_skip_scim = pytest.mark.skipif(
    not _SCIM_SPEC.exists(), reason="scim spec not yet written"
)

_SCIM_USER_ENDPOINTS = [
    ("get",   "/Users"),
    ("post",  "/Users"),
    ("get",   "/Users/{id}"),
    ("put",   "/Users/{id}"),
    ("patch", "/Users/{id}"),
]

_SCIM_DISCOVERY_ENDPOINTS = [
    ("get", "/ResourceTypes"),
    ("get", "/Schemas"),
    ("get", "/ServiceProviderConfig"),
]


@_skip_scim
def test_scim_spec_declares_bearer_auth():
    """SCIM uses standard Bearer token auth per RFC 7644 — must be declared."""
    spec = _load(_SCIM_SPEC)
    schemes = spec.get("components", {}).get("securitySchemes", {})
    bearer = [
        name for name, d in schemes.items()
        if d.get("type") == "http" and d.get("scheme") == "bearer"
    ]
    assert bearer, (
        "scim spec must declare a Bearer security scheme (type: http, scheme: bearer)"
    )


@_skip_scim
def test_scim_spec_declares_anaplan_token_scheme():
    """Anaplan also accepts AnaplanAuthToken on SCIM endpoints (pending live validation)."""
    spec = _load(_SCIM_SPEC)
    schemes = spec.get("components", {}).get("securitySchemes", {})
    anaplan = [
        name for name, d in schemes.items()
        if d.get("type") == "apiKey" and d.get("in") == "header"
    ]
    assert anaplan, (
        "scim spec must declare an AnaplanAuthToken-style scheme "
        "(type: apiKey, in: header)"
    )


@_skip_scim
@pytest.mark.parametrize("method,path", _SCIM_USER_ENDPOINTS, ids=lambda x: x)
def test_scim_spec_has_user_endpoint(method, path):
    """All SCIM user CRUD endpoints must be documented."""
    spec = _load(_SCIM_SPEC)
    paths = spec.get("paths", {})
    assert path in paths, f"scim spec must document {path}"
    assert method in paths[path], f"scim spec must document {method.upper()} {path}"


@_skip_scim
@pytest.mark.parametrize("method,path", _SCIM_DISCOVERY_ENDPOINTS, ids=lambda x: x)
def test_scim_spec_has_discovery_endpoint(method, path):
    """SCIM discovery endpoints must be documented."""
    spec = _load(_SCIM_SPEC)
    paths = spec.get("paths", {})
    assert path in paths, f"scim spec must document {path}"
    assert method in paths[path], f"scim spec must document {method.upper()} {path}"


@_skip_scim
def test_scim_spec_user_schema_has_entitlements():
    """User schema must include the Anaplan-specific entitlements attribute."""
    spec = _load(_SCIM_SPEC)
    user = spec.get("components", {}).get("schemas", {}).get("User", {})
    props = user.get("properties", {})
    assert "entitlements" in props, (
        "scim User schema must include 'entitlements' property "
        "(Anaplan-specific, not standard SCIM)"
    )


@_skip_scim
@pytest.mark.parametrize("schema_name", ["ListResponse", "ScimError", "PatchOp"])
def test_scim_spec_has_required_schema(schema_name):
    """ListResponse, ScimError, and PatchOp must be defined in components/schemas."""
    spec = _load(_SCIM_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    assert schema_name in schemas, (
        f"scim spec must define {schema_name!r} in components/schemas"
    )


@_skip_scim
def test_scim_get_users_declares_pagination_params():
    """GET /Users must declare the standard SCIM pagination and filter query params."""
    spec = _load(_SCIM_SPEC)
    params = _all_params(spec, "/Users", "get")
    names = {p["name"] for p in params if "name" in p}
    for param in ("startIndex", "count", "filter"):
        assert param in names, (
            f"GET /Users is missing {param!r} query parameter"
        )


# ─── Description formatting ────────────────────────────────────────────────


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_json_samples_use_fenced_code_blocks(spec_path):
    """Bare JSON objects/arrays in descriptions must be wrapped in fenced code blocks."""
    spec = _load(spec_path)
    violations = []
    for d in _all_description_strings(spec):
        in_fence = False
        for line in d.splitlines():
            if line.startswith("```"):
                in_fence = not in_fence
            elif not in_fence and re.match(r"^\s*[{\[]", line):
                violations.append(repr(line[:80]))
    assert not violations, (
        "{}: {} bare JSON line(s) found outside fenced code blocks:\n".format(
            spec_path.parent.name, len(violations)
        )
        + "\n".join("  " + v for v in violations[:3])
    )


def test_clean_descriptions_is_idempotent():
    """Running clean_descriptions twice on a dirty spec produces the same result as once."""
    from converter import clean_descriptions
    dirty = {
        "paths": {
            "/test": {"get": {"description": "has\xa0nbsp and bare JSON:\n{\"k\": 1}"}}
        }
    }
    once = clean_descriptions(dirty)
    twice = clean_descriptions(once)
    assert once == twice
