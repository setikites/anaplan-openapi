"""
Probe all Integration API GET endpoints and print response shapes,
field value patterns, and enum candidates. Used to inform spec description
and enum improvements (issue #90).

Run with:
    uv run --env-file .env python scripts/probe_integration_responses.py
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
# Use env-file values; defaults match the test model (Commercial Flash | PS [PREPROD])
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


def show(label: str, data, indent: int = 2) -> None:
    print(f"\n{'-'*60}")
    print(f"  {label}")
    print(f"{'-'*60}")
    print(json.dumps(data, indent=indent, ensure_ascii=True, default=str))


def collect_values(items: list[dict], field: str) -> list:
    vals = {item.get(field) for item in items if field in item and item[field] is not None}
    try:
        return sorted(vals)
    except TypeError:
        return list(vals)


def summarize(label: str, items: list[dict], fields: list[str]) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}  ({len(items)} items)")
    print(f"{'='*60}")
    for f in fields:
        vals = collect_values(items, f)
        print(f"  .{f} ({len(vals)} unique): {vals[:30]}")
    if items:
        print(f"\n  First item:")
        print(json.dumps(items[0], indent=4, ensure_ascii=True, default=str))


def main() -> None:
    with httpx.Client(timeout=30) as client:
        token = get_token(client)
        print(f"Authenticated. API_URL={API_URL}")
        print(f"WORKSPACE_ID={WORKSPACE_ID}  MODEL_ID={MODEL_ID}")

        h = lambda t: {"Authorization": f"AnaplanAuthToken {t}"}  # noqa: E731

        # ── Users ──────────────────────────────────────────────────────────
        r = get(client, token, "/users/me")
        if r:
            show("GET /users/me", r)

        r = get(client, token, "/users")
        if r:
            users = r.get("users", [])
            summarize("GET /users -> users[]", users, ["active", "emailOptIn"])

        # ── Workspaces ─────────────────────────────────────────────────────
        r = get(client, token, "/workspaces")
        if r:
            wss = r.get("workspaces", [])
            summarize("GET /workspaces -> workspaces[]", wss,
                      ["active", "sizeAllowance", "currentSize"])

        # ── Models ─────────────────────────────────────────────────────────
        r = get(client, token, "/models")
        if r:
            models = r.get("models", [])
            summarize("GET /models -> models[]", models,
                      ["activeState"])
            if models:
                show("First model (full)", models[0])

        # ── Model Calendar ─────────────────────────────────────────────────
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/modelCalendar")
        if r:
            show("GET /modelCalendar", r)

        # ── Versions ───────────────────────────────────────────────────────
        r = get(client, token, f"/models/{MODEL_ID}/versions")
        if r:
            versions = r.get("versions", [])
            summarize("GET /versions -> versions[]", versions,
                      ["isActual", "isCurrent"])
            for v in versions:
                show(f"version: {v.get('name','?')}", v)

        # ── Current Period ─────────────────────────────────────────────────
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/currentPeriod")
        if r:
            show("GET /currentPeriod", r)

        r = get(client, token, f"/models/{MODEL_ID}/currentPeriod")
        if r:
            show("GET /models/{modelId}/currentPeriod", r)

        # ── Files ──────────────────────────────────────────────────────────
        r = get(client, token, f"/models/{MODEL_ID}/files")
        if r:
            files = r.get("files", [])
            summarize("GET /files -> files[]", files,
                      ["origin", "format", "encoding", "delimiter",
                       "separator", "firstDataRow", "headerRow",
                       "chunkCount", "country", "language"])
            for f in files[:5]:
                show(f"file: {f.get('name','?')}", f)

        # ── Imports ────────────────────────────────────────────────────────
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/imports")
        if r:
            imports = r.get("imports", [])
            summarize("GET /imports -> imports[]", imports, ["importType"])
            for imp in imports[:3]:
                show(f"import: {imp.get('name','?')}", imp)
                imp_id = imp["id"]
                r2 = get(client, token,
                          f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/imports/{imp_id}")
                if r2:
                    show(f"  importMetadata for {imp_id}", r2)

        # ── Exports ────────────────────────────────────────────────────────
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports")
        if r:
            exports = r.get("exports", [])
            summarize("GET /exports -> exports[]", exports, ["exportType"])
            for exp in exports[:3]:
                show(f"export: {exp.get('name','?')}", exp)
                exp_id = exp["id"]
                r2 = get(client, token,
                          f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports/{exp_id}")
                if r2:
                    show(f"  exportMetadata for {exp_id}", r2)

        # ── Actions ────────────────────────────────────────────────────────
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/actions")
        if r:
            actions = r.get("actions", [])
            summarize("GET /actions -> actions[]", actions, [])
            if actions:
                show("First action (full)", actions[0])

        # ── Processes ──────────────────────────────────────────────────────
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/processes")
        if r:
            processes = r.get("processes", [])
            summarize("GET /processes -> processes[]", processes, [])
            if processes:
                show("First process (full)", processes[0])

        # ── Lists ──────────────────────────────────────────────────────────
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lists")
        if r:
            lists = r.get("lists", [])
            summarize("GET /lists -> lists[]", lists, [])
            if lists:
                show("First list (full)", lists[0])

        # ── Modules + LineItems ────────────────────────────────────────────
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/modules")
        if r:
            modules = r.get("modules", [])
            summarize("GET /modules -> modules[]", modules, [])
            if modules:
                show("First module (full)", modules[0])
                mod_id = modules[0]["id"]
                r2 = get(client, token,
                          f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/modules/{mod_id}/lineItems")
                if r2:
                    lis = r2.get("lineItems", [])
                    summarize("Module lineItems[]", lis,
                              ["format", "formulaScope", "timeScale", "timeRange",
                               "style", "summary", "breakback", "broughtForward",
                               "isSummary", "startOfSection", "useSwitchover"])
                    if lis:
                        show("First lineItem (full)", lis[0])

        # ── Model-level lineItems ──────────────────────────────────────────
        r = get(client, token, f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lineItems")
        if r:
            lis = r.get("lineItems", [])
            summarize("GET /lineItems (model-level) -> lineItems[]", lis,
                      ["format", "formulaScope", "timeScale", "timeRange",
                       "style", "summary"])

        # ── Dimensions ────────────────────────────────────────────────────
        r = get(client, token,
                f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/dimensions")
        if r:
            dims = r.get("dimensions", [])
            summarize("GET /dimensions -> dimensions[]", dims, [])
            if dims:
                show("First dimension (full)", dims[0])
                dim_id = dims[0]["id"]
                r2 = get(client, token,
                          f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/dimensions/{dim_id}/items")
                if r2:
                    key = next((k for k in r2 if isinstance(r2[k], list)), None)
                    items = r2.get(key, []) if key else []
                    summarize(f"Dimension items (dim {dim_id})", items,
                              ["read", "write", "subsetId"])
                    if items:
                        show("First dimension item (full)", items[0])

        print(f"\n{'='*60}")
        print("  PROBE COMPLETE")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
