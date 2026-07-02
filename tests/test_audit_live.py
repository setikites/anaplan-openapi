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
import time
import warnings

import httpx
import jsonschema
import pytest

from oauth.token_keyring import load_token

AUDIT_BASE_URL = os.getenv(
    "ANAPLAN_AUDIT_BASE_URL", "https://audit.anaplan.com/audit/api/1"
)
AUTH_URL = "https://auth.anaplan.com"
SPEC_PATH = pathlib.Path(__file__).parent.parent / "audit" / "audit-openapi.json"

with open(SPEC_PATH, encoding="utf-8") as _f:
    _SPEC = json.load(_f)
_AUDIT_EVENT_SCHEMA = _SPEC["components"]["schemas"]["AuditEvent"]
_AUDIT_PAGING_SCHEMA = _SPEC["components"]["schemas"]["AuditPaging"]
_TYPE_ENUM = next(
    p for p in _SPEC["paths"]["/events"]["get"]["parameters"] if p["name"] == "type"
)["schema"]["enum"]

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
    """Auth token for audit calls, sent as AnaplanAuthToken (module-scoped).

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


@pytest.fixture(scope="module")
def audit_events(audit_token):
    """One real GET /events page for contract checks (module-scoped).

    Requires a role-enabled token. Skips cleanly (rather than asserting) when the
    caller lacks the Tenant Auditor role, so the suite still runs end-to-end with
    a role-less token — the event-contract tests simply don't execute.
    """
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        response = client.get(
            f"{AUDIT_BASE_URL}/events",
            params={"intervalInHours": "24", "type": "all"},
            headers={
                "Authorization": f"AnaplanAuthToken {audit_token}",
                "Accept": "application/json",
            },
        )

    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify event contract")

    assert response.status_code == 200, (
        f"GET /events returned {response.status_code}: {response.text[:200]}"
    )
    return response.json()


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

# ── CEF (text/plain) output (issue #61) ───────────────────────────────────────

def _get_cef(token, **params):
    """GET /events with Accept: text/plain (CEF) and a role-enabled token."""
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        return client.get(
            f"{AUDIT_BASE_URL}/events",
            params=params,
            headers={
                "Authorization": f"AnaplanAuthToken {token}",
                "Accept": "text/plain",
            },
        )


@pytest.mark.live
def test_audit_get_events_returns_cef_text_plain(audit_token):
    """Accept: text/plain returns 200 CEF output — text/plain, non-JSON, CEF header.

    Confirms the spec's text/plain media-type declaration against real output and
    that a CEF line carries the event identity as key=value extension fields.
    """
    response = _get_cef(audit_token, type="all", intervalInHours="1")
    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify CEF output")

    assert response.status_code == 200, (
        f"expected 200 for Accept: text/plain, got {response.status_code}: "
        f"{response.text[:200]}"
    )

    content_type = response.headers.get("content-type", "")
    assert "text/plain" in content_type, (
        f"expected text/plain content-type, got {content_type!r}"
    )

    body = response.text
    assert not body.lstrip().startswith(("{", "[")), (
        "expected non-JSON CEF output, but body looks like JSON"
    )

    lines = [ln for ln in body.splitlines() if ln.strip()]
    assert lines, "expected >=1 CEF line in the last hour of events"

    # Each line is: "<ISO-8601 timestamp>  CEF:0|Anaplan, Inc.||null|<eventTypeId>
    # |<message>|<key=value extensions>". Find a representative CEF line.
    cef_line = next((ln for ln in lines if "CEF:0|" in ln), None)
    assert cef_line is not None, (
        f"no CEF header found in text/plain output; first line: {lines[0][:200]!r}"
    )
    assert "CEF:0|Anaplan, Inc.|" in cef_line, (
        f"unexpected CEF header vendor field: {cef_line[:120]!r}"
    )
    # The CEF extension carries the event identity as key=value pairs.
    extension = cef_line.split("CEF:0|", 1)[1]
    for key in ("id=", "userId="):
        assert key in extension, (
            f"CEF extension missing {key!r} field: {extension[:200]!r}"
        )


@pytest.mark.live
def test_audit_cef_output_is_not_paginated(audit_token):
    """CEF (text/plain) output ignores limit and returns the full result set.

    Confirmed discrepancy (live testing): unlike the JSON envelope, the text/plain
    response is not paged — it returns every matching event as CEF lines regardless
    of limit, and carries no meta/paging block. Uses the low-volume `conn_mgmt`
    type so the full CEF body stays small and deterministic. Documented in
    audit/README.md and the spec's text/plain media-type description.
    """
    page_size = 5
    cef = _get_cef(audit_token, type="conn_mgmt", limit=str(page_size))
    if _is_no_role_401(cef):
        pytest.skip("User lacks Tenant Auditor role — cannot verify CEF paging")
    assert cef.status_code == 200
    cef_lines = len([ln for ln in cef.text.splitlines() if ln.strip()])

    json_resp = _get_events(audit_token, type="conn_mgmt", limit=str(page_size))
    records = json_resp.json()["response"]
    json_total = json_resp.json()["meta"]["paging"]["totalSize"]

    if json_total <= page_size:
        pytest.skip("Too few conn_mgmt events to demonstrate CEF non-paging")

    # JSON honors the limit; CEF ignores it and returns the whole set.
    assert len(records) == page_size, "JSON envelope should honor the limit"
    assert cef_lines > page_size, (
        f"CEF appears limited to {cef_lines} line(s) despite {json_total} matching "
        f"events — expected the full (unpaginated) set"
    )
    assert cef_lines >= json_total * 0.8, (
        f"CEF returned {cef_lines} lines but ~{json_total} events match; expected "
        "the full set, not a paged subset"
    )


# ── Event record contract (issue #59) ─────────────────────────────────────────

@pytest.mark.live
def test_audit_event_fields_are_all_documented(audit_events):
    """Every field a live event returns must be documented in the AuditEvent schema.

    Guards against the spec silently omitting fields the API actually returns.
    """
    records = audit_events["response"]
    assert records, "expected >=1 audit event record to verify the field contract"

    documented = set(_AUDIT_EVENT_SCHEMA["properties"])
    returned = set().union(*(record.keys() for record in records))
    undocumented = returned - documented

    assert not undocumented, (
        "live events return fields not documented in the AuditEvent schema: "
        f"{sorted(undocumented)}"
    )


@pytest.mark.live
def test_audit_event_records_validate_against_schema(audit_events):
    """Each live event record conforms to the AuditEvent schema (declared types).

    Catches type drift between the spec and the real API — e.g. a field the spec
    types as a string that the API returns as an integer.
    """
    records = audit_events["response"]
    assert records, "expected >=1 audit event record to validate"

    for index, record in enumerate(records):
        try:
            jsonschema.validate(record, _AUDIT_EVENT_SCHEMA)
        except jsonschema.ValidationError as exc:
            pytest.fail(
                f"event record {index} (id={record.get('id')}) violates the "
                f"AuditEvent schema at {list(exc.absolute_path)}: {exc.message}"
            )


# Core fields that identify every audit event, with their documented JSON types.
# Confirmed present on every record across a 7-day live sample (issue #59).
_CORE_EVENT_FIELDS = {
    "id": int,
    "eventTypeId": str,
    "userId": str,
    "message": str,
    "success": bool,
    "eventDate": int,
    "checksum": str,
}


@pytest.mark.live
def test_audit_event_has_core_fields_with_documented_types(audit_events):
    """Every event carries the core identity fields with their documented types.

    These are the always-present fields named in the AuditEvent contract; the API
    must return them on every record for downstream SIEM consumers.
    """
    records = audit_events["response"]
    assert records, "expected >=1 audit event record to verify core fields"

    for index, record in enumerate(records):
        for field, expected_type in _CORE_EVENT_FIELDS.items():
            assert field in record, (
                f"event record {index} (id={record.get('id')}) is missing core "
                f"field {field!r}"
            )
            value = record[field]
            # bool is a subclass of int; keep the integer fields strictly non-bool.
            if expected_type is int:
                ok = isinstance(value, int) and not isinstance(value, bool)
            else:
                ok = isinstance(value, expected_type)
            assert ok, (
                f"event record {index} field {field!r} should be "
                f"{expected_type.__name__}, got {type(value).__name__} ({value!r})"
            )


# ── Filtering and pagination (issue #60) ──────────────────────────────────────

def _get_events(token, **params):
    """GET /events with the given query params and a role-enabled token."""
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        return client.get(
            f"{AUDIT_BASE_URL}/events",
            params=params,
            headers={
                "Authorization": f"AnaplanAuthToken {token}",
                "Accept": "application/json",
            },
        )


def _paging_or_skip(response):
    """Return meta.paging from a 200 response, or skip if the role is absent."""
    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify filtering/paging")
    assert response.status_code == 200, (
        f"GET /events returned {response.status_code}: {response.text[:200]}"
    )
    return response.json()["meta"]["paging"]


@pytest.mark.live
def test_audit_paging_fields_are_all_documented(audit_token):
    """Every field the API returns in meta.paging is documented in AuditPaging.

    Fetches a middle page (offset > 0 with more results after) so the full paging
    block — including nextOffset/nextUrl and previousUrl — is exercised.
    """
    response = _get_events(
        audit_token, type="all", intervalInHours="168", limit="3", offset="3"
    )
    paging = _paging_or_skip(response)

    documented = set(_AUDIT_PAGING_SCHEMA["properties"])
    undocumented = set(paging) - documented

    assert not undocumented, (
        "meta.paging returns fields not documented in AuditPaging: "
        f"{sorted(undocumented)}"
    )


@pytest.fixture(scope="module")
def audit_30d_window():
    """A 29-day dateFrom/dateTo window (the server caps the range at 30 days)."""
    now = int(time.time() * 1000)
    return {"dateFrom": str(now - 29 * 24 * 3600 * 1000), "dateTo": str(now)}


@pytest.fixture(scope="module")
def audit_all_total(audit_token, audit_30d_window):
    """totalSize for type=all over the window — the baseline for recognition checks."""
    response = _get_events(audit_token, type="all", limit="1", **audit_30d_window)
    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify type recognition")
    assert response.status_code == 200, response.text[:200]
    return response.json()["meta"]["paging"]["totalSize"]


@pytest.mark.live
@pytest.mark.parametrize("event_type", _TYPE_ENUM)
def test_audit_type_enum_value_is_recognized(
    audit_token, audit_30d_window, audit_all_total, event_type
):
    """Every value in the spec's `type` enum is recognized by the server (filters).

    A recognized type filters to a strict subset of events; an unrecognised value
    is silently treated as `all` and returns the full count (confirmed discrepancy
    — the enum is not enforced). Asserting each enum value filters guards against
    unverified values landing in the enum (e.g. `workflow`, which the server
    ignores and which is deliberately omitted).

    Types tied to products not used by the tenant (e.g. `byok`, `plan_iq`,
    `forecaster`) legitimately return zero — still a strict subset of `all`.
    """
    response = _get_events(audit_token, type=event_type, limit="1", **audit_30d_window)
    paging = _paging_or_skip(response)
    total = paging["totalSize"]
    assert isinstance(total, int) and total >= 0

    if event_type == "all":
        return
    assert total < audit_all_total, (
        f"type={event_type!r} returned {total}, the same as 'all' "
        f"({audit_all_total}) — the server does not recognise it as a filter, so "
        f"it should not be in the enum"
    )


@pytest.mark.live
def test_audit_invalid_type_is_not_rejected(audit_token):
    """An unrecognised `type` value is not rejected — the server treats it as `all`.

    Confirmed discrepancy (live testing): the documented enum is not enforced
    server-side; an unknown value returns 200 with the full (unfiltered) result
    set rather than a 4xx. Documented in audit/README.md.
    """
    response = _get_events(
        audit_token, type="not_a_real_type", intervalInHours="168", limit="5"
    )
    invalid_paging = _paging_or_skip(response)

    all_response = _get_events(
        audit_token, type="all", intervalInHours="168", limit="5"
    )
    all_paging = all_response.json()["meta"]["paging"]

    # totalSize drifts slightly as new events arrive; assert the unknown type maps
    # to the unfiltered 'all' count rather than filtering to a smaller set.
    assert invalid_paging["totalSize"] >= all_paging["totalSize"] * 0.95, (
        "expected an unknown type to behave like 'all' (no filtering), but "
        f"totalSize {invalid_paging['totalSize']} << all {all_paging['totalSize']}"
    )


@pytest.mark.live
def test_audit_date_range_filters_to_window(audit_token):
    """dateFrom/dateTo (Unix-ms) constrain results to events within the window."""
    now = int(time.time() * 1000)
    date_from = now - 24 * 3600 * 1000  # last 24h
    date_to = now

    response = _get_events(
        audit_token, type="all", dateFrom=str(date_from), dateTo=str(date_to), limit="50"
    )
    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify date-range filter")
    assert response.status_code == 200
    events = response.json()["response"]
    assert events, "expected >=1 event in the last 24h to verify date-range filtering"

    out_of_range = [
        e["eventDate"] for e in events if not (date_from <= e["eventDate"] <= date_to)
    ]
    assert not out_of_range, (
        f"dateFrom/dateTo window not honored — {len(out_of_range)} events fell "
        f"outside [{date_from}, {date_to}]: {out_of_range[:3]}"
    )


@pytest.mark.live
def test_audit_interval_hours_returns_recent_events(audit_token):
    """intervalInHours returns a rolling window of the previous N hours of events."""
    interval_hours = 24
    now = int(time.time() * 1000)
    # Generous slack for server/client clock skew and the createdDate lag.
    earliest = now - (interval_hours + 1) * 3600 * 1000
    latest = now + 5 * 60 * 1000

    response = _get_events(audit_token, type="all", intervalInHours=str(interval_hours), limit="50")
    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify interval window")
    assert response.status_code == 200
    events = response.json()["response"]
    assert events, "expected >=1 event in the last 24h to verify the interval window"

    out_of_window = [e["eventDate"] for e in events if not (earliest <= e["eventDate"] <= latest)]
    assert not out_of_window, (
        f"intervalInHours={interval_hours} returned {len(out_of_window)} events "
        f"outside the rolling window: {out_of_window[:3]}"
    )


@pytest.mark.live
def test_audit_limit_offset_paginates_disjoint_pages(audit_token):
    """limit caps page size; offset advances; consecutive pages are disjoint.

    Also confirms the paging cursors: page 1 exposes nextOffset/nextUrl, and
    page 2 (offset > 0) exposes previousUrl.
    """
    page_size = 3
    page0 = _get_events(
        audit_token, type="all", intervalInHours="168", limit=str(page_size), offset="0"
    )
    paging0 = _paging_or_skip(page0)
    records0 = page0.json()["response"]

    assert len(records0) == page_size, f"limit not honored: got {len(records0)} records"
    assert paging0["currentPageSize"] == page_size
    assert paging0["offSet"] == 0
    if paging0["totalSize"] > page_size:
        assert paging0["nextOffset"] == page_size
        assert "nextUrl" in paging0
        assert "previousUrl" not in paging0, "first page should not expose previousUrl"

    page1 = _get_events(
        audit_token, type="all", intervalInHours="168", limit=str(page_size), offset=str(page_size)
    )
    assert page1.status_code == 200
    paging1 = page1.json()["meta"]["paging"]
    records1 = page1.json()["response"]

    assert paging1["offSet"] == page_size
    assert "previousUrl" in paging1, "second page should expose previousUrl"

    ids0 = {e["id"] for e in records0}
    ids1 = {e["id"] for e in records1}
    assert ids0.isdisjoint(ids1), (
        f"pages overlap — offset paging not advancing: {ids0 & ids1}"
    )


@pytest.mark.live
def test_audit_limit_above_documented_max_is_accepted(audit_token):
    """A limit above the documented 10000 cap is accepted, not enforced.

    Confirmed discrepancy (live testing): the API description says the limit
    "cannot exceed 10000", but the server honors larger limits and returns more
    than 10000 records. The spec's hard `maximum` constraint was relaxed to match;
    this test locks the observed behavior. Documented in audit/README.md.
    """
    over_limit = 10001
    response = _get_events(
        audit_token, type="all", intervalInHours="168", limit=str(over_limit)
    )
    paging = _paging_or_skip(response)

    records = response.json()["response"]
    assert paging["currentPageSize"] > 10000, (
        f"expected the server to honor limit>10000, got currentPageSize="
        f"{paging['currentPageSize']}"
    )
    assert len(records) > 10000, (
        f"expected >10000 records for limit={over_limit}, got {len(records)}"
    )


@pytest.mark.live
def test_audit_date_range_over_30_days_is_rejected(audit_token):
    """A dateFrom/dateTo span wider than 30 days is rejected with 400.

    Confirmed via live testing: the server caps the date range at 30 days and
    returns 400 FAILURE_BAD_REQUEST. Documented in the spec and audit/README.md.
    """
    now = int(time.time() * 1000)
    date_from = now - 31 * 24 * 3600 * 1000  # 31-day span exceeds the cap

    response = _get_events(
        audit_token, type="all", dateFrom=str(date_from), dateTo=str(now), limit="1"
    )
    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify date-range cap")

    assert response.status_code == 400, (
        f"expected 400 for a >30-day range, got {response.status_code}: "
        f"{response.text[:200]}"
    )
    assert "30 day" in response.text.lower(), (
        f"expected a 30-day-cap message, got: {response.text[:200]}"
    )


@pytest.mark.live
def test_audit_interval_hours_over_30_days_is_rejected(audit_token):
    """intervalInHours above 720 (30 days) is rejected with the same 30-day cap.

    The 30-day range cap applies to the rolling window too (confirmed: 720 is
    accepted, 744 returns 400). Documented in the spec and audit/README.md.
    """
    response = _get_events(audit_token, type="all", intervalInHours="744", limit="1")
    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify interval cap")

    assert response.status_code == 400, (
        f"expected 400 for intervalInHours>720, got {response.status_code}: "
        f"{response.text[:200]}"
    )
    assert "30 day" in response.text.lower(), (
        f"expected a 30-day-cap message, got: {response.text[:200]}"
    )


@pytest.mark.live
def test_audit_no_date_filter_defaults_to_30_day_window(audit_token):
    """With no date filter, the server returns the previous 30 days, not all history.

    Confirmed via live testing: an otherwise-unfiltered request is implicitly
    bounded to the last 30 days. Uses the low-volume `conn_mgmt` type so the full
    set is small. Documented in the spec and audit/README.md.
    """
    now = int(time.time() * 1000)
    response = _get_events(audit_token, type="conn_mgmt", limit="10000")  # no date filter
    if _is_no_role_401(response):
        pytest.skip("User lacks Tenant Auditor role — cannot verify default window")
    assert response.status_code == 200
    events = response.json()["response"]
    if not events:
        pytest.skip("No conn_mgmt events to verify the default window")

    oldest = min(e["eventDate"] for e in events)
    # The default window is the previous 30 days; allow a day of slack.
    assert oldest >= now - 31 * 24 * 3600 * 1000, (
        f"oldest unfiltered event is {(now - oldest) / 86400000:.1f} days old — "
        "expected the default window to bound results to ~30 days"
    )
