"""
Live API integration tests for Anaplan Integration API.

Run with:
    uv run --env-file .env pytest tests/test_integration_live.py --live

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
"""

import base64
import os
import pathlib
import secrets
import warnings

import httpx
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

AUTH_URL = "https://auth.anaplan.com"
API_URL = os.getenv("ANAPLAN_API_BASE_URL", "https://api.anaplan.com")


def _sign_data(data: bytes, key_path: str, key_password: str | None = None) -> str:
    """Sign bytes with a private key using SHA512withRSA, return base64-encoded signature."""
    with open(key_path, "rb") as f:
        key_data = f.read()
    password = key_password.encode() if key_password else None
    private_key = serialization.load_pem_private_key(
        key_data, password=password, backend=default_backend()
    )
    signature = private_key.sign(data, padding.PKCS1v15(), hashes.SHA512())
    return base64.b64encode(signature).decode()


def _load_cert_b64(cert_path: str) -> str:
    """Return base64-encoded content of a certificate file."""
    with open(cert_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _auth_with_cert(client: httpx.Client, ca_certs: dict) -> str | None:
    """Authenticate via CA certificate. Returns AnaplanAuthToken value or None."""
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
    """Authenticate via HTTP Basic. Returns AnaplanAuthToken value or None."""
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
def integration_token(_ca_certs, _basic_creds):
    """AnaplanAuthToken for Integration API calls (module-scoped).

    Prefers certificate auth; falls back to basic auth. Logs out on teardown.
    """
    with httpx.Client() as client:
        token = None

        if _ca_certs:
            token = _auth_with_cert(client, _ca_certs)

        if not token and _basic_creds:
            token = _auth_with_basic(client, _basic_creds)

        if not token:
            pytest.skip("No valid authentication credentials for Integration API")

        yield token

        client.post(
            f"{AUTH_URL}/token/logout",
            headers={"Authorization": f"AnaplanAuthToken {token}"},
        )


# ─── Tracer bullet ─────────────────────────────────────────────────────────────

@pytest.mark.live
def test_get_current_user(integration_token):
    """GET /2/0/users/me returns current user identity."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/2/0/users/me",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body.get("status", {}).get("code") == 200

    # API returns either {user: {...}} or {users: [...]}; normalise to a single object
    user = body.get("user") or next(iter(body.get("users") or []), None)
    assert user, f"Response must contain 'user'; keys were: {list(body.keys())}"
    assert user.get("id"), "User must have an id"


# ─── Remaining endpoint groups ─────────────────────────────────────────────────

@pytest.mark.live
def test_get_user_by_id(integration_token):
    """GET /2/0/users/{userId} returns the same user as GET /users/me."""
    with httpx.Client() as client:
        me_response = client.get(
            f"{API_URL}/2/0/users/me",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )
        assert me_response.status_code == 200
        me_body = me_response.json()
        me_user = me_body.get("user") or next(iter(me_body.get("users") or []), {})
        user_id = me_user.get("id")
        assert user_id, "Could not obtain userId from GET /users/me"

        response = client.get(
            f"{API_URL}/2/0/users/{user_id}",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    user = body.get("user") or next(iter(body.get("users") or []), None)
    assert user, f"Response must contain 'user'; keys were: {list(body.keys())}"
    assert user.get("id") == user_id, "Returned user ID must match requested ID"


@pytest.mark.live
def test_list_workspaces(integration_token):
    """GET /2/0/workspaces returns list of accessible workspaces."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/2/0/workspaces",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    workspaces = body.get("workspaces")
    assert isinstance(workspaces, list), (
        f"Response must contain 'workspaces' array; keys were: {list(body.keys())}"
    )
    if workspaces:
        w = workspaces[0]
        assert w.get("id"), "Workspace must have an id"
        assert "name" in w, "Workspace must have a name"


@pytest.mark.live
def test_get_workspace(integration_token):
    """GET /2/0/workspaces/{workspaceId} returns workspace detail.

    NOTE: Live testing shows this endpoint returns 404 for non-Workspace-Administrator
    accounts even when the workspace is visible in GET /workspaces. See README discrepancies.
    """
    with httpx.Client() as client:
        list_response = client.get(
            f"{API_URL}/2/0/workspaces",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )
        assert list_response.status_code == 200
        workspaces = list_response.json().get("workspaces", [])
        if not workspaces:
            pytest.skip("No workspaces available to probe GET /workspaces/{workspaceId}")
        workspace_id = workspaces[0]["id"]

        response = client.get(
            f"{API_URL}/2/0/workspaces/{workspace_id}",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    if response.status_code == 404:
        warnings.warn(
            f"GET /workspaces/{workspace_id} returned 404 — "
            "endpoint likely requires Workspace Administrator role. "
            "See integration/README.md discrepancies.",
            UserWarning,
            stacklevel=2,
        )
        return

    assert response.status_code == 200, (
        f"Expected 200 or 404, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    # API may return {workspace: {...}} or {workspaces: [...]}
    workspace = body.get("workspace") or next(iter(body.get("workspaces") or []), None)
    assert workspace, f"Response must contain 'workspace'; keys were: {list(body.keys())}"
    assert workspace.get("id") == workspace_id, "Returned workspace ID must match requested ID"


@pytest.mark.live
def test_list_models(integration_token):
    """GET /2/0/models returns list of accessible models."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/2/0/models",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    models = body.get("models")
    assert isinstance(models, list), (
        f"Response must contain 'models' array; keys were: {list(body.keys())}"
    )
    if models:
        m = models[0]
        assert m.get("id"), "Model must have an id"
        assert "name" in m, "Model must have a name"


@pytest.mark.live
def test_get_model(integration_token):
    """GET /2/0/models/{modelId} returns model detail."""
    with httpx.Client() as client:
        list_response = client.get(
            f"{API_URL}/2/0/models",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )
        assert list_response.status_code == 200
        models = list_response.json().get("models", [])
        if not models:
            pytest.skip("No models available to probe GET /models/{modelId}")
        model_id = models[0]["id"]

        response = client.get(
            f"{API_URL}/2/0/models/{model_id}",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    # API may return {model: {...}} or {models: [...]}
    model = body.get("model") or next(iter(body.get("models") or []), None)
    assert model, f"Response must contain 'model'; keys were: {list(body.keys())}"
    assert model.get("id") == model_id, "Returned model ID must match requested ID"


# ─── Auth scheme probe ──────────────────────────────────────────────────────────

@pytest.mark.live
def test_auth_scheme_probe(integration_token):
    """Probe whether Bearer token is accepted alongside AnaplanAuthToken.

    Documents which auth scheme(s) the Integration API actually accepts.
    AnaplanAuthToken must succeed; Bearer acceptance is recorded as a warning.
    """
    findings = []

    with httpx.Client() as client:
        for endpoint in ["/2/0/users/me", "/2/0/workspaces", "/2/0/models"]:
            url = f"{API_URL}{endpoint}"
            anaplan_r = client.get(
                url, headers={"Authorization": f"AnaplanAuthToken {integration_token}"}
            )
            bearer_r = client.get(
                url, headers={"Authorization": f"Bearer {integration_token}"}
            )
            findings.append(
                f"GET {endpoint}: AnaplanAuthToken={anaplan_r.status_code}, "
                f"Bearer={bearer_r.status_code}"
            )
            assert anaplan_r.status_code == 200, (
                f"AnaplanAuthToken rejected on GET {endpoint}: {anaplan_r.status_code}"
            )
            if bearer_r.status_code == 200:
                warnings.warn(
                    f"Bearer scheme also accepted on GET {endpoint} — "
                    "spec BearerAuth listing is valid for AnaplanAuthTokens",
                    UserWarning,
                    stacklevel=2,
                )

    print("\nAuth scheme probe (Integration API):")
    for finding in findings:
        print(f"  {finding}")


# ─── Helpers ────────────────────────────────────────────────────────────────────

def assert_response_code(response, expected_codes, discrepancies):
    if response.status_code not in expected_codes:
        discrepancies.append(
            f"Got {response.status_code}, expected one of {expected_codes}"
        )
