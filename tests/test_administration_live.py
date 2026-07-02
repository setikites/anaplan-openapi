"""
Live API integration tests for the Anaplan Administration API.

Run with:
    uv run --env-file .env pytest tests/test_administration_live.py --live

Credentials are read from .env at the repo root.

Certificate authentication (preferred):
    ANAPLAN_CA_CERT_PATH      - path to CA certificate file (PEM format)
    ANAPLAN_CA_KEY_PATH       - path to private key file (PEM format)
    ANAPLAN_CA_KEY_PASSWORD   - password for the private key (if encrypted)

Basic authentication (fallback):
    ANAPLAN_USERNAME          - username
    ANAPLAN_PASSWORD          - password

Optional:
    ANAPLAN_API_BASE_URL      - API base URL (default: https://api.anaplan.com)

Administration-specific:
    ADMINISTRATION_EMAIL      - email of a safe existing user for idempotent import tests
    ADMINISTRATION_USERID     - user ID of that user (documents which account is safe to re-import)

**Confirmed behavior (live testing 2026-06-23, re-confirmed 2026-07-02):**
- Only the AnaplanAuthToken scheme is accepted. The same OAuth access_token
  sent as `Bearer` is rejected at the auth layer — 401 with an empty body and a
  `WWW-Authenticate: Bearer` challenge — before the application runs. This
  matches the help docs (Export Users to CSV) and the Audit/Exception APIs.
- Accounts lacking the Tenant Administrator role receive a role error (not an
  auth rejection). The error form differs by token type:
    - Basic-auth token → 500 INTERNAL_SERVER_ERROR
    - OAuth access_token → 401 ACCESS_CONTROL_DENIED (JSON body)
  The spec documents 403 for the role-denied case; both observed codes are
  confirmed discrepancies.
"""

import base64
import csv
import io
import json
import os
import pathlib
import secrets
import warnings

import httpx
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from oauth.token_keyring import load_token

AUTH_URL = "https://auth.anaplan.com"
_api_base = os.getenv("ANAPLAN_API_BASE_URL", "https://api.anaplan.com").rstrip("/")
ADMIN_URL = _api_base + "/admin/1/0"

ADMINISTRATION_EMAIL = os.getenv("ADMINISTRATION_EMAIL", "")

_NO_ROLE_CODES = frozenset({"INTERNAL_SERVER_ERROR", "ACCESS_CONTROL_DENIED"})


def _get_oauth_access_token() -> str | None:
    """Return the access_token from the OAuth Authorization Code token blob in the keyring.

    The grant helper script (scripts/oauth/oauth_authcode.py) stores the full token
    response under ANAPLAN_OAUTH_KEYRING_SERVICE. Anaplan accepts an OAuth access_token
    under the same ``AnaplanAuthToken`` Authorization scheme as a basic-auth token.
    """
    service = os.getenv("ANAPLAN_OAUTH_KEYRING_SERVICE", "anaplan-oauth-authcode")
    blob = load_token(service)
    if not blob:
        return None
    try:
        return json.loads(blob).get("access_token")
    except (ValueError, AttributeError):
        return None


def _is_no_role_error(response: httpx.Response) -> bool:
    """Return True when the API signals that the caller lacks the Tenant Administrator role.

    Two patterns observed via live testing 2026-06-23:
    - Basic-auth token:  500 INTERNAL_SERVER_ERROR
    - OAuth access_token: 401 ACCESS_CONTROL_DENIED

    In both cases the scheme WAS accepted — the error comes from the application layer
    (role check), not the auth layer (token validation). The spec documents 403 for
    this case; the API's non-standard status codes are a confirmed discrepancy.
    """
    if response.status_code not in (401, 403, 500):
        return False
    try:
        return response.json().get("errorCode") in _NO_ROLE_CODES
    except Exception:
        return False


def _sign_data(data: bytes, key_path: str, key_password: str | None = None) -> str:
    with open(key_path, "rb") as f:
        key_data = f.read()
    password = key_password.encode() if key_password else None
    private_key = serialization.load_pem_private_key(
        key_data, password=password, backend=default_backend()
    )
    signature = private_key.sign(data, padding.PKCS1v15(), hashes.SHA512())
    return base64.b64encode(signature).decode()


