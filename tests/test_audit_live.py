"""
Live API integration tests for the Anaplan Audit API.

Probes the GET /events and POST /events/search endpoints to verify that:
- The spec's documented paths and response shapes match the real API.
- The AnaplanAuthToken security scheme is accepted.
- The type query parameter and paging parameters work as documented.
- The Accept: text/plain header returns CEF-format output.

**Confirmed behavior (live testing 2026-06-08):**
- The Audit API returns 401 with {"status":"FAILURE_UNAUTHORIZED_USER_ACTION"}
  when the user lacks the Tenant Auditor role. This is non-standard HTTP
  semantics (401 is normally "unauthenticated", not "unauthorized"), but it
  is the real API's behavior. The token IS accepted; 401 here means missing role.

Run with:
    uv run --env-file .env pytest tests/test_audit_live.py --live

Credentials are read from .env at the repo root. Required variables:
    ANAPLAN_USERNAME  - username for basic auth (to obtain AnaplanAuthToken)
    ANAPLAN_PASSWORD  - password for basic auth

Optional variables:
    ANAPLAN_AUDIT_BASE_URL        - override audit base URL
                                    (default: https://audit.anaplan.com/audit/api/1)
    ANAPLAN_OAUTH_KEYRING_SERVICE - keyring service holding an OAuth token blob from
                                    the Authorization Code grant (default:
                                    anaplan-oauth-authcode). When a token is stored
                                    there (via scripts/oauth/oauth_authcode.py),
                                    its access_token is used as the bearer instead of
                                    basic auth — required to exercise the Tenant
                                    Auditor role over the OAuth path (issue #58).
"""

import base64
import json
import os
import pathlib
import warnings

import httpx
import pytest

from oauth.token_keyring import load_token

AUDIT_BASE_URL = os.getenv(
    "ANAPLAN_AUDIT_BASE_URL", "https://audit.anaplan.com/audit/api/1"
)
AUTH_URL = "https://auth.anaplan.com"
SPEC_PATH = pathlib.Path(__file__).parent.parent / "audit" / "audit-openapi.json"

_NO_ROLE_STATUS = "FAILURE_UNAUTHORIZED_USER_ACTION"

# Generous read timeout: an unfiltered GET /events pulls an unbounded result set
# that can exceed httpx's 5s default, producing flaky ReadTimeouts unrelated to
# the behavior under test. Applied to every client in this module.
_REQUEST_TIMEOUT = httpx.Timeout(30.0)


def _get_anaplan_token(username: str, password: str) -> str | None:
    """Authenticate via Basic auth and return an AnaplanAuthToken value."""
    auth_b64 = base64.b64encode(f"{username}:{password}".encode()).decode()
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        response = client.post(
            f"{AUTH_URL}/token/authenticate",
            headers={"Authorization": f"Basic {auth_b64}"},
        )
    if response.status_code == 201:
        return response.json().get("tokenInfo", {}).get("tokenValue")
    return None


def _get_oauth_access_token() -> str | None:
    """Return the access_token from the OAuth token blob in the keyring, if any.

    The Authorization Code grant helper scripts store the full token response under
    ANAPLAN_OAUTH_KEYRING_SERVICE. Anaplan accepts an OAuth access_token under the
    same ``AnaplanAuthToken`` Authorization scheme as a basic-auth token.
    """
    service = os.getenv("ANAPLAN_OAUTH_KEYRING_SERVICE", "anaplan-oauth-authcode")
    blob = load_token(service)
    if not blob:
        return None
    try:
        return json.loads(blob).get("access_token")
    except (ValueError, AttributeError):
        return None


def _is_no_role_401(response: httpx.Response) -> bool:
    """Return True when a 401 means 'token valid, user lacks Tenant Auditor role'.

    The Audit API uses 401 (not 403) for authorization failures. The status
    field FAILURE_UNAUTHORIZED_USER_ACTION distinguishes this from a genuinely
    rejected token, which would return a different error body or a 4xx from the
    auth layer before the application logic runs.
    """
    if response.status_code != 401:
        return False
    try:
        return response.json().get("status") == _NO_ROLE_STATUS
    except Exception:
        return False


