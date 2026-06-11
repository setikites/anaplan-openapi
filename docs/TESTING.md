# Live API testing

The specs in this repo are validated against a live Anaplan instance. This is
the single reference for how to set up credentials and run the live test suite.
Per-API READMEs link here rather than repeating these mechanics.

Live tests are **skipped by default** and require credentials. The unit/contract
tests (spec validation, converter, schema importer) need no credentials and run
with a plain `uv run pytest`.

## Credentials (`.env`)

Live tests read credentials from a `.env` file at the repo root. Pass it
explicitly so special characters in passwords and Windows paths are handled
correctly:

```sh
uv run --env-file .env pytest tests/ --live
```

| Variable | Used for | Notes |
|----------|----------|-------|
| `ANAPLAN_USERNAME` | Basic auth | Email/username for username+password auth |
| `ANAPLAN_PASSWORD` | Basic auth | Password (basic-auth fallback) |
| `ANAPLAN_CA_CERT_PATH` | Certificate auth (preferred) | Path to X.509 CA certificate (PEM) |
| `ANAPLAN_CA_KEY_PATH` | Certificate auth (preferred) | Path to the corresponding private key (PEM) |
| `ANAPLAN_CA_KEY_PASSWORD` | Certificate auth | Private-key password, if the key is encrypted |
| `ANAPLAN_API_BASE_URL` | Integration/data-plane tests | Override base URL (default `https://api.anaplan.com`) |
| `ANAPLAN_OAUTH_CLIENT_ID` | OAuth Authorization Code Grant | Client ID registered for the auth-code flow |
| `ANAPLAN_OAUTH_DEVICE_CLIENT_ID` | OAuth Device Grant | Client ID registered for the device flow |
| `ANAPLAN_OAUTH_AUTHCODE_CLIENT_ID` / `ANAPLAN_OAUTH_AUTHCODE_CLIENT_SECRET` | `scripts/oauth/` helpers | Auth-code client credentials for the manual OAuth helper scripts |

Certificate auth is preferred where configured; basic auth is the fallback.
Fixtures `skip` cleanly when a credential is missing, so you can run a subset
with only the credentials you have.

### Certificate auth prerequisites

- An X.509 certificate issued by a CA, in PEM format, plus its private key.
- The certificate must be **registered and enabled for API authentication** in
  your Anaplan instance. SMIME/email certificates alone will not work.
- The certificate authentication flow matches the community `anaplan-sdk`
  implementation: generate random data, sign it with the private key
  (SHA512withRSA), and send `encodedData` + `encodedSignedData` to
  `/token/authenticate`.

## Flags

| Flag | Effect |
|------|--------|
| `--live` | Run tests marked `@pytest.mark.live` (otherwise skipped) |
| `--allow-writes` | Permit write methods (PUT/POST/PATCH/DELETE) against the `api.anaplan.com` data plane. **Omit to keep live runs read-only.** Pass only after explicit human approval. |

The write-guard (`conftest.py`) blocks data-plane mutations during live runs
unless `--allow-writes` is given. Auth-plane calls (`auth.anaplan.com`,
`app.anaplan.com`) — i.e. obtaining tokens — are never blocked.

## Examples

```sh
# All live tests, read-only
uv run --env-file .env pytest tests/ --live

# One API
uv run --env-file .env pytest tests/test_integration_live.py --live

# A single certificate-auth workflow test
uv run --env-file .env pytest tests/test_auth_integration_live.py::test_auth_workflow_ca_cert --live

# Permit writes (only after human approval)
uv run --env-file .env pytest tests/test_integration_live.py --live --allow-writes
```

## Manual OAuth flows

The Authorization Code and Device grants need a browser step that cannot be
automated. The helper scripts in `scripts/oauth/` walk through them
interactively. Run them from the repo root (they read `.env` and write
short-lived artifacts like `.auth_code` / `.token` to the working directory —
these are git-ignored):

```sh
uv run python scripts/oauth/oauth_authcode_step1.py   # print auth URL, capture redirect code
uv run python scripts/oauth/oauth_authcode_step2.py   # exchange code for tokens
uv run python scripts/oauth/oauth_authcode_step3.py   # refresh using a live refresh token
uv run python scripts/oauth/oauth_device_step1.py     # request device + user code
uv run python scripts/oauth/oauth_device_step2.py     # poll for approval
```
