"""
Probe the four Schema2 usages in integration-openapi.json:
  1. PUT /models/{modelId}/versions/{versionId}/switchover  (date) — expected correct
  2. PUT /models/{modelId}/currentPeriod                    (date) — expected correct
  3. POST .../exports/{exportId}/tasks                      (localeName) — suspected wrong schema
  4. GET  .../exports/{exportId}/tasks/{taskId}             (localeName body) — suspected wrong method

Goals:
  - Confirm GET task-status needs no request body
  - Confirm POST export task body is {localeName} not {date}
  - See what a real export task response looks like

Run with:
    uv run --env-file .env python scripts/_probe_schema2.py
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


def req(client, token, method, path, body=None, params=None):
    url = f"{API_URL}{path}"
    kwargs = {
        "headers": {
            "Authorization": f"AnaplanAuthToken {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        "params": params or {},
    }
    if body is not None:
        if method == "get":
            kwargs["content"] = json.dumps(body).encode()
        else:
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
    print(snippet[:800])


def main():
    with httpx.Client(timeout=30) as client:
        token = get_token(client)
        print(f"Authenticated. API_URL={API_URL}")
        print(f"WORKSPACE_ID={WORKSPACE_ID}  MODEL_ID={MODEL_ID}")

        # ── Probe 1: list exports to get an exportId ─────────────────────────
        section("List exports (to find an exportId)")
        status, body = req(client, token, "get",
                           f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports")
        show(status, body)
        exports = body.get("exports", []) if isinstance(body, dict) else []
        if not exports:
            print("  No exports found — cannot probe task endpoints.")
            return
        export_id = exports[0]["id"]
        export_name = exports[0].get("name", "?")
        print(f"\n  Using exportId={export_id!r}  name={export_name!r}")

        # ── Probe 2: list existing export tasks (GET, no body) ───────────────
        section(f"GET .../exports/{export_id}/tasks  (no body)")
        status, body = req(client, token, "get",
                           f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports/{export_id}/tasks")
        show(status, body)
        tasks = body.get("tasks", []) if isinstance(body, dict) else []

        # ── Probe 3: if a task exists, GET its status — no body ──────────────
        if tasks:
            task_id = tasks[0].get("taskId") or tasks[0].get("id")
            section(f"GET .../tasks/{task_id}  (no body — confirm GET needs no requestBody)")
            status, body = req(client, token, "get",
                               f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports/{export_id}/tasks/{task_id}")
            show(status, body)

            section(f"GET .../tasks/{task_id}  (with localeName body — confirm body is ignored/errors)")
            status, body = req(client, token, "get",
                               f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports/{export_id}/tasks/{task_id}",
                               body={"localeName": "en_US"})
            show(status, body)
        else:
            print("\n  No existing tasks — skipping GET task/{taskId} probes.")

        # ── Probe 4: POST export task — try with localeName ──────────────────
        section(f"POST .../exports/{export_id}/tasks  body={{localeName: en_US}}")
        status, body = req(client, token, "post",
                           f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports/{export_id}/tasks",
                           body={"localeName": "en_US"})
        show(status, body)
        new_task_id = None
        if isinstance(body, dict):
            t = body.get("task", {})
            new_task_id = t.get("taskId") or t.get("id")

        # ── Probe 5: POST export task — try with date body (wrong field) ─────
        section(f"POST .../exports/{export_id}/tasks  body={{date: 2021-06-03}} (expect error/ignore)")
        status, body = req(client, token, "post",
                           f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports/{export_id}/tasks",
                           body={"date": "2021-06-03"})
        show(status, body)

        # ── Probe 6: POST export task — empty body ───────────────────────────
        section(f"POST .../exports/{export_id}/tasks  body={{}} (is localeName optional?)")
        status, body = req(client, token, "post",
                           f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports/{export_id}/tasks",
                           body={})
        show(status, body)

        if new_task_id:
            section(f"GET .../tasks/{new_task_id}  (poll status of task just started)")
            status, body = req(client, token, "get",
                               f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/exports/{export_id}/tasks/{new_task_id}")
            show(status, body)


if __name__ == "__main__":
    main()
