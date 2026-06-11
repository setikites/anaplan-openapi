"""Step 1: Open the auth URL in your browser, approve, then paste the redirect URL here."""
import os, json, secrets, urllib.parse

with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

client_id = os.getenv('ANAPLAN_OAUTH_AUTHCODE_CLIENT_ID')
client_secret = os.getenv('ANAPLAN_OAUTH_AUTHCODE_CLIENT_SECRET')
redirect_uri = 'https://www.anaplan.com'
state = secrets.token_urlsafe(16)

params = {
    'response_type': 'code',
    'client_id': client_id,
    'redirect_uri': redirect_uri,
    'scope': 'openid profile email offline_access',
    'state': state,
}
auth_url = 'https://us1a.app.anaplan.com/auth/prelogin?' + urllib.parse.urlencode(params)

print("Open this URL in your browser:")
print(f"  {auth_url}")
print()
print("After approving, your browser will redirect to https://www.anaplan.com")
print("Copy the full URL from the address bar and paste it below.")
print()

pasted = input("Redirect URL: ").strip()

parsed = urllib.parse.urlparse(pasted)
qs = urllib.parse.parse_qs(parsed.query)

returned_state = qs.get('state', [None])[0]
code = qs.get('code', [None])[0]

if returned_state != state:
    print(f"ERROR: state mismatch (expected {state}, got {returned_state})")
    raise SystemExit(1)

if not code:
    print("ERROR: no 'code' parameter found in the URL")
    raise SystemExit(1)

print(f"Code captured: {code[:12]}...")
print()
print("Run next: uv run python scripts/oauth/oauth_authcode_step2.py")

with open('.auth_code', 'w') as f:
    json.dump({
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
    }, f)
