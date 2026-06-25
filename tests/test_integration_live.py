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
    ANAPLAN_API_BASE_URL               - API base URL (default: https://api.anaplan.com)
    ANAPLAN_INTEGRATION_WORKSPACE_ID   - workspace ID for model-scoped tests
    ANAPLAN_INTEGRATION_MODEL_ID       - model ID for model-scoped tests
"""

import base64
import os
import pathlib
import re
import secrets
import time
import warnings

import httpx
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

AUTH_URL = "https://auth.anaplan.com"
_api_base = os.getenv("ANAPLAN_API_BASE_URL", "https://api.anaplan.com").rstrip("/")
API_URL = _api_base if _api_base.endswith("/2/0") else _api_base + "/2/0"
WORKSPACE_ID = os.getenv("ANAPLAN_INTEGRATION_WORKSPACE_ID", "")
MODEL_ID = os.getenv("ANAPLAN_INTEGRATION_MODEL_ID", "")
INTEGRATION_PROCESS_ID = os.getenv("INTEGRATION_PROCESS", "")
INTEGRATION_EXPORT_ID = os.getenv("INTEGRATION_EXPORT", "")
INTEGRATION_IMPORT_ID = os.getenv("INTEGRATION_IMPORT", "")
INTEGRATION_ACTION_ID = os.getenv("INTEGRATION_ACTION", "")
INTEGRATION_FILE_ID = os.getenv("INTEGRATION_FILE", "")
INTEGRATION_LIST_ID = os.getenv("INTEGRATION_LIST", "")
INTEGRATION_MODULE_ID = os.getenv("INTEGRATION_MODULE", "")  # default view ID equals module ID


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
            f"{API_URL}/users/me",
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
            f"{API_URL}/users/me",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )
        assert me_response.status_code == 200
        me_body = me_response.json()
        me_user = me_body.get("user") or next(iter(me_body.get("users") or []), {})
        user_id = me_user.get("id")
        assert user_id, "Could not obtain userId from GET /users/me"

        response = client.get(
            f"{API_URL}/users/{user_id}",
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
            f"{API_URL}/workspaces",
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
            f"{API_URL}/workspaces",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )
        assert list_response.status_code == 200
        workspaces = list_response.json().get("workspaces", [])
        if not workspaces:
            pytest.skip("No workspaces available to probe GET /workspaces/{workspaceId}")
        workspace_id = workspaces[0]["id"]

        response = client.get(
            f"{API_URL}/workspaces/{workspace_id}",
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
def test_get_workspace_admins(integration_token):
    """GET /2/0/workspaces/{workspaceId}/admins returns workspace administrator list.

    Requires tenant admin access (OAuth Authorization Code grant). Basic-auth tokens
    receive 500; this test warns and skips in that case.
    """
    if not WORKSPACE_ID:
        pytest.skip("ANAPLAN_INTEGRATION_WORKSPACE_ID not set")
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/admins",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    if response.status_code in (403, 500):
        warnings.warn(
            f"GET /workspaces/{WORKSPACE_ID}/admins returned {response.status_code} — "
            "endpoint requires tenant admin privilege (workspace admin alone is insufficient).",
            UserWarning,
            stacklevel=2,
        )
        return

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    admins = body.get("admins")
    assert isinstance(admins, list), (
        f"Response must contain 'admins' array; keys were: {list(body.keys())}"
    )
    for admin in admins:
        assert "email" in admin, f"Admin must have an email; keys: {list(admin.keys())}"
        assert "active" in admin, f"Admin must have active flag; keys: {list(admin.keys())}"


@pytest.mark.live
def test_get_workspace_visitors(integration_token):
    """GET /2/0/workspaces/{workspaceId}/visitors returns workspace visitor list.

    Requires tenant admin access (OAuth Authorization Code grant). Basic-auth tokens
    receive 500; this test warns and skips in that case.
    """
    if not WORKSPACE_ID:
        pytest.skip("ANAPLAN_INTEGRATION_WORKSPACE_ID not set")
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/visitors",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    if response.status_code in (403, 500):
        warnings.warn(
            f"GET /workspaces/{WORKSPACE_ID}/visitors returned {response.status_code} — "
            "endpoint requires tenant admin privilege (workspace admin alone is insufficient).",
            UserWarning,
            stacklevel=2,
        )
        return

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    visitors = body.get("visitors")
    assert isinstance(visitors, list), (
        f"Response must contain 'visitors' array; keys were: {list(body.keys())}"
    )
    for visitor in visitors:
        assert "email" in visitor, f"Visitor must have an email; keys: {list(visitor.keys())}"
        assert "active" in visitor, f"Visitor must have active flag; keys: {list(visitor.keys())}"


@pytest.mark.live
def test_list_models(integration_token):
    """GET /2/0/models returns list of accessible models."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models",
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
            f"{API_URL}/models",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )
        assert list_response.status_code == 200
        models = list_response.json().get("models", [])
        if not models:
            pytest.skip("No models available to probe GET /models/{modelId}")
        model_id = models[0]["id"]

        response = client.get(
            f"{API_URL}/models/{model_id}",
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


# ─── s / sort query parameter probes ──────────────────────────────────────────
# _SEARCH_SORT_PATHS: paths supporting both s= and sort=.
#   (path, list_key, search_key, sort_field)
#   search_key: item field for the s= probe; sort_field: field for sort=+/-{field}.
# _ALL_SORT_PATHS: every sort-capable path (superset of _SEARCH_SORT_PATHS).
#   (path, list_key, sort_field)
# Add new search+sort paths to _SEARCH_SORT_PATHS AND _ALL_SORT_PATHS.
# Add sort-only paths to _ALL_SORT_PATHS only.

_SEARCH_SORT_PATHS = [
    pytest.param("/workspaces", "workspaces", "name",  "name",      id="workspaces"),
    pytest.param("/models",     "models",     "name",  "name",      id="models"),
    pytest.param("/users",      "users",      "email", "firstName", id="users"),
]

_ALL_SORT_PATHS = [
    # search+sort paths (also in _SEARCH_SORT_PATHS)
    pytest.param("/workspaces",                                                  "workspaces", "name",      id="workspaces"),
    pytest.param("/models",                                                      "models",     "name",      id="models"),
    pytest.param("/users",                                                       "users",      "firstName", id="users"),
    # sort-only paths
    pytest.param(f"/models/{MODEL_ID}/files",                                    "files",      "name",      id="files"),
    pytest.param(f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/actions",        "actions",    "name",      id="actions"),
    pytest.param(f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/processes",      "processes",  "name",      id="processes"),
    pytest.param(f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/imports/",       "imports",    "name",      id="imports"),
    pytest.param(f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports",        "exports",    "name",      id="exports"),
]


@pytest.mark.live
@pytest.mark.parametrize("path,list_key,search_key,sort_field", _SEARCH_SORT_PATHS)
def test_s_param_filters(integration_token, path, list_key, search_key, sort_field):
    """GET {path}?s=<prefix> returns 200 and a known item appears in the filtered results.

    Derives a short prefix from the first item's search_key field in the unfiltered list,
    then confirms that same item is present after filtering. Skipped when the list is empty.
    """
    h = {"Authorization": f"AnaplanAuthToken {integration_token}"}
    url = f"{API_URL}{path}"
    with httpx.Client() as client:
        all_r = client.get(url, headers=h)
        assert all_r.status_code == 200, f"Baseline GET {path} failed: {all_r.status_code}"
        items = all_r.json().get(list_key, [])
        if not items:
            pytest.skip(f"No {list_key} available to probe s parameter")

        known_value = items[0][search_key]
        prefix = known_value[:4]

        filtered_r = client.get(url, headers=h, params={"s": prefix})

    assert filtered_r.status_code == 200, (
        f"GET {path}?s={prefix!r} returned {filtered_r.status_code}: {filtered_r.text[:200]}"
    )
    filtered_body = filtered_r.json()
    assert filtered_body.get("status", {}).get("code") == 200
    filtered = filtered_body.get(list_key, [])
    assert isinstance(filtered, list), (
        f"Expected {list_key!r} list in filtered response; keys: {list(filtered_body.keys())}"
    )
    values = [item[search_key] for item in filtered if search_key in item]
    assert any(known_value == v for v in values), (
        f"Known {search_key}={known_value!r} not in results for s={prefix!r}; got: {values[:5]}"
    )


@pytest.mark.live
@pytest.mark.parametrize("path,list_key,sort_field", _ALL_SORT_PATHS)
def test_sort_param(integration_token, path, list_key, sort_field):
    """GET {path}?sort=+{sort_field} and ?sort=-{sort_field} both return 200.

    When ≥2 items exist, verifies that ascending order has first ≤ last and
    descending has first ≥ last, and that the two orderings are opposite.
    """
    h = {"Authorization": f"AnaplanAuthToken {integration_token}"}
    url = f"{API_URL}{path}"
    with httpx.Client() as client:
        asc_r = client.get(url, headers=h, params={"sort": f"+{sort_field}"})
        desc_r = client.get(url, headers=h, params={"sort": f"-{sort_field}"})

    assert asc_r.status_code == 200, (
        f"GET {path}?sort=+{sort_field} returned {asc_r.status_code}: {asc_r.text[:200]}"
    )
    assert desc_r.status_code == 200, (
        f"GET {path}?sort=-{sort_field} returned {desc_r.status_code}: {desc_r.text[:200]}"
    )

    asc_vals = [item[sort_field] for item in asc_r.json().get(list_key, []) if sort_field in item]
    desc_vals = [item[sort_field] for item in desc_r.json().get(list_key, []) if sort_field in item]

    if len(asc_vals) >= 2:
        assert asc_vals[0] <= asc_vals[-1], (
            f"sort=+{sort_field}: expected ascending; got {asc_vals[0]!r} … {asc_vals[-1]!r}"
        )
    if len(desc_vals) >= 2:
        assert desc_vals[0] >= desc_vals[-1], (
            f"sort=-{sort_field}: expected descending; got {desc_vals[0]!r} … {desc_vals[-1]!r}"
        )
    if len(asc_vals) >= 2 and len(desc_vals) >= 2:
        assert asc_vals[0] <= desc_vals[0], (
            f"sort=+{sort_field} first={asc_vals[0]!r} should be ≤ sort=-{sort_field} first={desc_vals[0]!r}"
        )


# ─── Workspace-scoped model paths ──────────────────────────────────────────────
# Uses WORKSPACE_ID / MODEL_ID / _auth_headers defined in "Model structure metadata" below.


@pytest.mark.live
def test_list_workspace_models(integration_token):
    """GET /2/0/workspaces/{workspaceId}/models returns workspace-scoped model list.

    Compares response shape to GET /2/0/models. Documents any structural differences.
    """
    h = {"Authorization": f"AnaplanAuthToken {integration_token}"}
    with httpx.Client() as client:
        baseline = client.get(f"{API_URL}/models", headers=h)
        response = client.get(f"{API_URL}/workspaces/{WORKSPACE_ID}/models", headers=h)

    if response.status_code in (404, 405):
        pytest.skip(
            f"GET /workspaces/{{workspaceId}}/models returned {response.status_code} — "
            "endpoint not available for this account/region"
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    models = body.get("models")
    assert isinstance(models, list), (
        f"Response must contain 'models' array; keys: {list(body.keys())}"
    )
    if models:
        assert models[0].get("id"), "Model must have an id"
        assert "name" in models[0], "Model must have a name"

    if baseline.status_code == 200:
        baseline_models = baseline.json().get("models") or []
        baseline_keys = set(baseline_models[0].keys()) if baseline_models else set()
        workspace_keys = set(models[0].keys()) if models else set()
        if workspace_keys - baseline_keys:
            warnings.warn(
                f"GET /workspaces/{{workspaceId}}/models has extra fields vs GET /models: "
                f"{workspace_keys - baseline_keys}",
                UserWarning,
                stacklevel=2,
            )
        if baseline_keys - workspace_keys:
            warnings.warn(
                f"GET /workspaces/{{workspaceId}}/models missing fields vs GET /models: "
                f"{baseline_keys - workspace_keys}",
                UserWarning,
                stacklevel=2,
            )


@pytest.mark.live
def test_model_category_values(integration_token):
    """GET /workspaces/{workspaceId}/models embeds categoryValues in each model object.

    There is no dedicated /categories endpoint (returns 404). Category data is
    returned inline as Model.categoryValues[].  Confirms CategoryValue schema:
    {id, attribute, categoryId, categoryName, customerId}.
    """
    h = {"Authorization": f"AnaplanAuthToken {integration_token}"}
    with httpx.Client() as client:
        response = client.get(f"{API_URL}/workspaces/{WORKSPACE_ID}/models", headers=h)

    if response.status_code in (404, 405):
        pytest.skip(
            f"GET /workspaces/{{workspaceId}}/models returned {response.status_code}"
        )

    assert response.status_code == 200, response.text[:200]
    models = response.json().get("models", [])
    assert isinstance(models, list)

    for m in models:
        assert "categoryValues" in m, f"Model {m.get('id')} missing categoryValues field"
        assert isinstance(m["categoryValues"], list), (
            f"Model {m.get('id')} categoryValues must be a list"
        )
        for cv in m["categoryValues"]:
            for key in ("id", "attribute", "categoryId", "categoryName"):
                assert key in cv, (
                    f"CategoryValue missing key {key!r}; keys present: {list(cv.keys())}"
                )


@pytest.mark.live
def test_get_workspace_model(integration_token):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId} returns workspace-scoped model detail.

    Compares response shape to GET /2/0/models/{modelId}. Documents any structural differences.
    """
    h = {"Authorization": f"AnaplanAuthToken {integration_token}"}
    with httpx.Client() as client:
        baseline = client.get(f"{API_URL}/models/{MODEL_ID}", headers=h)
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}", headers=h
        )

    if response.status_code in (404, 405):
        pytest.skip(
            f"GET /workspaces/{{workspaceId}}/models/{{modelId}} returned {response.status_code} — "
            "endpoint not available for this account/region"
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    model = body.get("model") or next(iter(body.get("models") or []), None)
    assert model, f"Response must contain 'model'; keys: {list(body.keys())}"
    assert model.get("id") == MODEL_ID, "Returned model ID must match requested ID"

    if baseline.status_code == 200:
        baseline_body = baseline.json()
        baseline_model = baseline_body.get("model") or next(
            iter(baseline_body.get("models") or []), {}
        )
        baseline_keys = set(baseline_model.keys()) if baseline_model else set()
        workspace_keys = set(model.keys())
        if workspace_keys - baseline_keys:
            warnings.warn(
                f"GET /workspaces/{{workspaceId}}/models/{{modelId}} has extra fields vs "
                f"GET /models/{{modelId}}: {workspace_keys - baseline_keys}",
                UserWarning,
                stacklevel=2,
            )
        if baseline_keys - workspace_keys:
            warnings.warn(
                f"GET /workspaces/{{workspaceId}}/models/{{modelId}} missing fields vs "
                f"GET /models/{{modelId}}: {baseline_keys - workspace_keys}",
                UserWarning,
                stacklevel=2,
            )


# ─── Auth scheme probe ──────────────────────────────────────────────────────────

@pytest.mark.live
def test_auth_scheme_probe(integration_token):
    """Probe whether Bearer token is accepted alongside AnaplanAuthToken.

    Documents which auth scheme(s) the Integration API actually accepts.
    AnaplanAuthToken must succeed; Bearer acceptance is recorded as a warning.
    """
    findings = []

    with httpx.Client() as client:
        for endpoint in ["/users/me", "/workspaces", "/models"]:
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


# ─── Model structure metadata ──────────────────────────────────────────────────
# Fixed test IDs; non-destructive read-only endpoints only.


def _auth_headers(token):
    return {"Authorization": f"AnaplanAuthToken {token}"}


@pytest.fixture(scope="module")
def module_id_with_line_items(integration_token):
    """First module ID that has at least one line item."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(f"{API_URL}/models/{MODEL_ID}/modules", headers=h)
        if r.status_code != 200:
            pytest.skip(f"Could not list modules: {r.status_code}")
        for m in r.json().get("modules", []):
            r2 = client.get(
                f"{API_URL}/models/{MODEL_ID}/modules/{m['id']}/lineItems",
                headers=h,
            )
            if r2.status_code == 200 and r2.json().get("items"):
                return m["id"]
    pytest.skip("No module with line items found in test model")


@pytest.fixture(scope="module")
def module_id_with_views(integration_token):
    """First module ID that has at least one view."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(f"{API_URL}/models/{MODEL_ID}/modules", headers=h)
        if r.status_code != 200:
            pytest.skip(f"Could not list modules: {r.status_code}")
        for m in r.json().get("modules", []):
            r2 = client.get(
                f"{API_URL}/models/{MODEL_ID}/modules/{m['id']}/views",
                headers=h,
            )
            if r2.status_code == 200 and r2.json().get("views"):
                return m["id"]
    pytest.skip("No module with views found in test model")


@pytest.fixture(scope="module")
def view_id(integration_token):
    """First view ID from the model-level view list."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/views",
            headers=h,
        )
    if r.status_code != 200:
        pytest.skip(f"Could not list views: {r.status_code}")
    views = r.json().get("views", [])
    if not views:
        pytest.skip("No views in test model")
    return views[0]["id"]


@pytest.fixture(scope="module")
def line_item_and_dimension_ids(integration_token):
    """(line_item_id, dimension_id) — first line item that has at least one dimension."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(f"{API_URL}/models/{MODEL_ID}/lineItems", headers=h)
        if r.status_code != 200:
            pytest.skip(f"Could not list line items: {r.status_code}")
        for item in r.json().get("items", []):
            lid = item["id"]
            r2 = client.get(
                f"{API_URL}/models/{MODEL_ID}/lineItems/{lid}/dimensions",
                headers=h,
            )
            if r2.status_code == 200 and r2.json().get("dimensions"):
                return lid, r2.json()["dimensions"][0]["id"]
    pytest.skip("No line item with dimensions found in test model")


@pytest.fixture(scope="module")
def line_item_id(line_item_and_dimension_ids):
    return line_item_and_dimension_ids[0]


@pytest.fixture(scope="module")
def dimension_id(line_item_and_dimension_ids):
    return line_item_and_dimension_ids[1]


@pytest.fixture(scope="module")
def view_and_dimension_for_items(integration_token):
    """(view_id, dimension_id) — first view+dimension pair with at least one item."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/views", headers=h
        )
        if r.status_code != 200:
            pytest.skip(f"Could not list views: {r.status_code}")
        for v in r.json().get("views", []):
            vid = v["id"]
            r2 = client.get(f"{API_URL}/models/{MODEL_ID}/views/{vid}", headers=h)
            if r2.status_code != 200:
                continue
            for row in r2.json().get("rows", []):
                did = row["id"]
                r3 = client.get(
                    f"{API_URL}/models/{MODEL_ID}/views/{vid}/dimensions/{did}/items",
                    headers=h,
                )
                if r3.status_code == 200 and r3.json().get("items"):
                    return vid, did
    pytest.skip("No view+dimension with items found in test model")


@pytest.fixture(scope="module")
def list_id(integration_token):
    """First list ID from the workspace/model list endpoint."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lists",
            headers=h,
        )
    if r.status_code != 200:
        pytest.skip(f"Could not list lists: {r.status_code}")
    lists = r.json().get("lists", [])
    if not lists:
        pytest.skip("No lists in test model")
    return lists[0]["id"]


@pytest.mark.live
def test_list_modules(integration_token):
    """GET /2/0/models/{modelId}/modules returns list of modules."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/modules",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    modules = body.get("modules")
    assert isinstance(modules, list), f"Expected 'modules' list; keys: {list(body.keys())}"
    if modules:
        assert modules[0].get("id"), "Module must have an id"
        assert "name" in modules[0], "Module must have a name"


@pytest.mark.live
def test_list_module_line_items(integration_token, module_id_with_line_items):
    """GET /2/0/models/{modelId}/modules/{moduleId}/lineItems returns line items."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/modules/{module_id_with_line_items}/lineItems",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    items = body.get("items")
    assert isinstance(items, list), f"Expected 'items' list; keys: {list(body.keys())}"
    if items:
        assert items[0].get("id"), "Line item must have an id"
        assert "name" in items[0], "Line item must have a name"


@pytest.mark.live
def test_list_module_views(integration_token, module_id_with_views):
    """GET /2/0/models/{modelId}/modules/{moduleId}/views returns views for a module."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/modules/{module_id_with_views}/views",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    views = body.get("views")
    assert isinstance(views, list), f"Expected 'views' list; keys: {list(body.keys())}"
    if views:
        assert views[0].get("id"), "View must have an id"
        assert "name" in views[0], "View must have a name"


@pytest.mark.live
def test_list_model_views(integration_token):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/views returns all views."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/views",
            headers={"Authorization": f"AnaplanAuthToken {integration_token}"},
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    views = body.get("views")
    assert isinstance(views, list), f"Expected 'views' list; keys: {list(body.keys())}"
    if views:
        assert views[0].get("id"), "View must have an id"
        assert "name" in views[0], "View must have a name"


@pytest.mark.live
def test_get_view(integration_token, view_id):
    """GET /2/0/models/{modelId}/views/{viewId} returns view metadata including dimensions."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/views/{view_id}",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    # API returns flat viewName/viewId/rows, not a nested view object
    assert body.get("viewId") == view_id, (
        f"Returned viewId must match requested ID; keys: {list(body.keys())}"
    )
    assert "viewName" in body, "Response must have viewName"
    assert isinstance(body.get("rows"), list), "Response must have rows list"


@pytest.mark.live
def test_list_model_line_items(integration_token):
    """GET /2/0/models/{modelId}/lineItems returns all line items in the model."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/lineItems",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    items = body.get("items")
    assert isinstance(items, list), f"Expected 'items' list; keys: {list(body.keys())}"
    if items:
        assert items[0].get("id"), "Line item must have an id"
        assert "name" in items[0], "Line item must have a name"


@pytest.mark.live
def test_list_line_item_dimensions(integration_token, line_item_id):
    """GET /2/0/models/{modelId}/lineItems/{lineItemId}/dimensions returns dimensions."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/lineItems/{line_item_id}/dimensions",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    dims = body.get("dimensions")
    assert isinstance(dims, list), f"Expected 'dimensions' list; keys: {list(body.keys())}"
    if dims:
        assert dims[0].get("id"), "Dimension must have an id"
        assert "name" in dims[0], "Dimension must have a name"


@pytest.mark.live
def test_list_line_item_dimension_items(integration_token, line_item_id, dimension_id):
    """GET /2/0/models/{modelId}/lineItems/{lineItemId}/dimensions/{dimensionId}/items."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/lineItems/{line_item_id}/dimensions/{dimension_id}/items",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    items = body.get("items")
    assert isinstance(items, list), f"Expected 'items' list; keys: {list(body.keys())}"
    if items:
        assert items[0].get("id"), "Dimension item must have an id"
        assert "name" in items[0], "Dimension item must have a name"


@pytest.mark.live
def test_list_view_dimension_items(integration_token, view_and_dimension_for_items):
    """GET /2/0/models/{modelId}/views/{viewId}/dimensions/{dimensionId}/items."""
    vid, did = view_and_dimension_for_items
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/views/{vid}/dimensions/{did}/items",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    items = body.get("items")
    assert isinstance(items, list), f"Expected 'items' list; keys: {list(body.keys())}"
    if items:
        assert items[0].get("id"), "Dimension item must have an id"
        assert "name" in items[0], "Dimension item must have a name"


@pytest.mark.live
def test_list_workspace_dimension_items(integration_token, dimension_id):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/dimensions/{dimensionId}/items."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/dimensions/{dimension_id}/items",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    items = body.get("items")
    assert isinstance(items, list), f"Expected 'items' list; keys: {list(body.keys())}"
    if items:
        assert items[0].get("id"), "Dimension item must have an id"
        assert "name" in items[0], "Dimension item must have a name"


@pytest.mark.live
def test_list_lists(integration_token):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/lists returns list of lists."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lists",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    lists = body.get("lists")
    assert isinstance(lists, list), f"Expected 'lists' list; keys: {list(body.keys())}"
    if lists:
        assert lists[0].get("id"), "List must have an id"
        assert "name" in lists[0], "List must have a name"


@pytest.mark.live
def test_get_list(integration_token, list_id):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/lists/{listId} returns list metadata."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lists/{list_id}",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    metadata = body.get("metadata")
    assert metadata is not None, f"Expected 'metadata' key; keys: {list(body.keys())}"
    assert metadata.get("id") == list_id, "Returned list ID must match requested ID"
    assert "name" in metadata, "List metadata must have a name"


# ─── Path-duality probes (issue #26) ──────────────────────────────────────────
# For each endpoint that has both a model-direct and a workspace-prefixed URL form,
# probe the alternate form and compare its response shape to the known baseline.
# 404/405 → warn (document in README); 200 → compare shape (add valid paths to spec).
#
# list_key conventions:
#   str  → body[list_key] is a list or a dict; compare item/object keys to baseline
#   None → flat response (e.g. view detail); compare top-level keys to baseline

_DUALITY_PROBES = [
    pytest.param(
        "/2/0/models/{MODEL_ID}/modules",
        "/2/0/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/modules",
        "modules",
        id="modules",
    ),
    pytest.param(
        "/2/0/models/{MODEL_ID}/modules/{module_id_with_line_items}/lineItems",
        "/2/0/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/modules/{module_id_with_line_items}/lineItems",
        "items",
        id="module-lineItems",
    ),
    pytest.param(
        "/2/0/models/{MODEL_ID}/modules/{module_id_with_views}/views",
        "/2/0/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/modules/{module_id_with_views}/views",
        "views",
        id="module-views",
    ),
    pytest.param(
        "/2/0/models/{MODEL_ID}/lineItems",
        "/2/0/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lineItems",
        "items",
        id="lineItems",
    ),
    pytest.param(
        "/2/0/models/{MODEL_ID}/lineItems/{line_item_id}/dimensions",
        "/2/0/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lineItems/{line_item_id}/dimensions",
        "dimensions",
        id="lineItem-dimensions",
    ),
    pytest.param(
        "/2/0/models/{MODEL_ID}/lineItems/{line_item_id}/dimensions/{dimension_id}/items",
        "/2/0/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lineItems/{line_item_id}/dimensions/{dimension_id}/items",
        "items",
        id="lineItem-dimension-items",
    ),
    pytest.param(
        "/2/0/models/{MODEL_ID}/views/{view_id}",
        "/2/0/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/views/{view_id}",
        None,
        id="view-detail",
    ),
    pytest.param(
        "/2/0/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/views",
        "/2/0/models/{MODEL_ID}/views",
        "views",
        id="views",
    ),
    pytest.param(
        "/2/0/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/dimensions/{dimension_id}/items",
        "/2/0/models/{MODEL_ID}/dimensions/{dimension_id}/items",
        "items",
        id="dimension-items",
    ),
    pytest.param(
        "/2/0/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lists",
        "/2/0/models/{MODEL_ID}/lists",
        "lists",
        id="lists",
    ),
    pytest.param(
        "/2/0/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lists/{list_id}",
        "/2/0/models/{MODEL_ID}/lists/{list_id}",
        "metadata",
        id="list-detail",
    ),
]


def _warn_shape_diff(label, baseline_keys, alt_keys):
    if alt_keys - baseline_keys:
        warnings.warn(
            f"{label}: extra fields vs baseline: {alt_keys - baseline_keys}",
            UserWarning, stacklevel=3,
        )
    if baseline_keys - alt_keys:
        warnings.warn(
            f"{label}: missing fields vs baseline: {baseline_keys - alt_keys}",
            UserWarning, stacklevel=3,
        )


@pytest.mark.live
@pytest.mark.parametrize("baseline_tmpl,alt_tmpl,list_key", _DUALITY_PROBES)
def test_path_duality(request, integration_token, baseline_tmpl, alt_tmpl, list_key):
    """Probe that each endpoint's alternate URL form returns equivalent data (issue #26).

    Uses request.getfixturevalue() to resolve only the fixture IDs that appear in each
    path template, so unrelated fixture failures don't cascade across parametrize cases.
    """
    ctx = {"MODEL_ID": MODEL_ID, "WORKSPACE_ID": WORKSPACE_ID}
    for name in set(re.findall(r'\{(\w+)\}', baseline_tmpl + alt_tmpl)):
        if name not in ctx:
            ctx[name] = request.getfixturevalue(name)

    h = _auth_headers(integration_token)
    baseline_url = f"{API_URL}{baseline_tmpl.format(**ctx)}"
    alt_url = f"{API_URL}{alt_tmpl.format(**ctx)}"

    with httpx.Client() as client:
        baseline = client.get(baseline_url, headers=h)
        response = client.get(alt_url, headers=h)

    if response.status_code in (404, 405):
        warnings.warn(
            f"GET {alt_tmpl} returned {response.status_code} — alternate URL form not available.",
            UserWarning, stacklevel=2,
        )
        return

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200

    if list_key is None:
        if baseline.status_code == 200:
            _warn_shape_diff(alt_tmpl, set(baseline.json().keys()), set(body.keys()))
    else:
        value = body.get(list_key)
        assert value is not None, f"Expected '{list_key}' in response; keys: {list(body.keys())}"
        if isinstance(value, list):
            assert isinstance(value, list), f"Expected '{list_key}' to be a list"
            if baseline.status_code == 200:
                bl_first = (baseline.json().get(list_key) or [{}])[0]
                alt_first = (value or [{}])[0]
                _warn_shape_diff(alt_tmpl, set(bl_first.keys()), set(alt_first.keys()))
        else:
            assert isinstance(value, dict), \
                f"Expected '{list_key}' to be a list or dict; got {type(value)}"
            if baseline.status_code == 200:
                bl_obj = baseline.json().get(list_key) or {}
                _warn_shape_diff(alt_tmpl, set(bl_obj.keys()), set(value.keys()))


# ─── pages and sort query parameter probes (issue #31) ─────────────────────────


@pytest.fixture(scope="module")
def view_with_page_selector(integration_token):
    """(view_id, page_selector) — first view that has a page-axis dimension with items.

    Page-axis dimensions are those NOT on the rows or columns axes of the view.
    Items are fetched from GET /workspaces/{wid}/models/{mid}/dimensions/{did}/items.
    Dimensions are discovered via the module → lineItems → dimensions path.
    """
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        # Collect model dimensions via module/lineItem path
        model_dim_ids = set()
        mods_r = client.get(f"{API_URL}/models/{MODEL_ID}/modules", headers=h)
        if mods_r.status_code != 200:
            pytest.skip("Could not list modules for page selector discovery")
        for mod in mods_r.json().get("modules", [])[:5]:
            li_r = client.get(
                f"{API_URL}/models/{MODEL_ID}/modules/{mod['id']}/lineItems",
                headers=h,
            )
            if li_r.status_code != 200:
                continue
            for li in li_r.json().get("items", [])[:3]:
                dim_r = client.get(
                    f"{API_URL}/models/{MODEL_ID}/lineItems/{li['id']}/dimensions",
                    headers=h,
                )
                if dim_r.status_code == 200:
                    for dim in dim_r.json().get("dimensions", []):
                        model_dim_ids.add(dim["id"])

        # Find a view where at least one model dimension is on the pages axis
        views = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/views",
            headers=h,
        ).json().get("views", [])
        for v in views:
            vid = v["id"]
            detail = client.get(f"{API_URL}/models/{MODEL_ID}/views/{vid}", headers=h)
            if detail.status_code != 200:
                continue
            d = detail.json()
            axis_dims = (
                {r["id"] for r in d.get("rows", [])}
                | {c["id"] for c in d.get("columns", [])}
            )
            for did in model_dim_ids - axis_dims:
                items_r = client.get(
                    f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
                    f"/dimensions/{did}/items",
                    headers=h,
                )
                if items_r.status_code != 200 or not items_r.json().get("items"):
                    continue
                item_id = items_r.json()["items"][0]["id"]
                selector = f"{did}:{item_id}"
                # Validate the selector actually works on this view before returning
                probe = client.get(
                    f"{API_URL}/models/{MODEL_ID}/views/{vid}/data",
                    headers=h,
                    params={"pages": selector, "format": "v1"},
                )
                if probe.status_code == 200:
                    return vid, selector

    pytest.skip("No view with a page-axis dimension found in test model")


@pytest.mark.live
def test_view_data_pages_single_value(integration_token, view_with_page_selector):
    """GET /models/{modelId}/views/{viewId}/data?pages=dimId:itemId returns 200 (CSV).

    Confirms the pages parameter is accepted. Response is text/csv with format=v1.
    """
    vid, page_selector = view_with_page_selector
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/views/{vid}/data",
            headers=_auth_headers(integration_token),
            params={"pages": page_selector, "format": "v1"},
        )

    assert response.status_code == 200, (
        f"Expected 200 for pages param, got {response.status_code}: {response.text[:300]}"
    )
    assert "text/csv" in response.headers.get("content-type", ""), (
        f"Expected CSV response with format=v1, got: {response.headers.get('content-type')}"
    )


@pytest.mark.live
def test_view_data_pages_repeated_key(integration_token, view_with_page_selector):
    """GET view data with pages= as a repeated key also returns 200.

    Both pages=a:b,c:d (comma-separated) and pages=a:b&pages=c:d (repeated)
    are accepted. This test confirms the repeated-key form.
    """
    vid, page_selector = view_with_page_selector
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/views/{vid}/data",
            headers=_auth_headers(integration_token),
            params=[("pages", page_selector), ("format", "v1")],
        )

    assert response.status_code == 200, (
        f"Expected 200 for repeated pages key, got {response.status_code}: "
        f"{response.text[:300]}"
    )


