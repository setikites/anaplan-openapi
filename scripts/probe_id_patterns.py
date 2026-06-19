"""
Probe ID value patterns across all Integration API object types.
Collect sample IDs and summarize format/range per type.

Run with:
    uv run --env-file .env python scripts/probe_id_patterns.py
"""

import base64
import json
import os
import re
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


def get(client: httpx.Client, token: str, path: str) -> dict | None:
    url = f"{API_URL}{path}"
    r = client.get(url, headers={"Authorization": f"AnaplanAuthToken {token}"})
    if r.status_code == 200:
        return r.json()
    print(f"  [SKIP {r.status_code}] {path}")
    return None


def classify_id(id_val: str) -> str:
    """Classify the format of an ID string."""
    if re.fullmatch(r"[0-9a-f]{32}", id_val, re.IGNORECASE):
        return "32-char hex"
    if re.fullmatch(r"[0-9]{8,20}", id_val):
        return f"numeric({len(id_val)}d)"
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", id_val, re.IGNORECASE):
        return "UUID"
    if re.fullmatch(r"[A-Za-z0-9_-]+", id_val):
        return f"alphanum({len(id_val)})"
    return f"other({len(id_val)})"


def analyze_ids(label: str, items: list[dict], max_samples: int = 10) -> None:
    ids = [item["id"] for item in items if "id" in item]
    if not ids:
        print(f"\n  {label}: no 'id' field found")
        return

    formats = {}
    for i in ids:
        fmt = classify_id(i)
        formats.setdefault(fmt, []).append(i)

    print(f"\n{'='*60}")
    print(f"  {label}  ({len(ids)} IDs)")
    print(f"{'='*60}")
    for fmt, vals in formats.items():
        numeric_vals = []
        for v in vals:
            try:
                numeric_vals.append(int(v))
            except ValueError:
                pass
        range_str = ""
        if numeric_vals:
            range_str = f"  range: {min(numeric_vals):,} - {max(numeric_vals):,}"
        print(f"  format: {fmt}  count: {len(vals)}{range_str}")
        print(f"  samples: {vals[:max_samples]}")


def main() -> None:
    with httpx.Client(timeout=30) as client:
        token = get_token(client)
        print(f"Authenticated. API_URL={API_URL}")

        # Users
        r = get(client, token, "/users")
        if r:
            analyze_ids("users", r.get("users", []))

        r = get(client, token, "/users/me")
        if r:
            user = r.get("user", {})
            if "id" in user:
                analyze_ids("user (me)", [user])

        # Workspaces
        r = get(client, token, "/workspaces")
        if r:
            analyze_ids("workspaces", r.get("workspaces", []))

        # Models
        r = get(client, token, "/models")
        if r:
            analyze_ids("models", r.get("models", []))

        # Files
        r = get(client, token, f"/models/{MODEL_ID}/files")
        if r:
            analyze_ids("files", r.get("files", []))

        # Imports
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/imports")
        if r:
            analyze_ids("imports", r.get("imports", []))

        # Exports
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports")
        if r:
            analyze_ids("exports", r.get("exports", []))

        # Actions
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/actions")
        if r:
            analyze_ids("actions", r.get("actions", []))

        # Processes
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/processes")
        if r:
            analyze_ids("processes", r.get("processes", []))

        # Lists
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lists")
        if r:
            analyze_ids("lists", r.get("lists", []))

        # Modules
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/modules")
        if r:
            mods = r.get("modules", [])
            analyze_ids("modules", mods)

            # Views (from first module)
            if mods:
                mod_id = mods[0]["id"]
                r2 = get(client, token,
                         f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/modules/{mod_id}/views")
                if r2:
                    analyze_ids(f"views (module {mod_id})", r2.get("views", []))

        # Views (model-level)
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/views")
        if r:
            analyze_ids("views (model-level)", r.get("views", []))

        # Dimensions
        r = get(client, token,
                f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/dimensions")
        if r:
            dims = r.get("dimensions", [])
            analyze_ids("dimensions", dims)

            # Dimension items (first dimension)
            if dims:
                dim_id = dims[0]["id"]
                r2 = get(client, token,
                         f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/dimensions/{dim_id}/items")
                if r2:
                    key = next((k for k in r2 if isinstance(r2[k], list)), None)
                    items = r2.get(key, []) if key else []
                    analyze_ids(f"dimension items (dim {dim_id})", items)

        # Line items (model-level)
        r = get(client, token,
                f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lineItems")
        if r:
            analyze_ids("lineItems (model-level)", r.get("lineItems", []))

        # Dashboards
        r = get(client, token,
                f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/dashboards")
        if r:
            analyze_ids("dashboards", r.get("dashboards", []))

        print(f"\n{'='*60}")
        print("  PROBE COMPLETE")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
