"""Step 2: Exchange the authorization code for tokens. Run after the browser redirect completes."""
import httpx, json

with open('.auth_code') as f:
    saved = json.load(f)

r = httpx.post(
    'https://us1a.app.anaplan.com/oauth/token',
    json={
        'grant_type': 'authorization_code',
        'code': saved['code'],
        'client_id': saved['client_id'],
        'client_secret': saved['client_secret'],
        'redirect_uri': saved['redirect_uri'],
    },
)

body = r.json()
print(f"Status: {r.status_code}")
print(json.dumps(body, indent=2))

if r.status_code == 200:
    with open('.token', 'w') as f:
        json.dump({**saved, **body}, f)
    print()
    print("Token saved. Run next: uv run python scripts/oauth/oauth_authcode_step3.py")
