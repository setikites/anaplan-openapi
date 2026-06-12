"""Authorization Code grant: obtain an OAuth token and store it in the OS keyring.

Combines the former two-step helper (build the authorize URL + capture the browser
redirect, then exchange the code) into one run. The authorization code is passed
straight to ``exchange_code_for_token`` rather than round-tripped through a
``.auth_code`` file.

The full token response is stored as one chunked JSON blob in the OS credential
store via ``token_keyring``, under the service named by ANAPLAN_OAUTH_KEYRING_SERVICE
in .env (default: anaplan-oauth-authcode).

    uv run python scripts/oauth/oauth_authcode.py
"""
import json
import os
import pathlib
import secrets
import sys
import urllib.parse

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from token_keyring import store_token

API_URL = "https://us1a.app.anaplan.com"
REDIRECT_URI = "https://www.anaplan.com"
SCOPE = "openid profile email offline_access"


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


def build_auth_url(client_id, redirect_uri=REDIRECT_URI, state="", scope=SCOPE):
    """Return the prelogin authorize URL the user opens to approve access."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
    }
    return f"{API_URL}/auth/prelogin?" + urllib.parse.urlencode(params)


def extract_code(redirect_url, expected_state):
    """Return the authorization code from the pasted redirect URL.

    Raises ValueError if the state does not match (CSRF guard) or no code is present.
    """
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)
    returned_state = qs.get("state", [None])[0]
    code = qs.get("code", [None])[0]
    if returned_state != expected_state:
        raise ValueError(
            f"state mismatch (expected {expected_state!r}, got {returned_state!r})"
        )
    if not code:
        raise ValueError("no 'code' parameter found in the redirect URL")
    return code


def exchange_code_for_token(code, client_id, client_secret, redirect_uri=REDIRECT_URI):
    """Exchange an authorization code for the OAuth token response."""
    return httpx.post(
        f"{API_URL}/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
    )


def main():
    _load_env()
    client_id = os.getenv("ANAPLAN_OAUTH_AUTHCODE_CLIENT_ID")
    client_secret = os.getenv("ANAPLAN_OAUTH_AUTHCODE_CLIENT_SECRET")
    service = os.getenv("ANAPLAN_OAUTH_KEYRING_SERVICE", "anaplan-oauth-authcode")
    state = secrets.token_urlsafe(16)

    print("Open this URL in your browser:")
    print(f"  {build_auth_url(client_id, state=state)}")
    print()
    print(f"After approving, your browser will redirect to {REDIRECT_URI}")
    print("Copy the full URL from the address bar and paste it below.")
    print()

    code = extract_code(input("Redirect URL: ").strip(), expected_state=state)
    print(f"Code captured: {code[:12]}...")

    r = exchange_code_for_token(code, client_id, client_secret)
    body = r.json()
    print(f"Status: {r.status_code}")
    print(json.dumps({k: v for k, v in body.items() if k != "access_token"}, indent=2))

    if r.status_code != 200:
        raise SystemExit(1)

    token_blob = {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        **body,
    }
    store_token(service, json.dumps(token_blob))
    print()
    print(f"Token stored in OS keyring under service '{service}'.")
    print("Refresh later with: uv run python scripts/oauth/oauth_authcode_refresh.py")


if __name__ == "__main__":
    main()