def _load_cert_b64(cert_path: str) -> str:
    with open(cert_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _auth_with_cert(client: httpx.Client, ca_certs: dict) -> str | None:
    random_data = secrets.token_bytes(150)
    encoded_data = base64.b64encode(random_data).decode()
    signature = _sign_data(random_data, ca_certs["key_path"], ca_certs["key_password"])
    cert_b64 = _load_cert_b64(ca_certs["cert_path"])
    response = client.post(
        f"{AUTH_URL}/token/authenticate",
        headers={"Authorization": f"CACertificate {cert_b64}"},
        json={"encodedData": encoded_data, "encodedSignedData": signature},
    )
    if response.status_code == 201:
        return response.json().get("tokenInfo", {}).get("tokenValue")
    return None


def _auth_with_basic(client: httpx.Client, creds: dict) -> str | None:
    auth_b64 = base64.b64encode(
        f"{creds['username']}:{creds['password']}".encode()
    ).decode()
    response = client.post(
        f"{AUTH_URL}/token/authenticate",
        headers={"Authorization": f"Basic {auth_b64}"},
    )
    if response.status_code == 201:
        return response.json().get("tokenInfo", {}).get("tokenValue")
    return None


@pytest.fixture(scope="module")
def _ca_certs():
    cert_path = os.getenv("ANAPLAN_CA_CERT_PATH")
    key_path = os.getenv("ANAPLAN_CA_KEY_PATH")
    if not cert_path or not key_path:
        return None
    cert_file = pathlib.Path(cert_path)
    key_file = pathlib.Path(key_path)
    if not cert_file.exists() or not key_file.exists():
        return None
    return {
        "cert_path": str(cert_file),
        "key_path": str(key_file),
        "key_password": os.getenv("ANAPLAN_CA_KEY_PASSWORD"),
    }


@pytest.fixture(scope="module")
def _basic_creds():
    username = os.getenv("ANAPLAN_USERNAME")
    password = os.getenv("ANAPLAN_PASSWORD")
    if not username or not password:
        return None
    return {"username": username, "password": password}


@pytest.fixture(scope="module")
def admin_token(_ca_certs, _basic_creds):
    """AnaplanAuthToken (or OAuth access_token) with admin privilege (module-scoped).

    Prefers an OAuth Authorization Code access_token from the keyring — the grant
    path that can carry the Tenant Administrator role. Falls back to certificate auth,
    then to basic auth. The OAuth token is left intact on teardown (it is owned by the
    human-run grant flow); basic-auth tokens are logged out.
    """
    oauth_token = _get_oauth_access_token()
    if oauth_token:
        yield oauth_token
        return

    with httpx.Client() as client:
        token = None

        if _ca_certs:
            token = _auth_with_cert(client, _ca_certs)

        if not token and _basic_creds:
            token = _auth_with_basic(client, _basic_creds)

        if not token:
            pytest.skip("No valid authentication credentials for Administration API")

        yield token

        client.post(
            f"{AUTH_URL}/token/logout",
            headers={"Authorization": f"AnaplanAuthToken {token}"},
        )


# ─── Tracer bullet ─────────────────────────────────────────────────────────────


@pytest.mark.live
def test_export_users(admin_token):
    """GET /admin/1/0/users/export returns 200, text/csv, non-empty body with expected columns.

    A 403/500 with errorCode INTERNAL_SERVER_ERROR indicates the caller lacks the
    Tenant Administrator role — the token was accepted, but the account is
    insufficiently privileged. This mirrors the Integration API's behavior on
    GET /workspaces/{workspaceId}/admins and is a known API discrepancy (should be 403).
    """
    with httpx.Client() as client:
        response = client.get(
            f"{ADMIN_URL}/users/export",
            headers={"Authorization": f"AnaplanAuthToken {admin_token}"},
        )

    print(f"\nGET /users/export: {response.status_code}")
    print(f"Body: {response.text[:200]}")

    if _is_no_role_error(response):
        warnings.warn(
            f"GET /users/export returned {response.status_code} "
            f"({response.json().get('errorCode', '?')}) — "
            "AnaplanAuthToken was accepted; account lacks the Tenant Administrator role. "
            "Spec documents 403 for the role-denied case; observed codes are a discrepancy "
            "(basic-auth token → 500 INTERNAL_SERVER_ERROR; OAuth token → 401 ACCESS_CONTROL_DENIED). "
            "Re-run with credentials that have Tenant Administrator privilege to validate "
            "the 200/text/csv response shape.",
            UserWarning,
            stacklevel=2,
        )
        return

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )
    ct = response.headers.get("content-type", "")
    assert "text/csv" in ct, f"Expected text/csv content-type, got {ct!r}"

    body = response.text
    assert body.strip(), "Response body must be non-empty"

    reader = csv.reader(io.StringIO(body))
    headers = next(reader, None)
    assert headers is not None, "CSV must have a header row"
    for col in ("username", "first_name", "last_name", "licenses"):
        assert col in headers, (
            f"CSV header missing expected column {col!r}; got {headers}"
        )