@pytest.mark.live
def test_tasks_sort_param(integration_token):
    """Task list endpoints accept sort parameter with documented field names and prefixes.

    Probes creationDate, taskId, taskState, progress with -, +, and no prefix.
    All combinations return 200. The API does not validate sort field names
    server-side — invalid fields also return 200 (silently ignored or default order).
    Actual ordering cannot be verified when the task list is empty.
    """
    h = _auth_headers(integration_token)
    sort_values = [
        "creationDate", "-creationDate", "+creationDate",
        "taskId", "-taskId", "+taskId",
        "taskState", "-taskState", "+taskState",
        "progress", "-progress", "+progress",
    ]
    action_types = ["imports", "exports", "processes", "actions"]
    findings = []
    with httpx.Client() as client:
        for action_type in action_types:
            list_url = (
                f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/{action_type}"
            )
            r = client.get(list_url, headers=h)
            if r.status_code != 200:
                findings.append(f"{action_type}: could not list ({r.status_code})")
                continue
            resources = r.json().get(action_type, [])
            if not resources:
                findings.append(f"{action_type}: no resources, skipping")
                continue
            rid = resources[0]["id"]
            tasks_url = (
                f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
                f"/{action_type}/{rid}/tasks"
            )
            for sv in sort_values:
                r_sort = client.get(tasks_url, headers=h, params={"sort": sv})
                findings.append(f"{action_type} sort={sv!r} -> {r_sort.status_code}")
                assert r_sort.status_code == 200, (
                    f"sort={sv!r} rejected on {action_type} tasks: {r_sort.status_code}"
                )

    print("\nSort probe results:")
    for f in findings:
        print(f"  {f}")


