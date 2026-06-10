"""
Live API integration tests for Anaplan Exception Users API.

Verifies the contract for POST /permissions/exception-users/search and
PATCH /permissions/exception-users/users/{userGuid} using an Anaplan API key.

Anaplan API keys (auk_…) are sent with the AnaplanApiKey Authorization prefix:
    Authorization: AnaplanApiKey auk_<region>_<value>

Run with:
    uv run --env-file .env pytest tests/test_exception_live.py --live --allow-writes

Required .env variables:
    ANAPLAN_API_KEY - Anaplan API key (format: auk_<region>_<value>)

Optional .env variables:
    ANAPLAN_EXCEPTION_WORKSPACE_GUID - a workspace GUID the account has Tenant Security Admin access to
    ANAPLAN_EXCEPTION_USER_GUID      - a user GUID to use in search-by-user probe
    ANAPLAN_EXCEPTION_BASE_URL       - override base URL (default: https://api.anaplan.com/admin/1/0)
"""

import os
import warnings

import httpx
import pytest

EXCEPTION_BASE_URL = os.getenv(
    "ANAPLAN_EXCEPTION_BASE_URL", "https://api.anaplan.com/admin/1/0"
)
SEARCH_URL = f"{EXCEPTION_BASE_URL}/permissions/exception-users/search"


@pytest.fixture(scope="module")
def api_key():
    """Anaplan API key used with the AnaplanApiKey Authorization prefix."""
    key = os.getenv("ANAPLAN_API_KEY")
    if not key:
        pytest.skip("ANAPLAN_API_KEY not set")
    return key


# ── Tracer bullet ────────────────────────────────────────────────────────────

@pytest.mark.live
def test_exception_users_anaplan_api_key_accepted(api_key):
    """AnaplanApiKey prefix is accepted by the Exception Users search endpoint.

    A 400 without FAILURE_BAD_HEADER confirms the key was recognized (auth
    passed; the bogus GUID triggers FAILURE_BAD_REQUEST validation instead).
    A FAILURE_BAD_HEADER response means the AnaplanApiKey format was rejected.
    """
    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"AnaplanApiKey {api_key}"},
            json={"workspaceGuid": "00000000000000000000000000000000"},
        )

    status = response.status_code
    body_text = response.text
    print(f"\nPOST /search with AnaplanApiKey: {status} — {body_text[:200]}")
    assert "FAILURE_BAD_HEADER" not in body_text, (
        f"AnaplanApiKey was rejected (FAILURE_BAD_HEADER); got {status}: {body_text}"
    )
    assert status != 401, (
        f"AnaplanApiKey was rejected with 401; scheme not accepted"
    )


# ── Probe: Bearer scheme with API key ────────────────────────────────────────

@pytest.mark.live
def test_exception_users_bearer_scheme_probe(api_key):
    """Probes whether the API key is also accepted with the Bearer prefix.

    Confirmed rejected in live testing — documents the result for spec accuracy.
    """
    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"workspaceGuid": "00000000000000000000000000000000"},
        )

    status = response.status_code
    body_text = response.text
    print(f"\nPOST /search Bearer prefix probe: {status} — {body_text[:200]}")

    if "FAILURE_BAD_HEADER" in body_text or status == 401:
        warnings.warn(
            f"Bearer prefix rejected for API key on POST /search (status {status}) — "
            "AnaplanApiKey is the correct prefix; spec BearerAuth does not apply to API keys.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"Bearer prefix accepted for API key on POST /search (status {status}) — "
            "both AnaplanApiKey and Bearer prefixes work; update spec accordingly.",
            UserWarning,
            stacklevel=2,
        )


# ── Probe: AnaplanAuthToken scheme ───────────────────────────────────────────

@pytest.mark.live
def test_exception_users_anaplan_auth_token_scheme_probe(api_key):
    """Probes whether the AnaplanAuthToken header scheme is accepted.

    The spec declares both AnaplanAuthToken and BearerAuth. This probe checks
    whether the API key also works under the AnaplanAuthToken prefix.
    """
    with httpx.Client() as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"AnaplanAuthToken {api_key}"},
            json={"workspaceGuid": "00000000000000000000000000000000"},
        )

    status = response.status_code
    body_text = response.text
    print(f"\nPOST /search AnaplanAuthToken prefix probe: {status} — {body_text[:200]}")

    if status in (200, 400, 403, 404) and "FAILURE_BAD_HEADER" not in body_text:
        warnings.warn(
            f"AnaplanAuthToken prefix accepted on POST /search (status {status}) — "
            "AnaplanAuthToken scheme is also valid for Exception Users API.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 401 or "FAILURE_BAD_HEADER" in body_text:
        warnings.warn(
            "AnaplanAuthToken prefix rejected on POST /search — "
            "AnaplanApiKey is the correct prefix for API key auth.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"AnaplanAuthToken prefix probe returned unexpected status {status} on POST /search.",
            UserWarning,
            stacklevel=2,
        )


# ── POST search by workspace ─────────────────────────────────────────────────

@pytest.mark.live
def test_exception_search_by_workspace_returns_response_array(api_key):
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
            headers={"Authorization": f"AnaplanApiKey {api_key}"},
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
def test_exception_search_by_user_returns_response_array(api_key):
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
            headers={"Authorization": f"AnaplanApiKey {api_key}"},
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
def test_exception_patch_invalid_op_returns_400(api_key):
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
            headers={"Authorization": f"AnaplanApiKey {api_key}"},
            json={"op": "invalid_op", "workspaceGuid": workspace_guid},
        )

    print(f"\nPATCH /users/{{userGuid}} with invalid op: {response.status_code}")
    assert response.status_code == 400, (
        f"Expected 400 for invalid op, got {response.status_code}: {response.text}"
    )
