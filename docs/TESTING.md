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
| `ANAPLAN_OAUTH_KEYRING_SERVICE` | `scripts/oauth/` helpers + audit live tests | Keyring service name under which the Authorization Code grant token blob is stored (default `anaplan-oauth-authcode`). When a token is present, the audit live tests send its `access_token` as `AnaplanAuthToken` instead of basic auth. |
| `ANAPLAN_INTEGRATION_WORKSPACE_ID` | Integration live tests | Workspace ID for model-scoped Integration API tests |
| `ANAPLAN_INTEGRATION_MODEL_ID` | Integration live tests | Model ID for model-scoped Integration API tests |
| `ANAPLAN_ALM_WORKSPACE_ID` | ALM live tests | Workspace ID for ALM API tests |
| `ANAPLAN_ALM_MODEL_ID` | ALM live tests | Model ID for ALM API tests |
| `ANAPLAN_EXCEPTION_WORKSPACE_GUID` | Exception live tests | Workspace GUID for Exception API tests |
| `ANAPLAN_EXCEPTION_USER_GUID` | Exception live tests | User GUID for Exception API tests |

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
interactively. Run them from the repo root (they read `.env`):

```sh
uv run python scripts/oauth/oauth_authcode.py         # print auth URL, capture code, exchange + store in keyring
uv run python scripts/oauth/oauth_authcode_refresh.py # refresh the stored token (rotates it in keyring)
uv run python scripts/oauth/oauth_device_step1.py     # request device + user code
uv run python scripts/oauth/oauth_device_step2.py     # poll for approval
```

### Authorization Code grant → audit live tests (issue #58)

The audit API's `GET /events` happy path needs a token for an account holding
the **Tenant Auditor** role, obtained via the Authorization Code grant and sent
as `Authorization: AnaplanAuthToken {token}` (the audit host rejects `Bearer`).
The flow is human-in-the-loop (the browser approval can't be automated), but is
repeatable:

1. **One-time setup**: assign the Tenant Auditor role to the test account in
   Anaplan Administration, and register an Authorization Code grant OAuth client
   (`ANAPLAN_OAUTH_AUTHCODE_CLIENT_ID` / `_SECRET` in `.env`).
2. Run `oauth_authcode.py`, approve in the browser, and paste the redirect URL
   back when prompted. The script exchanges the code and stores the full token
   response in the OS keyring (Windows Credential Manager / macOS Keychain /
   Secret Service) under `ANAPLAN_OAUTH_KEYRING_SERVICE`. The JWT blob is chunked
   across multiple keyring entries because backends cap a single secret at
   ~2.5 KB.
3. Run the audit live tests. With a token in the keyring they use its
   `access_token` as the bearer automatically — no per-run code changes:

   ```sh
   uv run --env-file .env pytest tests/test_audit_live.py --live
   ```

   `GET /events` should return `200` (not `401 FAILURE_UNAUTHORIZED_USER_ACTION`),
   confirming both the role and the OAuth path end-to-end.
4. When the access token expires (~35 min), run `oauth_authcode_refresh.py` to
   refresh it in place; no browser step is needed until the refresh token
   itself expires.

Remove the stored token at any time from a Python shell:
`from oauth.token_keyring import clear_token; clear_token("anaplan-oauth-authcode")`.
