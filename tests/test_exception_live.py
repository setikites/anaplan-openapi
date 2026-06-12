"""
Live API integration tests for the Anaplan Exception Users API.

Verifies the contract for POST /permissions/exception-users/search and
PATCH /permissions/exception-users/users/{userGuid} against the real API.

Authentication uses the OAuth Authorization Code grant with the AnaplanAuthToken
scheme — the account must hold the Tenant Security Admin role. Authenticate
interactively before running:

    uv run python scripts/oauth/oauth_authcode.py

This stores the token in the OS keyring. Then run:

    uv run --env-file .env pytest tests/test_exception_live.py --live

Optional .env variables:
    ANAPLAN_OAUTH_KEYRING_SERVICE    — keyring service name
                                       (default: anaplan-oauth-authcode)
    ANAPLAN_EXCEPTION_WORKSPACE_GUID — workspace GUID the account has
                                       Tenant Security Admin access to
    ANAPLAN_EXCEPTION_USER_GUID      — user GUID for the search-by-user probe
    ANAPLAN_EXCEPTION_BASE_URL       — override base URL
                                       (default: https://api.anaplan.com/admin/1/0)
    ANAPLAN_API_KEY                  — Anaplan API key for the AnaplanApiKey
                                       scheme probe (optional)
"""

import json
import os
import warnings

import httpx
import pytest

from oauth.token_keyring import load_token

EXCEPTION_BASE_URL = os.getenv(
    "ANAPLAN_EXCEPTION_BASE_URL", "https://api.anaplan.com/admin/1/0"
)
SEARCH_URL = f"{EXCEPTION_BASE_URL}/permissions/exception-users/search"


def _get_oauth_access_token() -> str | None:
    """Return the access_token from the OAuth token blob in the keyring, if any.

    The Authorization Code grant helper stores the full token response under
    ANAPLAN_OAUTH_KEYRING_SERVICE. The Exception Users API accepts OAuth tokens
    under the AnaplanAuthToken scheme (Bearer is rejected with FAILURE_BAD_HEADER).
    """
    service = os.getenv("ANAPLAN_OAUTH_KEYRING_SERVICE", "anaplan-oauth-authcode")
    blob = load_token(service)
    if not blob:
        return None
    try:
        return json.loads(blob).get("access_token")
    except (ValueError, AttributeError):
        return None


@pytest.fixture(scope="module")
def exception_token():
    """OAuth access token for Exception Users API calls (module-scoped).

    Loaded from the OS keyring (stored by oauth_authcode.py). The account must
    hold the Tenant Security Admin role for the search and PATCH tests to succeed.

    Authenticate first:
        uv run python scripts/oauth/oauth_authcode.py
    """
    token = _get_oauth_access_token()
    if not token:
        service = os.getenv("ANAPLAN_OAUTH_KEYRING_SERVICE", "anaplan-oauth-authcode")
        pytest.skip(
            f"No OAuth token in keyring under service {service!r}. "
            "Run: uv run python scripts/oauth/oauth_authcode.py"
        )
    return token


# ── Tracer bullet ─────────────────────────────────────────────────────────────

@pytest.mark.live
def test_exception_users_anaplan_auth_token_accepted(exception_token):
    """AnaplanAuthToken (OAuth access token) is accepted by the Exception Users search endpoint.

    A non-401, non-FAILURE_BAD_HEADER response confirms the token was recognised.
    Live testing confirmed Bearer is rejected (FAILURE_BAD_HEADER); AnaplanAuthToken
    returns 404 (auth accepted, resource not found for the dummy GUID).
    """
    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"AnaplanAuthToken {exception_token}"},
            json={"workspaceGuid": "00000000000000000000000000000000"},
        )

    status = response.status_code
    print(f"\nPOST /search with AnaplanAuthToken (OAuth): {status} — {response.text[:200]}")
    assert status != 401, "AnaplanAuthToken rejected (401)"
    assert "FAILURE_BAD_HEADER" not in response.text, (
        f"AnaplanAuthToken rejected (FAILURE_BAD_HEADER): {response.text}"
    )


# ── POST search by workspace ──────────────────────────────────────────────────

@pytest.mark.live
def test_exception_search_by_workspace_returns_response_array(exception_token):
    """POST /search with a workspaceGuid returns 200 with a 'response' array.

    Verifies the spec's ExceptionUserSearchResponse shape: top-level object
    with a 'response' key containing an array of workspace result objects,
    each with 'workspaceGuid' and 'users' fields.
    """
    workspace_guid = os.getenv("ANAPLAN_EXCEPTION_WORKSPACE_GUID")
    if not workspace_guid:
        pytest.skip("ANAPLAN_EXCEPTION_WORKSPACE_GUID not set")

    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"AnaplanAuthToken {exception_token}"},
            json={"workspaceGuid": workspace_guid},
        )

    print(f"\nPOST /search by workspace: {response.status_code}")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "response" in body, f"Expected 'response' key in body, got: {list(body.keys())}"
    assert isinstance(body["response"], list), (
        f"Expected 'response' to be an array, got: {type(body['response'])}"
    )
    for result in body["response"]:
        assert "workspaceGuid" in result, f"workspace result missing 'workspaceGuid': {result}"
        assert "users" in result, f"workspace result missing 'users': {result}"
        assert isinstance(result["users"], list), (
            f"'users' should be an array, got: {type(result['users'])}"
        )


