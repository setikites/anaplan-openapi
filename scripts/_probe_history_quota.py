"""
Probe two stub schemas from integration-openapi.json (issue #118):
  1. HistoryReadRequest — POST /workspaces/{wId}/models/{mId}/lineItems/{liId}/history/readRequests
  2. ReadRequestsQuota  — GET  /workspaces/{wId}/readRequestsQuota

Run with:
    uv run --env-file .env python scripts/_probe_history_quota.py
"""

import base64
import json
import os
import secrets

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

AUTH_URL = "https://auth.anaplan.com"
_api_base = os.getenv("ANAPLAN_API_BASE_URL", "https://api.anaplan.com").rstrip("/")
API_URL = _api_base if _api_base.endswith("/2/0") else _api_base + "/2/0"
WORKSPACE_ID = os.getenv("ANAPLAN_WORKSPACE_ID") or os.getenv("ANAPLAN_INTEGRATION_WORKSPACE_ID", "")
MODEL_ID = os.getenv("ANAPLAN_MODEL_ID") or os.getenv("ANAPLAN_INTEGRATION_MODEL_ID", "")


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


def get_token(client: httpx.Client) -> str:
    cert_path = os.getenv("ANAPLAN_CA_CERT_PATH")
    key_path = os.getenv("ANAPLAN_CA_KEY_PATH")
    key_password = os.getenv("ANAPLAN_CA_KEY_PASSWORD")
    if cert_path and key_path:
        random_data = secrets.token_bytes(150)
        encoded_data = base64.b64encode(random_data).decode()
        signature = _sign_data(random_data, key_path, key_password)
        cert_b64 = _load_cert_b64(cert_path)
        r = client.post(
            f"{AUTH_URL}/token/authenticate",
            headers={"Authorization": f"CACertificate {cert_b64}"},
            json={"encodedData": encoded_data, "encodedSignedData": signature},
        )
        if r.status_code == 201:
            return r.json()["tokenInfo"]["tokenValue"]
    username = os.getenv("ANAPLAN_USERNAME")
    password = os.getenv("ANAPLAN_PASSWORD")
    if username and password:
        auth_b64 = base64.b64encode(f"{username}:{password}".encode()).decode()
        r = client.post(
            f"{AUTH_URL}/token/authenticate",
            headers={"Authorization": f"Basic {auth_b64}"},
        )
        if r.status_code == 201:
            return r.json()["tokenInfo"]["tokenValue"]
    raise RuntimeError("No credentials found in environment")


def req(client, token, method, path, body=None):
    url = f"{API_URL}{path}"
    kwargs = {
        "headers": {
            "Authorization": f"AnaplanAuthToken {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    }
    if body is not None:
        kwargs["json"] = body
    r = client.request(method.upper(), url, **kwargs)
    ct = r.headers.get("content-type", "")
    body_out = r.json() if ct.startswith("application/json") else r.text
    return r.status_code, body_out


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def show(status, body):
    snippet = json.dumps(body, indent=2, default=str) if isinstance(body, dict) else str(body)
    print(f"  HTTP {status}")
    print(snippet[:1200])


def main():
    with httpx.Client(timeout=30) as client:
        token = get_token(client)
        print(f"Authenticated. API_URL={API_URL}")
        print(f"WORKSPACE_ID={WORKSPACE_ID}  MODEL_ID={MODEL_ID}")

        # ── Probe A: GET /workspaces/{wId}/readRequestsQuota ─────────────────
        section("GET /workspaces/{workspaceId}/readRequestsQuota")
        status, body = req(client, token, "get", f"/workspaces/{WORKSPACE_ID}/readRequestsQuota")
        show(status, body)

        # ── Probe B: find a lineItemId ────────────────────────────────────────
        section("GET /workspaces/{wId}/models/{mId}/lineItems  (to find a lineItemId)")
        status, body = req(client, token, "get",
                           f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lineItems")
        show(status, body)
        line_items = []
        if isinstance(body, dict):
            line_items = body.get("lineItems", body.get("items", []))
        if not line_items:
            print("\n  No lineItems found — trying /models/{modelId}/lineItems")
            status2, body2 = req(client, token, "get",
                                 f"/models/{MODEL_ID}/lineItems")
            show(status2, body2)
            if isinstance(body2, dict):
                line_items = body2.get("lineItems", body2.get("items", []))

        if not line_items:
            print("\n  Still no lineItems — cannot probe history/readRequests.")
        else:
            li = line_items[0]
            line_item_id = li.get("id") or li.get("lineItemId") or li.get("entityId")
            print(f"\n  Using lineItemId={line_item_id!r}  name={li.get('name', '?')!r}")

            # ── Probe C: POST history/readRequests ────────────────────────────
            section(f"POST /workspaces/{{wId}}/models/{{mId}}/lineItems/{line_item_id}/history/readRequests")
            path = f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lineItems/{line_item_id}/history/readRequests"
            status, body = req(client, token, "post", path, body={})
            show(status, body)

            # Try again with a minimal body in case the empty body caused an error
            if status not in (200, 201, 202):
                section(f"POST history/readRequests — retry with exportType body")
                status, body = req(client, token, "post", path,
                                   body={"exportType": "TABULAR_MULTI_COLUMN"})
                show(status, body)


if __name__ == "__main__":
    main()
