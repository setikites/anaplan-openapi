"""
Live API integration tests for the Anaplan CloudWorks API.

Resolves open questions documented in cloudworks/README.md:
  1. Which base URL is canonical: api.cloudworks.anaplan.com/2/0 or
     api.anaplan.com/cloudworks/2/0?
  2. Are both AnaplanAuthToken and Bearer token accepted?
  3. Is auth_method required on AzureBlob connection bodies?
  4. Do GET /integrations/connections, GET /integrations, and
     GET /integrationflows return the shapes documented in the spec?

Run with:
    uv run --env-file .env pytest tests/test_cloudworks_live.py --live

Credentials are read from .env at the repo root. Required variables:
    ANAPLAN_USERNAME  - username for basic auth (to obtain AnaplanAuthToken)
    ANAPLAN_PASSWORD  - password for basic auth

Optional variables:
    ANAPLAN_CLOUDWORKS_BASE_URL  - skip base URL probe and use this URL directly
                                   (e.g. https://api.cloudworks.anaplan.com/2/0)
    ANAPLAN_OAUTH_ACCESS_TOKEN   - pre-obtained OAuth Bearer token for Bearer probe
"""

import base64
import os
import pathlib
import warnings

import httpx
import pytest

_URL_PRIMARY = "https://api.cloudworks.anaplan.com/2/0"
_URL_ALT = "https://api.anaplan.com/cloudworks/2/0"

CLOUDWORKS_BASE_URL_OVERRIDE = os.getenv("ANAPLAN_CLOUDWORKS_BASE_URL")
AUTH_URL = "https://auth.anaplan.com"
SPEC_PATH = pathlib.Path(__file__).parent.parent / "cloudworks" / "cloudworks-openapi.json"


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
def cw_token():
    """AnaplanAuthToken for CloudWorks calls (module-scoped). Logs out on teardown."""
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


# ── Base URL probe ────────────────────────────────────────────────────────────

@pytest.mark.live
def test_cloudworks_base_url_probe(cw_token):
    """Determine which base URL the CloudWorks API is served from.

    Two candidate base URLs are documented in the spec:
      - https://api.cloudworks.anaplan.com/2/0  (per Apiary curl examples)
      - https://api.anaplan.com/cloudworks/2/0  (per Apiary production URL field)

    This test probes both and reports which one(s) respond with a recognised
    HTTP status. The canonical URL should be recorded in cloudworks/README.md
    and the spec's servers[] array updated accordingly.
    """
    if CLOUDWORKS_BASE_URL_OVERRIDE:
        pytest.skip(
            f"ANAPLAN_CLOUDWORKS_BASE_URL is set to {CLOUDWORKS_BASE_URL_OVERRIDE!r}; "
            "base URL probe skipped"
        )

    headers = {
        "Authorization": f"AnaplanAuthToken {cw_token}",
        "Accept": "application/json",
    }
    results = {}
    with httpx.Client() as client:
        for url in [_URL_PRIMARY, _URL_ALT]:
            try:
                r = client.get(f"{url}/integrations/connections", headers=headers, timeout=10)
                results[url] = r.status_code
            except httpx.ConnectError:
                results[url] = "CONNECT_ERROR"
            except httpx.TimeoutException:
                results[url] = "TIMEOUT"

    print(f"\nBase URL probe results: {results}")

    responding = [u for u, s in results.items() if isinstance(s, int)]
    if not responding:
        warnings.warn(
            f"Neither candidate base URL responded: {results}. "
            "CloudWorks may require a different network or region.",
            UserWarning,
            stacklevel=2,
        )
        return

    if len(responding) == 2:
        warnings.warn(
            f"Both candidate base URLs responded: {results}. "
            "Determine which is canonical and update servers[] in the spec.",
            UserWarning,
            stacklevel=2,
        )
    else:
        canonical = responding[0]
        warnings.warn(
            f"Canonical CloudWorks base URL confirmed: {canonical!r} "
            f"(status {results[canonical]}). "
            "Update servers[] in the spec and set ANAPLAN_CLOUDWORKS_BASE_URL in .env.",
            UserWarning,
            stacklevel=2,
        )