# ── POST search by user ───────────────────────────────────────────────────────

@pytest.mark.live
def test_exception_search_by_user_returns_response_array(exception_token):
    """POST /search with a userGuid returns 200 with a 'response' array.

    Verifies the by-user search path returns the same ExceptionUserSearchResponse
    shape as the by-workspace path.
    """
    user_guid = os.getenv("ANAPLAN_EXCEPTION_USER_GUID")
    if not user_guid:
        pytest.skip("ANAPLAN_EXCEPTION_USER_GUID not set")

    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"AnaplanAuthToken {exception_token}"},
            json={"userGuid": user_guid},
        )

    print(f"\nPOST /search by user: {response.status_code}")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "response" in body, f"Expected 'response' key in body, got: {list(body.keys())}"
    assert isinstance(body["response"], list), (
        f"Expected 'response' to be an array, got: {type(body['response'])}"
    )


# ── PATCH invalid op returns 400 ──────────────────────────────────────────────

@pytest.mark.live
def test_exception_patch_invalid_op_returns_400(exception_token):
    """PATCH /users/{userGuid} with an invalid 'op' value returns 400.

    Non-destructive error probe: a deliberately invalid op triggers a validation
    error rather than any actual assign/unassign. Verifies the API enforces the
    op enum ('assign' | 'unassign') declared in the spec.
    """
    workspace_guid = os.getenv("ANAPLAN_EXCEPTION_WORKSPACE_GUID")
    user_guid = os.getenv("ANAPLAN_EXCEPTION_USER_GUID")
    if not workspace_guid or not user_guid:
        pytest.skip(
            "ANAPLAN_EXCEPTION_WORKSPACE_GUID and ANAPLAN_EXCEPTION_USER_GUID not set"
        )

    patch_url = f"{EXCEPTION_BASE_URL}/permissions/exception-users/users/{user_guid}"

    with httpx.Client() as client:
        response = client.patch(
            patch_url,
            headers={"Authorization": f"AnaplanAuthToken {exception_token}"},
            json={"op": "invalid_op", "workspaceGuid": workspace_guid},
        )

    print(f"\nPATCH /users/{{userGuid}} with invalid op: {response.status_code}")
    assert response.status_code == 400, (
        f"Expected 400 for invalid op, got {response.status_code}: {response.text}"
    )


# ── Probe: Bearer scheme ─────────────────────────────────────────────────────

@pytest.mark.live
def test_exception_users_bearer_scheme_probe(exception_token):
    """Confirms that Bearer is NOT accepted by the Exception Users API.

    Live testing showed Bearer returns FAILURE_BAD_HEADER (400). This probe
    documents that finding — if the status changes to non-400 or the body no
    longer contains FAILURE_BAD_HEADER, update the spec to add BearerAuth.
    """
    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {exception_token}"},
            json={"workspaceGuid": "00000000000000000000000000000000"},
        )

    status = response.status_code
    print(f"\nPOST /search Bearer probe: {status} — {response.text[:200]}")

    if "FAILURE_BAD_HEADER" in response.text or status == 401:
        warnings.warn(
            f"Bearer rejected on POST /search (status {status}, FAILURE_BAD_HEADER) — "
            "BearerAuth correctly absent from the spec.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"Bearer accepted on POST /search (status {status}) — "
            "add BearerAuth to the spec's security schemes.",
            UserWarning,
            stacklevel=2,
        )


# ── Probe: AnaplanApiKey scheme ───────────────────────────────────────────────

@pytest.mark.live
def test_exception_users_anaplan_api_key_scheme_probe():
    """Probes whether an Anaplan API key is accepted with the AnaplanApiKey prefix.

    Skipped if ANAPLAN_API_KEY is not set. A 400 (bad GUID) confirms the key
    was recognised; a 401 or FAILURE_BAD_HEADER means it is rejected.
    """
    api_key = os.getenv("ANAPLAN_API_KEY")
    if not api_key:
        pytest.skip("ANAPLAN_API_KEY not set")

    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"AnaplanApiKey {api_key}"},
            json={"workspaceGuid": "00000000000000000000000000000000"},
        )

    status = response.status_code
    body_text = response.text
    print(f"\nPOST /search AnaplanApiKey probe: {status} — {body_text[:200]}")

    if status != 401 and "FAILURE_BAD_HEADER" not in body_text:
        warnings.warn(
            f"AnaplanApiKey accepted on POST /search (status {status}) — "
            "AnaplanApiKey scheme is valid for this endpoint; keep it in the spec.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"AnaplanApiKey rejected on POST /search (status {status}) — "
            "remove AnaplanApiKey from the spec's security schemes.",
            UserWarning,
            stacklevel=2,
        )
