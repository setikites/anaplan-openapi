"""Probe view-data endpoints for issue #110.

Usage:
    uv run --env-file .env scripts/_probe_view_data.py
"""

import base64
import json
import os
import pathlib
import secrets

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

AUTH_URL = "https://auth.anaplan.com"
_api_base = os.getenv("ANAPLAN_API_BASE_URL", "https://api.anaplan.com").rstrip("/")
API_URL = _api_base if _api_base.endswith("/2/0") else _api_base + "/2/0"

WORKSPACE_ID = os.getenv("ANAPLAN_INTEGRATION_WORKSPACE_ID", "")
MODEL_ID = os.getenv("ANAPLAN_INTEGRATION_MODEL_ID", "")
VIEW_ID = os.getenv("INTEGRATION_MODULE", "")  # module default view has same ID


def _sign(data, key_path, key_password=None):
    with open(key_path, "rb") as f:
        key_data = f.read()
    pw = key_password.encode() if key_password else None
    key = serialization.load_pem_private_key(key_data, password=pw, backend=default_backend())
    sig = key.sign(data, padding.PKCS1v15(), hashes.SHA512())
    return base64.b64encode(sig).decode()


def _load_cert_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def get_token(client):
    cert_path = os.getenv("ANAPLAN_CA_CERT_PATH")
    key_path = os.getenv("ANAPLAN_CA_KEY_PATH")
    if cert_path and key_path and pathlib.Path(cert_path).exists():
        random_data = secrets.token_bytes(150)
        encoded = base64.b64encode(random_data).decode()
        sig = _sign(random_data, key_path, os.getenv("ANAPLAN_CA_KEY_PASSWORD"))
        cert_b64 = _load_cert_b64(cert_path)
        r = client.post(
            f"{AUTH_URL}/token/authenticate",
            headers={"Authorization": f"CACertificate {cert_b64}"},
            json={"encodedData": encoded, "encodedSignedData": sig},
        )
        if r.status_code == 201:
            return r.json()["tokenInfo"]["tokenValue"]

    username = os.getenv("ANAPLAN_USERNAME", "")
    password = os.getenv("ANAPLAN_PASSWORD", "")
    auth_b64 = base64.b64encode(f"{username}:{password}".encode()).decode()
    r = client.post(
        f"{AUTH_URL}/token/authenticate",
        headers={"Authorization": f"Basic {auth_b64}"},
    )
    if r.status_code == 201:
        return r.json()["tokenInfo"]["tokenValue"]
    raise RuntimeError(f"Auth failed: {r.status_code} {r.text[:200]}")


def h(token):
    return {"Authorization": f"AnaplanAuthToken {token}"}


def main():
    print(f"WORKSPACE_ID: {WORKSPACE_ID}")
    print(f"MODEL_ID:     {MODEL_ID}")
    print(f"VIEW_ID:      {VIEW_ID}")
    print()

    with httpx.Client(timeout=30) as client:
        token = get_token(client)
        print("Authenticated OK\n")

        # ── 1. GET /models/{modelId}/views/{viewId}/data (CSV) ────────────────
        print("=== GET /models/{modelId}/views/{viewId}/data (no format, default CSV) ===")
        r = client.get(
            f"{API_URL}/models/{MODEL_ID}/views/{VIEW_ID}/data",
            headers=h(token),
        )
        print(f"Status: {r.status_code}")
        print(f"Content-Type: {r.headers.get('content-type')}")
        print(f"Body (first 500 chars): {r.text[:500]!r}")
        print()

        # ── 2. GET /models/{modelId}/views/{viewId}/data?format=v1 (JSON) ────
        print("=== GET /models/{modelId}/views/{viewId}/data?format=v1 (JSON) ===")
        r2 = client.get(
            f"{API_URL}/models/{MODEL_ID}/views/{VIEW_ID}/data",
            headers={**h(token), "Accept": "application/json"},
            params={"format": "v1"},
        )
        print(f"Status: {r2.status_code}")
        print(f"Content-Type: {r2.headers.get('content-type')}")
        if "application/json" in r2.headers.get("content-type", ""):
            body = r2.json()
            print(f"Top-level keys: {list(body.keys())}")
            if "rows" in body:
                print(f"  rows count: {len(body['rows'])}")
                if body["rows"]:
                    print(f"  first row keys: {list(body['rows'][0].keys())}")
            print(f"Body (first 800 chars): {json.dumps(body)[:800]}")
        else:
            print(f"Body (first 500): {r2.text[:500]!r}")
        print()

        # ── 3. POST /workspaces/{wid}/models/{mid}/views/{vid}/readRequests ──
        print("=== POST .../views/{viewId}/readRequests ===")
        r3 = client.post(
            f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/views/{VIEW_ID}/readRequests",
            headers={**h(token), "Content-Type": "application/json"},
            json={"exportType": "TABULAR_MULTI_COLUMN"},
        )
        print(f"Status: {r3.status_code}")
        print(f"Content-Type: {r3.headers.get('content-type')}")
        if r3.status_code == 200:
            rb = r3.json()
            print(f"Body: {json.dumps(rb, indent=2)[:600]}")
            request_id = rb.get("viewReadRequest", {}).get("requestId")
        else:
            print(f"Body: {r3.text[:400]!r}")
            request_id = None
        print()

        if request_id:
            # ── 4. GET .../readRequests/{requestId} ──────────────────────────
            print(f"=== GET .../readRequests/{request_id} ===")
            import time
            # Poll until COMPLETE or timeout
            for _ in range(10):
                r4 = client.get(
                    f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
                    f"/views/{VIEW_ID}/readRequests/{request_id}",
                    headers=h(token),
                )
                print(f"Status: {r4.status_code}")
                if r4.status_code == 200:
                    rb4 = r4.json()
                    print(f"Body: {json.dumps(rb4, indent=2)[:600]}")
                    state = rb4.get("viewReadRequest", {}).get("requestState")
                    pages = rb4.get("viewReadRequest", {}).get("availablePages", 0)
                    print(f"  requestState: {state}, availablePages: {pages}")
                    if state in ("COMPLETE", "CANCELLED"):
                        break
                    time.sleep(3)
                else:
                    print(f"Body: {r4.text[:400]!r}")
                    break
            print()

            # ── 5. GET .../readRequests/{requestId}/pages/0 ──────────────────
            if pages and pages > 0:
                print(f"=== GET .../readRequests/{request_id}/pages/0 ===")
                r5 = client.get(
                    f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
                    f"/views/{VIEW_ID}/readRequests/{request_id}/pages/0",
                    headers={**h(token), "Accept": "text/csv"},
                )
                print(f"Status: {r5.status_code}")
                print(f"Content-Type: {r5.headers.get('content-type')}")
                print(f"Body (first 500 chars): {r5.text[:500]!r}")
                print()

            # ── 6. DELETE .../readRequests/{requestId} ────────────────────────
            print(f"=== DELETE .../readRequests/{request_id} ===")
            r6 = client.delete(
                f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
                f"/views/{VIEW_ID}/readRequests/{request_id}",
                headers=h(token),
            )
            print(f"Status: {r6.status_code}")
            print(f"Content-Type: {r6.headers.get('content-type')}")
            if r6.status_code == 200:
                print(f"Body: {json.dumps(r6.json(), indent=2)[:600]}")
            else:
                print(f"Body: {r6.text[:400]!r}")
            print()

        # Logout
        client.post(f"{AUTH_URL}/token/logout", headers=h(token))
        print("Logged out OK")


if __name__ == "__main__":
    main()
