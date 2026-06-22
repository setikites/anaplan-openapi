"""
Contract tests verifying OpenAPI 3.0 spec files against domain invariants
from CONTEXT.md. These tests run without network access.

Invariants checked:
  Universal        — version, info, servers[], paths, responses, refs, security
  Cross-spec       — no path appears in more than one spec file
  Server URLs      — each API family must use its correct host pattern
  Security schemes — each API must declare the scheme(s) it accepts
  Required paths   — each API must document its core (method, path) pairs
  Auth API         — security requirement present on token endpoint
  OAuth API        — TokenResponse schema complete; RFC 6749 error fields
  Integration      — component schemas, query params, envelope schemas
  SCIM             — User schema has entitlements; required schemas defined
  ALM              — server URL count; specific query parameters
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
# audit.anaplan.com → Audit API (dedicated global host; confirmed via live testing)
# api.anaplan.com   → all other data-plane APIs
SERVER_URL_PATTERNS: dict[str, str] = {
    "authentication":          "auth.anaplan.com",
    "oauth":                   "app.anaplan.com",
    "integration":             "api.anaplan.com",
    "scim":                    "api.anaplan.com",
    "alm":                     "api.anaplan.com",
    "audit":                   "audit.anaplan.com",
    "cloudworks":              "api.anaplan.com",
    "financial-consolidation": "fluenceapi-prod.fluence.app",
    "exception":               "api.anaplan.com",
}

# Host fragments that must NOT appear in a spec of each family.
# Catches copy-paste where e.g. a data-plane spec accidentally carries app.anaplan.com URLs.
_WRONG_URL_FRAGMENTS: dict[str, list[str]] = {
    "auth.anaplan.com":  ["api.anaplan.com"],
    "app.anaplan.com":   ["auth.anaplan.com", "api.anaplan.com"],
    "api.anaplan.com":   ["auth.anaplan.com", "app.anaplan.com"],
    # Audit has a dedicated host; the api.anaplan.com data-plane hosts return 404
    # for /audit/api/1 (confirmed via live testing, issues #58–#61).
    "audit.anaplan.com": ["api.anaplan.com"],
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


def _skip_if_missing(api_dir: str):
    spec_path = REPO_ROOT / api_dir / f"{api_dir}-openapi.json"
    return pytest.mark.skipif(
        not spec_path.exists(), reason=f"{api_dir} spec not yet written"
    )


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


_SCAFFOLD_SPECS: set[str] = set()


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_paths_is_nonempty(spec_path):
    spec = _load(spec_path)
    if spec_path.parent.name in _SCAFFOLD_SPECS:
        pytest.skip("scaffold spec — paths will be populated in a follow-up issue")
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


def _resolve_param(spec: dict, param: dict) -> dict:
    """Resolve a parameter dict, following a local $ref if present."""
    if "$ref" in param:
        ref = param["$ref"]
        if ref.startswith("#/components/parameters/"):
            name = ref.split("/")[-1]
            return spec.get("components", {}).get("parameters", {}).get(name, param)
    return param


_PATH_PARAM_RE = re.compile(r"\{(\w+)\}")


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_path_params_not_inside_operations(spec_path):
    """Path parameters must be declared at path item level, not inside operations (ADR 0002)."""
    spec = _load(spec_path)
    violations = []
    for path_str, method, operation in _all_operations(spec):
        for param in operation.get("parameters", []):
            resolved = _resolve_param(spec, param)
            if resolved.get("in") == "path":
                violations.append(
                    f"{method.upper()} {path_str}: path param "
                    f"{resolved.get('name', '?')!r} must be at path item level"
                )
    assert not violations, (
        "Path parameters found inside operations (ADR 0002 — move to path item level):\n"
        + "\n".join(f"  {v}" for v in violations)
    )


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_path_items_declare_inline_path_params(spec_path):
    """Every path with {param} segments must declare those params inline at path item level (ADR 0002)."""
    spec = _load(spec_path)
    violations = []
    for path_str, path_item in spec.get("paths", {}).items():
        expected = set(_PATH_PARAM_RE.findall(path_str))
        if not expected:
            continue
        declared = {
            p["name"]
            for p in path_item.get("parameters", [])
            if isinstance(p, dict) and "name" in p and p.get("in") == "path"
        }
        for name in sorted(expected - declared):
            violations.append(
                f"{path_str}: path param {name!r} not declared inline at path item level"
            )
    assert not violations, (
        "Path parameters missing from path item level (ADR 0002):\n"
        + "\n".join(f"  {v}" for v in violations)
    )


@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_path_item_parameters_precede_verbs(spec_path):
    """In every path item, the 'parameters' key must appear before any HTTP verb key (ADR 0002)."""
    spec = _load(spec_path)
    violations = []
    for path_str, path_item in spec.get("paths", {}).items():
        if "parameters" not in path_item:
            continue
        keys = list(path_item.keys())
        params_index = keys.index("parameters")
        for verb in _HTTP_METHODS:
            if verb in path_item:
                verb_index = keys.index(verb)
                if verb_index < params_index:
                    violations.append(
                        f"{path_str}: '{verb}' (index {verb_index}) appears before "
                        f"'parameters' (index {params_index})"
                    )
    assert not violations, (
        "Path item 'parameters' must come before HTTP verb keys (ADR 0002):\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ─── Cross-spec invariants ────────────────────────────────────────────────


# Known cross-spec path overlaps that are intentional and not copy-paste errors.
# Each tuple is (path, api_a, api_b). These APIs run on completely different hosts
# and are unrelated — the path string coincidence is harmless.
_ALLOWED_PATH_OVERLAPS: set[frozenset] = {
    # Integration API (api.anaplan.com) and Financial Consolidation API
    # (fluenceapi-prod.fluence.app) both expose /users for user management.
    frozenset({"integration", "financial-consolidation"}),
}


def test_no_path_appears_in_more_than_one_spec():
    """Each URL path must be documented in exactly one spec file.

    Paths duplicated across specs cause client-generator confusion and drift
    when the two copies fall out of sync. Known intentional overlaps between
    specs on entirely different hosts are listed in _ALLOWED_PATH_OVERLAPS.
    """
    seen: dict[str, str] = {}  # path → first spec that defines it
    duplicates: list[str] = []

    for spec_path in SPEC_FILES:
        spec = _load(spec_path)
        api_name = spec_path.parent.name
        for path in spec.get("paths", {}):
            if path in seen:
                pair = frozenset({seen[path], api_name})
                if pair not in _ALLOWED_PATH_OVERLAPS:
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


# Minimum server entry count for specs that cover all 19 Anaplan regions.
# 12 = 11 unique regional hosts + 1 shared legacy host (api.anaplan.com).
# cloudworks is excluded until its spec reaches full regional coverage.
# audit is excluded: it is served from a single dedicated global host
# (audit.anaplan.com), not the regional api.anaplan.com pattern — confirmed via
# live testing (issues #58–#61).
_MIN_SERVER_COUNT: dict[str, int] = {
    "integration": 12,
    "alm":         12,
    "scim":        12,
    "exception":   12,
}


@pytest.mark.parametrize(
    "spec_path",
    [p for p in SPEC_FILES if p.parent.name in _MIN_SERVER_COUNT],
    ids=lambda p: p.parent.name,
)
def test_spec_covers_minimum_regions(spec_path):
    """Specs with full regional coverage must declare at least one server per distinct host."""
    api_dir = spec_path.parent.name
    minimum = _MIN_SERVER_COUNT[api_dir]
    spec = _load(spec_path)
    urls = [s.get("url", "") for s in spec.get("servers", [])]
    assert len(urls) >= minimum, (
        f"{api_dir}: declares only {len(urls)} server(s); "
        f"expected at least {minimum} (one per distinct regional host)"
    )


# ─── Security scheme declarations ─────────────────────────────────────────
# Each row declares that a spec must contain at least one security scheme
# matching the given type. New APIs: add rows here.
#
# Scheme types:
#   basic         — type: http, scheme: basic
#   bearer        — type: http, scheme: bearer
#   anaplan_token — type: apiKey, in: header  (AnaplanAuthToken or CACertAuth)

_SCHEME_REQUIREMENTS = [
    # Authentication: Basic for token generation; AnaplanAuthToken for refresh/validate/logout
    pytest.param("authentication", "basic",         id="auth-basic"),
    pytest.param("authentication", "anaplan_token", id="auth-anaplan-token"),
    # Integration: both Bearer and AnaplanAuthToken accepted
    pytest.param("integration",    "anaplan_token", id="integration-anaplan-token"),
    pytest.param("integration",    "bearer",        id="integration-bearer"),
    # SCIM: all three schemes accepted (confirmed via live testing, issue #44)
    pytest.param("scim",           "bearer",        id="scim-bearer"),
    pytest.param("scim",           "anaplan_token", id="scim-anaplan-token"),
    pytest.param("scim",           "basic",         id="scim-basic"),
    # ALM: AnaplanAuthToken confirmed via Apiary; Bearer declared but unconfirmed
    pytest.param("alm",            "anaplan_token", id="alm-anaplan-token"),
    # Exception Users: AnaplanAuthToken only (Apiary confirmed; Bearer not documented)
    pytest.param("exception",      "anaplan_token", id="exception-anaplan-token"),
    # Audit: AnaplanAuthToken confirmed via Apiary; Bearer declared but unconfirmed
    pytest.param("audit",          "anaplan_token", id="audit-anaplan-token"),
    # Financial Consolidation: X_API_TOKEN apiKey header (Fluence platform — different host)
    pytest.param("financial-consolidation", "anaplan_token", id="fc-api-token"),
]

_SCHEME_MATCHERS = {
    "basic":         lambda d: d.get("type") == "http" and d.get("scheme") == "basic",
    "bearer":        lambda d: d.get("type") == "http" and d.get("scheme") == "bearer",
    "anaplan_token": lambda d: d.get("type") == "apiKey" and d.get("in") == "header",
}


@pytest.mark.parametrize("api_dir,scheme_type", _SCHEME_REQUIREMENTS)
def test_spec_declares_security_scheme(api_dir, scheme_type):
    """Each API spec must declare the security scheme(s) it accepts."""
    spec_path = REPO_ROOT / api_dir / f"{api_dir}-openapi.json"
    if not spec_path.exists():
        pytest.skip(f"{api_dir} spec not yet written")
    spec = _load(spec_path)
    schemes = spec.get("components", {}).get("securitySchemes", {})
    match = _SCHEME_MATCHERS[scheme_type]
    assert any(match(d) for d in schemes.values()), (
        f"{api_dir}: missing {scheme_type!r} security scheme in components/securitySchemes"
    )


# ─── Required endpoint declarations ───────────────────────────────────────
# Each row declares that a spec must document the given (method, path) pair.
# New APIs: add rows here.

_REQUIRED_ENDPOINTS = [
    # Authentication API
    pytest.param("authentication", "post", "/token/authenticate",                                                                         id="auth-token-authenticate"),
    # OAuth API
    pytest.param("oauth",          "post", "/oauth/token",                                                                                id="oauth-token"),
    pytest.param("oauth",          "post", "/oauth/device/code",                                                                          id="oauth-device-code"),
    pytest.param("oauth",          "get",  "/auth/authorize",                                                                             id="oauth-authorize"),
    # SCIM API — user CRUD
    pytest.param("scim",           "get",  "/Users",                                                                                      id="scim-list-users"),
    pytest.param("scim",           "post", "/Users",                                                                                      id="scim-create-user"),
    pytest.param("scim",           "get",  "/Users/{id}",                                                                                 id="scim-get-user"),
    pytest.param("scim",           "put",  "/Users/{id}",                                                                                 id="scim-update-user"),
    pytest.param("scim",           "patch","/Users/{id}",                                                                                 id="scim-patch-user"),
    # SCIM API — discovery
    pytest.param("scim",           "get",  "/ResourceTypes",                                                                              id="scim-resource-types"),
    pytest.param("scim",           "get",  "/Schemas",                                                                                    id="scim-schemas"),
    pytest.param("scim",           "get",  "/ServiceProviderConfig",                                                                      id="scim-service-provider-config"),
    # ALM API — revisions
    pytest.param("alm",            "get",  "/models/{modelId}/alm/latestRevision",                                                        id="alm-latest-revision"),
    pytest.param("alm",            "get",  "/models/{modelId}/alm/revisions",                                                             id="alm-list-revisions"),
    pytest.param("alm",            "post", "/models/{modelId}/alm/revisions",                                                             id="alm-create-revision"),
    pytest.param("alm",            "get",  "/models/{modelId}/alm/revisions/{revisionId}/appliedToModels",                                id="alm-applied-to-models"),
    # ALM API — sync tasks
    pytest.param("alm",            "get",  "/models/{modelId}/alm/syncableRevisions",                                                     id="alm-syncable-revisions"),
    pytest.param("alm",            "get",  "/models/{modelId}/alm/syncTasks",                                                             id="alm-list-sync-tasks"),
    pytest.param("alm",            "post", "/models/{modelId}/alm/syncTasks",                                                             id="alm-create-sync-task"),
    pytest.param("alm",            "get",  "/models/{modelId}/alm/syncTasks/{syncTaskId}",                                                id="alm-get-sync-task"),
    # ALM API — comparison and summary reports
    pytest.param("alm",            "post", "/models/{modelId}/alm/comparisonReportTasks",                                                 id="alm-create-comparison-task"),
    pytest.param("alm",            "get",  "/models/{modelId}/alm/comparisonReportTasks/{taskId}",                                        id="alm-get-comparison-task"),
    pytest.param("alm",            "get",  "/models/{modelId}/alm/comparisonReports/{targetRevisionId}/{sourceRevisionId}",               id="alm-comparison-report"),
    pytest.param("alm",            "post", "/models/{modelId}/alm/summaryReportTasks",                                                    id="alm-create-summary-task"),
    pytest.param("alm",            "get",  "/models/{modelId}/alm/summaryReportTasks/{taskId}",                                           id="alm-get-summary-task"),
    pytest.param("alm",            "get",  "/models/{modelId}/alm/summaryReports/{targetRevisionId}/{sourceRevisionId}",                  id="alm-summary-report"),
    # ALM API — online status
    pytest.param("alm",            "post", "/models/{modelId}/onlineStatus",                                                              id="alm-online-status-post"),
    pytest.param("alm",            "put",  "/models/{modelId}/onlineStatus",                                                              id="alm-online-status-put"),
    # Exception Users API
    pytest.param("exception",      "patch", "/permissions/exception-users/users/{userGuid}", id="exception-patch-user"),
    pytest.param("exception",      "post",  "/permissions/exception-users/search",           id="exception-search"),
    # Audit API
    pytest.param("audit",          "get",   "/events",                                       id="audit-get-events"),
    pytest.param("audit",          "post",  "/events/search",                                id="audit-post-search"),
    # Financial Consolidation API — OData endpoints
    pytest.param("financial-consolidation", "get",    "/odata/{tableName}",       id="fc-odata-get"),
    pytest.param("financial-consolidation", "post",   "/odata/{tableName}",       id="fc-odata-post"),
    pytest.param("financial-consolidation", "post",   "/odata/batch/{tableName}", id="fc-odata-batch"),
    pytest.param("financial-consolidation", "put",    "/odata/{tableName}",       id="fc-odata-put"),
    pytest.param("financial-consolidation", "delete", "/odata/{tableName}",       id="fc-odata-delete"),
    # Financial Consolidation API — Metadata endpoints
    pytest.param("financial-consolidation", "get", "/metadata/Dimensions",                          id="fc-metadata-dimensions-tenant"),
    pytest.param("financial-consolidation", "get", "/metadata/models/{modelName}/Dimensions",       id="fc-metadata-dimensions-model"),
    pytest.param("financial-consolidation", "get", "/metadata/Dimensions/{dimensionName}",          id="fc-metadata-dimension-members"),
    # Financial Consolidation API — Workflow endpoints
    pytest.param("financial-consolidation", "post", "/process/start/{path}/{name_of_workflow}", id="fc-workflow-start"),
    pytest.param("financial-consolidation", "post", "/process/stop/{path}/{name_of_workflow}",  id="fc-workflow-stop"),
    pytest.param("financial-consolidation", "get",  "/process/state/{path}/{name_of_workflow}", id="fc-workflow-state"),
    # Financial Consolidation API — User Management endpoints
    pytest.param("financial-consolidation", "get",    "/users",                    id="fc-users-list"),
    pytest.param("financial-consolidation", "post",   "/users",                    id="fc-users-add"),
    pytest.param("financial-consolidation", "put",    "/users",                    id="fc-users-update"),
    pytest.param("financial-consolidation", "delete", "/users/{username}",         id="fc-users-delete"),
    pytest.param("financial-consolidation", "get",    "/user/{username}/roles",    id="fc-user-roles-list"),
    pytest.param("financial-consolidation", "put",    "/user/{username}/roles",    id="fc-user-roles-assign"),
    pytest.param("financial-consolidation", "delete", "/user/{username}/roles",    id="fc-user-roles-unassign"),
]


@pytest.mark.parametrize("api_dir,method,path", _REQUIRED_ENDPOINTS)
def test_spec_has_required_endpoint(api_dir, method, path):
    """Each API spec must document the required (method, path) combinations."""
    spec_path = REPO_ROOT / api_dir / f"{api_dir}-openapi.json"
    if not spec_path.exists():
        pytest.skip(f"{api_dir} spec not yet written")
    spec = _load(spec_path)
    paths = spec.get("paths", {})
    assert path in paths, f"{api_dir}: spec must document {path}"
    assert method in paths[path], (
        f"{api_dir}: spec must document {method.upper()} {path}"
    )


# ─── Authentication API ────────────────────────────────────────────────────
# Auth API uses HTTP Basic for token generation and AnaplanAuthToken for
# refresh/validate/logout. Both schemes must be declared.

_AUTH_SPEC = REPO_ROOT / "authentication" / "authentication-openapi.json"
_skip_auth = _skip_if_missing("authentication")


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
_skip_oauth = _skip_if_missing("oauth")


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
_skip_integration = _skip_if_missing("integration")


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
def test_integration_model_active_state_is_enum():
    """Model.activeState must constrain values to the confirmed set of lifecycle states."""
    spec = _load(_INTEGRATION_SPEC)
    active_state = (
        spec.get("components", {})
        .get("schemas", {})
        .get("Model", {})
        .get("properties", {})
        .get("activeState", {})
    )
    expected = {"MAINTENANCE", "UNLOCKED", "PRODUCTION", "ARCHIVED", "PRODUCTION_MAINTENANCE", "LOCKED"}
    actual = set(active_state.get("enum", []))
    assert actual == expected, (
        f"Model.activeState enum drifted from the confirmed set: {actual!r}"
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


def _walk_descriptions_with_path(obj, path: str = ""):
    """Recursively walk spec yielding (json_path, description_str) for every description key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}" if path else k
            if k == "description" and isinstance(v, str):
                yield child_path, v
            else:
                yield from _walk_descriptions_with_path(v, child_path)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _walk_descriptions_with_path(item, f"{path}[{i}]")


