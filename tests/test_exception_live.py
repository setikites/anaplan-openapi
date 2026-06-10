"""
Live API integration tests for Anaplan Exception Users API.

Probes which authentication schemes the API accepts and verifies the contract
for POST /permissions/exception-users/search and PATCH /permissions/exception-users/users/{userGuid}.
Requires the Tenant Security Admin role on the test account.

Run with:
    uv run --env-file .env pytest tests/test_exception_live.py --live

Credentials are read from .env at the repo root. Required variables:
    ANAPLAN_USERNAME       - username for basic auth (to obtain AnaplanAuthToken)
    ANAPLAN_PASSWORD       - password for basic auth
    ANAPLAN_EXCEPTION_WORKSPACE_GUID - a workspace GUID the account has Tenant Security Admin access to
    ANAPLAN_EXCEPTION_USER_GUID      - a user GUID to use in search-by-user probe

Optional variables:
    ANAPLAN_OAUTH_ACCESS_TOKEN - pre-obtained OAuth 2.0 access token for Bearer probe
    ANAPLAN_EXCEPTION_BASE_URL - override base URL (default: https://api.anaplan.com/admin/1/0)
"""

import base64
import os
import warnings

import httpx
import pytest

AUTH_URL = "https://auth.anaplan.com"
EXCEPTION_BASE_URL = os.getenv(
    "ANAPLAN_EXCEPTION_BASE_URL", "https://api.anaplan.com/admin/1/0"
)
SEARCH_URL = f"{EXCEPTION_BASE_URL}/permissions/exception-users/search"


def _get_anaplan_token(username: str, password: str) -> str | None:
    """Authenticate via Basic auth and return an AnaplanAuthToken value."""
    auth_b64 = base64.b64encode(f"{username}:{password}".encode()).decode()
    with httpx.Client() as client:
        response = client.post(
            f"{AUTH_URL}/token/authenticate",
            headers={"Authorization": f"Basic {auth_b64}"},
        )
    if response.status_code == 201:
        return response.json().get("tokenInfo", {}).get("tokenValue")
    return None


@pytest.fixture(scope="module")
def exception_token():
    """AnaplanAuthToken for Exception Users API calls (module-scoped). Logs out on teardown."""
    username = os.getenv("ANAPLAN_USERNAME")
    password = os.getenv("ANAPLAN_PASSWORD")
    if not username or not password:
        pytest.skip("ANAPLAN_USERNAME and ANAPLAN_PASSWORD not set")

    token = _get_anaplan_token(username, password)
    if not token:
        pytest.skip("Failed to obtain AnaplanAuthToken from basic auth")

    yield token

    with httpx.Client() as client:
        client.post(
            f"{AUTH_URL}/token/logout",
            headers={"Authorization": f"AnaplanAuthToken {token}"},
        )


# ── Tracer bullet ────────────────────────────────────────────────────────────

@pytest.mark.live
def test_exception_users_anaplan_auth_token_accepted(exception_token):
    """AnaplanAuthToken is accepted by the Exception Users search endpoint.

    A 200 or 403 confirms the token was recognized (403 = auth ok, no
    Tenant Security Admin role). A 400 with a search-criteria error also
    confirms authentication passed. A 401 would mean AnaplanAuthToken is
    rejected, which would invalidate the spec's AnaplanAuthToken security
    scheme declaration.
    """
    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"AnaplanAuthToken {exception_token}"},
            json={"workspaceGuid": "00000000000000000000000000000000"},
        )

    print(f"\nPOST /search with AnaplanAuthToken: {response.status_code}")
    assert response.status_code in (200, 400, 403, 404), (
        f"AnaplanAuthToken was rejected (got {response.status_code}); "
        "expected 200/400/403/404 (auth accepted) rather than 401 (auth rejected)"
    )


# ── Probe: Bearer with AnaplanAuthToken value ────────────────────────────────

