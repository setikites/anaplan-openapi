"""
Live API integration tests for Anaplan SCIM API.

Probes which authentication schemes the SCIM /Users endpoint actually accepts,
resolving the ambiguity between Apiary docs (Basic, AnaplanAuthToken, Bearer)
and RFC 7644 (Bearer only). See issue #44.

Run with:
    uv run --env-file .env pytest tests/test_scim_live.py --live

Credentials are read from .env at the repo root. Required variables:
    ANAPLAN_USERNAME       - username for basic auth (to obtain AnaplanAuthToken)
    ANAPLAN_PASSWORD       - password for basic auth

Optional variables:
    ANAPLAN_OAUTH_ACCESS_TOKEN - pre-obtained OAuth 2.0 access token for Bearer probe
    ANAPLAN_SCIM_BASE_URL      - override SCIM base URL (default: https://api.anaplan.com/scim/1/0/v2)
"""

import base64
import os
import warnings

import httpx
import pytest

AUTH_URL = "https://auth.anaplan.com"
SCIM_BASE_URL = os.getenv(
    "ANAPLAN_SCIM_BASE_URL", "https://api.anaplan.com/scim/1/0/v2"
)


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
def scim_token():
    """AnaplanAuthToken for SCIM calls (module-scoped). Logs out on teardown."""
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


@pytest.fixture(scope="module")
def admin_token():
    """AnaplanAuthToken for a User Admin account (issue #180 role confirmation).

    Distinct from scim_token (a Standard User with no elevated role) so the two
    can be compared against the same endpoints. Logs out on teardown.
    """
    username = os.getenv("ANAPLAN_ADMIN_USERNAME")
    password = os.getenv("ANAPLAN_ADMIN_PASSWORD")
    if not username or not password:
        pytest.skip("ANAPLAN_ADMIN_USERNAME and ANAPLAN_ADMIN_PASSWORD not set")

    token = _get_anaplan_token(username, password)
    if not token:
        pytest.skip("Failed to obtain AnaplanAuthToken for admin account")

    yield token

    with httpx.Client() as client:
        client.post(
            f"{AUTH_URL}/token/logout",
            headers={"Authorization": f"AnaplanAuthToken {token}"},
        )


# ── Tracer bullet ────────────────────────────────────────────────────────────