@pytest.fixture(scope="module")
def cw_base_url(cw_token):
    """Resolve and return the working CloudWorks base URL (module-scoped).

    Uses ANAPLAN_CLOUDWORKS_BASE_URL if set; otherwise probes both candidates
    and returns the first one that responds. Skips all dependents if neither responds.
    """
    if CLOUDWORKS_BASE_URL_OVERRIDE:
        return CLOUDWORKS_BASE_URL_OVERRIDE.rstrip("/")

    headers = {
        "Authorization": f"AnaplanAuthToken {cw_token}",
        "Accept": "application/json",
    }
    with httpx.Client() as client:
        for url in [_URL_PRIMARY, _URL_ALT]:
            try:
                r = client.get(f"{url}/integrations/connections", headers=headers, timeout=10)
                if isinstance(r.status_code, int):
                    return url
            except (httpx.ConnectError, httpx.TimeoutException):
                continue

    pytest.skip(
        "Neither CloudWorks base URL is reachable. "
        "Set ANAPLAN_CLOUDWORKS_BASE_URL in .env to override."
    )


# ── Authentication scheme probes ──────────────────────────────────────────────

@pytest.mark.live
def test_cloudworks_anaplan_auth_token_accepted(cw_token, cw_base_url):
    """AnaplanAuthToken is accepted by GET /integrations/connections.

    A 200 or 403 confirms the token was recognised. A 401 would mean
    AnaplanAuthToken is rejected for CloudWorks and the spec's security
    declaration needs revision.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{cw_base_url}/integrations/connections",
            headers={
                "Authorization": f"AnaplanAuthToken {cw_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /integrations/connections with AnaplanAuthToken: {response.status_code}")
    print(f"Body: {response.text[:200]}")

    assert response.status_code in (200, 403), (
        f"AnaplanAuthToken was rejected (got {response.status_code}); "
        "expected 200 (ok) or 403 (auth accepted, insufficient permission). "
        f"Body: {response.text[:200]}"
    )


@pytest.mark.live
def test_cloudworks_bearer_with_anaplan_token_probe(cw_token, cw_base_url):
    """Probes whether the Bearer scheme accepts an AnaplanAuthToken value.

    If 200 or 403 is returned, AnaplanAuthToken and Bearer are interchangeable
    on CloudWorks and BearerAuth must stay in the spec. A 401 means they are not.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{cw_base_url}/integrations/connections",
            headers={
                "Authorization": f"Bearer {cw_token}",
                "Accept": "application/json",
            },
        )

    status = response.status_code
    print(f"\nGET /integrations/connections with Bearer (AnaplanAuthToken value): {status}")

    if status in (200, 403):
        warnings.warn(
            f"Bearer scheme accepted an AnaplanAuthToken value on CloudWorks "
            f"(status {status}) — AnaplanAuthToken and Bearer are interchangeable; "
            "keep BearerAuth in the spec.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 401:
        warnings.warn(
            "Bearer scheme rejected AnaplanAuthToken value on CloudWorks (401) — "
            "Bearer requires a distinct OAuth 2.0 token.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"Bearer probe returned unexpected status {status} on CloudWorks.",
            UserWarning,
            stacklevel=2,
        )


@pytest.mark.live
def test_cloudworks_oauth_bearer_probe(cw_base_url):
    """Probes whether a real OAuth 2.0 Bearer token is accepted by CloudWorks.

    Requires ANAPLAN_OAUTH_ACCESS_TOKEN in .env. Skipped if absent.
    A 200 or 403 confirms BearerAuth is valid for CloudWorks.
    """
    oauth_token = os.getenv("ANAPLAN_OAUTH_ACCESS_TOKEN")
    if not oauth_token:
        pytest.skip("ANAPLAN_OAUTH_ACCESS_TOKEN not set")

    with httpx.Client() as client:
        response = client.get(
            f"{cw_base_url}/integrations/connections",
            headers={
                "Authorization": f"Bearer {oauth_token}",
                "Accept": "application/json",
            },
        )

    status = response.status_code
    print(f"\nGET /integrations/connections with OAuth Bearer token: {status}")

    if status in (200, 403):
        warnings.warn(
            f"OAuth Bearer token accepted on CloudWorks (status {status}) — "
            "BearerAuth spec declaration confirmed correct.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 401:
        warnings.warn(
            "OAuth Bearer token rejected on CloudWorks (401) — "
            "remove BearerAuth from the spec; AnaplanAuthToken is the only valid scheme.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"OAuth Bearer probe returned unexpected status {status} on CloudWorks.",
            UserWarning,
            stacklevel=2,
        )


# ── GET /integrations/connections ─────────────────────────────────────────────

@pytest.mark.live
def test_cloudworks_get_connections_responds(cw_token, cw_base_url):
    """GET /integrations/connections returns 200 and a recognisable envelope."""
    with httpx.Client() as client:
        response = client.get(
            f"{cw_base_url}/integrations/connections",
            headers={
                "Authorization": f"AnaplanAuthToken {cw_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /integrations/connections: {response.status_code}")
    print(f"Body: {response.text[:300]}")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text[:200]}"
    )


@pytest.mark.live
def test_cloudworks_get_connections_response_shape(cw_token, cw_base_url):
    """GET /integrations/connections response must include status and connections array.

    Verifies the envelope shape documented in the spec:
      { status: {...}, connections: [...] }
    Each connection item must have at least connectionId and connectionType.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{cw_base_url}/integrations/connections",
            headers={
                "Authorization": f"AnaplanAuthToken {cw_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /integrations/connections (shape): {response.status_code}")
    assert response.status_code == 200, f"Unexpected {response.status_code}: {response.text[:200]}"

    body = response.json()
    assert "connections" in body, (
        "Response must have a top-level 'connections' key (matches spec schema)"
    )
    assert isinstance(body["connections"], list), "'connections' must be an array"

    for i, conn in enumerate(body["connections"]):
        assert "connectionId" in conn, f"connections[{i}] missing 'connectionId'"
        assert "connectionType" in conn, f"connections[{i}] missing 'connectionType'"
        assert conn["connectionType"] in ("AmazonS3", "GoogleBigQuery", "AzureBlob"), (
            f"connections[{i}].connectionType {conn['connectionType']!r} is not a "
            "documented enum value"
        )


# ── Azure Blob auth_method probe ──────────────────────────────────────────────

@pytest.mark.live
def test_cloudworks_azure_blob_auth_method_required_probe(cw_token, cw_base_url):
    """Probes whether auth_method is required on AzureBlob connection bodies.

    Sends a POST /integrations/connections with a well-formed AzureBlob body
    that intentionally omits auth_method (the pre-update shape). The expected
    response is:
      - 400  → auth_method is required; our spec addition is correct.
      - 200  → auth_method is NOT required; the spec should remove it from
               required[] (and a connection was created — check the warnings).
      - 403  → insufficient permission to create connections; inconclusive.

    A fake storageAccountName and sasToken are used so that even if the API
    accepts the body, no real storage is accessible. The connection ID is
    emitted as a warning if a 200 is returned so it can be cleaned up manually.
    """
    probe_body = {
        "type": "AzureBlob",
        "body": {
            "name": "live-test-probe-no-auth-method",
            "storageAccountName": "liveprobestorageaccount",
            "sasToken": "sv=9999-01-01&probe=true",
            "containerName": "live-test-probe-container",
        },
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{cw_base_url}/integrations/connections",
            json=probe_body,
            headers={
                "Authorization": f"AnaplanAuthToken {cw_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    status = response.status_code
    print(f"\nPOST /integrations/connections (no auth_method): {status}")
    print(f"Body: {response.text[:300]}")

    if status == 400:
        warnings.warn(
            "POST without auth_method returned 400 — auth_method is confirmed "
            "required on AzureBlob connections; spec required[] is correct.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 200:
        connection_id = response.json().get("connectionId", "<unknown>")
        warnings.warn(
            f"POST without auth_method returned 200 (connectionId={connection_id!r}) — "
            "auth_method is NOT required by the API; remove it from required[] in the spec. "
            "MANUAL CLEANUP NEEDED: delete this connection via "
            f"DELETE /integrations/connections/{connection_id}.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 403:
        warnings.warn(
            "POST /integrations/connections returned 403 — insufficient permission "
            "to create connections; auth_method requirement cannot be confirmed. "
            "Run with a CloudWorks admin account to complete this probe.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"POST /integrations/connections probe returned unexpected status {status}. "
            f"Body: {response.text[:200]}",
            UserWarning,
            stacklevel=2,
        )


# ── GET /integrations ─────────────────────────────────────────────────────────

@pytest.mark.live
def test_cloudworks_get_integrations_responds(cw_token, cw_base_url):
    """GET /integrations with pagination params returns 200.

    Pagination params are required in large tenants — calling without offset/limit
    can time out when the tenant has hundreds of integrations.
    """
    with httpx.Client(timeout=30) as client:
        response = client.get(
            f"{cw_base_url}/integrations",
            params={"offset": 0, "limit": 10},
            headers={
                "Authorization": f"AnaplanAuthToken {cw_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /integrations?offset=0&limit=10: {response.status_code}")
    print(f"Body: {response.text[:300]}")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text[:200]}"
    )


@pytest.mark.live
def test_cloudworks_get_integrations_response_shape(cw_token, cw_base_url):
    """GET /integrations response must include status, integrations array, and meta.paging.

    Verifies the envelope and paging shapes from the spec.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{cw_base_url}/integrations",
            params={"offset": 0, "limit": 10},
            headers={
                "Authorization": f"AnaplanAuthToken {cw_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /integrations?offset=0&limit=10 (shape): {response.status_code}")
    assert response.status_code == 200, f"Unexpected {response.status_code}: {response.text[:200]}"

    body = response.json()
    assert "integrations" in body, "Response must have a top-level 'integrations' key"
    assert isinstance(body["integrations"], list), "'integrations' must be an array"

    paging = body.get("meta", {}).get("paging")
    if paging is None:
        warnings.warn(
            "GET /integrations did not return meta.paging — may be absent when "
            "result set is empty; spec's PagingMeta shape cannot be confirmed.",
            UserWarning,
            stacklevel=2,
        )
    else:
        for field in ("currentPageSize", "totalSize", "offset"):
            assert field in paging, (
                f"meta.paging is missing required field {field!r} "
                "(PagingMeta schema requires it)"
            )


# ── GET /integrationflows ─────────────────────────────────────────────────────

@pytest.mark.live
def test_cloudworks_get_integration_flows_responds(cw_token, cw_base_url):
    """GET /integrationflows returns 200 and an integrationFlows array."""
    with httpx.Client() as client:
        response = client.get(
            f"{cw_base_url}/integrationflows",
            headers={
                "Authorization": f"AnaplanAuthToken {cw_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /integrationflows: {response.status_code}")
    print(f"Body: {response.text[:300]}")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text[:200]}"
    )

    body = response.json()
    assert "integrationFlows" in body, (
        "Response must have a top-level 'integrationFlows' key (matches spec schema)"
    )
    assert isinstance(body["integrationFlows"], list), "'integrationFlows' must be an array"


