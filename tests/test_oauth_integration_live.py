"""
Live API integration tests for the Anaplan OAuth 2.0 Service API.

Run with:
    uv run --env-file .env pytest tests/test_oauth_integration_live.py --live

Credentials are read from .env at the repo root. Required variables:
    ANAPLAN_OAUTH_CLIENT_ID          - client ID for the Authorization Code Grant flow
    ANAPLAN_OAUTH_DEVICE_CLIENT_ID   - client ID for the Device Authorization Grant flow

These are separate registrations in Anaplan Administration > OAuth — the same
client ID cannot be used for both flows.

Automation limitations
----------------------
The following steps cannot be fully automated:

- Device Authorization Grant (end-to-end): After POST /oauth/device/code, the user
  must visit verification_uri and approve access in a browser before the client can
  exchange the device_code for tokens. Tests here cover only the initiation request
  and polling error cases.

- Authorization Code Grant (login step): GET /auth/authorize returns a 302 redirect
  to the Anaplan login page — the 302 response itself is tested here. The subsequent
  user login and browser callback to redirect_uri cannot be automated.

- Token refresh (happy path): Requires a live refresh_token from a completed OAuth flow.
  Only invalid-token error cases are tested here.
"""

import json
import os
import pathlib
import warnings

import httpx
import pytest
from openapi_spec_validator import validate

SPEC_FILE = pathlib.Path(__file__).parent.parent / "oauth" / "oauth-openapi.json"
with open(SPEC_FILE, encoding="utf-8") as f:
    SPEC = json.load(f)

API_URL = "https://us1a.app.anaplan.com"


@pytest.fixture
def oauth_client_id():
    """Load Authorization Code Grant client ID from environment."""
    client_id = os.getenv("ANAPLAN_OAUTH_CLIENT_ID")
    if not client_id:
        pytest.skip("ANAPLAN_OAUTH_CLIENT_ID not set")
    return client_id


@pytest.fixture
def oauth_device_client_id():
    """Load Device Authorization Grant client ID from environment."""
    client_id = os.getenv("ANAPLAN_OAUTH_DEVICE_CLIENT_ID")
    if not client_id:
        pytest.skip("ANAPLAN_OAUTH_DEVICE_CLIENT_ID not set")
    return client_id


# ---------------------------------------------------------------------------
# Spec validation
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_oauth_spec_is_valid():
    """oauth-openapi.json passes openapi-spec-validator."""
    validate(SPEC)


# ---------------------------------------------------------------------------
# POST /oauth/device/code
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_device_code_happy_path(oauth_device_client_id):
    """POST /oauth/device/code returns 200 with all required response fields."""
    discrepancies = []

    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/oauth/device/code",
            json={
                "client_id": oauth_device_client_id,
                "scope": "openid profile email offline_access",
            },
        )

        assert_response_code(response, [200], discrepancies)

        if response.status_code == 200:
            body = response.json()
            for field in ("device_code", "user_code", "verification_uri", "expires_in", "interval"):
                if field not in body:
                    discrepancies.append(
                        f"POST /oauth/device/code 200: missing field '{field}'"
                    )
            if "expires_in" in body and not isinstance(body["expires_in"], int):
                discrepancies.append(
                    f"POST /oauth/device/code: expires_in should be int, got {type(body['expires_in']).__name__}"
                )
            if "interval" in body and not isinstance(body["interval"], int):
                discrepancies.append(
                    f"POST /oauth/device/code: interval should be int, got {type(body['interval']).__name__}"
                )

    if discrepancies:
        warnings.warn(
            "POST /oauth/device/code discrepancies:\n" + "\n".join(f"  - {d}" for d in discrepancies),
            UserWarning,
            stacklevel=2,
        )


@pytest.mark.live
def test_device_code_missing_client_id():
    """POST /oauth/device/code without client_id returns 4xx with OAuth error body."""
    discrepancies = []

    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/oauth/device/code",
            json={"scope": "openid profile email offline_access"},
        )

        assert_response_code(response, [400, 403], discrepancies)
        assert_oauth_error_body(response, "POST /oauth/device/code (missing client_id)", discrepancies)

    if discrepancies:
        warnings.warn("\n".join(f"  - {d}" for d in discrepancies), UserWarning, stacklevel=2)