@pytest.mark.live
def test_scim_users_anaplan_auth_token_accepted(scim_token):
    """AnaplanAuthToken is accepted by the SCIM /Users endpoint.

    A 200 or 403 confirms the token was recognized (403 = auth ok, no USER_ADMIN
    role). A 401 would mean AnaplanAuthToken is rejected, which would invalidate
    the spec's AnaplanAuthToken security scheme declaration.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{SCIM_BASE_URL}/Users",
            headers={"Authorization": f"AnaplanAuthToken {scim_token}"},
        )

    print(f"\nGET /Users with AnaplanAuthToken: {response.status_code}")
    assert response.status_code in (200, 403), (
        f"AnaplanAuthToken was rejected (got {response.status_code}); "
        "expected 200 (ok) or 403 (auth accepted, no USER_ADMIN role)"
    )


# ── Probe: Bearer with AnaplanAuthToken value ────────────────────────────────

@pytest.mark.live
def test_scim_users_bearer_with_anaplan_token_probe(scim_token):
    """Probes whether the Bearer scheme accepts an AnaplanAuthToken value.

    Hypothesis: Anaplan tokens are not OAuth 2.0 tokens, so Bearer {anaplan_token}
    is likely rejected with 401. If 200/403 is returned, the SCIM endpoint treats
    AnaplanAuthToken and Bearer interchangeably — BearerAuth must stay in the spec.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{SCIM_BASE_URL}/Users",
            headers={"Authorization": f"Bearer {scim_token}"},
        )

    status = response.status_code
    print(f"\nGET /Users with Bearer (AnaplanAuthToken value): {status}")

    if status in (200, 403):
        warnings.warn(
            f"Bearer scheme accepted an AnaplanAuthToken value on GET /Users "
            f"(status {status}) — AnaplanAuthToken and Bearer are interchangeable "
            "on the SCIM endpoint; keep BearerAuth in the spec.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 401:
        warnings.warn(
            "Bearer scheme rejected AnaplanAuthToken value (401) — "
            "Bearer on SCIM requires a distinct OAuth 2.0 token.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"Bearer probe returned unexpected status {status} on GET /Users.",
            UserWarning,
            stacklevel=2,
        )


# ── Probe: HTTP Basic directly against SCIM ──────────────────────────────────

@pytest.mark.live
def test_scim_users_http_basic_probe():
    """Probes whether HTTP Basic auth is accepted directly by the SCIM endpoint.

    Apiary docs listed Basic as an option; RFC 7644 specifies Bearer only.
    Hypothesis: Basic is rejected with 401. If 200/403 is returned, the spec
    must add a BasicAuth security scheme.
    """
    username = os.getenv("ANAPLAN_USERNAME")
    password = os.getenv("ANAPLAN_PASSWORD")
    if not username or not password:
        pytest.skip("ANAPLAN_USERNAME and ANAPLAN_PASSWORD not set")

    auth_b64 = base64.b64encode(f"{username}:{password}".encode()).decode()

    with httpx.Client() as client:
        response = client.get(
            f"{SCIM_BASE_URL}/Users",
            headers={"Authorization": f"Basic {auth_b64}"},
        )

    status = response.status_code
    print(f"\nGET /Users with Basic auth: {status}")

    if status in (200, 403):
        warnings.warn(
            f"HTTP Basic auth accepted on SCIM GET /Users (status {status}) — "
            "Apiary docs were correct; add BasicAuth to the spec.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 401:
        warnings.warn(
            "HTTP Basic auth rejected on SCIM GET /Users (401) — "
            "RFC 7644 Bearer-only behavior confirmed; do not add Basic to the spec.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"Basic auth probe returned unexpected status {status} on GET /Users.",
            UserWarning,
            stacklevel=2,
        )


# ── Probe: DELETE /Users/{id} existence ─────────────────────────────────────

@pytest.mark.live
@pytest.mark.write
def test_scim_delete_user_endpoint_exists(scim_token):
    """Probes whether DELETE /Users/{id} is implemented on the SCIM endpoint.

    Apiary does not document DELETE; issue #43 excluded it from the spec on that
    basis. This test sends DELETE with a nonexistent user ID to distinguish:
      - 404 → endpoint exists, user not found (DELETE is implemented)
      - 405 → Method Not Allowed (DELETE not implemented; spec exclusion correct)
      - 403 → endpoint exists, auth ok but no permission

    Requires --allow-writes because DELETE is a write method. The target ID is a
    deliberately nonexistent UUID so no real user is at risk.
    """
    fake_id = "00000000-0000-0000-0000-000000000000"

    with httpx.Client() as client:
        response = client.delete(
            f"{SCIM_BASE_URL}/Users/{fake_id}",
            headers={"Authorization": f"AnaplanAuthToken {scim_token}"},
        )

    status = response.status_code
    print(f"\nDELETE /Users/{{fake_id}}: {status}")

    if status == 405:
        warnings.warn(
            "DELETE /Users/{id} returned 405 Method Not Allowed — "
            "endpoint is not implemented; spec exclusion is correct.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 404:
        warnings.warn(
            "DELETE /Users/{id} returned 404 — endpoint exists but user not found; "
            "DELETE is implemented and should be added to the spec.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 403:
        warnings.warn(
            f"DELETE /Users/{{id}} returned 403 — endpoint exists, auth accepted, "
            "no permission; DELETE is implemented and should be added to the spec.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"DELETE /Users/{{id}} probe returned unexpected status {status}.",
            UserWarning,
            stacklevel=2,
        )


# ── Probe: OAuth Bearer token ────────────────────────────────────────────────

@pytest.mark.live
def test_scim_users_oauth_bearer_probe():
    """Probes whether a real OAuth 2.0 Bearer token is accepted by SCIM /Users.

    Requires ANAPLAN_OAUTH_ACCESS_TOKEN in .env. Skipped if absent.
    This is the RFC 7644-specified auth scheme. Hypothesis: 200 or 403 (not 401).
    If accepted, the spec's BearerAuth declaration is confirmed as correct.
    """
    oauth_token = os.getenv("ANAPLAN_OAUTH_ACCESS_TOKEN")
    if not oauth_token:
        pytest.skip("ANAPLAN_OAUTH_ACCESS_TOKEN not set")

    with httpx.Client() as client:
        response = client.get(
            f"{SCIM_BASE_URL}/Users",
            headers={"Authorization": f"Bearer {oauth_token}"},
        )

    status = response.status_code
    print(f"\nGET /Users with OAuth Bearer token: {status}")

    if status in (200, 403):
        warnings.warn(
            f"OAuth Bearer token accepted on SCIM GET /Users (status {status}) — "
            "BearerAuth spec declaration confirmed correct.",
            UserWarning,
            stacklevel=2,
        )
    elif status == 401:
        warnings.warn(
            "OAuth Bearer token rejected on SCIM GET /Users (401) — "
            "remove BearerAuth from the spec; AnaplanAuthToken is the only valid scheme.",
            UserWarning,
            stacklevel=2,
        )
    else:
        warnings.warn(
            f"OAuth Bearer probe returned unexpected status {status} on GET /Users.",
            UserWarning,
            stacklevel=2,
        )


# ── Role confirmation (issue #180, ADR 0006) ────────────────────────────────
# Confirms the min-role annotations by probing each endpoint class with two
# credential sets: cert_token = the cert-auth user, now a Standard User (no
# elevated role); admin_token = User Admin. Read-only — the USER_ADMIN gate is
# enforced at the /Users resource level, so a GET on the collection settles the
# gate for all six /Users ops without issuing any write.

# GET-only discovery endpoints annotated "None" (public — no auth, no role).
_METADATA_PATHS = ["/ResourceTypes", "/Schemas", "/ServiceProviderConfig"]


def _scim_get(token: str, path: str):
    with httpx.Client() as client:
        return client.get(
            f"{SCIM_BASE_URL}{path}",
            headers={"Authorization": f"AnaplanAuthToken {token}"},
        )


@pytest.mark.live
def test_scim_users_gate_denies_standard_user(cert_token):
    """Standard User (no USER_ADMIN) is denied on GET /Users.

    Confirms the /Users resource is gated: expect 403 (auth ok, no role).
    A 200 would mean the account actually holds User Admin — re-check the
    credential set, the cert-auth user must be a Standard User.
    """
    status = _scim_get(cert_token, "/Users").status_code
    print(f"\n[std] GET /Users: {status}")
    assert status == 403, (
        f"expected 403 for a Standard User on GET /Users, got {status}"
    )


@pytest.mark.live
def test_scim_users_gate_allows_user_admin(admin_token):
    """User Admin passes the /Users gate → 200.

    Confirms "User Administrator" is the correct minimum role for the six
    /Users operations (Anaplan help + internal USER_ADMIN string).
    """
    status = _scim_get(admin_token, "/Users").status_code
    print(f"\n[admin] GET /Users: {status}")
    assert status == 200, (
        f"expected 200 for a User Admin on GET /Users, got {status}"
    )


@pytest.mark.live
@pytest.mark.parametrize("path", _METADATA_PATHS)
def test_scim_metadata_requires_no_auth(path):
    """Discovery endpoints are public → 200 with no Authorization header.

    Confirms the "None" annotation (no role gate, no login) on /ResourceTypes,
    /Schemas, and /ServiceProviderConfig. Per SCIM RFC 7644 §7 these MAY be
    served unauthenticated; Anaplan does. A 401 here would mean auth is
    required — re-annotate to Standard User.
    """
    with httpx.Client() as client:
        status = client.get(f"{SCIM_BASE_URL}{path}").status_code
    print(f"\n[no-auth] GET {path}: {status}")
    assert status == 200, (
        f"expected 200 unauthenticated on GET {path}, got {status} "
        "(if 401, auth is required — re-annotate to Standard User)"
    )