# ─── PUT /currentPeriod interface probe ────────────────────────────────────────
# Non-destructive: all requests use invalid inputs so the API rejects them
# before making any change.


@pytest.mark.live
def test_current_period_invalid_date_in_body_returns_400(integration_token):
    """PUT /2/0/models/{modelId}/currentPeriod with invalid date in body returns 400."""
    h = {**_auth_headers(integration_token), "Content-Type": "application/json"}
    with httpx.Client() as client:
        response = client.put(
            f"{API_URL}/models/{MODEL_ID}/currentPeriod",
            headers=h,
            json={"date": "not-a-date"},
        )

    assert response.status_code == 400, (
        f"Expected 400 for invalid date in body, got {response.status_code}: "
        f"{response.text[:300]}"
    )
    body = response.json()
    print(f"\nbody form 400 response: {body}")


@pytest.mark.live
def test_current_period_invalid_date_as_query_param_returns_400(integration_token):
    """PUT /2/0/models/{modelId}/currentPeriod?date=invalid returns 400.

    Confirms date is accepted as a query parameter (no body sent).
    Live probe also confirmed: sending both query param and body returns
    400 'use query parameter or body to set date, not both'.
    """
    with httpx.Client() as client:
        response = client.put(
            f"{API_URL}/models/{MODEL_ID}/currentPeriod",
            headers=_auth_headers(integration_token),
            params={"date": "not-a-date"},
        )

    assert response.status_code == 400, (
        f"Expected 400 for invalid date as query param, got {response.status_code}: "
        f"{response.text[:300]}"
    )
    body = response.json()
    assert "Invalid ISO date format" in body.get("status", {}).get("message", ""), (
        f"Expected format-error message, got: {body}"
    )


