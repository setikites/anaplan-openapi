"""
Probe GET /workspaces/{workspaceId}/models/{modelId}/categories and
GET /workspaces/{workspaceId}/models to check if Category data is
available in the Integration API (issue #114).

Run with:
    uv run --env-file .env python scripts/_probe_categories.py
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
WORKSPACE_ID = os.getenv("ANAPLAN_INTEGRATION_WORKSPACE_ID") or os.getenv("ANAPLAN_WORKSPACE_ID", "")
MODEL_ID = os.getenv("ANAPLAN_INTEGRATION_MODEL_ID") or os.getenv("ANAPLAN_MODEL_ID", "")


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


def get(client: httpx.Client, token: str, path: str):
    url = f"{API_URL}{path}"
    r = client.get(url, headers={"Authorization": f"AnaplanAuthToken {token}"})
    ct = r.headers.get("content-type", "")
    body = r.json() if ct.startswith("application/json") else r.text
    return r.status_code, body


def probe(client: httpx.Client, token: str, path: str, label: str) -> None:
    print(f"{'='*70}")
    print(f"  {label}")
    print(f"  GET {path}")
    status, body = get(client, token, path)
    print(f"  HTTP {status}")
    if isinstance(body, dict):
        print(f"  top-level keys: {list(body.keys())}")
        for key, val in body.items():
            if isinstance(val, list):
                print(f"  .{key}: {len(val)} item(s)")
                if val:
                    first = val[0]
                    print(f"  first item keys: {list(first.keys()) if isinstance(first, dict) else type(first).__name__}")
                    print(f"  first item:\n{json.dumps(first, indent=4, default=str)}")
            elif isinstance(val, dict):
                print(f"  .{key}: {json.dumps(val, indent=4, default=str)[:600]}")
            else:
                print(f"  .{key}: {val!r}")
    else:
        print(f"  body: {str(body)[:600]}")
    print()


def main() -> None:
    if not WORKSPACE_ID or not MODEL_ID:
        print("ERROR: Set ANAPLAN_INTEGRATION_WORKSPACE_ID and ANAPLAN_INTEGRATION_MODEL_ID in .env")
        return

    with httpx.Client(timeout=30) as client:
        token = get_token(client)
        print(f"Authenticated. API_URL={API_URL}")
        print(f"WORKSPACE_ID={WORKSPACE_ID}  MODEL_ID={MODEL_ID}\n")

        # Candidate 1: dedicated categories endpoint
        probe(
            client, token,
            f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/categories",
            "Candidate 1: dedicated categories endpoint",
        )

        # Candidate 2: model list — check if categoryValues embedded
        probe(
            client, token,
            f"/workspaces/{WORKSPACE_ID}/models",
            "Candidate 2: model list (check for embedded categoryValues)",
        )

        # Candidate 3: single model — check if categoryValues embedded
        probe(
            client, token,
            f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}",
            "Candidate 3: single model (check for embedded categoryValues)",
        )


if __name__ == "__main__":
    main()
