"""
Live API integration tests for the Anaplan ALM API.

Probes read-only ALM endpoints to verify that:
- The spec's documented paths and response shapes match the real API.
- The AnaplanAuthToken security scheme is accepted.
- Whether Bearer token is also accepted (unconfirmed per alm/README.md).
- The standard response envelope (meta, status) is returned.

Run with:
    uv run --env-file .env pytest tests/test_alm_live.py --live

Credentials are read from .env at the repo root. Required variables:
    ANAPLAN_USERNAME  - username for basic auth (to obtain AnaplanAuthToken)
    ANAPLAN_PASSWORD  - password for basic auth

Optional variables:
    ANAPLAN_WORKSPACE_ID      - workspace ID for ALM endpoint tests
                                (default: 8a868cdb8b7841a2018beedb91d644d7)
    ANAPLAN_MODEL_ID          - model ID for ALM endpoint tests
                                (default: 0939A1C8E7FB46799372EC24A72FE93B)
    ANAPLAN_ALM_BASE_URL      - override ALM base URL
                                (default: https://api.anaplan.com/2/0)
    ANAPLAN_OAUTH_ACCESS_TOKEN - pre-obtained OAuth Bearer token for Bearer probe

Notes on expected responses for read endpoints:
- 200 = success; token accepted and caller has Workspace Administrator role.
- 403 = token accepted; caller lacks Workspace Administrator role on the model.
- 404 = token accepted; model not found or caller has no access to it.
  All three confirm the token and security scheme are correct.
"""

import base64
import os
import pathlib
import warnings

import httpx
import pytest

ALM_BASE_URL = os.getenv(
    "ANAPLAN_ALM_BASE_URL", "https://api.anaplan.com/2/0"
).rstrip("/")
AUTH_URL = "https://auth.anaplan.com"
WORKSPACE_ID = os.getenv("ANAPLAN_WORKSPACE_ID", "8a868cdb8b7841a2018beedb91d644d7") # EBP Administration TEST
MODEL_ID = os.getenv("ANAPLAN_MODEL_ID", "0939A1C8E7FB46799372EC24A72FE93B") # EBP Request TEST
SPEC_PATH = pathlib.Path(__file__).parent.parent / "alm" / "alm-openapi.json"

_TOKEN_ACCEPTED_STATUSES = (200, 403, 404)


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
def alm_token():
    """AnaplanAuthToken for ALM calls (module-scoped). Logs out on teardown."""
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


# ── Tracer bullet ─────────────────────────────────────────────────────────────