# ── Fixture: first available integrationId ────────────────────────────────────

@pytest.fixture(scope="module")
def cw_first_integration(cw_token, cw_base_url):
    """Return the first IntegrationSummary from GET /integrations, or skip if none.

    Used by tests that need a real integrationId to probe /integrations/{id}
    and /integrations/runs/{id}. Uses a 30-second timeout because large tenants
    are slow to respond even with limit=1.
    """
    with httpx.Client(timeout=30) as client:
        response = client.get(
            f"{cw_base_url}/integrations",
            params={"offset": 0, "limit": 1},
            headers={
                "Authorization": f"AnaplanAuthToken {cw_token}",
                "Accept": "application/json",
            },
        )
    if response.status_code != 200:
        pytest.skip(f"GET /integrations returned {response.status_code}; cannot get integrationId")
    integrations = response.json().get("integrations", [])
    if not integrations:
        pytest.skip("No integrations available in this tenant; skipping integration-detail probes")
    return integrations[0]


# ── GET /integrations/{integrationId} ────────────────────────────────────────

@pytest.mark.live
def test_cloudworks_get_integration_by_id_shape(cw_token, cw_base_url, cw_first_integration):
    """GET /integrations/{integrationId} returns IntegrationDetail shape.

    Observes:
    - Which fields are present on a real IntegrationDetail response
    - Whether 'version' is present and what value it carries
    - Whether 'latestRun' appears and what sub-fields it contains
    - Whether 'jobs' appears (absent for process integrations)

    Findings should inform the spec's IntegrationDetail property descriptions.
    """
    integration_id = cw_first_integration.get("integrationId")
    assert integration_id, "cw_first_integration must have an integrationId"

    with httpx.Client() as client:
        response = client.get(
            f"{cw_base_url}/integrations/{integration_id}",
            headers={
                "Authorization": f"AnaplanAuthToken {cw_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /integrations/{integration_id}: {response.status_code}")
    print(f"Body: {response.text[:500]}")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text[:200]}"
    )

    body = response.json()
    assert "integration" in body or "status" in body, (
        "Response must have at least 'integration' or 'status' key"
    )
    integration = body.get("integration", body)

    # version field — confirmed "2.0" in live testing
    assert integration.get("version") == "2.0", (
        f"IntegrationDetail.version expected '2.0', got {integration.get('version')!r}"
    )

    # integrationType — confirmed enum in live testing
    int_type = integration.get("integrationType")
    if int_type is not None:
        assert int_type in ("Process", "Export", "Import"), (
            f"IntegrationDetail.integrationType {int_type!r} is not a known enum value"
        )

    # latestRun — check triggerSource enum
    latest_run = integration.get("latestRun")
    if latest_run:
        trigger = latest_run.get("triggerSource")
        if trigger is not None:
            assert trigger in ("scheduled", "manual", "scheduled_inf"), (
                f"latestRun.triggerSource {trigger!r} is not a known enum value"
            )
        warnings.warn(
            f"IntegrationDetail.latestRun keys: {sorted(latest_run.keys())}, "
            f"triggerSource={trigger!r}, executionErrorCode={latest_run.get('executionErrorCode')!r}",
            UserWarning, stacklevel=2,
        )

    # jobs field — absent for Process, present for Export/Import
    if "jobs" in integration:
        warnings.warn(
            f"IntegrationDetail.jobs present, len={len(integration['jobs'])} — "
            f"integrationType={int_type!r}",
            UserWarning, stacklevel=2,
        )
    elif integration.get("processId"):
        warnings.warn(
            "IntegrationDetail.jobs absent and processId present — Process integration confirmed.",
            UserWarning, stacklevel=2,
        )