@pytest.mark.live
def test_workspace_current_period_put_invalid_date_returns_400(integration_token):
    """PUT /2/0/workspaces/{workspaceId}/models/{modelId}/currentPeriod with invalid date returns 400.

    Live probe confirmed this workspace-scoped form exists and behaves identically
    to the model-direct PUT /models/{modelId}/currentPeriod.
    Non-destructive: invalid date is rejected before any state change.
    """
    h = {**_auth_headers(integration_token), "Content-Type": "application/json"}
    with httpx.Client() as client:
        response = client.put(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/currentPeriod",
            headers=h,
            json={"date": "not-a-date"},
        )

    assert response.status_code == 400, (
        f"Expected 400 for invalid date on workspace currentPeriod PUT, got {response.status_code}: "
        f"{response.text[:300]}"
    )
    body = response.json()
    assert "Invalid ISO date format" in body.get("status", {}).get("message", ""), (
        f"Expected format-error message, got: {body}"
    )


@pytest.mark.live
def test_model_dimension_items_post_empty_body_returns_400(integration_token, dimension_id):
    """POST /2/0/models/{modelId}/dimensions/{dimensionId}/items with empty names/codes returns 400.

    Live probe confirmed this model-direct form exists and behaves identically to
    POST /workspaces/{workspaceId}/models/{modelId}/dimensions/{dimensionId}/items.
    Non-destructive: empty names+codes is rejected before returning any data.
    """
    h = {**_auth_headers(integration_token), "Content-Type": "application/json"}
    with httpx.Client() as client:
        response = client.post(
            f"{API_URL}/models/{MODEL_ID}/dimensions/{dimension_id}/items",
            headers=h,
            json={"names": [], "codes": []},
        )

    assert response.status_code == 400, (
        f"Expected 400 for empty names/codes on model dimension items POST, got {response.status_code}: "
        f"{response.text[:300]}"
    )
    body = response.json()
    assert body.get("status", {}).get("code") == 400, f"Expected status.code 400, got: {body}"


# ─── Model settings (versions, current period, model calendar) ─────────────────


@pytest.fixture(scope="module")
def version_id(integration_token):
    """First version ID from the model versions list."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(f"{API_URL}/models/{MODEL_ID}/versions", headers=h)
    if r.status_code != 200:
        pytest.skip(f"Could not list versions: {r.status_code}")
    versions = r.json().get("versionMetadata", [])
    if not versions:
        pytest.skip("No versions in test model")
    return versions[0]["id"]


@pytest.mark.live
def test_list_versions(integration_token):
    """GET /2/0/models/{modelId}/versions returns list of version metadata."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/versions",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    versions = body.get("versionMetadata")
    assert isinstance(versions, list), f"Expected 'versionMetadata' list; keys: {list(body.keys())}"
    if versions:
        assert versions[0].get("id"), "Version must have an id"
        assert "name" in versions[0], "Version must have a name"


@pytest.mark.live
def test_get_workspace_current_period(integration_token):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/currentPeriod returns current period."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/currentPeriod",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    period = body.get("currentPeriod")
    assert period is not None, f"Expected 'currentPeriod'; keys: {list(body.keys())}"
    assert "periodText" in period, "currentPeriod must have periodText"
    assert "lastDay" in period, "currentPeriod must have lastDay"


@pytest.mark.live
def test_get_model_current_period(integration_token):
    """GET /2/0/models/{modelId}/currentPeriod returns current period (model-scoped)."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/currentPeriod",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    period = body.get("currentPeriod")
    assert period is not None, f"Expected 'currentPeriod'; keys: {list(body.keys())}"
    assert "periodText" in period, "currentPeriod must have periodText"
    assert "lastDay" in period, "currentPeriod must have lastDay"


@pytest.mark.live
def test_get_model_calendar(integration_token):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/modelCalendar returns model calendar."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/modelCalendar",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    calendar = body.get("modelCalendar")
    assert calendar is not None, f"Expected 'modelCalendar'; keys: {list(body.keys())}"


@pytest.mark.live
def test_get_fiscal_year(integration_token):
    """GET /2/0/models/{modelId}/modelCalendar/fiscalYear returns 405 — GET not supported.

    Live testing confirmed this path only supports PUT. Fiscal year info is available
    via GET /workspaces/{workspaceId}/models/{modelId}/modelCalendar instead.
    See integration/README.md discrepancies.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/modelCalendar/fiscalYear",
            headers=_auth_headers(integration_token),
        )

    if response.status_code == 405:
        warnings.warn(
            "GET /models/{modelId}/modelCalendar/fiscalYear returned 405 — "
            "only PUT is supported on this path. Use GET /workspaces/{workspaceId}/models/{modelId}/modelCalendar "
            "for fiscal year data. See integration/README.md discrepancies.",
            UserWarning,
            stacklevel=2,
        )
        return

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    calendar = body.get("modelCalendar")
    assert calendar is not None, f"Expected 'modelCalendar'; keys: {list(body.keys())}"
    fiscal_year = calendar.get("fiscalYear")
    assert fiscal_year is not None, (
        f"modelCalendar must have fiscalYear; calendar keys: {list(calendar.keys())}"
    )
    assert "year" in fiscal_year, "fiscalYear must have year"


@pytest.mark.live
@pytest.mark.write
def test_switchover_invalid_date_returns_400(integration_token, version_id):
    """PUT /2/0/models/{modelId}/versions/{versionId}/switchover with invalid date returns 400.

    Non-destructive guard: invalid date format is rejected before any state change.
    Auto-skipped without --allow-writes (conftest guard intercepts the PUT).
    """
    h = {**_auth_headers(integration_token), "Content-Type": "application/json"}
    with httpx.Client() as client:
        response = client.put(
            f"{API_URL}/models/{MODEL_ID}/versions/{version_id}/switchover",
            headers=h,
            json={"date": "not-a-date"},
        )

    assert response.status_code == 400, (
        f"Expected 400 for invalid switchover date, got {response.status_code}: "
        f"{response.text[:300]}"
    )


# ─── File and chunk operations ─────────────────────────────────────────────────


@pytest.fixture(scope="module")
def file_id(integration_token):
    """File ID for file management tests.

    Uses INTEGRATION_FILE env var when set; falls back to first file in the model.
    """
    if INTEGRATION_FILE_ID:
        return INTEGRATION_FILE_ID
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(f"{API_URL}/models/{MODEL_ID}/files", headers=h)
    if r.status_code != 200:
        pytest.skip(f"Could not list files: {r.status_code}")
    files = r.json().get("files", [])
    if not files:
        pytest.skip("No files in test model")
    return files[0]["id"]


