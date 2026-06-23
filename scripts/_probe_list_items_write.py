"""
Probe POST and PUT /lists/{listId}/items for list item write operations.

Steps:
  1. POST two items to INTEGRATION_LIST (action=add).
  2. PUT one of those items to update its code.
  3. Run INTEGRATION_ACTION (Delete Alternate SKU) to clean up.

Run with:
    uv run --env-file .env python scripts/_probe_list_items_write.py
"""

import base64
import json
import os
import secrets
import time

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

AUTH_URL = "https://auth.anaplan.com"
_api_base = os.getenv("ANAPLAN_API_BASE_URL", "https://api.anaplan.com").rstrip("/")
API_URL = _api_base if _api_base.endswith("/2/0") else _api_base + "/2/0"
WORKSPACE_ID = os.getenv("ANAPLAN_INTEGRATION_WORKSPACE_ID", "")
MODEL_ID = os.getenv("ANAPLAN_INTEGRATION_MODEL_ID", "")
LIST_ID = os.getenv("INTEGRATION_LIST", "")
ACTION_ID = os.getenv("INTEGRATION_ACTION", "")


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


def _auth(token: str) -> dict:
    return {"Authorization": f"AnaplanAuthToken {token}"}


def _print_response(label: str, r: httpx.Response) -> dict | str:
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"  HTTP {r.status_code}")
    ct = r.headers.get("content-type", "")
    if "application/json" in ct:
        body = r.json()
        print(f"  body:\n{json.dumps(body, indent=4, default=str)}")
        return body
    else:
        print(f"  body (non-JSON): {r.text[:400]}")
        return r.text


def _poll_action(client: httpx.Client, token: str, task_id: str, timeout: int = 60) -> dict:
    url = (
        f"{API_URL}/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}"
        f"/actions/{ACTION_ID}/tasks/{task_id}"
    )
    terminal = {"COMPLETE", "CANCELLED", "CANCELLING"}
    deadline = time.time() + timeout
    task: dict = {}
    while time.time() < deadline:
        r = client.get(url, headers=_auth(token))
        assert r.status_code == 200, f"Poll failed: {r.status_code}: {r.text[:200]}"
        task = r.json().get("task", {})
        state = task.get("taskState", "")
        print(f"    taskState={state}")
        if state in terminal:
            break
        time.sleep(2)
    return task


def main() -> None:
    if not LIST_ID:
        raise RuntimeError("INTEGRATION_LIST not set in environment")
    if not ACTION_ID:
        raise RuntimeError("INTEGRATION_ACTION not set in environment")

    print(f"API_URL={API_URL}")
    print(f"WORKSPACE_ID={WORKSPACE_ID}")
    print(f"MODEL_ID={MODEL_ID}")
    print(f"LIST_ID={LIST_ID}")
    print(f"ACTION_ID={ACTION_ID}")

    items_path = (
        f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/lists/{LIST_ID}/items"
    )
    action_tasks_path = (
        f"/workspaces/{WORKSPACE_ID}/models/{MODEL_ID}/actions/{ACTION_ID}/tasks"
    )

    with httpx.Client(timeout=60) as client:
        token = get_token(client)
        print(f"\nAuthenticated.")
        h = _auth(token)
        hj = {**h, "Content-Type": "application/json"}

        # ── 1. POST — add two items ───────────────────────────────────────────
        post_body = {
            "items": [
                {"name": "probe-item-A", "code": "probe-A"},
                {"name": "probe-item-B", "code": "probe-B"},
            ]
        }
        print(f"\nPOST {items_path}?action=add")
        print(f"  request body: {json.dumps(post_body)}")
        post_r = client.post(
            f"{API_URL}{items_path}",
            headers=hj,
            params={"action": "add"},
            json=post_body,
        )
        post_resp = _print_response("POST /lists/{listId}/items?action=add", post_r)

        # ── 2. PUT — update probe-item-A's code ───────────────────────────────
        put_body = {
            "items": [
                {"name": "probe-item-A", "code": "probe-A-updated"},
            ]
        }
        print(f"\nPUT {items_path}")
        print(f"  request body: {json.dumps(put_body)}")
        put_r = client.put(
            f"{API_URL}{items_path}",
            headers=hj,
            json=put_body,
        )
        put_resp = _print_response("PUT /lists/{listId}/items", put_r)

        # ── 3. Run cleanup action (Delete Alternate SKU) ─────────────────────
        print(f"\nPOST {action_tasks_path}  (cleanup: Delete Alternate SKU)")
        cleanup_r = client.post(
            f"{API_URL}{action_tasks_path}",
            headers=hj,
            json={"localeName": "en_US"},
        )
        cleanup_resp = _print_response(
            "POST /actions/{actionId}/tasks (cleanup)", cleanup_r
        )
        if cleanup_r.status_code == 200:
            task_id = (
                cleanup_resp.get("task", {}).get("taskId")
                if isinstance(cleanup_resp, dict)
                else None
            )
            if task_id:
                print(f"\n  Polling cleanup task {task_id}...")
                final = _poll_action(client, token, task_id)
                print(f"\n  Cleanup task final state: {final.get('taskState')}")
                result = final.get("result", {})
                print(f"  Cleanup result: {json.dumps(result, indent=4, default=str)}")

        # ── Summary ───────────────────────────────────────────────────────────
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"POST top-level keys: {list(post_resp.keys()) if isinstance(post_resp, dict) else 'non-dict'}")
        print(f"PUT  top-level keys: {list(put_resp.keys()) if isinstance(put_resp, dict) else 'non-dict'}")


if __name__ == "__main__":
    main()