@pytest.fixture(scope="module")
def audit_token():
    """Bearer token for audit calls (module-scoped).

    Prefers an OAuth access_token from the keyring (Authorization Code grant, the
    path that can carry the Tenant Auditor role — issue #58). Falls back to a
    basic-auth AnaplanAuthToken when no OAuth token is stored. The basic-auth
    token is logged out on teardown; the OAuth token is left intact (it is owned
    by the human-run grant flow and revoking it would break repeat test runs).
    """
    oauth_token = _get_oauth_access_token()
    if oauth_token:
        yield oauth_token
        return

    username = os.getenv("ANAPLAN_USERNAME")
    password = os.getenv("ANAPLAN_PASSWORD")
    if not username or not password:
        pytest.skip(
            "No OAuth token in keyring and ANAPLAN_USERNAME/ANAPLAN_PASSWORD not set"
        )

    token = _get_anaplan_token(username, password)
    if not token:
        pytest.skip("Failed to obtain AnaplanAuthToken from basic auth")

    yield token

    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        client.post(
            f"{AUTH_URL}/token/logout",
            headers={"Authorization": f"AnaplanAuthToken {token}"},
        )


# ── Tracer bullet ─────────────────────────────────────────────────────────────

@pytest.mark.live
def test_audit_get_events_responds(audit_token):
    """GET /events is reachable and AnaplanAuthToken is accepted by the server.

    A 200 confirms events are returned.
    A 401 with FAILURE_UNAUTHORIZED_USER_ACTION confirms the token was accepted
    but the user lacks the Tenant Auditor role (Audit API uses 401, not 403,
    for this case — confirmed via live testing 2026-06-08).
    Any other status indicates a genuine authentication failure.
    """
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        response = client.get(
            f"{AUDIT_BASE_URL}/events",
            headers={
                "Authorization": f"AnaplanAuthToken {audit_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /events: {response.status_code}")
    print(f"Body: {response.text[:200]}")

    if _is_no_role_401(response):
        warnings.warn(
            "GET /events returned 401 FAILURE_UNAUTHORIZED_USER_ACTION — "
            "AnaplanAuthToken was accepted; user lacks the Tenant Auditor role. "
            "Spec security scheme declaration is correct. "
            "Assign the Tenant Auditor role to test data retrieval.",
            UserWarning,
            stacklevel=2,
        )
        return

    assert response.status_code == 200, (
        f"AnaplanAuthToken was rejected (got {response.status_code}, "
        f"body: {response.text[:200]})"
    )


# ── Response shape ────────────────────────────────────────────────────────────

@pytest.mark.live
def test_audit_get_events_response_has_response_key(audit_token):
    """GET /events JSON response must include a top-level 'response' array.

    Verifies the AuditEventsResponse schema shape documented in the spec.
    Skipped if caller lacks the Tenant Auditor role (401 FAILURE_UNAUTHORIZED_USER_ACTION).
    """
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        response = client.get(
            f"{AUDIT_BASE_URL}/events",
            params={"intervalInHours": "1"},
            headers={
                "Authorization": f"AnaplanAuthToken {audit_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /events?intervalInHours=1: {response.status_code}")

    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify response shape")

    assert response.status_code == 200, f"Unexpected status: {response.status_code}"
    body = response.json()
    assert "response" in body, (
        "Response body must have a top-level 'response' key "
        "(matches AuditEventsResponse schema)"
    )
    assert isinstance(body["response"], list), "'response' must be an array"


@pytest.mark.live
def test_audit_get_events_paging_meta_shape(audit_token):
    """When meta.paging is present, it must include currentPageSize, totalSize, and offSet.

    Verifies the AuditPaging schema fields documented in the spec.
    Skipped if caller lacks the Tenant Auditor role.
    """
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        response = client.get(
            f"{AUDIT_BASE_URL}/events",
            params={"intervalInHours": "24"},
            headers={
                "Authorization": f"AnaplanAuthToken {audit_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /events?intervalInHours=24 (paging check): {response.status_code}")

    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify paging shape")

    assert response.status_code == 200
    body = response.json()
    paging = body.get("meta", {}).get("paging")
    if paging is None:
        warnings.warn(
            "GET /events did not return meta.paging — may not be present when "
            "result set is small; spec's AuditPaging shape cannot be confirmed.",
            UserWarning,
            stacklevel=2,
        )
        return

    for field in ("currentPageSize", "totalSize", "offSet"):
        assert field in paging, (
            f"meta.paging is missing required field {field!r} "
            f"(AuditPaging schema requires it)"
        )


# ── type parameter ────────────────────────────────────────────────────────────

@pytest.mark.live
def test_audit_get_events_type_param_all(audit_token):
    """GET /events?type=all is accepted without error.

    The spec documents three enum values: all, byok, user_activity.
    A 200 or role-based 401 confirms the parameter is processed without error.
    """
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        response = client.get(
            f"{AUDIT_BASE_URL}/events",
            params={"type": "all", "intervalInHours": "1"},
            headers={
                "Authorization": f"AnaplanAuthToken {audit_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /events?type=all: {response.status_code}")
    assert response.status_code == 200 or _is_no_role_401(response), (
        f"type=all rejected with unexpected status {response.status_code}: "
        f"{response.text[:200]}"
    )


# ── POST /events/search ───────────────────────────────────────────────────────

@pytest.mark.live
def test_audit_post_search_responds(audit_token):
    """POST /events/search accepts an interval body and responds correctly.

    Verifies the POST endpoint exists at the documented path and accepts the
    AuditSearchRequest schema's 'interval' field.
    """
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        response = client.post(
            f"{AUDIT_BASE_URL}/events/search",
            json={"interval": 1},
            headers={
                "Authorization": f"AnaplanAuthToken {audit_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    print(f"\nPOST /events/search: {response.status_code}")
    print(f"Body: {response.text[:200]}")
    assert response.status_code == 200 or _is_no_role_401(response), (
        f"POST /events/search responded with unexpected status {response.status_code}: "
        f"{response.text[:200]}"
    )


@pytest.mark.live
def test_audit_post_search_response_shape(audit_token):
    """POST /events/search response must match the AuditEventsResponse envelope.

    Skipped if caller lacks the Tenant Auditor role.
    """
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        response = client.post(
            f"{AUDIT_BASE_URL}/events/search",
            json={"interval": 24},
            headers={
                "Authorization": f"AnaplanAuthToken {audit_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    print(f"\nPOST /events/search (shape check): {response.status_code}")

    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify response shape")

    assert response.status_code == 200
    body = response.json()
    assert "response" in body, (
        "POST /events/search body must have a top-level 'response' key"
    )
    assert isinstance(body["response"], list), "'response' must be an array"


# ── CEF format probe ──────────────────────────────────────────────────────────

@pytest.mark.live
def test_audit_get_events_cef_format_probe(audit_token):
    """Probes whether Accept: text/plain returns CEF-format output from GET /events.

    The spec documents a text/plain response media type for CEF output.
    A 200 with a non-JSON body beginning with a timestamp or 'CEF:' confirms
    the spec's text/plain content type declaration is accurate.
    Skipped if caller lacks the Tenant Auditor role.
    """
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        response = client.get(
            f"{AUDIT_BASE_URL}/events",
            params={"intervalInHours": "1"},
            headers={
                "Authorization": f"AnaplanAuthToken {audit_token}",
                "Accept": "text/plain",
            },
        )

    print(f"\nGET /events Accept: text/plain: {response.status_code}")

    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify CEF output")

    if response.status_code != 200:
        warnings.warn(
            f"GET /events with Accept: text/plain returned {response.status_code} "
            "— CEF format may not be supported; verify text/plain in spec.",
            UserWarning,
            stacklevel=2,
        )
        return

    ct = response.headers.get("content-type", "")
    body_text = response.text
    if "text/plain" in ct or (body_text and not body_text.strip().startswith("{")):
        warnings.warn(
            "GET /events returned text/plain (CEF) output — "
            "spec's text/plain content type declaration is confirmed.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"GET /events with Accept: text/plain returned content-type {ct!r}; "
            "body may be JSON rather than CEF — verify text/plain response in spec.",
            UserWarning,
            stacklevel=2,
        )