@pytest.mark.live
def test_list_model_files(integration_token):
    """GET /2/0/models/{modelId}/files returns list of model files."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/files",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    files = body.get("files")
    assert isinstance(files, list), f"Expected 'files' list; keys: {list(body.keys())}"
    if files:
        assert files[0].get("id"), "File must have an id"
        assert "name" in files[0], "File must have a name"


@pytest.mark.live
def test_get_file_metadata(integration_token, file_id):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/files/{fileId} returns file metadata.

    NOTE: Live testing shows this endpoint returns 404 even for files visible in
    GET /models/{modelId}/files. Individual file metadata is only available via
    the full list endpoint. See integration/README.md discrepancies.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/files/{file_id}",
            headers=_auth_headers(integration_token),
        )

    if response.status_code == 404:
        warnings.warn(
            f"GET /workspaces/.../files/{file_id} returned 404 — "
            "individual file metadata endpoint not available; use GET /models/{modelId}/files instead. "
            "See integration/README.md discrepancies.",
            UserWarning,
            stacklevel=2,
        )
        return

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    ct = response.headers.get("content-type", "")
    if "application/json" not in ct:
        warnings.warn(
            f"GET /workspaces/.../files/{file_id} returned 200 with non-JSON content-type "
            f"({ct!r}) — endpoint returned file content rather than metadata for this file. "
            "See integration/README.md discrepancies.",
            UserWarning,
            stacklevel=2,
        )
        return
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    file_obj = body.get("file")
    assert file_obj is not None, f"Expected 'file' key; keys: {list(body.keys())}"
    assert file_obj.get("id") == file_id, "Returned file ID must match requested ID"
    assert "name" in file_obj, "File metadata must have a name"


@pytest.mark.live
def test_list_file_chunks(integration_token, file_id):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/files/{fileId}/chunks returns chunk list."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/files/{file_id}/chunks",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    chunks = body.get("chunks")
    # When chunkCount == 0, the API omits the 'chunks' key entirely; accept None or list.
    assert chunks is None or isinstance(chunks, list), (
        f"Expected 'chunks' to be a list or absent; got {type(chunks)}"
    )
    if chunks:
        assert "id" in chunks[0], "Chunk must have an id"


@pytest.mark.live
def test_download_first_chunk(integration_token, file_id):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/files/{fileId}/chunks/0 downloads first chunk.

    Uses the model-level file list to check chunkCount (workspace-scoped metadata
    endpoint returns 404 for non-Workspace-Administrator accounts).
    Skipped when the file has no chunks — INTEGRATION_FILE is an import source file
    whose content is populated by the import action; it may be empty between test runs.
    Also skips when chunks/0 returns 404 (content deleted by a prior write test teardown).
    """
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        files_r = client.get(f"{API_URL}/models/{MODEL_ID}/files", headers=h)
        if files_r.status_code != 200:
            pytest.skip(f"Could not list files: {files_r.status_code}")
        file_meta = next(
            (f for f in files_r.json().get("files", []) if str(f["id"]) == str(file_id)),
            None,
        )
        if file_meta is None:
            pytest.skip(f"File {file_id} not found in model file list")
        if not file_meta.get("chunkCount"):
            pytest.skip(f"File {file_id} has no chunks (chunkCount=0)")

        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/files/{file_id}/chunks/0",
            headers=h,
        )

    if response.status_code == 404:
        pytest.skip(
            f"GET .../files/{file_id}/chunks/0 returned 404 — "
            "file content was cleared by a prior write-test teardown; "
            "upload new content to re-enable this test."
        )
    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    assert len(response.content) > 0, "Chunk download must return non-empty body"
    ct = response.headers.get("content-type", "")
    print(f"\nGET .../chunks/0 content-type: {ct!r}, body bytes: {len(response.content)}")
    assert "octet-stream" in ct, (
        f"Expected application/octet-stream response; content-type: {ct!r}"
    )


@pytest.mark.live
@pytest.mark.write
def test_upload_single_chunk(integration_token, file_id):
    """PUT /2/0/workspaces/{workspaceId}/models/{modelId}/files/{fileId} uploads a file as a single chunk.

    Single-chunk upload: PUT directly to the file path (no set-chunk-count or complete step).
    Probes PUT response body (JSON envelope or no-body 204) and DELETE response shape.
    Verifies the chunk appears in GET .../chunks. Teardown via DELETE.
    """
    h = _auth_headers(integration_token)
    chunk_data = b"col_a\nval1\n"

    with httpx.Client() as client:
        # Upload file as single chunk directly to the file path
        upload_r = client.put(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/files/{file_id}",
            headers={**h, "Content-Type": "application/octet-stream"},
            content=chunk_data,
        )
        assert upload_r.status_code in (200, 204), (
            f"PUT single-chunk upload failed: {upload_r.status_code}: {upload_r.text[:200]}"
        )
        print(f"\nPUT /files/{{fileId}} status: {upload_r.status_code}")
        if upload_r.status_code == 200 and upload_r.content:
            put_body = upload_r.json()
            print(f"PUT /files/{{fileId}} body keys: {list(put_body.keys())}")
            assert "status" in put_body, (
                f"Expected 'status' in PUT 200 response; keys: {list(put_body.keys())}"
            )

        # Verify the chunk appears
        verify_r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/files/{file_id}/chunks",
            headers=h,
        )
        assert verify_r.status_code == 200
        chunks = verify_r.json().get("chunks", [])
        assert len(chunks) == 1, (
            f"Expected 1 chunk after upload; got {len(chunks)}"
        )

        # Teardown — probe DELETE response shape
        delete_r = client.delete(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/files/{file_id}",
            headers=h,
        )
        assert delete_r.status_code in (200, 204), (
            f"DELETE file failed: {delete_r.status_code}: {delete_r.text[:200]}"
        )
        print(f"\nDELETE /files/{{fileId}} status: {delete_r.status_code}")
        if delete_r.status_code == 200 and delete_r.content:
            del_body = delete_r.json()
            print(f"DELETE /files/{{fileId}} body keys: {list(del_body.keys())}")


@pytest.mark.live
@pytest.mark.write
def test_upload_and_complete_cycle(integration_token, file_id):
    """Multi-chunk upload cycle: set chunk count → PUT chunk → POST complete → verify → teardown.

    Uses the first available file staging area. Tests the three-step multi-chunk pattern.
    Restores original state via DELETE.

    NOTE: Live testing shows POST /complete returns 500 for standard Integration API users
    on this test model. Set chunk count, PUT chunk, and GET chunks all succeed. The 500
    on complete is documented as a discrepancy. See integration/README.md.
    """
    h = _auth_headers(integration_token)
    chunk_data = b"col_a,col_b\nval1,val2\n"

    with httpx.Client() as client:
        # Step 1: set chunk count to -1 (variable-length multi-chunk mode)
        set_count_r = client.post(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/files/{file_id}",
            headers={**h, "Content-Type": "application/json"},
            json={"chunkCount": -1},
        )
        assert set_count_r.status_code == 200, (
            f"POST set chunk count failed: {set_count_r.status_code}: {set_count_r.text[:200]}"
        )

        # Step 2: upload chunk 0 — API returns 204 No Content on success
        upload_r = client.put(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/files/{file_id}/chunks/0",
            headers={**h, "Content-Type": "application/octet-stream"},
            content=chunk_data,
        )
        assert upload_r.status_code in (200, 204), (
            f"PUT chunk 0 failed: {upload_r.status_code}: {upload_r.text[:200]}"
        )

        # Verify the chunk is staged
        chunks_r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/files/{file_id}/chunks",
            headers=h,
        )
        assert chunks_r.status_code == 200
        assert len(chunks_r.json().get("chunks", [])) == 1, "Chunk must be staged before complete"

        # Step 3: mark upload complete — requires Content-Type header
        complete_r = client.post(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/files/{file_id}/complete",
            headers={**h, "Content-Type": "application/json"},
        )
        if complete_r.status_code == 500:
            warnings.warn(
                f"POST /files/{file_id}/complete returned 500 — "
                "complete endpoint not supported on this model/account. "
                "Set chunk count, PUT chunk, and GET chunks all succeeded. "
                "See integration/README.md discrepancies.",
                UserWarning,
                stacklevel=2,
            )
        else:
            assert complete_r.status_code in (200, 204), (
                f"POST complete failed: {complete_r.status_code}: {complete_r.text[:200]}"
            )

        # Teardown
        client.delete(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/files/{file_id}",
            headers=h,
        )


# ─── Action execution fixtures ────────────────────────────────────────────────


@pytest.fixture(scope="module")
def import_id(integration_token):
    """First import ID from the workspace/model import list, or skip if none."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/imports/",
            headers=h,
        )
    if r.status_code != 200:
        pytest.skip(f"Could not list imports: {r.status_code}")
    imports = r.json().get("imports", [])
    if not imports:
        pytest.skip("No imports in test model")
    return imports[0]["id"]


@pytest.fixture(scope="module")
def export_id(integration_token):
    """First export ID from the workspace/model export list, or skip if none."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports",
            headers=h,
        )
    if r.status_code != 200:
        pytest.skip(f"Could not list exports: {r.status_code}")
    exports = r.json().get("exports", [])
    if not exports:
        pytest.skip("No exports in test model")
    return exports[0]["id"]


@pytest.fixture(scope="module")
def process_id(integration_token):
    """First process ID from the workspace/model process list, or skip if none."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/processes",
            headers=h,
        )
    if r.status_code != 200:
        pytest.skip(f"Could not list processes: {r.status_code}")
    processes = r.json().get("processes", [])
    if not processes:
        pytest.skip("No processes in test model")
    return processes[0]["id"]


@pytest.fixture(scope="module")
def action_id(integration_token):
    """First action ID from the workspace/model action list, or skip if none."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/actions",
            headers=h,
        )
    if r.status_code != 200:
        pytest.skip(f"Could not list actions: {r.status_code}")
    actions = r.json().get("actions", [])
    if not actions:
        pytest.skip("No actions in test model")
    return actions[0]["id"]


@pytest.fixture(scope="module")
def import_task_id(integration_token, import_id):
    """Most-recent task ID for the first import, or skip if task history is empty."""
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{import_id}/tasks",
            headers=h,
        )
    if r.status_code != 200:
        pytest.skip(f"Could not list import tasks: {r.status_code}")
    body = r.json()
    tasks = body.get("tasks") or ([body["task"]] if body.get("task") else [])
    if not tasks:
        pytest.skip("No import task history for this import")
    return tasks[0].get("taskId")


# ─── Imports ──────────────────────────────────────────────────────────────────


@pytest.mark.live
def test_list_imports(integration_token):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/imports/ returns import list."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/imports/",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    imports = body.get("imports")
    assert isinstance(imports, list), f"Expected 'imports' list; keys: {list(body.keys())}"
    if imports:
        assert imports[0].get("id"), "Import must have an id"
        assert "name" in imports[0], "Import must have a name"


