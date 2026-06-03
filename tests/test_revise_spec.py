"""Tests for revise_spec.py (issue #23)."""

import pytest
from revise_spec import revise_spec


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minimal_spec(**overrides):
    base = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {},
    }
    base.update(overrides)
    return base


# ── Fixtures ──────────────────────────────────────────────────────────────────

BEARER_SCHEME = {"BearerAuth": {"type": "http", "scheme": "bearer"}}
BASIC_SCHEME = {"BasicAuth": {"type": "http", "scheme": "basic"}}
APIKEY_SCHEME = {"AnaplanAuthToken": {"type": "apiKey", "in": "header", "name": "Authorization"}}

AUTH_HEADER_PARAM = {"name": "Authorization", "in": "header", "schema": {"type": "string"}}
CUSTOM_HEADER_PARAM = {"name": "X-Custom-Header", "in": "header", "schema": {"type": "string"}}
QUERY_PARAM = {"name": "limit", "in": "query", "schema": {"type": "integer"}}


# ── Behavior 1: tracer bullet ─────────────────────────────────────────────────

def test_spec_with_no_schemes_and_no_params_returns_dict_and_list():
    spec = _minimal_spec()
    result, summary = revise_spec(spec)
    assert isinstance(result, dict)
    assert isinstance(summary, list)


# ── Behavior 2: Authorization param removed for http bearer scheme ─────────────

def test_authorization_header_param_removed_for_bearer_scheme():
    spec = _minimal_spec(
        components={"securitySchemes": BEARER_SCHEME},
        paths={"/items": {"get": {"parameters": [AUTH_HEADER_PARAM], "responses": {"200": {"description": "ok"}}}}},
    )
    result, summary = revise_spec(spec)
    assert result["paths"]["/items"]["get"]["parameters"] == []
    assert any("Authorization" in line for line in summary)


# ── Behavior 3: Authorization param removed for http basic scheme ──────────────

def test_authorization_header_param_removed_for_basic_scheme():
    spec = _minimal_spec(
        components={"securitySchemes": BASIC_SCHEME},
        paths={"/items": {"get": {"parameters": [AUTH_HEADER_PARAM], "responses": {"200": {"description": "ok"}}}}},
    )
    result, _ = revise_spec(spec)
    assert result["paths"]["/items"]["get"]["parameters"] == []


# ── Behavior 4: apiKey in-header scheme name removed ──────────────────────────

def test_apikey_header_param_removed_when_scheme_covers_it():
    spec = _minimal_spec(
        components={"securitySchemes": APIKEY_SCHEME},
        paths={"/items": {"get": {"parameters": [AUTH_HEADER_PARAM], "responses": {"200": {"description": "ok"}}}}},
    )
    result, _ = revise_spec(spec)
    assert result["paths"]["/items"]["get"]["parameters"] == []


# ── Behavior 5: $ref to redundant header component is removed ─────────────────

def test_ref_param_removed_when_resolved_target_is_redundant_header():
    spec = _minimal_spec(
        components={
            "securitySchemes": BEARER_SCHEME,
            "parameters": {"AuthHeader": AUTH_HEADER_PARAM},
        },
        paths={"/items": {"get": {
            "parameters": [{"$ref": "#/components/parameters/AuthHeader"}],
            "responses": {"200": {"description": "ok"}},
        }}},
    )
    result, summary = revise_spec(spec)
    assert result["paths"]["/items"]["get"]["parameters"] == []
    assert "AuthHeader" in result["components"]["parameters"]  # component kept


# ── Behavior 6: non-redundant header param is preserved ───────────────────────

def test_unrelated_header_param_is_not_removed():
    spec = _minimal_spec(
        components={"securitySchemes": BEARER_SCHEME},
        paths={"/items": {"get": {
            "parameters": [CUSTOM_HEADER_PARAM, QUERY_PARAM],
            "responses": {"200": {"description": "ok"}},
        }}},
    )
    result, summary = revise_spec(spec)
    assert result["paths"]["/items"]["get"]["parameters"] == [CUSTOM_HEADER_PARAM, QUERY_PARAM]
    assert not any("Removed" in line for line in summary)


# ── Behavior 7: root security array rebuilt from all securitySchemes ───────────

def test_root_security_array_rebuilt_from_all_schemes():
    all_schemes = {**BEARER_SCHEME, **APIKEY_SCHEME}
    spec = _minimal_spec(components={"securitySchemes": all_schemes})
    result, summary = revise_spec(spec)
    assert result["security"] == [{"BearerAuth": []}, {"AnaplanAuthToken": []}]
    assert any("security" in line.lower() for line in summary)


def test_root_security_array_created_when_absent():
    spec = _minimal_spec(components={"securitySchemes": BEARER_SCHEME})
    result, summary = revise_spec(spec)
    assert result["security"] == [{"BearerAuth": []}]


def test_root_security_set_to_empty_when_no_schemes():
    spec = _minimal_spec()
    result, summary = revise_spec(spec)
    assert result["security"] == []
    assert any("security" in line.lower() for line in summary)


def test_root_security_empty_already_produces_no_summary():
    spec = _minimal_spec(security=[])
    result, summary = revise_spec(spec)
    assert result["security"] == []
    assert not any("security" in line.lower() for line in summary)


# ── Behavior 8: most-common op security promoted to root; minority override kept

ANAPLANAPIKEY_SCHEME = {"AnaplanAuth": {"type": "apiKey", "in": "header", "name": "Authorization"}}
CACERT_SCHEME = {"CACertAuth": {"type": "apiKey", "in": "header", "name": "Authorization"}}