@pytest.mark.live
def test_exception_users_bearer_with_anaplan_token_probe(exception_token):
    """Probes whether the Bearer scheme accepts an AnaplanAuthToken value.

    Hypothesis: Anaplan tokens are not OAuth 2.0 tokens, so Bearer {anaplan_token}
    is likely rejected with 401. If 200/400/403/404 is returned, the endpoint treats
    AnaplanAuthToken and Bearer interchangeably — BearerAuth must be added to the spec.
    """
    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {exception_token}"},
            json={"workspaceGuid": "00000000000000000000000000000000"},
        )

    status = response.status_code
    print(f"\nPOST /search with Bearer (AnaplanAuthToken value): {status}")

    if status in (200, 400, 403, 404):
        warnings.warn(
            f"Bearer scheme accepted an AnaplanAuthToken value on POST /search "
            f"(status {status}) — AnaplanAuthToken and Bearer are interchangeable; "
            "add BearerAuth to the exception spec.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 401:
        warnings.warn(
            "Bearer scheme rejected AnaplanAuthToken value (401) on POST /search — "
            "Bearer requires a distinct OAuth 2.0 token; spec is correct with AnaplanAuthToken only.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"Bearer probe returned unexpected status {status} on POST /search.",
            UserWarning,
            stacklevel=2,
        )


# ── Probe: OAuth Bearer token ────────────────────────────────────────────────

@pytest.mark.live
def test_exception_users_oauth_bearer_probe():
    """Probes whether a real OAuth 2.0 Bearer token is accepted by the search endpoint.

    Requires ANAPLAN_OAUTH_ACCESS_TOKEN in .env. Skipped if absent.
    If 200/400/403/404 is returned, add BearerAuth to the spec.
    """
    oauth_token = os.getenv("ANAPLAN_OAUTH_ACCESS_TOKEN")
    if not oauth_token:
        pytest.skip("ANAPLAN_OAUTH_ACCESS_TOKEN not set")

    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {oauth_token}"},
            json={"workspaceGuid": "00000000000000000000000000000000"},
        )

    status = response.status_code
    print(f"\nPOST /search with OAuth Bearer token: {status}")

    if status in (200, 400, 403, 404):
        warnings.warn(
            f"OAuth Bearer token accepted on POST /search (status {status}) — "
            "add BearerAuth to the exception spec.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 401:
        warnings.warn(
            "OAuth Bearer token rejected on POST /search (401) — "
            "AnaplanAuthToken is the only valid scheme; spec is correct.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"OAuth Bearer probe returned unexpected status {status} on POST /search.",
            UserWarning,
            stacklevel=2,
        )


# ── POST search by workspace ─────────────────────────────────────────────────

@pytest.mark.live
def test_exception_search_by_workspace_returns_response_array(exception_token):
    """POST /search with a workspaceGuid returns 200 with a 'response' array.

    Verifies the spec's ExceptionUserSearchResponse shape: top-level object
    with a 'response' key containing an array.
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

    for workspace_result in body["response"]:
        assert "workspaceGuid" in workspace_result, (
            f"workspace result missing 'workspaceGuid': {workspace_result}"
        )
        assert "users" in workspace_result, (
            f"workspace result missing 'users': {workspace_result}"
        )
        assert isinstance(workspace_result["users"], list), (
            f"'users' should be an array, got: {type(workspace_result['users'])}"
        )


# ── POST search by user ──────────────────────────────────────────────────────

@pytest.mark.live
def test_exception_search_by_user_returns_response_array(exception_token):
    """POST /search with a userGuid returns 200 with a 'response' array.

    Verifies the spec handles the by-user search path and returns the same
    ExceptionUserSearchResponse shape.
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


# ── PATCH invalid op returns 400 ─────────────────────────────────────────────

@pytest.mark.live
def test_exception_patch_invalid_op_returns_400(exception_token):
    """PATCH /users/{userGuid} with an invalid 'op' value returns 400.

    Non-destructive error probe: uses a deliberate invalid op value so no
    actual assign/unassign occurs. Verifies the API enforces the op enum
    ('assign' | 'unassign') and returns 400 for bad input.
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
