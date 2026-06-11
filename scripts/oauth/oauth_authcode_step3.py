"""Step 3: Refresh the access token using the stored refresh token.

Reads the token blob from the OS keyring (service from ANAPLAN_OAUTH_KEYRING_SERVICE,
default anaplan-oauth-authcode), refreshes it, and stores the rotated token back.
"""
import json
import os
import pathlib
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from token_keyring import load_token, store_token


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

stored = load_token(service)
if not stored:
    print(f"No token found in keyring under service '{service}'.")
    print("Run oauth_authcode_step1.py and oauth_authcode_step2.py first.")
    raise SystemExit(1)

saved = json.loads(stored)

r = httpx.post(
    "https://us1a.app.anaplan.com/oauth/token",
    json={
        "grant_type": "refresh_token",
        "client_id": saved["client_id"],
        "client_secret": saved["client_secret"],
        "refresh_token": saved["refresh_token"],
    },
)

body = r.json()
print(f"Status: {r.status_code}")
print(json.dumps({k: v for k, v in body.items() if k != "access_token"}, indent=2))

if r.status_code == 200:
    token_blob = {**saved, **body}
    store_token(service, json.dumps(token_blob))
    print()
    print(f"Refreshed token stored in OS keyring under service '{service}'.")
