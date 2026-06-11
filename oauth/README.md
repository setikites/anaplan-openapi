# Anaplan OAuth 2.0 Service API

## Sources

| Source | Available | Notes |
|--------|-----------|-------|
| Apiary docs | ✓ | https://anaplanoauth2service.docs.apiary.io/ — primary source |
| Postman collection | Partial | Official Anaplan Collection — covered within the "Authentication > OAuth 2.0" subfolder (2 requests: Obtain Refresh Token, Swap Refresh Token for Access Token via `us1a.app.anaplan.com/oauth/token`). The Authorization Code Grant and Device Authorization Grant flows in this spec are not covered by the collection. |
| Live testing | Partial | See Testing Coverage below |

## Servers

The OAuth 2.0 API is served from `{region}.app.anaplan.com`. The correct URL depends on which Anaplan region your tenant is hosted in. Source: [URL, IP, and allowlist requirements](https://support.anaplan.com/url-ip-and-allowlist-requirements-c8235c7d-8af2-413b-a9ff-d465978806b9).

The Apiary docs incorrectly list `https://auth.anaplan.com` as the OAuth API URL — that domain hosts the separate Authentication Service API (`/token/authenticate`, etc.).

| Region code | Description | OAuth 2.0 API base URL |
|-------------|-------------|------------------------|
| us1 | Data Center - US East | `https://us1a.app.anaplan.com` |
| us2 | Data Center - US West | `https://us1a.app.anaplan.com` |
| us5 | Cloud - US East | `https://us1a.app.anaplan.com` |
| us7 | Cloud - US | `https://us1a.app.anaplan.com` |
| us9 | Cloud - US | `https://us9.app.anaplan.com` |
| eu1 | Data Center - Netherlands | `https://us1a.app.anaplan.com` |
| eu2 | Data Center - Germany | `https://us1a.app.anaplan.com` |
| eu3 | Cloud - Europe | `https://eu3.app.anaplan.com` |
| eu4 | Cloud - Europe | `https://us1a.app.anaplan.com` |
| eu5 | Cloud - Europe | `https://eu5.app.anaplan.com` |
| gb1 | Cloud - UK | `https://gb1.app.anaplan.com` |
| ap1 | Cloud - Japan | `https://us1a.app.anaplan.com` |
| au1 | Cloud - Australia | `https://au1a.app2.anaplan.com` |
| ca1 | Cloud - Canada | `https://ca1a.app.anaplan.com` |
| sg1 | Cloud - Singapore | `https://sg1.app.anaplan.com` |
| ae1 | Cloud - UAE | `https://ae1.app.anaplan.com` |
| in1 | Cloud - India | `https://in1.app.anaplan.com` |
| id1 | Cloud - Indonesia | `https://id1.app.anaplan.com` |
| me1 | Cloud - Saudi Arabia | `https://me1.app.anaplan.com` |

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
| `GET /auth/authorize` | Partial (302 verified) | Partial | 302 + Location header confirmed; login step and code callback require browser |
| `POST /oauth/device/code` | ✓ | ✓ | Device approval step requires browser |
| `POST /oauth/token` (device grant) | ✓ | ✓ | Requires user to approve at `verification_uri` |
| `POST /oauth/token` (auth code grant) | ✓ | ✓ | Requires browser redirect to obtain code; tested via `scripts/oauth/oauth_authcode_step1.py` / `oauth_authcode_step2.py` |
| `POST /oauth/token` (refresh) | ✓ | ✓ | Tested via `scripts/oauth/oauth_authcode_step3.py` using a live refresh token from the auth code flow |

## Discrepancies and Notes

- **Server URL differs from Apiary docs**: Apiary lists `https://auth.anaplan.com` as the production URL, but live testing confirmed the OAuth endpoints are served at `{region}.app.anaplan.com` (e.g. `us1a.app.anaplan.com`). The `auth.anaplan.com` domain hosts only the Authentication Service API. See the Servers table above for all regional URLs.
- **`/auth/prelogin` vs `/auth/authorize`**: The Apiary docs document `/auth/authorize` as the Authorization Code Grant entry point (returns 302 redirect to the login page). The `anaplan-sdk` library uses `GET /auth/prelogin` instead, which returns the login page HTML directly (200). The spec documents `/auth/authorize` as the canonical Apiary-defined endpoint; `/auth/prelogin` is noted in its description as an equivalent alternative used by some clients.
- **`expires_in`**: Live testing confirmed `expires_in` is 2100 seconds (35 minutes) across all three grant types. The spec example has been updated accordingly.
- **`anaplan_token` not returned**: Apiary documents `anaplan_token` as present on token responses. Live testing of all three grant types (device grant, authorization code grant, and refresh token grant) returned no `anaplan_token` field in any response. The field has been removed from the spec.
- **`profile` scope silently dropped**: Requesting `scope: openid profile email offline_access` in `GET /auth/authorize` results in a granted scope of `openid email offline_access` — the server drops `profile` without error. The `profile` scope is listed in Anaplan's documentation but does not appear to be honoured. The spec scope example has been updated to reflect what the server actually returns.
- **Refresh tokens are rotatable**: Live testing confirmed the API issues a new `refresh_token` on each refresh call, consistent with the spec note about rotatable tokens.
- **`audience` parameter**: Documented in the Apiary docs as optional on `POST /oauth/device/code`. Not mentioned for other endpoints.
- **Device flow error codes**: Standard RFC 8628 codes (`authorization_pending`, `slow_down`, `expired_token`) are expected during polling but not explicitly documented in Apiary.
