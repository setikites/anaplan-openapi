# Anaplan OAuth 2.0 Service API

## Sources

| Source | Available | Notes |
|--------|-----------|-------|
| Apiary docs | ✓ | https://anaplanoauth2service.docs.apiary.io/ — primary source |
| Postman collection | ✗ | Not included in official Anaplan Postman collection |
| Live testing | Partial | See Testing Coverage below |

## Server

`https://us1a.app.anaplan.com`

The Apiary docs list `https://auth.anaplan.com` as the production URL, but live testing shows the OAuth endpoints (`/oauth/device/code`, `/oauth/token`, `/auth/prelogin`) are served at `us1a.app.anaplan.com`. The `auth.anaplan.com` domain hosts the separate Authentication Service API (`/token/authenticate`, etc.).

## OAuth Flows

### Authorization Code Grant

Supports both SSO (SAML) and basic authentication. For web applications with browser-based redirect flows.

1. `GET /auth/authorize` — Redirects user to Anaplan login; browser is redirected back to `redirect_uri?code=...`
2. `POST /oauth/token` with `grant_type: authorization_code` — Exchanges code for tokens

### Device Authorization Grant

Basic authentication only (SSO/SAML not supported). For devices or CLIs without a browser.

1. `POST /oauth/device/code` — Returns `device_code` and `user_code`
2. Display `verification_uri` and `user_code` to the user
3. Poll `POST /oauth/token` with `grant_type: urn:ietf:params:oauth:grant-type:device_code` until user approves or code expires

### Token Refresh

Both flows issue a `refresh_token`. Exchange via `POST /oauth/token` with `grant_type: refresh_token`.

Refresh tokens may be rotatable (new token on each use, 30-day rotation) or non-rotatable, depending on client configuration in Anaplan Administration.

## Scopes

| Scope | Description |
|-------|-------------|
| `openid` | Trigger OIDC flow; returns JWT verifying user identity |
| `profile` | Basic non-sensitive user information |
| `email` | User's primary email address |
| `offline_access` | Request a refresh token for long-lived access |

## Client IDs

The Authorization Code Grant and Device Authorization Grant use **separate client registrations** in Anaplan Administration > OAuth. The same `client_id` value cannot be used for both flows. In `.env`:

- `ANAPLAN_OAUTH_CLIENT_ID` — client ID for Authorization Code Grant
- `ANAPLAN_OAUTH_DEVICE_CLIENT_ID` — client ID for Device Authorization Grant

## Authentication

None of the OAuth service endpoints require an `Authorization` request header. All authentication parameters are passed in the request body or query string. This API is the auth server itself, not an API protected by OAuth.

## Testing Coverage

| Endpoint | Happy Path | Error Cases | Automation Limitation |
|----------|-----------|-------------|----------------------|
| `GET /auth/authorize` | Not automatable | Partial | Requires browser redirect; only error paths testable in CI |
| `POST /oauth/device/code` | ✓ | ✓ | Device approval step requires browser |
| `POST /oauth/token` (device grant) | Not automatable end-to-end | ✓ | Requires user to approve at `verification_uri` |
| `POST /oauth/token` (auth code grant) | Not automatable | ✓ | Requires browser redirect to obtain code |
| `POST /oauth/token` (refresh) | Not automatable end-to-end | ✓ | Requires a live refresh token from a prior non-automated flow |

## Discrepancies and Notes

- **Server URL differs from Apiary docs**: Apiary lists `https://auth.anaplan.com` as the production URL, but live testing confirmed the OAuth endpoints are served at `https://us1a.app.anaplan.com`. The `auth.anaplan.com` domain hosts only the Authentication Service API.
- **`/auth/prelogin` vs `/auth/authorize`**: The Apiary docs document `/auth/authorize` as the Authorization Code Grant entry point. Live testing and the `anaplan-sdk` library show that `/auth/prelogin` is the actual endpoint used — it returns a 200 HTML login page directly, while `/auth/authorize` returns a 302 redirect. Both paths are at `us1a.app.anaplan.com`.
- **`expires_in` vs `expiresAt`**: The token response `expires_in` field follows RFC 6749 (seconds until expiry, e.g. `3600`). The `expiresAt` field inside `anaplan_token.tokenInfo` is an absolute milliseconds-since-epoch timestamp. The original Apiary docs were ambiguous and the handwritten draft conflated these with a Unix epoch example value on `expires_in`.
- **`status_message` casing**: The `anaplan_token` object uses `status_message` (snake_case), whereas the Authentication Service API uses `statusMessage` (camelCase) for the same field. This inconsistency exists in the Apiary source.
- **`audience` parameter**: Documented in the Apiary docs as optional on `POST /oauth/device/code`. Not mentioned for other endpoints.
- **Device flow error codes**: Standard RFC 8628 codes (`authorization_pending`, `slow_down`, `expired_token`) are expected during polling but not explicitly documented in Apiary.
