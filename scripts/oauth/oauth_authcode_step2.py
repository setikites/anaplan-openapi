"""Step 2: Exchange the authorization code for tokens and store them in the OS keyring.

The full token response (access_token, refresh_token, id_token, ...) is stored as
one JSON blob in the operating system credential store via ``token_keyring``,
chunked to fit backend size limits. The keyring service name is read from
ANAPLAN_OAUTH_KEYRING_SERVICE in .env (default: anaplan-oauth-authcode).
"""
import json
import os
import pathlib
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from token_keyring import store_token


def _load_env():
    env_path = pathlib.Path(".env")
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()
service = os.getenv("ANAPLAN_OAUTH_KEYRING_SERVICE", "anaplan-oauth-authcode")

with open(".auth_code") as f:
    saved = json.load(f)

r = httpx.post(
    "https://us1a.app.anaplan.com/oauth/token",
    json={
        "grant_type": "authorization_code",
        "code": saved["code"],
        "client_id": saved["client_id"],
        "client_secret": saved["client_secret"],
        "redirect_uri": saved["redirect_uri"],
    },
)

body = r.json()
print(f"Status: {r.status_code}")
print(json.dumps({k: v for k, v in body.items() if k != "access_token"}, indent=2))

if r.status_code == 200:
    token_blob = {**saved, **body}
    store_token(service, json.dumps(token_blob))
    print()
    print(f"Token stored in OS keyring under service '{service}'.")
    print("Run next: uv run python scripts/oauth/oauth_authcode_step3.py")