def test_most_common_op_security_promoted_to_root():
    """Authentication API case: AnaplanAuth on 3 paths, BasicAuth+CACertAuth on 1."""
    all_schemes = {**ANAPLANAPIKEY_SCHEME, **BASIC_SCHEME, **CACERT_SCHEME}
    spec = _minimal_spec(
        components={"securitySchemes": all_schemes},
        paths={
            "/token/authenticate": {"post": {
                "security": [{"BasicAuth": []}, {"CACertAuth": []}],
                "responses": {"200": {"description": "ok"}},
            }},
            "/token/refresh": {"post": {
                "security": [{"AnaplanAuth": []}],
                "responses": {"200": {"description": "ok"}},
            }},
            "/token/validate": {"get": {
                "security": [{"AnaplanAuth": []}],
                "responses": {"200": {"description": "ok"}},
            }},
            "/token/logout": {"post": {
                "security": [{"AnaplanAuth": []}],
                "responses": {"200": {"description": "ok"}},
            }},
        },
    )
    result, summary = revise_spec(spec)
    assert result["security"] == [{"AnaplanAuth": []}]
    assert result["paths"]["/token/authenticate"]["post"]["security"] == [{"BasicAuth": []}, {"CACertAuth": []}]
    assert "security" not in result["paths"]["/token/refresh"]["post"]
    assert "security" not in result["paths"]["/token/validate"]["get"]
    assert "security" not in result["paths"]["/token/logout"]["post"]


def test_tie_in_op_security_leaves_root_unchanged():
    spec = _minimal_spec(
        components={"securitySchemes": {**BEARER_SCHEME, **BASIC_SCHEME}},
        paths={
            "/a": {"get": {"security": [{"BearerAuth": []}], "responses": {"200": {"description": "ok"}}}},
            "/b": {"get": {"security": [{"BasicAuth": []}], "responses": {"200": {"description": "ok"}}}},
        },
    )
    result, _ = revise_spec(spec)
    assert "security" not in result
    assert result["paths"]["/a"]["get"]["security"] == [{"BearerAuth": []}]
    assert result["paths"]["/b"]["get"]["security"] == [{"BasicAuth": []}]


def test_revise_spec_is_idempotent():
    """Running revise_spec twice produces the same result as running it once."""
    all_schemes = {**ANAPLANAPIKEY_SCHEME, **BASIC_SCHEME, **CACERT_SCHEME}
    spec = _minimal_spec(
        components={"securitySchemes": all_schemes},
        paths={
            "/token/authenticate": {"post": {
                "security": [{"BasicAuth": []}, {"CACertAuth": []}],
                "responses": {"200": {"description": "ok"}},
            }},
            "/token/refresh": {"post": {
                "security": [{"AnaplanAuth": []}],
                "responses": {"200": {"description": "ok"}},
            }},
            "/token/validate": {"get": {
                "security": [{"AnaplanAuth": []}],
                "responses": {"200": {"description": "ok"}},
            }},
            "/token/logout": {"post": {
                "security": [{"AnaplanAuth": []}],
                "responses": {"200": {"description": "ok"}},
            }},
        },
    )
    once, _ = revise_spec(spec)
    twice, summary2 = revise_spec(once)
    assert twice == once
    assert summary2 == []


def test_minority_op_security_override_preserved_after_promotion():
    """After majority is promoted to root, the minority operation keeps its override."""
    all_schemes = {**BEARER_SCHEME, **BASIC_SCHEME}
    spec = _minimal_spec(
        components={"securitySchemes": all_schemes},
        paths={
            "/a": {"get": {"security": [{"BearerAuth": []}], "responses": {"200": {"description": "ok"}}}},
            "/b": {"get": {"security": [{"BearerAuth": []}], "responses": {"200": {"description": "ok"}}}},
            "/login": {"post": {"security": [{"BasicAuth": []}], "responses": {"200": {"description": "ok"}}}},
        },
    )
    result, _ = revise_spec(spec)
    assert result["security"] == [{"BearerAuth": []}]
    assert "security" not in result["paths"]["/a"]["get"]
    assert "security" not in result["paths"]["/b"]["get"]
    assert result["paths"]["/login"]["post"]["security"] == [{"BasicAuth": []}]


# ── Behavior 9: path-level parameters cleaned ─────────────────────────────────

def test_path_level_authorization_param_removed():
    spec = _minimal_spec(
        components={"securitySchemes": BEARER_SCHEME},
        paths={"/items": {
            "parameters": [AUTH_HEADER_PARAM],
            "get": {"responses": {"200": {"description": "ok"}}},
        }},
    )
    result, summary = revise_spec(spec)
    assert result["paths"]["/items"]["parameters"] == []
    assert any("/items" in line for line in summary)


# ── Behavior 10: redundant per-operation security removed if it matches root ──

def test_operation_security_matching_root_is_removed():
    spec = _minimal_spec(
        components={"securitySchemes": BEARER_SCHEME},
        paths={"/items": {"get": {
            "security": [{"BearerAuth": []}],
            "responses": {"200": {"description": "ok"}},
        }}},
    )
    result, summary = revise_spec(spec)
    assert "security" not in result["paths"]["/items"]["get"]
    assert any("security" in line.lower() for line in summary)


def test_operation_security_opt_out_not_removed_even_if_other_ops_match():
    spec = _minimal_spec(
        components={"securitySchemes": BEARER_SCHEME},
        paths={
            "/items": {"get": {
                "security": [{"BearerAuth": []}],
                "responses": {"200": {"description": "ok"}},
            }},
            "/public": {"get": {
                "security": [],
                "responses": {"200": {"description": "ok"}},
            }},
        },
    )
    result, _ = revise_spec(spec)
    assert result["paths"]["/public"]["get"]["security"] == []
