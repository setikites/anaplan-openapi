"""
Probe GET .../dimensions/{dimensionId}/items for up to 5 dimensions, checking
whether the DimensionItem stub fields (read, write, listId, listName, parent,
parentId, properties, subsetId, subsets) appear in real responses.

Tries multiple query-parameter combinations per dimension:
  - no params
  - includeAll=true
  - includeSubsets=true

Run with:
    uv run --env-file .env python scripts/_probe_dimension_items.py
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
WORKSPACE_ID = os.getenv("ANAPLAN_WORKSPACE_ID", "8a868cd885f53bd201860f5a4fea1ff1")
MODEL_ID = os.getenv("ANAPLAN_MODEL_ID", "09F86E3942A84353892853BE3BE82280")

STUB_FIELDS = {"read", "write", "listId", "listName", "parent", "parentId", "properties", "subsetId", "subsets"}
QUERY_VARIANTS = [
    {},
    {"includeAll": "true"},
    {"includeSubsets": "true"},
]


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


def get(client: httpx.Client, token: str, path: str, params: dict | None = None):
    url = f"{API_URL}{path}"
    r = client.get(
        url,
        headers={"Authorization": f"AnaplanAuthToken {token}"},
        params=params or {},
    )
    ct = r.headers.get("content-type", "")
    body = r.json() if ct.startswith("application/json") else r.text
    return r.status_code, body


def item_keys(body: dict) -> set[str]:
    """Return the union of all keys across every item in the response."""
    found: set[str] = set()
    for key in ("items", "dimensionItems"):
        items = body.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    found.update(item.keys())
    return found


def main() -> None:
    with httpx.Client(timeout=30) as client:
        token = get_token(client)
        print(f"Authenticated. API_URL={API_URL}")
        print(f"WORKSPACE_ID={WORKSPACE_ID}  MODEL_ID={MODEL_ID}\n")

        # Discover dimensions via line items (no top-level /dimensions endpoint exists)
        status, body = get(client, token, f"/models/{MODEL_ID}/lineItems")
        if status != 200:
            print(f"[{status}] GET /lineItems failed: {body}")
            return

        line_items = body.get("items", [])
        print(f"Found {len(line_items)} line item(s). Collecting up to 5 unique dimensions...")

        seen: dict[str, str] = {}  # dim_id -> dim_name
        for li in line_items:
            if len(seen) >= 5:
                break
            lid = li.get("id") or li.get("lineItemId")
            if not lid:
                continue
            s2, b2 = get(client, token, f"/models/{MODEL_ID}/lineItems/{lid}/dimensions")
            if s2 == 200 and isinstance(b2, dict):
                for dim in b2.get("dimensions", []):
                    did = dim.get("id")
                    if did and did not in seen:
                        seen[did] = dim.get("name", "?")
                        if len(seen) >= 5:
                            break

        dims = [{"id": k, "name": v} for k, v in seen.items()]
        print(f"Collected {len(dims)} unique dimension(s). Probing...\n")

        all_observed: set[str] = set()
        probed = 0

        for dim in dims:
            if probed >= 5:
                break
            dim_id = dim.get("id") or dim.get("dimensionId")
            dim_name = dim.get("name", "?")
            if not dim_id:
                continue

            print(f"{'='*70}")
            print(f"  Dimension: {dim_name!r}  id={dim_id}")

            for params in QUERY_VARIANTS:
                path = f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/dimensions/{dim_id}/items"
                param_str = f"?{'&'.join(f'{k}={v}' for k,v in params.items())}" if params else ""
                print(f"  GET {path}{param_str}")

                status, resp = get(client, token, path, params)
                print(f"    HTTP {status}")

                if status == 200 and isinstance(resp, dict):
                    keys = item_keys(resp)
                    all_observed |= keys
                    stub_hit = keys & STUB_FIELDS
                    print(f"    item keys observed: {sorted(keys)}")
                    if stub_hit:
                        print(f"    *** STUB FIELDS FOUND: {sorted(stub_hit)} ***")
                        items_list = resp.get("items") or resp.get("dimensionItems") or []
                        if items_list:
                            print(f"    first item:\n{json.dumps(items_list[0], indent=6, default=str)}")
                    else:
                        items_list = resp.get("items") or resp.get("dimensionItems") or []
                        if items_list:
                            print(f"    first item: {json.dumps(items_list[0], default=str)}")
                else:
                    snippet = json.dumps(resp, default=str)[:300] if isinstance(resp, dict) else str(resp)[:300]
                    print(f"    body: {snippet}")

            print()
            probed += 1

        print(f"Probed {probed} dimension(s).")
        print(f"\nAll item keys observed across all responses: {sorted(all_observed)}")
        stub_found = all_observed & STUB_FIELDS
        if stub_found:
            print(f"\nSTUB FIELDS CONFIRMED in live responses: {sorted(stub_found)}")
        else:
            print(f"\nNone of {sorted(STUB_FIELDS)} appeared — DimensionItem stub can be retired.")


if __name__ == "__main__":
    main()