# ─── Helpers ───────────────────────────────────────────────────────────────────

_EXCEPTION_SPEC = (
    pathlib.Path(__file__).parent.parent / "exception" / "exception-openapi.json"
)


def _region_label(url: str) -> str:
    """Short identifier for a server URL: 'legacy' for api.anaplan.com, else the subdomain."""
    host = httpx.URL(url).host
    return "legacy" if host == "api.anaplan.com" else host.split(".")[0]


# ─── Auth scheme probe ─────────────────────────────────────────────────────────


@pytest.mark.live
def test_auth_scheme_probe(admin_token):
    """Confirm the Administration API accepts only the AnaplanAuthToken scheme.

    Sends the same token with both Authorization schemes. AnaplanAuthToken reaches
    the application layer (200, or a role error for a non-admin account); Bearer is
    rejected at the auth layer — an empty 401 with a ``WWW-Authenticate: Bearer``
    challenge — so the spec correctly declares only AnaplanAuthToken. Matches the
    help docs and the Audit/Exception APIs.
    """
    url = f"{ADMIN_URL}/users/export"

    with httpx.Client() as client:
        anaplan_r = client.get(
            url, headers={"Authorization": f"AnaplanAuthToken {admin_token}"}
        )
        bearer_r = client.get(
            url, headers={"Authorization": f"Bearer {admin_token}"}
        )

    print(f"\nAuth scheme probe (Administration API) — GET /users/export:")
    print(f"  AnaplanAuthToken: {anaplan_r.status_code}  {anaplan_r.text[:120]}")
    print(f"  Bearer:           {bearer_r.status_code}  www-authenticate="
          f"{bearer_r.headers.get('www-authenticate')!r}  body={bearer_r.text[:80]!r}")

    # AnaplanAuthToken must reach the application layer.
    assert anaplan_r.status_code == 200 or _is_no_role_error(anaplan_r), (
        f"AnaplanAuthToken scheme rejected on GET /users/export: "
        f"{anaplan_r.status_code}: {anaplan_r.text[:200]}"
    )

    # Bearer must be rejected by the auth layer, not reach the app: an empty 401,
    # never a 200 or a role-error JSON body.
    assert not (bearer_r.status_code == 200 or _is_no_role_error(bearer_r)), (
        f"Bearer scheme unexpectedly reached the application layer "
        f"(status {bearer_r.status_code}): {bearer_r.text[:200]} — "
        "the Administration host is expected to reject Bearer"
    )
    assert bearer_r.status_code == 401, (
        f"expected an auth-layer 401 for Bearer, got {bearer_r.status_code}: "
        f"{bearer_r.text[:200]}"
    )


# ─── Regional server probe ─────────────────────────────────────────────────────