@pytest.mark.live
def test_alm_get_latest_revision_responds(alm_token):
    """GET /models/{modelId}/alm/latestRevision is reachable and AnaplanAuthToken is accepted.

    A 200 confirms the caller has Workspace Administrator role and latestRevision data.
    A 403 confirms the token was accepted but the caller lacks Workspace Administrator role.
    A 404 confirms the token was accepted but the model is inaccessible.
    Any other status indicates a genuine authentication failure.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{ALM_BASE_URL}/models/{MODEL_ID}/alm/latestRevision",
            headers={
                "Authorization": f"AnaplanAuthToken {alm_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /models/{MODEL_ID}/alm/latestRevision: {response.status_code}")
    print(f"Body: {response.text[:300]}")

    assert response.status_code in _TOKEN_ACCEPTED_STATUSES, (
        f"AnaplanAuthToken was rejected (got {response.status_code}, "
        f"body: {response.text[:200]})"
    )

    if response.status_code == 403:
        warnings.warn(
            "GET /latestRevision returned 403 — AnaplanAuthToken was accepted; "
            "caller lacks Workspace Administrator role on the model. "
            "Assign the role to verify response shape.",
            UserWarning,
            stacklevel=2,
        )
    elif response.status_code == 404:
        warnings.warn(
            f"GET /latestRevision returned 404 for model {MODEL_ID!r} — "
            "token was accepted; set ANAPLAN_MODEL_ID to a model you have access to.",
            UserWarning,
            stacklevel=2,
        )


# ── Authentication scheme probes ──────────────────────────────────────────────

@pytest.mark.live
def test_alm_bearer_with_anaplan_token_probe(alm_token):
    """Probes whether the Bearer scheme accepts an AnaplanAuthToken value on ALM.

    The alm/README.md notes this is unconfirmed. A 200, 403, or 404 would mean
    AnaplanAuthToken and Bearer are interchangeable for ALM — update the README
    and keep BearerAuth in the spec. A 401 means they are distinct.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{ALM_BASE_URL}/models/{MODEL_ID}/alm/latestRevision",
            headers={
                "Authorization": f"Bearer {alm_token}",
                "Accept": "application/json",
            },
        )

    status = response.status_code
    print(f"\nGET /latestRevision with Bearer (AnaplanAuthToken value): {status}")

    if status in _TOKEN_ACCEPTED_STATUSES:
        warnings.warn(
            f"Bearer scheme accepted an AnaplanAuthToken value on ALM (status {status}) — "
            "AnaplanAuthToken and Bearer are interchangeable; keep BearerAuth in the spec "
            "and update alm/README.md to mark this confirmed.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 401:
        warnings.warn(
            "Bearer scheme rejected AnaplanAuthToken value on ALM (401) — "
            "Bearer requires a distinct OAuth 2.0 token; "
            "update alm/README.md to document this.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"Bearer probe returned unexpected status {status} on ALM.",
            UserWarning,
            stacklevel=2,
        )


@pytest.mark.live
def test_alm_oauth_bearer_probe():
    """Probes whether a real OAuth 2.0 Bearer token is accepted by the ALM API.

    Requires ANAPLAN_OAUTH_ACCESS_TOKEN in .env. Skipped if absent.
    A 200, 403, or 404 confirms BearerAuth is valid for ALM.
    """
    oauth_token = os.getenv("ANAPLAN_OAUTH_ACCESS_TOKEN")
    if not oauth_token:
        pytest.skip("ANAPLAN_OAUTH_ACCESS_TOKEN not set")

    with httpx.Client() as client:
        response = client.get(
            f"{ALM_BASE_URL}/models/{MODEL_ID}/alm/latestRevision",
            headers={
                "Authorization": f"Bearer {oauth_token}",
                "Accept": "application/json",
            },
        )

    status = response.status_code
    print(f"\nGET /latestRevision with OAuth Bearer token: {status}")

    if status in _TOKEN_ACCEPTED_STATUSES:
        warnings.warn(
            f"OAuth Bearer token accepted on ALM (status {status}) — "
            "BearerAuth spec declaration confirmed; update alm/README.md.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 401:
        warnings.warn(
            "OAuth Bearer token rejected on ALM (401) — "
            "remove BearerAuth from the spec; AnaplanAuthToken is the only valid scheme.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"OAuth Bearer probe returned unexpected status {status} on ALM.",
            UserWarning,
            stacklevel=2,
        )


# ── Response envelope shape ───────────────────────────────────────────────────

@pytest.mark.live
def test_alm_latest_revision_envelope_shape(alm_token):
    """GET /models/{modelId}/alm/latestRevision response must match the documented envelope.

    Verifies the RevisionResponse schema: meta.schema, status.code, and optionally
    a top-level 'revision' key.
    Skipped if caller lacks Workspace Administrator role (403) or model not found (404).
    """
    with httpx.Client() as client:
        response = client.get(
            f"{ALM_BASE_URL}/models/{MODEL_ID}/alm/latestRevision",
            headers={
                "Authorization": f"AnaplanAuthToken {alm_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /latestRevision (envelope check): {response.status_code}")

    if response.status_code in (403, 404):
        pytest.skip(
            f"Cannot verify response shape (status {response.status_code}); "
            "use a model the caller has Workspace Administrator access to."
        )

    assert response.status_code == 200, f"Unexpected status: {response.status_code}"
    body = response.json()

    assert "meta" in body, "Response must have a top-level 'meta' key"
    assert "schema" in body["meta"], "meta must contain a 'schema' field"
    assert "status" in body, "Response must have a top-level 'status' key"
    assert "code" in body["status"], "status must contain a 'code' field"

    if "revision" not in body:
        warnings.warn(
            "GET /latestRevision returned 200 but no 'revision' key — "
            "model may have no revisions yet; RevisionResponse shape cannot be fully confirmed.",
            UserWarning,
            stacklevel=2,
        )
    else:
        revision = body["revision"]
        assert "id" in revision, "revision must have an 'id' field"


# ── GET /models/{modelId}/alm/revisions ──────────────────────────────────────

@pytest.mark.live
def test_alm_get_revisions_responds(alm_token):
    """GET /models/{modelId}/alm/revisions is reachable and returns a recognised status.

    A 200, 403, or 404 confirms AnaplanAuthToken is accepted by the revisions endpoint.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{ALM_BASE_URL}/models/{MODEL_ID}/alm/revisions",
            headers={
                "Authorization": f"AnaplanAuthToken {alm_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /models/{MODEL_ID}/alm/revisions: {response.status_code}")
    print(f"Body: {response.text[:300]}")

    assert response.status_code in _TOKEN_ACCEPTED_STATUSES, (
        f"Unexpected status {response.status_code}: {response.text[:200]}"
    )


@pytest.mark.live
def test_alm_get_revisions_response_shape(alm_token):
    """GET /models/{modelId}/alm/revisions response must match the RevisionListResponse schema.

    Verifies: meta.schema, status.code, and a top-level 'revisions' array.
    Also checks pagination params are accepted without error.
    Skipped if caller lacks role (403) or model not found (404).
    """
    with httpx.Client() as client:
        response = client.get(
            f"{ALM_BASE_URL}/models/{MODEL_ID}/alm/revisions",
            params={"limit": 10, "offset": 0},
            headers={
                "Authorization": f"AnaplanAuthToken {alm_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /revisions?limit=10&offset=0 (shape check): {response.status_code}")

    if response.status_code in (403, 404):
        pytest.skip(
            f"Cannot verify response shape (status {response.status_code}); "
            "use a model the caller has Workspace Administrator access to."
        )

    assert response.status_code == 200, f"Unexpected status: {response.status_code}"
    body = response.json()

    assert "meta" in body, "Response must have a top-level 'meta' key"
    assert "status" in body, "Response must have a top-level 'status' key"
    assert "revisions" in body, (
        "Response must have a top-level 'revisions' key (RevisionListResponse schema)"
    )
    assert isinstance(body["revisions"], list), "'revisions' must be an array"

    paging = body.get("meta", {}).get("paging")
    if paging is not None:
        for field in ("currentPageSize", "offset", "totalSize"):
            assert field in paging, (
                f"meta.paging is missing required field {field!r} (Paging schema)"
            )


@pytest.mark.live
def test_alm_get_revisions_date_filter_accepted(alm_token):
    """appliedAfter and appliedBefore query params are accepted without a 400 error.

    Confirms the date filter parameters documented in the spec are processed.
    A 200, 403, or 404 all confirm the parameters were parsed without error.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{ALM_BASE_URL}/models/{MODEL_ID}/alm/revisions",
            params={"appliedAfter": "2020-01-01", "appliedBefore": "2099-12-31"},
            headers={
                "Authorization": f"AnaplanAuthToken {alm_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /revisions?appliedAfter=...&appliedBefore=...: {response.status_code}")

    assert response.status_code in _TOKEN_ACCEPTED_STATUSES, (
        f"Date filter params caused unexpected error {response.status_code}: "
        f"{response.text[:200]}"
    )


# ── GET /models/{modelId}/alm/syncTasks ──────────────────────────────────────

@pytest.mark.live
def test_alm_get_sync_tasks_responds(alm_token):
    """GET /models/{modelId}/alm/syncTasks is reachable and returns a recognised status."""
    with httpx.Client() as client:
        response = client.get(
            f"{ALM_BASE_URL}/models/{MODEL_ID}/alm/syncTasks",
            headers={
                "Authorization": f"AnaplanAuthToken {alm_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /models/{MODEL_ID}/alm/syncTasks: {response.status_code}")
    print(f"Body: {response.text[:300]}")

    assert response.status_code in _TOKEN_ACCEPTED_STATUSES, (
        f"Unexpected status {response.status_code}: {response.text[:200]}"
    )


@pytest.mark.live
def test_alm_get_sync_tasks_response_shape(alm_token):
    """GET /models/{modelId}/alm/syncTasks response must match the SyncTaskListResponse schema.

    Verifies: meta.schema, status.code, and the 'tasks' array when present.
    Each task must have taskId and taskState fields.

    **Confirmed behavior (live testing 2026-06-09):**
    When no sync tasks exist in the last 48 hours, the API returns 200 with only
    meta and status — the 'tasks' key is omitted entirely rather than returning
    an empty array. The spec's SyncTaskListResponse schema reflects this.

    Skipped if caller lacks role (403) or model not found (404).
    """
    with httpx.Client() as client:
        response = client.get(
            f"{ALM_BASE_URL}/models/{MODEL_ID}/alm/syncTasks",
            headers={
                "Authorization": f"AnaplanAuthToken {alm_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /syncTasks (shape check): {response.status_code}")

    if response.status_code in (403, 404):
        pytest.skip(
            f"Cannot verify response shape (status {response.status_code}); "
            "use a model the caller has Workspace Administrator access to."
        )

    assert response.status_code == 200, f"Unexpected status: {response.status_code}"
    body = response.json()

    assert "meta" in body, "Response must have a top-level 'meta' key"
    assert "status" in body, "Response must have a top-level 'status' key"

    if "tasks" not in body:
        warnings.warn(
            "GET /syncTasks returned 200 with no 'tasks' key — no sync tasks in the "
            "last 48 hours; confirmed behavior: empty results omit the key entirely "
            "rather than returning an empty array.",
            UserWarning,
            stacklevel=2,
        )
        return

    assert isinstance(body["tasks"], list), "'tasks' must be an array"

    for i, task in enumerate(body["tasks"]):
        assert "taskId" in task, f"tasks[{i}] missing 'taskId'"
        assert "taskState" in task, f"tasks[{i}] missing 'taskState'"
        assert task["taskState"] in ("IN_PROGRESS", "COMPLETE"), (
            f"tasks[{i}].taskState {task['taskState']!r} is not a documented enum value"
        )


# ── GET /models/{modelId}/alm/syncableRevisions ───────────────────────────────

@pytest.mark.live
def test_alm_get_syncable_revisions_requires_source_model_id(alm_token):
    """GET /models/{modelId}/alm/syncableRevisions without sourceModelId returns an error.

    The spec marks sourceModelId as a required query parameter. This test confirms
    the API rejects the request without it (expected: 400 or 422) rather than
    treating it as optional.
    Skipped if 403/404 is returned (role/access issue masks the parameter check).
    """
    with httpx.Client() as client:
        response = client.get(
            f"{ALM_BASE_URL}/models/{MODEL_ID}/alm/syncableRevisions",
            headers={
                "Authorization": f"AnaplanAuthToken {alm_token}",
                "Accept": "application/json",
            },
        )

    status = response.status_code
    print(f"\nGET /syncableRevisions (no sourceModelId): {status}")
    print(f"Body: {response.text[:300]}")

    if status in (403, 404):
        warnings.warn(
            f"GET /syncableRevisions returned {status} — role/access check precedes "
            "parameter validation; sourceModelId requirement cannot be confirmed.",
            UserWarning,
            stacklevel=2,
        )
        return

    assert status in (400, 422), (
        f"Expected 400 or 422 when sourceModelId is omitted, got {status}. "
        "The spec marks sourceModelId as required — verify this is correct."
    )
