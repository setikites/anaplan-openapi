"""
Contract tests verifying OpenAPI 3.0 spec files against domain invariants
from CONTEXT.md. These tests run without network access.

Invariants checked:
  Universal   — version, info, servers[], paths, responses, refs, security
  Server URLs — each API family must use its correct host pattern
  Auth API    — BasicAuth + AnaplanAuthToken schemes; core endpoints present
  OAuth API   — core endpoints present; TokenResponse schema complete
  Integration — AnaplanAuthToken scheme declared (skipped until spec exists)
  SCIM        — BearerAuth scheme declared (skipped until spec exists)
"""

import json
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

@pytest.mark.skipif(
    not (REPO_ROOT / "integration" / "integration-openapi.json").exists(),
    reason="integration spec not yet written",
)
def test_integration_spec_declares_anaplan_token_scheme():
    """Integration API uses AnaplanAuthToken — must be declared as a securityScheme."""
    spec = _load(REPO_ROOT / "integration" / "integration-openapi.json")
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


# ─── SCIM API ──────────────────────────────────────────────────────────────
# SCIM is a standard (RFC 7644) and uses Bearer token authentication.

@pytest.mark.skipif(
    not (REPO_ROOT / "scim" / "scim-openapi.json").exists(),
    reason="scim spec not yet written",
)
def test_scim_spec_declares_bearer_auth():
    """SCIM uses standard Bearer token auth per RFC 7644 — must be declared."""
    spec = _load(REPO_ROOT / "scim" / "scim-openapi.json")
    schemes = spec.get("components", {}).get("securitySchemes", {})
    bearer = [
        name for name, d in schemes.items()
        if d.get("type") == "http" and d.get("scheme") == "bearer"
    ]
    assert bearer, (
        "scim spec must declare a Bearer security scheme (type: http, scheme: bearer)"
    )