@pytest.mark.live
def test_regional_server_probe(admin_token):
    """Probe every regional api.anaplan.com server to confirm which host the Administration API.

    Server list is read dynamically from the Exception Users spec — that API shares the
    same /admin/1/0 base path and has the full confirmed regional list. For each server,
    GET /users/export is sent with AnaplanAuthToken. A 200 or role-error response
    (ACCESS_CONTROL_DENIED / INTERNAL_SERVER_ERROR) means the server hosts the API and
    accepted the token scheme; a connection error means the server is unreachable or
    not in this tenant's region.
    """
    with open(_EXCEPTION_SPEC, encoding="utf-8") as f:
        exception_spec = json.load(f)

    servers = [(s.get("description", "?"), s["url"]) for s in exception_spec["servers"]]
    h = {"Authorization": f"AnaplanAuthToken {admin_token}"}

    responses: dict[str, httpx.Response | Exception] = {}
    with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
        for _, base_url in servers:
            label = _region_label(base_url)
            try:
                responses[label] = client.get(f"{base_url}/users/export", headers=h)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                responses[label] = exc

    print("\nRegional server probe — GET /admin/1/0/users/export:")
    for label, result in responses.items():
        if isinstance(result, Exception):
            print(f"  {label:10s}: unreachable ({type(result).__name__})")
        else:
            print(f"  {label:10s}: {result.status_code}  {result.text[:100]}")

    live = {k: v for k, v in responses.items() if isinstance(v, httpx.Response)}
    auth_accepted = {k for k, v in live.items()
                     if v.status_code == 200 or _is_no_role_error(v)}
    unreachable = {k for k, v in responses.items() if isinstance(v, Exception)}

    warnings.warn(
        f"Regional probe ({len(live)}/{len(servers)} responded): "
        f"auth accepted on {sorted(auth_accepted)} | "
        f"unreachable: {sorted(unreachable)}",
        UserWarning,
        stacklevel=2,
    )

    assert live, "No regional servers responded to GET /admin/1/0/users/export"


# ─── Write-guarded import ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def test_user_csv_row(admin_token):
    """Export all users and return the DictReader row for ADMINISTRATION_EMAIL.

    Provides the user's live field values so test_import_users can re-upload them
    unchanged (idempotent — no net change to the tenant).
    """
    if not ADMINISTRATION_EMAIL:
        pytest.skip("ADMINISTRATION_EMAIL not set — cannot build idempotent import payload")

    with httpx.Client() as client:
        response = client.get(
            f"{ADMIN_URL}/users/export",
            headers={"Authorization": f"AnaplanAuthToken {admin_token}"},
        )

    if _is_no_role_error(response):
        pytest.skip(
            f"GET /users/export returned {response.status_code} — "
            "account lacks Tenant Administrator role; cannot build import payload"
        )

    assert response.status_code == 200, (
        f"Export failed: {response.status_code}: {response.text[:200]}"
    )

    reader = csv.DictReader(io.StringIO(response.text))
    for row in reader:
        if row.get("username", "").lower() == ADMINISTRATION_EMAIL.lower():
            return row

    pytest.skip(
        f"Test user {ADMINISTRATION_EMAIL!r} not found in export — "
        "cannot build idempotent import payload"
    )


@pytest.mark.live
@pytest.mark.write
def test_import_users(admin_token, test_user_csv_row):
    """PUT /admin/1/0/users/import returns 207 with accepted/created/updated counts.

    Uploads a one-row CSV re-importing the test user with unchanged values
    (idempotent — no net change to the tenant).
    """
    row = test_user_csv_row

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["username", "first_name", "last_name", "licenses"])
    writer.writerow([row["username"], row["first_name"], row["last_name"], row["licenses"]])
    csv_bytes = output.getvalue().encode()

    with httpx.Client() as client:
        response = client.put(
            f"{ADMIN_URL}/users/import",
            headers={"Authorization": f"AnaplanAuthToken {admin_token}"},
            files={"file": ("users.csv", csv_bytes, "text/csv")},
        )

    assert response.status_code == 207, (
        f"Expected 207, got {response.status_code}: {response.text[:300]}"
    )
    body = response.json()
    for field in ("accepted", "created", "updated"):
        assert field in body, (
            f"Response missing expected field {field!r}; keys: {list(body.keys())}"
        )
    assert isinstance(body["accepted"], int), "'accepted' must be an integer"
    assert isinstance(body["created"], int), "'created' must be an integer"
    assert isinstance(body["updated"], int), "'updated' must be an integer"
    assert body["accepted"] == 1, (
        f"Expected 1 accepted row (idempotent re-import); got {body['accepted']}: {body}"
    )