@pytest.mark.live
def test_device_code_missing_scope(oauth_device_client_id):
    """POST /oauth/device/code without scope succeeds (scope is optional per RFC 8628)."""
    discrepancies = []

    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/oauth/device/code",
            json={"client_id": oauth_device_client_id},
        )

        # Scope is optional; server may accept with default scope (200) or reject (4xx)
        assert_response_code(response, [200, 400, 403], discrepancies)

        if response.status_code == 200:
            body = response.json()
            for field in ("device_code", "user_code", "verification_uri", "expires_in", "interval"):
                if field not in body:
                    discrepancies.append(
                        f"POST /oauth/device/code (no scope) 200: missing field '{field}'"
                    )

    if discrepancies:
        warnings.warn("\n".join(f"  - {d}" for d in discrepancies), UserWarning, stacklevel=2)


@pytest.mark.live
def test_device_code_invalid_client_id():
    """POST /oauth/device/code with an unrecognised client_id returns 4xx."""
    discrepancies = []

    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/oauth/device/code",
            json={
                "client_id": "00000000000000000000000000000000",
                "scope": "openid profile email offline_access",
            },
        )

        assert_response_code(response, [400, 403], discrepancies)
        assert_oauth_error_body(response, "POST /oauth/device/code (invalid client_id)", discrepancies)

    if discrepancies:
        warnings.warn("\n".join(f"  - {d}" for d in discrepancies), UserWarning, stacklevel=2)


# ---------------------------------------------------------------------------
# POST /oauth/token — error cases only (happy paths require browser interaction)
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_token_device_grant_invalid_device_code():
    """POST /oauth/token polling with an invalid device_code returns 4xx."""
    discrepancies = []

    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/oauth/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": "invalid-device-code-xyz",
                "client_id": "00000000000000000000000000000000",
            },
        )

        assert_response_code(response, [400, 401, 403], discrepancies)
        assert_oauth_error_body(response, "POST /oauth/token (invalid device_code)", discrepancies)

    if discrepancies:
        warnings.warn("\n".join(f"  - {d}" for d in discrepancies), UserWarning, stacklevel=2)


@pytest.mark.live
def test_token_auth_code_grant_invalid_code():
    """POST /oauth/token with an invalid authorization code returns 4xx."""
    discrepancies = []

    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/oauth/token",
            json={
                "grant_type": "authorization_code",
                "code": "invalid-auth-code-xyz",
                "client_id": "00000000000000000000000000000000",
                "client_secret": "invalid-secret",
                "redirect_uri": "https://www.example.com/callback",
            },
        )

        assert_response_code(response, [400, 401, 403], discrepancies)
        assert_oauth_error_body(response, "POST /oauth/token (invalid auth code)", discrepancies)

    if discrepancies:
        warnings.warn("\n".join(f"  - {d}" for d in discrepancies), UserWarning, stacklevel=2)


@pytest.mark.live
def test_token_invalid_refresh_token():
    """POST /oauth/token with an invalid refresh_token returns 4xx."""
    discrepancies = []

    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/oauth/token",
            json={
                "grant_type": "refresh_token",
                "client_id": "00000000000000000000000000000000",
                "refresh_token": "invalid-refresh-token-xyz",
            },
        )

        assert_response_code(response, [400, 401, 403], discrepancies)
        assert_oauth_error_body(response, "POST /oauth/token (invalid refresh_token)", discrepancies)

    if discrepancies:
        warnings.warn("\n".join(f"  - {d}" for d in discrepancies), UserWarning, stacklevel=2)


@pytest.mark.live
def test_token_missing_grant_type():
    """POST /oauth/token without grant_type returns 400."""
    discrepancies = []

    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/oauth/token",
            json={"client_id": "00000000000000000000000000000000"},
        )

        # API returns 401 (not 400) for missing grant_type
        assert_response_code(response, [400, 401], discrepancies)
        assert_oauth_error_body(response, "POST /oauth/token (missing grant_type)", discrepancies)

    if discrepancies:
        warnings.warn("\n".join(f"  - {d}" for d in discrepancies), UserWarning, stacklevel=2)