@pytest.mark.live
def test_get_import_metadata(integration_token, import_id):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/imports/{importId} returns metadata.

    NOTE: Live testing shows the API returns {importMetadata: {name, type}} — no id field.
    The id is only included in the list response, not the single-item metadata response.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/imports/{import_id}",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    import_obj = body.get("importMetadata")
    assert import_obj is not None, f"Expected 'importMetadata' key; keys: {list(body.keys())}"
    assert "name" in import_obj, "Import metadata must have a name"


@pytest.mark.live
def test_list_import_tasks(integration_token, import_id):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/imports/{importId}/tasks lists tasks.

    NOTE: When no tasks have ever run, the API returns {meta: {paging: {totalSize: 0}}, status}
    with no 'tasks' or 'task' key. This is the correct empty-list representation.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{import_id}/tasks",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    tasks = body.get("tasks") or ([body["task"]] if body.get("task") else [])
    for t in tasks:
        assert t.get("taskId"), "Task must have a taskId"
        assert "taskState" in t, "Task must have a taskState"


@pytest.mark.live
def test_get_import_task(integration_token, import_id, import_task_id):
    """GET .../imports/{importId}/tasks/{taskId} returns task status with result."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{import_id}/tasks/{import_task_id}",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    task = body.get("task")
    assert task is not None, f"Expected 'task' key; keys: {list(body.keys())}"
    assert task.get("taskId") == import_task_id, "Returned taskId must match requested ID"
    assert "taskState" in task, "Task must have a taskState"
    assert task["taskState"] in {"NOT_STARTED", "IN_PROGRESS", "COMPLETE", "CANCELLING", "CANCELLED"}, (
        f"Unknown taskState: {task['taskState']}"
    )


@pytest.mark.live
def test_import_dump_chunks(integration_token, import_id, import_task_id):
    """GET .../imports/{importId}/tasks/{taskId}/dump/chunks returns chunk list.

    Only meaningful when the task completed with failures (failureDumpAvailable=True).
    Probes the endpoint and accepts 200 with any valid shape. Skips if the task
    poll shows no dump is available.
    """
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        task_r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{import_id}/tasks/{import_task_id}",
            headers=h,
        )
        if task_r.status_code != 200:
            pytest.skip(f"Could not fetch task status: {task_r.status_code}")
        task = task_r.json().get("task", {})
        result = task.get("result", {})

        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{import_id}/tasks/{import_task_id}/dump/chunks",
            headers=h,
        )

    if not result.get("failureDumpAvailable"):
        if response.status_code in (404, 400):
            return
        if response.status_code == 200:
            body = response.json()
            chunks = body.get("chunks", [])
            assert isinstance(chunks, list), f"Expected 'chunks' list; keys: {list(body.keys())}"
            return

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    chunks = body.get("chunks")
    assert isinstance(chunks, list), f"Expected 'chunks' list; keys: {list(body.keys())}"


@pytest.mark.live
def test_import_dump(integration_token, import_id, import_task_id):
    """GET .../imports/{importId}/tasks/{taskId}/dump returns text/plain or 404.

    Returns the full dump file (unchunked). When failureDumpAvailable=True the
    body is plain text with CSV-formatted error rows. When no dump is available
    the API returns 404 (or 204 on some regions).
    """
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        task_r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{import_id}/tasks/{import_task_id}",
            headers=h,
        )
        if task_r.status_code != 200:
            pytest.skip(f"Could not fetch task status: {task_r.status_code}")
        task = task_r.json().get("task", {})
        dump_available = task.get("result", {}).get("failureDumpAvailable", False)

        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{import_id}/tasks/{import_task_id}/dump",
            headers=h,
        )

    if not dump_available:
        assert response.status_code in (200, 204, 404), (
            f"GET .../dump (no dump expected) returned unexpected status: {response.status_code}"
        )
        return

    assert response.status_code in (200, 404), (
        f"GET .../dump returned unexpected status: {response.status_code}: {response.text[:200]}"
    )
    if response.status_code == 200:
        ct = response.headers.get("content-type", "")
        assert "text" in ct or "octet" in ct, (
            f"Expected text/plain or octet-stream for dump content; got: {ct!r}"
        )
        assert len(response.content) > 0, "Dump body must not be empty when status is 200"
        print(f"\nGET .../dump content-type: {ct!r}, body bytes: {len(response.content)}")


@pytest.mark.live
def test_import_dump_chunk_download(integration_token, import_id, import_task_id):
    """GET .../imports/{importId}/tasks/{taskId}/dump/chunks/0 downloads first dump chunk.

    Only probed when failureDumpAvailable=True and dump/chunks lists at least one chunk.
    Confirms the response is plain text with CSV-formatted error rows.
    """
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        task_r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{import_id}/tasks/{import_task_id}",
            headers=h,
        )
        if task_r.status_code != 200:
            pytest.skip(f"Could not fetch task status: {task_r.status_code}")
        task = task_r.json().get("task", {})
        if not task.get("result", {}).get("failureDumpAvailable"):
            pytest.skip("failureDumpAvailable=False for this task — no dump chunk to download")

        chunks_r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{import_id}/tasks/{import_task_id}/dump/chunks",
            headers=h,
        )
        if chunks_r.status_code != 200:
            pytest.skip(f"dump/chunks returned {chunks_r.status_code}")
        chunks = chunks_r.json().get("chunks", [])
        if not chunks:
            pytest.skip("dump/chunks returned empty list — no chunks to download")

        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{import_id}/tasks/{import_task_id}/dump/chunks/0",
            headers=h,
        )

    assert response.status_code == 200, (
        f"GET .../dump/chunks/0 returned {response.status_code}: {response.text[:200]}"
    )
    assert len(response.content) > 0, "Dump chunk 0 must have non-empty content"
    ct = response.headers.get("content-type", "")
    print(f"\nGET .../dump/chunks/0 content-type: {ct!r}, body bytes: {len(response.content)}")
    assert "text" in ct or "octet" in ct, (
        f"Expected text/plain or octet-stream for dump chunk; got: {ct!r}"
    )


# ─── Exports ──────────────────────────────────────────────────────────────────


@pytest.mark.live
def test_list_exports(integration_token):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/exports returns export list."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    exports = body.get("exports")
    assert isinstance(exports, list), f"Expected 'exports' list; keys: {list(body.keys())}"
    if exports:
        assert exports[0].get("id"), "Export must have an id"
        assert "name" in exports[0], "Export must have a name"


@pytest.mark.live
def test_get_export_metadata(integration_token, export_id):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/exports/{exportId} returns metadata.

    NOTE: Live testing shows the API returns {exportMetadata: {...}} — no id field in the
    metadata object. The id is only included in the list response.
    """
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports/{export_id}",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    export_obj = body.get("exportMetadata")
    assert export_obj is not None, f"Expected 'exportMetadata' key; keys: {list(body.keys())}"
    assert isinstance(export_obj, dict) and export_obj, "exportMetadata must be a non-empty object"
    assert "encoding" in export_obj, f"exportMetadata must have 'encoding'; keys: {list(export_obj.keys())}"


@pytest.mark.live
def test_list_export_tasks(integration_token, export_id):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/exports/{exportId}/tasks lists tasks."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/exports/{export_id}/tasks",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    tasks = body.get("tasks") or ([body["task"]] if body.get("task") else [])
    assert isinstance(tasks, list), f"Expected 'tasks' list; keys: {list(body.keys())}"
    if tasks:
        assert tasks[0].get("taskId"), "Task must have a taskId"
        assert "taskState" in tasks[0], "Task must have a taskState"


@pytest.mark.live
@pytest.mark.write
def test_run_export_and_poll_task(integration_token, export_id):
    """POST export task + poll GET until terminal state (non-destructive run-and-poll cycle).

    Requires --allow-writes. Without it the POST is auto-skipped by the write guard.
    Times out after 30 s; fails if terminal state is not reached.
    """
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        run_r = client.post(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/exports/{export_id}/tasks",
            headers={**h, "Content-Type": "application/json"},
            json={"localeName": "en_US"},
        )

    assert run_r.status_code == 200, (
        f"POST export task failed: {run_r.status_code}: {run_r.text[:200]}"
    )
    run_body = run_r.json()
    task_id = run_body.get("task", {}).get("taskId") or run_body.get("taskId")
    assert task_id, f"Expected taskId in POST response; keys: {list(run_body.keys())}"

    terminal_states = {"COMPLETE", "CANCELLED", "CANCELLING"}
    deadline = time.time() + 30
    task = None
    with httpx.Client() as client:
        while time.time() < deadline:
            poll_r = client.get(
                f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
                f"/exports/{export_id}/tasks/{task_id}",
                headers=h,
            )
            assert poll_r.status_code == 200, (
                f"Poll failed: {poll_r.status_code}: {poll_r.text[:200]}"
            )
            task = poll_r.json().get("task", {})
            if task.get("taskState") in terminal_states:
                break
            time.sleep(2)

    assert task is not None, "No task response received during polling"
    assert task.get("taskState") in terminal_states, (
        f"Export task did not reach terminal state within 30s; "
        f"last state: {task.get('taskState')}"
    )
    assert task.get("taskId") == task_id, "Polled taskId must match started taskId"
    result = task.get("result")
    assert result is not None, "Completed task must have a result"
    assert "successful" in result, "Task result must have 'successful' field"


# ─── Actions ──────────────────────────────────────────────────────────────────


@pytest.mark.live
def test_list_actions(integration_token):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/actions returns action list."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/actions",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    actions = body.get("actions")
    assert isinstance(actions, list), f"Expected 'actions' list; keys: {list(body.keys())}"
    if actions:
        assert actions[0].get("id"), "Action must have an id"
        assert "name" in actions[0], "Action must have a name"


@pytest.mark.live
def test_list_action_tasks(integration_token, action_id):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/actions/{actionId}/tasks lists tasks."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/actions/{action_id}/tasks",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    tasks = body.get("tasks") or ([body["task"]] if body.get("task") else [])
    assert isinstance(tasks, list), f"Expected 'tasks' list; keys: {list(body.keys())}"
    if tasks:
        assert tasks[0].get("taskId"), "Task must have a taskId"
        assert "taskState" in tasks[0], "Task must have a taskState"


# ─── Processes ────────────────────────────────────────────────────────────────


@pytest.mark.live
def test_list_processes(integration_token):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/processes returns process list."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/processes",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    processes = body.get("processes")
    assert isinstance(processes, list), f"Expected 'processes' list; keys: {list(body.keys())}"
    if processes:
        assert processes[0].get("id"), "Process must have an id"
        assert "name" in processes[0], "Process must have a name"


@pytest.mark.live
def test_get_process_detail(integration_token, process_id):
    """GET /2/0/models/{modelId}/processes/{processId} returns process detail."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/processes/{process_id}",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    process = body.get("process") or body.get("processMetadata")
    assert process is not None, f"Expected process detail key; keys: {list(body.keys())}"
    assert "name" in process, "Process detail must have a name"


@pytest.mark.live
def test_list_process_tasks(integration_token, process_id):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/processes/{processId}/tasks lists tasks."""
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/processes/{process_id}/tasks",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    tasks = body.get("tasks") or ([body["task"]] if body.get("task") else [])
    assert isinstance(tasks, list), f"Expected 'tasks' list; keys: {list(body.keys())}"
    if tasks:
        assert tasks[0].get("taskId"), "Task must have a taskId"
        assert "taskState" in tasks[0], "Task must have a taskState"


