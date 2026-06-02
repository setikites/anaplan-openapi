"""Step 2: Poll for token after browser approval. Run after approving in the browser."""
import httpx, json, time

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
        print("== Token response ==")
        print(json.dumps(body, indent=2))
        break
    err = body.get('error')
    print(f"  [{attempt}] {err}")
    if err not in ('authorization_pending', 'slow_down'):
        print(json.dumps(body, indent=2))
        break
    time.sleep(5)