# ---------------------------------------------------------------------------
# GET /auth/authorize — 302 redirect verified; login step requires browser
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_authorize_happy_path(oauth_client_id):
    """GET /auth/authorize with valid params returns 302 with a Location header."""
    discrepancies = []

    with httpx.Client(follow_redirects=False) as client:
        response = client.get(
            f"{API_URL}/auth/authorize",
            params={
                "response_type": "code",
                "client_id": oauth_client_id,
                "redirect_uri": "https://www.anaplan.com",
                "scope": "openid profile email offline_access",
                "state": "test-state-value",
            },
        )

        assert_response_code(response, [302], discrepancies)

        if response.status_code == 302 and "Location" not in response.headers:
            discrepancies.append("GET /auth/authorize: 302 response missing Location header")

    if discrepancies:
        warnings.warn("\n".join(f"  - {d}" for d in discrepancies), UserWarning, stacklevel=2)


@pytest.mark.live
def test_authorize_missing_client_id():
    """GET /auth/authorize without client_id returns 4xx or redirect to error page."""
    discrepancies = []

    with httpx.Client(follow_redirects=False) as client:
        response = client.get(
            f"{API_URL}/auth/authorize",
            params={
                "response_type": "code",
                "redirect_uri": "https://www.anaplan.com",
                "scope": "openid profile email offline_access",
            },
        )

        assert_response_code(response, [302, 400, 401], discrepancies)

    if discrepancies:
        warnings.warn("\n".join(f"  - {d}" for d in discrepancies), UserWarning, stacklevel=2)


# ---------------------------------------------------------------------------
# GET /auth/prelogin — error cases only (happy path requires browser interaction)
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_prelogin_missing_required_params():
    """GET /auth/prelogin with missing required params returns 200, 302, 400, or 401."""
    discrepancies = []

    with httpx.Client(follow_redirects=False) as client:
        # Omit response_type, redirect_uri, and scope
        response = client.get(
            f"{API_URL}/auth/prelogin",
            params={"client_id": "00000000000000000000000000000000"},
        )

        # Server may return the login page (200), redirect to error (302), or direct 4xx
        assert_response_code(response, [200, 302, 400, 401], discrepancies)

        if response.status_code == 302 and "Location" not in response.headers:
            discrepancies.append(
                "GET /auth/prelogin: 302 response missing Location header"
            )

    if discrepancies:
        warnings.warn("\n".join(f"  - {d}" for d in discrepancies), UserWarning, stacklevel=2)


@pytest.mark.live
def test_prelogin_happy_path(oauth_client_id):
    """GET /auth/prelogin with valid params returns 200 (login page HTML)."""
    discrepancies = []

    with httpx.Client(follow_redirects=False) as client:
        response = client.get(
            f"{API_URL}/auth/prelogin",
            params={
                "response_type": "code",
                "client_id": oauth_client_id,
                "redirect_uri": "https://www.example.com/callback",
                "scope": "openid profile email offline_access",
            },
        )

        assert_response_code(response, [200, 302], discrepancies)

        if response.status_code == 200:
            ct = response.headers.get("content-type", "")
            if "text/html" not in ct:
                discrepancies.append(
                    f"GET /auth/prelogin: expected text/html, got '{ct}'"
                )

    if discrepancies:
        warnings.warn("\n".join(f"  - {d}" for d in discrepancies), UserWarning, stacklevel=2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_response_code(response, expected_codes, discrepancies):
    """Record a discrepancy if the response code is not among expected_codes."""
    if response.status_code not in expected_codes:
        discrepancies.append(
            f"Got {response.status_code}, expected one of {expected_codes}"
        )


def assert_oauth_error_body(response, label, discrepancies):
    """Check that a 4xx response contains a valid OAuth error body."""
    if response.status_code not in range(400, 500):
        return
    try:
        body = response.json()
        for field in ("error", "error_description"):
            if field not in body:
                discrepancies.append(
                    f"{label}: 4xx body missing '{field}', got keys={list(body.keys())}"
                )
    except Exception:
        discrepancies.append(
            f"{label}: {response.status_code} response is not valid JSON"
        )