_INLINE_EXAMPLE_RE = re.compile(r"\be\.g\.|for example\b", re.IGNORECASE)


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


@pytest.mark.xfail(reason="inline examples not yet migrated to example: field — blocked until issues #100–#106 are resolved", strict=False)
@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_descriptions_have_no_inline_examples(spec_path):
    """Descriptions must not embed inline examples via 'e.g.' or 'for example'; use example: field."""
    spec = _load(spec_path)
    violations = []
    for json_path, description in _walk_descriptions_with_path(spec):
        if _INLINE_EXAMPLE_RE.search(description):
            violations.append(f"{json_path}: {description[:80]!r}")
    assert not violations, (
        "{}: {} description(s) contain inline example phrases (use example: field instead):\n".format(
            spec_path.parent.name, len(violations)
        )
        + "\n".join(f"  {v}" for v in violations)
    )


# ─── SCIM API ──────────────────────────────────────────────────────────────
# SCIM is a standard (RFC 7644). Anaplan implements Users + entitlements only.
# Auth: AnaplanAuthToken + BearerAuth + BasicAuth — all three confirmed via live
# testing (issue #44). All three return 403 (not 401) on GET /Users when the
# caller lacks USER_ADMIN role, confirming the auth layer accepts each scheme.

_SCIM_SPEC = REPO_ROOT / "scim" / "scim-openapi.json"
_skip_scim = _skip_if_missing("scim")


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