# ─── Write tests: run-and-poll cycles using INTEGRATION_* env vars ────────────


def _poll_to_terminal(client, url, h, timeout=60):
    """Poll GET url until taskState reaches a terminal state. Returns final task dict."""
    terminal = {"COMPLETE", "CANCELLED", "CANCELLING"}
    deadline = time.time() + timeout
    task: dict = {}
    while time.time() < deadline:
        poll_r = client.get(url, headers=h)
        assert poll_r.status_code == 200, (
            f"Poll failed: {poll_r.status_code}: {poll_r.text[:200]}"
        )
        task = poll_r.json().get("task", {})
        if task.get("taskState") in terminal:
            break
        time.sleep(2)
    return task


@pytest.mark.live
@pytest.mark.write
def test_run_process_and_poll_task(integration_token):
    """POST .../processes/{processId}/tasks starts a process; GET .../tasks/{taskId} polls it.

    Uses INTEGRATION_PROCESS from .env. Skipped when the variable is not set.
    """
    if not INTEGRATION_PROCESS_ID:
        pytest.skip("INTEGRATION_PROCESS not set in environment")
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        run_r = client.post(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/processes/{INTEGRATION_PROCESS_ID}/tasks",
            headers={**h, "Content-Type": "application/json"},
            json={"localeName": "en_US"},
        )
        assert run_r.status_code == 200, (
            f"POST process task failed: {run_r.status_code}: {run_r.text[:200]}"
        )
        run_body = run_r.json()
        task_id = run_body.get("task", {}).get("taskId") or run_body.get("taskId")
        assert task_id, f"Expected taskId in POST response; keys: {list(run_body.keys())}"

        task = _poll_to_terminal(
            client,
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/processes/{INTEGRATION_PROCESS_ID}/tasks/{task_id}",
            h,
        )

    assert task is not None, "No task response received"
    assert task.get("taskState") in {"COMPLETE", "CANCELLED", "CANCELLING"}, (
        f"Process task did not reach terminal state within 60s; last: {task.get('taskState')}"
    )
    assert task.get("taskId") == task_id, "Polled taskId must match started taskId"
    result = task.get("result")
    assert result is not None, "Completed process task must have a result"
    assert "successful" in result, "Task result must have 'successful' field"


@pytest.mark.live
@pytest.mark.write
def test_run_action_and_poll_task(integration_token):
    """POST .../actions/{actionId}/tasks starts an action; GET .../tasks/{taskId} polls it.

    Uses INTEGRATION_ACTION from .env. Skipped when the variable is not set.
    Also probes GET /actions/{actionId}/tasks/{taskId} to validate the spec entry.
    """
    if not INTEGRATION_ACTION_ID:
        pytest.skip("INTEGRATION_ACTION not set in environment")
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        run_r = client.post(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/actions/{INTEGRATION_ACTION_ID}/tasks",
            headers={**h, "Content-Type": "application/json"},
            json={"localeName": "en_US"},
        )
        assert run_r.status_code == 200, (
            f"POST action task failed: {run_r.status_code}: {run_r.text[:200]}"
        )
        run_body = run_r.json()
        task_id = run_body.get("task", {}).get("taskId") or run_body.get("taskId")
        assert task_id, f"Expected taskId in POST response; keys: {list(run_body.keys())}"

        task = _poll_to_terminal(
            client,
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/actions/{INTEGRATION_ACTION_ID}/tasks/{task_id}",
            h,
        )

    assert task is not None, "No task response received"
    assert task.get("taskState") in {"COMPLETE", "CANCELLED", "CANCELLING"}, (
        f"Action task did not reach terminal state within 60s; last: {task.get('taskState')}"
    )
    assert task.get("taskId") == task_id, "Polled taskId must match started taskId"
    result = task.get("result")
    assert result is not None, "Completed action task must have a result"
    assert "successful" in result, "Task result must have 'successful' field"


@pytest.mark.live
@pytest.mark.write
def test_export_import_cycle(integration_token):
    """Full export → stage → import cycle using INTEGRATION_* env vars.

    Steps:
      1. POST export task (INTEGRATION_EXPORT) → poll to completion.
      2. Download all chunks from INTEGRATION_FILE — confirms export wrote the file.
      3. Re-upload the same content to INTEGRATION_FILE as a single chunk — tests the
         upload path and ensures the import sees fresh data.
      4. POST import task (INTEGRATION_IMPORT) → poll to completion.
      5. Probe the dump endpoints — accepts both empty and non-empty dump lists since
         a successful import has no failure rows.

    Skipped when any INTEGRATION_* variable is missing.
    """
    missing = [
        name for name, val in [
            ("INTEGRATION_EXPORT", INTEGRATION_EXPORT_ID),
            ("INTEGRATION_IMPORT", INTEGRATION_IMPORT_ID),
            ("INTEGRATION_FILE", INTEGRATION_FILE_ID),
        ] if not val
    ]
    if missing:
        pytest.skip(f"Required env vars not set: {', '.join(missing)}")

    h = _auth_headers(integration_token)

    with httpx.Client() as client:
        # ── Step 1: run export ────────────────────────────────────────────────
        export_r = client.post(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/exports/{INTEGRATION_EXPORT_ID}/tasks",
            headers={**h, "Content-Type": "application/json"},
            json={"localeName": "en_US"},
        )
        assert export_r.status_code == 200, (
            f"POST export task failed: {export_r.status_code}: {export_r.text[:200]}"
        )
        export_body = export_r.json()
        export_task_id = (
            export_body.get("task", {}).get("taskId") or export_body.get("taskId")
        )
        assert export_task_id, f"Expected taskId in export POST response; keys: {list(export_body.keys())}"

        export_task = _poll_to_terminal(
            client,
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/exports/{INTEGRATION_EXPORT_ID}/tasks/{export_task_id}",
            h,
        )
        assert export_task.get("taskState") == "COMPLETE", (
            f"Export did not complete; last state: {export_task.get('taskState')}"
        )
        assert export_task.get("result", {}).get("successful"), (
            f"Export task result not successful: {export_task.get('result')}"
        )

        # ── Step 2: download chunks from the export output file ───────────────
        # The export output file ID equals the export action ID.
        chunks_r = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/files/{INTEGRATION_EXPORT_ID}/chunks",
            headers=h,
        )
        assert chunks_r.status_code == 200, (
            f"GET export file chunks failed: {chunks_r.status_code}: {chunks_r.text[:200]}"
        )
        chunks = chunks_r.json().get("chunks", [])
        assert chunks, (
            f"Export completed but no chunks in export file ({INTEGRATION_EXPORT_ID})"
        )

        file_content = b""
        for chunk in chunks:
            chunk_id = chunk["id"]
            dl_r = client.get(
                f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
                f"/files/{INTEGRATION_EXPORT_ID}/chunks/{chunk_id}",
                headers=h,
            )
            assert dl_r.status_code == 200, (
                f"GET chunk {chunk_id} failed: {dl_r.status_code}"
            )
            file_content += dl_r.content

        assert file_content, "Downloaded file content must not be empty"

        # ── Step 3: re-upload to INTEGRATION_FILE as a single chunk ──────────
        upload_r = client.put(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/files/{INTEGRATION_FILE_ID}",
            headers={**h, "Content-Type": "application/octet-stream"},
            content=file_content,
        )
        assert upload_r.status_code in (200, 204), (
            f"PUT file upload failed: {upload_r.status_code}: {upload_r.text[:200]}"
        )

        # ── Step 4: run import ────────────────────────────────────────────────
        import_r = client.post(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{INTEGRATION_IMPORT_ID}/tasks",
            headers={**h, "Content-Type": "application/json"},
            json={"localeName": "en_US"},
        )
        assert import_r.status_code == 200, (
            f"POST import task failed: {import_r.status_code}: {import_r.text[:200]}"
        )
        import_body = import_r.json()
        import_task_id = (
            import_body.get("task", {}).get("taskId") or import_body.get("taskId")
        )
        assert import_task_id, f"Expected taskId in import POST response; keys: {list(import_body.keys())}"

        import_task = _poll_to_terminal(
            client,
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{INTEGRATION_IMPORT_ID}/tasks/{import_task_id}",
            h,
            timeout=120,
        )
        assert import_task.get("taskState") in {"COMPLETE", "CANCELLED", "CANCELLING"}, (
            f"Import did not reach terminal state within 120s; last: {import_task.get('taskState')}"
        )
        import_result = import_task.get("result", {})
        assert "successful" in import_result, "Import task result must have 'successful' field"

        # ── Step 5: probe dump endpoints ──────────────────────────────────────
        # When the import succeeded, failureDumpAvailable is False and the dump
        # endpoints return 404. When failures exist they return 200 with chunk data.
        dump_available = import_result.get("failureDumpAvailable", False)
        dump_base = (
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/imports/{INTEGRATION_IMPORT_ID}/tasks/{import_task_id}/dump"
        )

        dump_r = client.get(dump_base, headers=h)
        assert dump_r.status_code in (200, 204, 404), (
            f"GET import dump returned unexpected status: {dump_r.status_code}"
        )

        dump_chunks_r = client.get(f"{dump_base}/chunks", headers=h)
        assert dump_chunks_r.status_code in (200, 400, 404), (
            f"GET dump/chunks unexpected status: {dump_chunks_r.status_code}"
        )
        if dump_available and dump_chunks_r.status_code == 200:
            dump_chunks = dump_chunks_r.json().get("chunks", [])
            if dump_chunks:
                chunk0_r = client.get(f"{dump_base}/chunks/0", headers=h)
                assert chunk0_r.status_code == 200, (
                    f"GET dump/chunks/0 failed: {chunk0_r.status_code}"
                )
                assert chunk0_r.content, "Dump chunk 0 must have non-empty content"


# ─── List item write (issue #109) ─────────────────────────────────────────────


@pytest.mark.live
def test_get_list_items(integration_token):
    """GET /2/0/workspaces/{workspaceId}/models/{modelId}/lists/{listId}/items returns list items.

    Uses INTEGRATION_LIST. Skipped when the variable is not set.
    """
    if not INTEGRATION_LIST_ID:
        pytest.skip("INTEGRATION_LIST not set in environment")
    h = _auth_headers(integration_token)
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/lists/{INTEGRATION_LIST_ID}/items",
            headers=h,
            params={"includeAll": "true"},
        )

    assert response.status_code == 200, f"{response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body.get("status", {}).get("code") == 200
    items = body.get("listItems")
    assert isinstance(items, list), f"Expected 'listItems' list; keys: {list(body.keys())}"