# ── GET /integrations/runs/{integrationId} ───────────────────────────────────

@pytest.mark.live
def test_cloudworks_get_run_history_shape(cw_token, cw_base_url, cw_first_integration):
    """GET /integrations/runs/{integrationId} returns RunRecord shape.

    Observes:
    - The structure of RunRecord items in the history_of_runs.runs array
    - Whether 'lastRun' is present and whether it differs from 'endDate'
    - What 'message' and 'executionErrorCode' contain on success vs. failure

    Findings should inform RunRecord property descriptions in the spec.
    """
    integration_id = cw_first_integration.get("integrationId")
    assert integration_id, "cw_first_integration must have an integrationId"

    with httpx.Client() as client:
        response = client.get(
            f"{cw_base_url}/integrations/runs/{integration_id}",
            params={"offset": 0, "limit": 3},
            headers={
                "Authorization": f"AnaplanAuthToken {cw_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /integrations/runs/{integration_id}: {response.status_code}")
    print(f"Body: {response.text[:500]}")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text[:200]}"
    )

    body = response.json()
    history = body.get("history_of_runs", {})
    runs = history.get("runs", [])

    if not runs:
        warnings.warn(
            "GET /integrations/runs returned no runs — "
            "RunRecord shape cannot be confirmed from this integration.",
            UserWarning, stacklevel=2,
        )
        return

    run = runs[0]

    # lastRun is a Unix timestamp integer (confirmed in live testing)
    assert isinstance(run.get("lastRun"), int), (
        f"RunRecord.lastRun expected integer Unix timestamp, got {run.get('lastRun')!r}"
    )

    # triggerSource enum — confirmed values: scheduled, manual, scheduled_inf
    trigger = run.get("triggerSource")
    if trigger is not None:
        assert trigger in ("scheduled", "manual", "scheduled_inf"), (
            f"RunRecord.triggerSource {trigger!r} is not a known enum value"
        )

    warnings.warn(
        f"RunRecord keys: {sorted(run.keys())}, "
        f"lastRun={run.get('lastRun')!r} (Unix timestamp), "
        f"triggerSource={trigger!r}, "
        f"executionErrorCode={run.get('executionErrorCode')!r}",
        UserWarning, stacklevel=2,
    )

    schema_url = body.get("meta", {}).get("schema")
    if schema_url:
        warnings.warn(
            f"PagingMeta.schema URL: {schema_url!r}",
            UserWarning, stacklevel=2,
        )