# ─── ALM API ───────────────────────────────────────────────────────────────
# ALM (Application Lifecycle Management) manages model revisions, sync tasks,
# and comparison/summary reports. Auth: AnaplanAuthToken (confirmed via Apiary).
# BearerAuth declared but unconfirmed — pending live testing.

_ALM_SPEC = REPO_ROOT / "alm" / "alm-openapi.json"
_skip_alm = _skip_if_missing("alm")


@_skip_alm
def test_alm_syncable_revisions_declares_source_model_query_param():
    """GET /models/{modelId}/alm/syncableRevisions requires sourceModelId query param."""
    spec = _load(_ALM_SPEC)
    params = _all_params(spec, "/models/{modelId}/alm/syncableRevisions", "get")
    names = {p["name"] for p in params if "name" in p}
    assert "sourceModelId" in names, (
        "GET /models/{modelId}/alm/syncableRevisions must declare sourceModelId query parameter"
    )
    p = next(p for p in params if p.get("name") == "sourceModelId")
    assert p.get("in") == "query"
    assert p.get("required") is True


@_skip_alm
def test_alm_revisions_get_declares_pagination_params():
    """GET /models/{modelId}/alm/revisions must declare limit and offset query params."""
    spec = _load(_ALM_SPEC)
    params = _all_params(spec, "/models/{modelId}/alm/revisions", "get")
    names = {p["name"] for p in params if "name" in p}
    for param in ("limit", "offset"):
        assert param in names, (
            f"GET /models/{{modelId}}/alm/revisions must declare {param!r} query parameter"
        )


