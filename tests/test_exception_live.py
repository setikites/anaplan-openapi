"""
Live API integration tests for Anaplan Exception Users API.

Verifies the contract for POST /permissions/exception-users/search and
PATCH /permissions/exception-users/users/{userGuid} using OAuth Bearer auth.

Before running, obtain an OAuth access token via the authcode flow:
    uv run python oauth_authcode_step1.py
    uv run python oauth_authcode_step2.py
    uv run python oauth_authcode_step3.py   # refresh if token expired

The token is read automatically from .token at the repo root.

Run with:
    uv run --env-file .env pytest tests/test_exception_live.py --live

Optional .env variables:
    ANAPLAN_EXCEPTION_WORKSPACE_GUID - a workspace GUID the account has Tenant Security Admin access to
    ANAPLAN_EXCEPTION_USER_GUID      - a user GUID to use in search-by-user probe
    ANAPLAN_EXCEPTION_BASE_URL       - override base URL (default: https://api.anaplan.com/admin/1/0)
"""

import json
import os
import warnings

import httpx
import pytest

EXCEPTION_BASE_URL = os.getenv(
    "ANAPLAN_EXCEPTION_BASE_URL", "https://api.anaplan.com/admin/1/0"
)
SEARCH_URL = f"{EXCEPTION_BASE_URL}/permissions/exception-users/search"


@pytest.fixture(scope="module")
def oauth_token():
    """Bearer access token read from .token (written by oauth_authcode_step2.py)."""
    token_path = os.path.join(os.path.dirname(__file__), "..", ".token")
    if not os.path.exists(token_path):
        pytest.skip(".token file not found — run oauth_authcode_step1/2/3.py first")
    with open(token_path) as f:
        data = json.load(f)
    token = data.get("access_token")
    if not token:
        pytest.skip("No access_token in .token — run oauth_authcode_step3.py to refresh")
    return token


# ── Tracer bullet ────────────────────────────────────────────────────────────

@pytest.mark.live
def test_exception_users_oauth_bearer_accepted(oauth_token):
    """OAuth Bearer token is accepted by the Exception Users search endpoint.

    A 200/400/403/404 confirms the token was recognized. A 401 means Bearer
    is rejected, which would invalidate the spec's BearerAuth declaration.
    """
    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {oauth_token}"},
            json={"workspaceGuid": "00000000000000000000000000000000"},
        )

    status = response.status_code
    print(f"\nPOST /search with OAuth Bearer: {status}")
    assert status in (200, 400, 403, 404), (
        f"OAuth Bearer was rejected (got {status}); "
        "expected 200/400/403/404 (auth accepted) rather than 401 (auth rejected)"
    )


# ── Probe: AnaplanAuthToken scheme ───────────────────────────────────────────

@pytest.mark.live
def test_exception_users_anaplan_auth_token_scheme_probe(oauth_token):
    """Probes whether the AnaplanAuthToken scheme is accepted alongside Bearer.

    The spec currently declares only AnaplanAuthToken. If 200/400/403/404 is
    returned with Bearer, Bearer must be added to (or replace) the spec's
    security declaration. This test documents the live result.
    """
    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {oauth_token}"},
            json={"workspaceGuid": "00000000000000000000000000000000"},
        )

    status = response.status_code
    print(f"\nPOST /search Bearer scheme probe: {status}")

    if status in (200, 400, 403, 404):
        warnings.warn(
            f"OAuth Bearer token accepted on POST /search (status {status}) — "
            "add BearerAuth to the exception spec security declaration.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 401:
        warnings.warn(
            "OAuth Bearer token rejected on POST /search (401) — "
            "AnaplanAuthToken remains the only valid scheme; spec is correct.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"Bearer scheme probe returned unexpected status {status} on POST /search.",
            UserWarning,
            stacklevel=2,
        )


# ── POST search by workspace ─────────────────────────────────────────────────

@pytest.mark.live
def test_exception_search_by_workspace_returns_response_array(oauth_token):
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
            headers={"Authorization": f"Bearer {oauth_token}"},
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
def test_exception_search_by_user_returns_response_array(oauth_token):
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
            headers={"Authorization": f"Bearer {oauth_token}"},
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
def test_exception_patch_invalid_op_returns_400(oauth_token):
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
            headers={"Authorization": f"Bearer {oauth_token}"},
            json={"op": "invalid_op", "workspaceGuid": workspace_guid},
        )

    print(f"\nPATCH /users/{{userGuid}} with invalid op: {response.status_code}")
    assert response.status_code == 400, (
        f"Expected 400 for invalid op, got {response.status_code}: {response.text}"
    )