# ── GET /integrations/notification/{notificationId} ──────────────────────────

@pytest.mark.live
def test_cloudworks_get_notification_shape(cw_token, cw_base_url, cw_first_integration):
    """GET /integrations/notification/{notificationId} returns NotificationConfig shape.

    Requires the first integration to have a notificationId. Skips otherwise.
    Observes the full NotificationConfig structure including resolved user details.
    """
    notification_id = cw_first_integration.get("notificationId")
    if not notification_id:
        pytest.skip(
            "First integration has no notificationId — "
            "cannot probe GET /integrations/notification/{notificationId}"
        )

    with httpx.Client() as client:
        response = client.get(
            f"{cw_base_url}/integrations/notification/{notification_id}",
            headers={
                "Authorization": f"AnaplanAuthToken {cw_token}",
                "Accept": "application/json",
            },
        )

    print(f"\nGET /integrations/notification/{notification_id}: {response.status_code}")
    print(f"Body: {response.text[:500]}")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text[:200]}"
    )

    body = response.json()
    notifications = body.get("notifications", {})
    warnings.warn(
        f"NotificationConfig keys observed: {sorted(notifications.keys()) if isinstance(notifications, dict) else type(notifications).__name__}",
        UserWarning, stacklevel=2,
    )

    config = notifications.get("config", []) if isinstance(notifications, dict) else []
    if config:
        entry = config[0]
        warnings.warn(
            f"NotificationConfig.config[0] keys: {sorted(entry.keys())}, "
            f"type={entry.get('type')!r}, users[0]={entry.get('users', [{}])[0] if entry.get('users') else 'none'}",
            UserWarning, stacklevel=2,
        )
