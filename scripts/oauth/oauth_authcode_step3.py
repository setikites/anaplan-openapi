"""Step 3: Refresh the access token using the refresh token."""
import httpx, json, os

if os.path.exists('.token'):
    with open('.token') as f:
        saved = json.load(f)
    client_id = saved['client_id']
    client_secret = saved['client_secret']
    refresh_token = saved['refresh_token']
else:
    # .token not saved yet — paste values from step 2 output
    with open('.auth_code') as f:
        saved = json.load(f)
    client_id = saved['client_id']
    client_secret = saved['client_secret']
    print("No .token file found. Paste the refresh_token from the step 2 output:")
    refresh_token = input("refresh_token: ").strip()

r = httpx.post(
    'https://us1a.app.anaplan.com/oauth/token',
    json={
        'grant_type': 'refresh_token',
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
    },
)

print(f"Status: {r.status_code}")
print(json.dumps(r.json(), indent=2))
