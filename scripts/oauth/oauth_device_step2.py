"""Step 2: Poll for token after browser approval. Run after approving in the browser.

On success the token blob is stored in the OS keyring rather than printed. The service
name comes from ANAPLAN_OAUTH_DEVICE_KEYRING_SERVICE (default anaplan-oauth-device) —
deliberately distinct from the Authorization Code grant's service so the two flows do
not overwrite each other's tokens.
"""
import os, pathlib, sys
import httpx, json, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from token_keyring import store_token

service = os.getenv('ANAPLAN_OAUTH_DEVICE_KEYRING_SERVICE', 'anaplan-oauth-device')

with open('.device_code') as f:
    saved = json.load(f)

device_code = saved['device_code']
client_id = saved['client_id']

print("Polling for token...")
for attempt in range(1, 20):
    r = httpx.post(
        'https://us1a.app.anaplan.com/oauth/token',
        json={
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
            'device_code': device_code,
            'client_id': client_id,
        },
    )
    body = r.json()
    if r.status_code == 200:
        # Never echo the body: it carries access_token/refresh_token/id_token.
        store_token(service, json.dumps({'client_id': client_id, **body}))
        print(f"Approval received. Token stored in OS keyring under service '{service}'.")
        if 'expires_in' in body:
            print(f"Access token expires in {body['expires_in']}s.")
        break
    err = body.get('error')
    print(f"  [{attempt}] {err}")
    if err not in ('authorization_pending', 'slow_down'):
        # Error bodies carry no secrets, so the description is safe to show.
        print(f"  stopped: HTTP {r.status_code} {body.get('error_description', '')}".rstrip())
        raise SystemExit(1)
    time.sleep(5)
else:
    print("Timed out waiting for browser approval.")
    raise SystemExit(1)