@pytest.mark.live
@pytest.mark.write
def test_post_and_put_list_items(integration_token):
    """POST + PUT .../lists/{listId}/items confirm write response schemas; cleanup via INTEGRATION_ACTION.

    Uses INTEGRATION_LIST (a numbered list — name not allowed, only code).
    POST adds two items. PUT probes the update envelope. Cleans up by running
    INTEGRATION_ACTION (Delete Alternate SKU) and polling to completion.

    Skipped when INTEGRATION_LIST or INTEGRATION_ACTION is not set.
    """
    missing = [
        name for name, val in [
            ("INTEGRATION_LIST", INTEGRATION_LIST_ID),
            ("INTEGRATION_ACTION", INTEGRATION_ACTION_ID),
        ] if not val
    ]
    if missing:
        pytest.skip(f"Required env vars not set: {', '.join(missing)}")

    h = _auth_headers(integration_token)
    hj = {**h, "Content-Type": "application/json"}
    items_url = (
        f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
        f"/lists/{INTEGRATION_LIST_ID}/items"
    )

    with httpx.Client(timeout=60) as client:
        # ── POST: add items (numbered list — code only) ───────────────────────
        post_r = client.post(
            items_url,
            headers=hj,
            params={"action": "add"},
            json={"items": [{"code": "probe-test-001"}, {"code": "probe-test-002"}]},
        )
        assert post_r.status_code == 200, (
            f"POST list items failed: {post_r.status_code}: {post_r.text[:200]}"
        )
        post_body = post_r.json()
        assert post_body.get("status", {}).get("code") == 200
        for key in ("added", "ignored", "total", "failures"):
            assert key in post_body, (
                f"POST response missing '{key}'; keys: {list(post_body.keys())}"
            )
        assert isinstance(post_body["added"], int), "'added' must be an integer"
        assert isinstance(post_body["ignored"], int), "'ignored' must be an integer"
        assert isinstance(post_body["total"], int), "'total' must be an integer"
        assert isinstance(post_body["failures"], list), "'failures' must be a list"
        assert post_body["total"] == 2, f"Expected total=2; got {post_body['total']}"

        # failures is omitted when all items succeed
        post_failures = post_body.get("failures", [])
        assert isinstance(post_failures, list), "'failures' must be a list when present"
        for failure in post_failures:
            assert "requestIndex" in failure, "Each failure must have 'requestIndex'"
            assert "failureType" in failure, "Each failure must have 'failureType'"
            assert "failureMessageDetails" in failure, (
                "Each failure must have 'failureMessageDetails'"
            )

        # ── PUT: update items (reference by code) ─────────────────────────────
        put_r = client.put(
            items_url,
            headers=hj,
            json={"items": [{"code": "probe-test-001"}, {"code": "probe-test-002"}]},
        )
        assert put_r.status_code == 200, (
            f"PUT list items failed: {put_r.status_code}: {put_r.text[:200]}"
        )
        put_body = put_r.json()
        assert put_body.get("status", {}).get("code") == 200
        for key in ("updated", "ignored", "total"):
            assert key in put_body, (
                f"PUT response missing '{key}'; keys: {list(put_body.keys())}"
            )
        assert isinstance(put_body["updated"], int), "'updated' must be an integer"
        assert isinstance(put_body["ignored"], int), "'ignored' must be an integer"
        assert isinstance(put_body["total"], int), "'total' must be an integer"
        assert put_body["total"] == 2, f"Expected total=2; got {put_body['total']}"

        # failures is omitted when all items succeed
        put_failures = put_body.get("failures", [])
        assert isinstance(put_failures, list), "'failures' must be a list when present"
        for failure in put_failures:
            assert "requestIndex" in failure, "Each failure must have 'requestIndex'"
            assert "failureType" in failure, "Each failure must have 'failureType'"
            assert "failureMessageDetails" in failure, (
                "Each failure must have 'failureMessageDetails'"
            )

        # ── Cleanup: run Delete Alternate SKU action ───────────────────────────
        cleanup_r = client.post(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/actions/{INTEGRATION_ACTION_ID}/tasks",
            headers=hj,
            json={"localeName": "en_US"},
        )
        assert cleanup_r.status_code == 200, (
            f"POST cleanup action failed: {cleanup_r.status_code}: {cleanup_r.text[:200]}"
        )
        cleanup_body = cleanup_r.json()
        task_id = cleanup_body.get("task", {}).get("taskId") or cleanup_body.get("taskId")
        assert task_id, f"Expected taskId in cleanup POST response; keys: {list(cleanup_body.keys())}"

        cleanup_task = _poll_to_terminal(
            client,
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
            f"/actions/{INTEGRATION_ACTION_ID}/tasks/{task_id}",
            h,
        )

    assert cleanup_task.get("taskState") in {"COMPLETE", "CANCELLED", "CANCELLING"}, (
        f"Cleanup action did not reach terminal state within 60s; "
        f"last: {cleanup_task.get('taskState')}"
    )
    assert cleanup_task.get("result", {}).get("successful"), (
        f"Cleanup action result not successful: {cleanup_task.get('result')}"
    )


# ─── View data and large read-request lifecycle (issue #110) ──────────────────


@pytest.mark.live
def test_view_data_csv(integration_token):
    """GET /models/{modelId}/views/{viewId}/data returns 200 text/csv by default.

    Uses INTEGRATION_MODULE as the view ID (every module has a default view with
    the same ID as the module itself). Skipped when the variable is not set.
    """
    if not INTEGRATION_MODULE_ID:
        pytest.skip("INTEGRATION_MODULE not set in environment")
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/views/{INTEGRATION_MODULE_ID}/data",
            headers=_auth_headers(integration_token),
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:300]}"
    )
    assert "text/csv" in response.headers.get("content-type", ""), (
        f"Expected text/csv, got: {response.headers.get('content-type')}"
    )
    assert len(response.content) > 0, "CSV response must not be empty"


@pytest.mark.live
def test_view_data_json(integration_token):
    """GET /models/{modelId}/views/{viewId}/data?format=v1 with Accept: application/json returns 200 JSON.

    Uses INTEGRATION_MODULE as the view ID. Confirms response has pages,
    columnCoordinates, and rows keys. Skipped when the variable is not set.
    """
    if not INTEGRATION_MODULE_ID:
        pytest.skip("INTEGRATION_MODULE not set in environment")
    with httpx.Client() as client:
        response = client.get(
            f"{API_URL}/models/{MODEL_ID}/views/{INTEGRATION_MODULE_ID}/data",
            headers={**_auth_headers(integration_token), "Accept": "application/json"},
            params={"format": "v1"},
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:300]}"
    )
    assert "application/json" in response.headers.get("content-type", ""), (
        f"Expected application/json, got: {response.headers.get('content-type')}"
    )
    body = response.json()
    assert "columnCoordinates" in body, (
        f"JSON response must have columnCoordinates; keys: {list(body.keys())}"
    )
    assert "rows" in body, f"JSON response must have rows; keys: {list(body.keys())}"
    assert isinstance(body["columnCoordinates"], list), "columnCoordinates must be a list"
    assert isinstance(body["rows"], list), "rows must be a list"
    if body["rows"]:
        row = body["rows"][0]
        assert "rowCoordinates" in row, f"Row must have rowCoordinates; keys: {list(row.keys())}"
        assert "cells" in row, f"Row must have cells; keys: {list(row.keys())}"


@pytest.mark.live
@pytest.mark.write
def test_view_read_request_lifecycle(integration_token):
    """POST readRequest → poll GET → GET page 0 (CSV) → DELETE: covers all three issue #110 endpoints.

    Uses INTEGRATION_MODULE as the view ID. Steps:
      1. POST .../readRequests to initiate a large read.
      2. Poll GET .../readRequests/{requestId} until COMPLETE.
      3. GET .../readRequests/{requestId}/pages/0 confirms CSV page download.
      4. DELETE .../readRequests/{requestId} confirms JSON response with viewReadRequest.

    Skipped when INTEGRATION_MODULE is not set.
    """
    if not INTEGRATION_MODULE_ID:
        pytest.skip("INTEGRATION_MODULE not set in environment")

    h = _auth_headers(integration_token)
    base = (
        f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
        f"/views/{INTEGRATION_MODULE_ID}/readRequests"
    )

    with httpx.Client(timeout=60) as client:
        # Step 1: initiate
        post_r = client.post(
            base,
            headers={**h, "Content-Type": "application/json"},
            json={"exportType": "TABULAR_MULTI_COLUMN"},
        )
        assert post_r.status_code == 200, (
            f"POST readRequest failed: {post_r.status_code}: {post_r.text[:300]}"
        )
        post_body = post_r.json()
        request_id = post_body.get("viewReadRequest", {}).get("requestId")
        assert request_id, f"Expected requestId in POST response; keys: {list(post_body.keys())}"

        # Step 2: poll until COMPLETE
        task = _poll_read_request(client, f"{base}/{request_id}", h)
        assert task.get("requestState") == "COMPLETE", (
            f"readRequest did not complete within 60s; last state: {task.get('requestState')}"
        )
        assert task.get("successful") is True, (
            f"readRequest reported unsuccessful: {task}"
        )
        available_pages = task.get("availablePages", 0)
        assert available_pages >= 1, f"Expected at least 1 available page; got {available_pages}"

        # Step 3: download page 0 — must be CSV
        page_r = client.get(
            f"{base}/{request_id}/pages/0",
            headers={**h, "Accept": "text/csv"},
        )
        assert page_r.status_code == 200, (
            f"GET page 0 failed: {page_r.status_code}: {page_r.text[:300]}"
        )
        assert "text/csv" in page_r.headers.get("content-type", ""), (
            f"Expected text/csv for page download; got: {page_r.headers.get('content-type')}"
        )
        assert len(page_r.content) > 0, "Page 0 must contain non-empty CSV data"

        # Step 4: delete — must return JSON with viewReadRequest
        del_r = client.delete(f"{base}/{request_id}", headers=h)
        assert del_r.status_code == 200, (
            f"DELETE readRequest failed: {del_r.status_code}: {del_r.text[:300]}"
        )
        del_body = del_r.json()
        assert del_body.get("status", {}).get("code") == 200
        vrr = del_body.get("viewReadRequest")
        assert vrr is not None, (
            f"DELETE response must contain viewReadRequest; keys: {list(del_body.keys())}"
        )
        assert vrr.get("requestId") == request_id, "Returned requestId must match deleted requestId"
        assert vrr.get("requestState") in {"CANCELLED", "COMPLETE"}, (
            f"Unexpected requestState after DELETE: {vrr.get('requestState')}"
        )


def _poll_read_request(client, url, h, timeout=60):
    """Poll GET url until requestState reaches a terminal state. Returns final viewReadRequest dict."""
    terminal = {"COMPLETE", "CANCELLED"}
    deadline = time.time() + timeout
    vrr: dict = {}
    while time.time() < deadline:
        r = client.get(url, headers=h)
        assert r.status_code == 200, f"Poll failed: {r.status_code}: {r.text[:200]}"
        vrr = r.json().get("viewReadRequest", {})
        if vrr.get("requestState") in terminal:
            break
        time.sleep(2)
    return vrr
