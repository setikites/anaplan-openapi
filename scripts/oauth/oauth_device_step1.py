"""Step 1: Start device flow and display the approval URL. Run this first."""
import os, httpx, json

with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

client_id = os.getenv('ANAPLAN_OAUTH_DEVICE_CLIENT_ID')
r = httpx.post(
    'https://us1a.app.anaplan.com/oauth/device/code',
    json={'client_id': client_id, 'scope': 'openid profile email offline_access'},
)
data = r.json()

print(f"Open this URL in your browser:")
print(f"  {data['verification_uri_complete']}")
print(f"  User code: {data['user_code']}")
print(f"  Expires in: {data['expires_in']}s")
print()
print("Approve in the browser, then run: uv run python scripts/oauth/oauth_device_step2.py")

with open('.device_code', 'w') as f:
    json.dump({'device_code': data['device_code'], 'client_id': client_id}, f)