# ─── Exception Users API ──────────────────────────────────────────────────
# Manages exception users (users who bypass SSO enforcement) in workspaces.
# Auth: AnaplanAuthToken (OAuth Authorization Code tokens accepted) and
# AnaplanApiKey — both confirmed via live testing (issue #51).
# Bearer rejected with FAILURE_BAD_HEADER even for valid OAuth tokens.
# Error response shape confirmed: { status, statusMessage } (not { status, message }).

_EXCEPTION_SPEC = REPO_ROOT / "exception" / "exception-openapi.json"
_skip_exception = _skip_if_missing("exception")


@_skip_exception
@pytest.mark.parametrize("schema_name", [
    "ExceptionUserPatchRequest",
    "ExceptionUserSearchRequest",
    "ExceptionUserSearchByWorkspaceRequest",
    "ExceptionUserSearchByUserRequest",
    "ExceptionUserSearchResponse",
    "ExceptionUserWorkspaceResult",
    "ExceptionUser",
])
def test_exception_spec_has_required_schema(schema_name):
    """All Exception Users domain schemas must be defined in components/schemas."""
    spec = _load(_EXCEPTION_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    assert schema_name in schemas, (
        f"exception spec must define {schema_name!r} in components/schemas"
    )


@_skip_exception
def test_exception_patch_request_op_is_enum():
    """PATCH request body must constrain op to 'assign' | 'unassign' via an enum."""
    spec = _load(_EXCEPTION_SPEC)
    schema = (
        spec.get("components", {})
        .get("schemas", {})
        .get("ExceptionUserPatchRequest", {})
    )
    op_prop = schema.get("properties", {}).get("op", {})
    assert op_prop.get("enum") == ["assign", "unassign"], (
        "ExceptionUserPatchRequest.op must be an enum of ['assign', 'unassign']"
    )


@_skip_exception
def test_exception_patch_request_requires_op_and_workspace():
    """PATCH request body must mark both op and workspaceGuid as required."""
    spec = _load(_EXCEPTION_SPEC)
    schema = (
        spec.get("components", {})
        .get("schemas", {})
        .get("ExceptionUserPatchRequest", {})
    )
    required = set(schema.get("required", []))
    assert {"op", "workspaceGuid"} <= required, (
        "ExceptionUserPatchRequest must require both 'op' and 'workspaceGuid'"
    )


@_skip_exception
def test_exception_search_request_uses_oneof():
    """POST search request body must use oneOf to distinguish workspace vs user search."""
    spec = _load(_EXCEPTION_SPEC)
    schema = (
        spec.get("components", {})
        .get("schemas", {})
        .get("ExceptionUserSearchRequest", {})
    )
    assert "oneOf" in schema, (
        "ExceptionUserSearchRequest must use oneOf "
        "(workspace search and user search are mutually exclusive)"
    )


@_skip_exception
def test_exception_search_response_has_response_array():
    """Search response must wrap results in a top-level 'response' array."""
    spec = _load(_EXCEPTION_SPEC)
    schema = (
        spec.get("components", {})
        .get("schemas", {})
        .get("ExceptionUserSearchResponse", {})
    )
    response_prop = schema.get("properties", {}).get("response", {})
    assert response_prop.get("type") == "array", (
        "ExceptionUserSearchResponse.response must be type array"
    )


@_skip_exception
def test_exception_patch_declares_user_guid_path_param():
    """PATCH endpoint must declare userGuid as a required path parameter."""
    spec = _load(_EXCEPTION_SPEC)
    patch_path = "/permissions/exception-users/users/{userGuid}"
    params = _all_params(spec, patch_path, "patch")
    names = {p["name"] for p in params if "name" in p}
    assert "userGuid" in names, (
        f"PATCH {patch_path} must declare userGuid path parameter"
    )
    p = next(p for p in params if p.get("name") == "userGuid")
    assert p.get("in") == "path"
    assert p.get("required") is True


@_skip_exception
def test_exception_error_response_has_status_message_property():
    """ErrorResponse must declare statusMessage (not message) as confirmed by live testing.

    Live testing returned { "status": "FAILURE_BAD_HEADER", "statusMessage": "..." }.
    Apiary documented the field as 'message'; the confirmed name is 'statusMessage'.
    """
    spec = _load(_EXCEPTION_SPEC)
    props = (
        spec.get("components", {})
        .get("schemas", {})
        .get("ErrorResponse", {})
        .get("properties", {})
    )
    assert "statusMessage" in props, (
        "ErrorResponse must declare 'statusMessage' property "
        "(confirmed field name from live testing — Apiary used 'message')"
    )
    assert props["statusMessage"].get("type") == "string", (
        "ErrorResponse.statusMessage must be type string"
    )


# ─── Audit API ─────────────────────────────────────────────────────────────
# Delivers audit events (BYOK + user activity) for a tenant.
# Auth: AnaplanAuthToken (Apiary confirmed). Bearer declared but unconfirmed.
# Responses available in JSON or CEF (text/plain) via Accept header.
# Endpoints extracted from Apiary HTML descriptions — no structured resources[]
# existed in the Apiary source; spec paths were hand-authored from documentation.

_AUDIT_SPEC = REPO_ROOT / "audit" / "audit-openapi.json"
_skip_audit = _skip_if_missing("audit")


@_skip_audit
def test_audit_get_events_declares_type_param():
    """GET /events must declare the type query param with the confirmed enum values.

    The enum was expanded beyond the original three after live testing confirmed
    additional recognized values (issue #60); each maps to an eventTypeId prefix.
    """
    spec = _load(_AUDIT_SPEC)
    params = _all_params(spec, "/events", "get")
    names = {p["name"] for p in params if "name" in p}
    assert "type" in names, "GET /events must declare type query parameter"
    p = next(p for p in params if p.get("name") == "type")
    assert p.get("in") == "query"
    enum = p.get("schema", {}).get("enum")
    expected = {
        "all", "user_activity", "access_control", "int", "conn_mgmt",
        "comment", "byok", "plan_iq", "forecaster",
    }
    assert set(enum) == expected, f"type enum drifted from the confirmed set: {enum}"


@_skip_audit
def test_audit_get_events_declares_paging_params():
    """GET /events must declare limit and offset query parameters for pagination."""
    spec = _load(_AUDIT_SPEC)
    params = _all_params(spec, "/events", "get")
    names = {p["name"] for p in params if "name" in p}
    for param in ("limit", "offset"):
        assert param in names, f"GET /events must declare {param!r} query parameter"
    limit_p = next(p for p in params if p.get("name") == "limit")
    assert limit_p.get("in") == "query"
    assert limit_p.get("schema", {}).get("type") == "integer"
    # The documented 10000 cap is not enforced by the server (confirmed via live
    # testing, issue #60), so the spec must not declare a hard maximum the API
    # does not apply.
    assert "maximum" not in limit_p.get("schema", {}), (
        "limit must not declare a maximum — the documented 10000 cap is not "
        "enforced server-side (issue #60)"
    )


@_skip_audit
def test_audit_get_events_declares_date_range_params():
    """GET /events must declare dateFrom, dateTo, and intervalInHours query parameters."""
    spec = _load(_AUDIT_SPEC)
    params = _all_params(spec, "/events", "get")
    names = {p["name"] for p in params if "name" in p}
    for param in ("dateFrom", "dateTo", "intervalInHours"):
        assert param in names, f"GET /events must declare {param!r} query parameter"


@_skip_audit
@pytest.mark.parametrize(
    "method,path", [("get", "/events"), ("post", "/events/search")]
)
def test_audit_events_declare_400_response(method, path):
    """The events endpoints must document a 400 response with the error schema.

    The dateFrom/dateTo and intervalInHours/interval descriptions promise a 400
    (FAILURE_BAD_REQUEST) for a range over 30 days — confirmed via live testing —
    so the response must be declared (using AuditErrorResponse).
    """
    spec = _load(_AUDIT_SPEC)
    responses = spec["paths"][path][method]["responses"]
    assert "400" in responses, (
        f"audit {method.upper()} {path} must document a 400 response"
    )
    schema = (
        responses["400"].get("content", {}).get("application/json", {}).get("schema", {})
    )
    assert schema.get("$ref", "").endswith("/AuditErrorResponse"), (
        f"audit {method.upper()} {path} 400 must use the AuditErrorResponse schema"
    )


@_skip_audit
def test_audit_post_search_has_request_body():
    """POST /events/search must declare a JSON request body schema."""
    spec = _load(_AUDIT_SPEC)
    operation = spec.get("paths", {}).get("/events/search", {}).get("post", {})
    body = operation.get("requestBody", {})
    assert "application/json" in body.get("content", {}), (
        "POST /events/search must declare an application/json request body"
    )
    schema_ref = (
        body["content"]["application/json"].get("schema", {}).get("$ref", "")
    )
    assert schema_ref, "POST /events/search request body must reference a schema"


@_skip_audit
def test_audit_search_request_schema_has_time_range_fields():
    """AuditSearchRequest schema must have from, to, and interval fields."""
    spec = _load(_AUDIT_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    assert "AuditSearchRequest" in schemas, "AuditSearchRequest schema must be defined"
    props = schemas["AuditSearchRequest"].get("properties", {})
    for field in ("from", "to", "interval"):
        assert field in props, f"AuditSearchRequest must define {field!r} property"


@_skip_audit
@pytest.mark.parametrize("schema_name", ["AuditEvent", "AuditEventsResponse", "AuditPaging", "AuditSearchRequest"])
def test_audit_spec_has_required_schema(schema_name):
    """Core Audit API schemas must be defined in components/schemas."""
    spec = _load(_AUDIT_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    assert schema_name in schemas, (
        f"audit spec must define {schema_name!r} in components/schemas"
    )


@_skip_audit
def test_audit_event_schema_has_core_fields():
    """AuditEvent schema must include the fields present in every documented example."""
    spec = _load(_AUDIT_SPEC)
    schema = spec.get("components", {}).get("schemas", {}).get("AuditEvent", {})
    props = schema.get("properties", {})
    for field in ("id", "eventTypeId", "userId", "tenantId", "message", "eventDate", "checksum"):
        assert field in props, f"AuditEvent must define {field!r} property"


@_skip_audit
def test_audit_events_response_wraps_array_in_response_key():
    """AuditEventsResponse must wrap event array under a top-level 'response' key."""
    spec = _load(_AUDIT_SPEC)
    schema = spec.get("components", {}).get("schemas", {}).get("AuditEventsResponse", {})
    response_prop = schema.get("properties", {}).get("response", {})
    assert response_prop.get("type") == "array", (
        "AuditEventsResponse.response must be type array"
    )
    assert "response" in schema.get("required", []), (
        "AuditEventsResponse must mark 'response' as required"
    )


@_skip_audit
def test_audit_endpoints_declare_json_and_cef_responses():
    """Both audit endpoints must declare application/json and text/plain (CEF) response media types."""
    spec = _load(_AUDIT_SPEC)
    for path, method in (("/events", "get"), ("/events/search", "post")):
        operation = spec["paths"][path][method]
        content = operation["responses"]["200"]["content"]
        assert "application/json" in content, (
            f"{method.upper()} {path}: must declare application/json response"
        )
        assert "text/plain" in content, (
            f"{method.upper()} {path}: must declare text/plain (CEF) response"
        )


# ─── Financial Consolidation API ──────────────────────────────────────────
# Manages financial consolidation workflows via the Fluence acquisition.
# Host: fluenceapi-prod.fluence.app (different from all other Anaplan API hosts)
# Auth: X_API_TOKEN apiKey header + required TENANT header on every request.
# No regional variants known — single production endpoint only.

_FC_SPEC = REPO_ROOT / "financial-consolidation" / "financial-consolidation-openapi.json"
_skip_fc = _skip_if_missing("financial-consolidation")


@_skip_fc
def test_financial_consolidation_api_token_scheme_uses_x_api_token_header():
    """apiToken scheme must name X_API_TOKEN as the header (not Authorization or AnaplanAuthToken)."""
    spec = _load(_FC_SPEC)
    schemes = spec.get("components", {}).get("securitySchemes", {})
    api_token = schemes.get("apiToken", {})
    assert api_token.get("type") == "apiKey", "apiToken must be type: apiKey"
    assert api_token.get("in") == "header", "apiToken must be in: header"
    assert api_token.get("name") == "X_API_TOKEN", (
        "apiToken header must be named X_API_TOKEN (not Authorization or other)"
    )


@_skip_fc
def test_financial_consolidation_has_tenant_header_parameter():
    """components/parameters must define a reusable TenantHeader parameter."""
    spec = _load(_FC_SPEC)
    params = spec.get("components", {}).get("parameters", {})
    assert "TenantHeader" in params, (
        "financial-consolidation spec must define TenantHeader in components/parameters"
    )
    tenant = params["TenantHeader"]
    assert tenant.get("in") == "header", "TenantHeader must be in: header"
    assert tenant.get("name") == "TENANT", "TenantHeader header name must be TENANT"
    assert tenant.get("required") is True, "TenantHeader must be required: true"


@_skip_fc
def test_fc_odata_get_declares_page_and_pagesize_params():
    """GET /odata/{tableName} must declare Page and PageSize integer query parameters."""
    spec = _load(_FC_SPEC)
    params = _all_params(spec, "/odata/{tableName}", "get")
    names = {p["name"] for p in params if "name" in p}
    for param_name in ("Page", "PageSize"):
        assert param_name in names, (
            f"GET /odata/{{tableName}} must declare {param_name!r} query parameter"
        )
        p = next(p for p in params if p.get("name") == param_name)
        assert p.get("in") == "query"
        assert p.get("schema", {}).get("type") == "integer", (
            f"{param_name} must be type integer"
        )


@_skip_fc
def test_fc_odata_get_declares_200_json_response():
    """GET /odata/{tableName} must declare a 200 application/json response."""
    spec = _load(_FC_SPEC)
    op = spec["paths"]["/odata/{tableName}"]["get"]
    content = op.get("responses", {}).get("200", {}).get("content", {})
    assert "application/json" in content, (
        "GET /odata/{tableName} must declare application/json 200 response"
    )


@_skip_fc
@pytest.mark.parametrize("method,path", [
    pytest.param("post",   "/odata/{tableName}",       id="fc-odata-post-body"),
    pytest.param("post",   "/odata/batch/{tableName}", id="fc-odata-batch-body"),
    pytest.param("put",    "/odata/{tableName}",       id="fc-odata-put-body"),
    pytest.param("delete", "/odata/{tableName}",       id="fc-odata-delete-body"),
])
def test_fc_odata_mutating_operations_declare_request_body(method, path):
    """POST, PUT, and DELETE OData operations must declare an application/json request body."""
    spec = _load(_FC_SPEC)
    op = spec["paths"][path][method]
    body = op.get("requestBody", {})
    assert "application/json" in body.get("content", {}), (
        f"{method.upper()} {path} must declare an application/json request body"
    )


@_skip_fc
@pytest.mark.parametrize("method,path", [
    pytest.param("get",    "/odata/{tableName}",       id="fc-tenant-get"),
    pytest.param("post",   "/odata/{tableName}",       id="fc-tenant-post"),
    pytest.param("post",   "/odata/batch/{tableName}", id="fc-tenant-batch"),
    pytest.param("put",    "/odata/{tableName}",       id="fc-tenant-put"),
    pytest.param("delete", "/odata/{tableName}",       id="fc-tenant-delete"),
])
def test_fc_odata_operations_reference_tenant_header(method, path):
    """Every OData operation must reference the reusable TenantHeader component parameter."""
    spec = _load(_FC_SPEC)
    params = _all_params(spec, path, method)
    refs = [p.get("$ref", "") for p in params]
    assert "#/components/parameters/TenantHeader" in refs, (
        f"{method.upper()} {path} must reference #/components/parameters/TenantHeader"
    )


@_skip_fc
def test_fc_odata_record_schema_defined():
    """components/schemas must define ODataRecord for reuse across OData request/response bodies."""
    spec = _load(_FC_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    assert "ODataRecord" in schemas, (
        "financial-consolidation spec must define ODataRecord in components/schemas"
    )


@_skip_fc
@pytest.mark.parametrize("path", [
    pytest.param("/metadata/Dimensions",                          id="fc-meta-tenant"),
    pytest.param("/metadata/models/{modelName}/Dimensions",       id="fc-meta-model"),
    pytest.param("/metadata/Dimensions/{dimensionName}",          id="fc-meta-members"),
])
def test_fc_metadata_operations_reference_tenant_header(path):
    """Every metadata GET must reference the reusable TenantHeader component parameter."""
    spec = _load(_FC_SPEC)
    params = _all_params(spec, path, "get")
    refs = [p.get("$ref", "") for p in params]
    assert "#/components/parameters/TenantHeader" in refs, (
        f"GET {path} must reference #/components/parameters/TenantHeader"
    )


@_skip_fc
def test_fc_metadata_model_dimensions_declares_model_name_path_param():
    """GET /metadata/models/{modelName}/Dimensions must declare modelName as a required path parameter."""
    spec = _load(_FC_SPEC)
    path = "/metadata/models/{modelName}/Dimensions"
    params = _all_params(spec, path, "get")
    names = {p["name"] for p in params if "name" in p}
    assert "modelName" in names, f"GET {path} must declare modelName path parameter"
    p = next(p for p in params if p.get("name") == "modelName")
    assert p.get("in") == "path"
    assert p.get("required") is True


@_skip_fc
def test_fc_metadata_dimension_members_declares_dimension_name_path_param():
    """GET /metadata/Dimensions/{dimensionName} must declare dimensionName as a required path parameter."""
    spec = _load(_FC_SPEC)
    path = "/metadata/Dimensions/{dimensionName}"
    params = _all_params(spec, path, "get")
    names = {p["name"] for p in params if "name" in p}
    assert "dimensionName" in names, f"GET {path} must declare dimensionName path parameter"
    p = next(p for p in params if p.get("name") == "dimensionName")
    assert p.get("in") == "path"
    assert p.get("required") is True


@_skip_fc
def test_fc_metadata_dimension_members_declares_page_and_pagesize_params():
    """GET /metadata/Dimensions/{dimensionName} must declare Page and PageSize query parameters for pagination."""
    spec = _load(_FC_SPEC)
    path = "/metadata/Dimensions/{dimensionName}"
    params = _all_params(spec, path, "get")
    names = {p["name"] for p in params if "name" in p}
    for param_name in ("Page", "PageSize"):
        assert param_name in names, (
            f"GET {path} must declare {param_name!r} query parameter"
        )
        p = next(p for p in params if p.get("name") == param_name)
        assert p.get("in") == "query"
        assert p.get("schema", {}).get("type") == "number"


@_skip_fc
@pytest.mark.parametrize("schema_name", [
    "Dimension", "DimensionProperty", "DimensionMembersResponse", "DimensionMember",
])
def test_fc_metadata_schemas_defined(schema_name):
    """Metadata domain schemas must be defined in components/schemas."""
    spec = _load(_FC_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    assert schema_name in schemas, (
        f"financial-consolidation spec must define {schema_name!r} in components/schemas"
    )


@_skip_fc
def test_fc_dimension_schema_has_core_fields():
    """Dimension schema must include the fields present in the documented response example."""
    spec = _load(_FC_SPEC)
    schema = spec.get("components", {}).get("schemas", {}).get("Dimension", {})
    props = schema.get("properties", {})
    for field in ("dimensionName", "properties", "processingStatus"):
        assert field in props, f"Dimension schema must define {field!r} property"


@_skip_fc
@pytest.mark.parametrize("path,method", [
    pytest.param("/process/start/{path}/{name_of_workflow}", "post", id="fc-wf-start-tenant"),
    pytest.param("/process/stop/{path}/{name_of_workflow}",  "post", id="fc-wf-stop-tenant"),
    pytest.param("/process/state/{path}/{name_of_workflow}", "get",  id="fc-wf-state-tenant"),
])
def test_fc_workflow_operations_reference_tenant_header(path, method):
    """Every workflow operation must reference the reusable TenantHeader component parameter."""
    spec = _load(_FC_SPEC)
    params = _all_params(spec, path, method)
    refs = [p.get("$ref", "") for p in params]
    assert "#/components/parameters/TenantHeader" in refs, (
        f"{method.upper()} {path} must reference #/components/parameters/TenantHeader"
    )


@_skip_fc
@pytest.mark.parametrize("path,method", [
    pytest.param("/process/start/{path}/{name_of_workflow}", "post", id="fc-wf-start-pathparams"),
    pytest.param("/process/stop/{path}/{name_of_workflow}",  "post", id="fc-wf-stop-pathparams"),
    pytest.param("/process/state/{path}/{name_of_workflow}", "get",  id="fc-wf-state-pathparams"),
])
def test_fc_workflow_operations_declare_path_and_name_params(path, method):
    """Every workflow operation must declare `path` and `name_of_workflow` as required path parameters."""
    spec = _load(_FC_SPEC)
    params = _all_params(spec, path, method)
    named = {p["name"]: p for p in params if "name" in p}
    for param_name in ("path", "name_of_workflow"):
        assert param_name in named, (
            f"{method.upper()} {path} must declare {param_name!r} path parameter"
        )
        p = named[param_name]
        assert p.get("in") == "path"
        assert p.get("required") is True


@_skip_fc
def test_fc_workflow_start_declares_request_body():
    """POST /process/start must declare an application/json request body for workflow parameters."""
    spec = _load(_FC_SPEC)
    op = spec["paths"]["/process/start/{path}/{name_of_workflow}"]["post"]
    body = op.get("requestBody", {})
    assert "application/json" in body.get("content", {}), (
        "POST /process/start/{path}/{name_of_workflow} must declare an application/json request body"
    )


@_skip_fc
def test_fc_workflow_state_response_schema_has_run_id():
    """GET /process/state 200 response must reference a schema containing runId."""
    spec = _load(_FC_SPEC)
    op = spec["paths"]["/process/state/{path}/{name_of_workflow}"]["get"]
    content = op["responses"]["200"]["content"]
    assert "application/json" in content, (
        "GET /process/state/{path}/{name_of_workflow} must declare application/json 200 response"
    )
    schema_ref = content["application/json"].get("schema", {}).get("$ref", "")
    assert schema_ref, (
        "GET /process/state/{path}/{name_of_workflow} 200 response must reference a schema"
    )
    schema_name = schema_ref.split("/")[-1]
    schemas = spec.get("components", {}).get("schemas", {})
    assert schema_name in schemas, f"Referenced schema {schema_name!r} must exist in components/schemas"
    props = schemas[schema_name].get("properties", {})
    assert "runId" in props, f"{schema_name} must define a runId property"


@_skip_fc
def test_fc_dimension_members_response_has_pagination_fields():
    """DimensionMembersResponse schema must include pagination envelope fields."""
    spec = _load(_FC_SPEC)
    schema = spec.get("components", {}).get("schemas", {}).get("DimensionMembersResponse", {})
    props = schema.get("properties", {})
    for field in ("dimensionMembers", "totalRows", "currentPage", "totalPages"):
        assert field in props, f"DimensionMembersResponse schema must define {field!r} property"


# ─── Financial Consolidation API — User Management ────────────────────────

@_skip_fc
@pytest.mark.parametrize("schema_name", ["User", "UserInput"])
def test_fc_user_management_schemas_defined(schema_name):
    """User management domain schemas must be defined in components/schemas."""
    spec = _load(_FC_SPEC)
    schemas = spec.get("components", {}).get("schemas", {})
    assert schema_name in schemas, (
        f"financial-consolidation spec must define {schema_name!r} in components/schemas"
    )


@_skip_fc
def test_fc_user_schema_has_core_fields():
    """User schema must include all fields present in the documented GET /users response."""
    spec = _load(_FC_SPEC)
    schema = spec.get("components", {}).get("schemas", {}).get("User", {})
    props = schema.get("properties", {})
    for field in ("userId", "userName", "fullName", "isDisabled", "email", "roles"):
        assert field in props, f"User schema must define {field!r} property"


@_skip_fc
@pytest.mark.parametrize("path,method", [
    pytest.param("/users",                 "get",    id="fc-users-list-tenant"),
    pytest.param("/users",                 "post",   id="fc-users-add-tenant"),
    pytest.param("/users",                 "put",    id="fc-users-update-tenant"),
    pytest.param("/users/{username}",      "delete", id="fc-users-delete-tenant"),
    pytest.param("/user/{username}/roles", "get",    id="fc-user-roles-list-tenant"),
    pytest.param("/user/{username}/roles", "put",    id="fc-user-roles-assign-tenant"),
    pytest.param("/user/{username}/roles", "delete", id="fc-user-roles-unassign-tenant"),
])
def test_fc_user_management_operations_reference_tenant_header(path, method):
    """Every user management operation must reference the reusable TenantHeader component parameter."""
    spec = _load(_FC_SPEC)
    params = _all_params(spec, path, method)
    refs = [p.get("$ref", "") for p in params]
    assert "#/components/parameters/TenantHeader" in refs, (
        f"{method.upper()} {path} must reference #/components/parameters/TenantHeader"
    )


@_skip_fc
@pytest.mark.parametrize("path", [
    pytest.param("/users/{username}",      id="fc-users-username-param"),
    pytest.param("/user/{username}/roles", id="fc-user-roles-username-param"),
])
def test_fc_user_management_declares_username_path_param(path):
    """Endpoints with {username} in path must declare it as a required path parameter."""
    spec = _load(_FC_SPEC)
    all_methods = [m for m in _HTTP_METHODS if m in spec.get("paths", {}).get(path, {})]
    assert all_methods, f"No operations found for path {path!r}"
    for method in all_methods:
        params = _all_params(spec, path, method)
        names = {p["name"]: p for p in params if "name" in p}
        assert "username" in names, (
            f"{method.upper()} {path} must declare username path parameter"
        )
        p = names["username"]
        assert p.get("in") == "path"
        assert p.get("required") is True
