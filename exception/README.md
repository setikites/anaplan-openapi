# Anaplan Exception Users API

## Sources

| Source | Available | Notes |
|--------|-----------|-------|
| Apiary docs | ✓ | https://exceptionusersapi2.docs.apiary.io/ — primary source |
| Local blueprint | ✓ | `exception/apiary-blueprint.json` — Apiary blueprint cached locally |
| Postman collection | ✗ | Not included in official Anaplan Postman collection |
| Live testing | Partial | Auth scheme and PATCH error probe confirmed; search contract blocked (see below) |

## Purpose

Manage exception users — users who are permitted to bypass SSO enforcement — in Anaplan workspaces. Intended for tenants with SSO enabled who need to allow specific users (e.g. service accounts or emergency access accounts) to log in with a password instead.

Requires the **Tenant Security Admin** role.

## Servers

The Exception Users API is served from `{region}.api.anaplan.com` under the `/admin/1/0` base path, following the same regional pattern as the Integration and SCIM APIs.

| Region code | Description | Base URL |
|-------------|-------------|----------|
| us1 | Data Center - US East | `https://api.anaplan.com` |
| us2 | Data Center - US West | `https://api.anaplan.com` |
| us5 | Cloud - US East | `https://api.anaplan.com` |
| us7 | Cloud - US | `https://api.anaplan.com` |
| us9 | Cloud - US | `https://us9.api.anaplan.com` |
| eu1 | Data Center - Netherlands | `https://api.anaplan.com` |
| eu2 | Data Center - Germany | `https://api.anaplan.com` |
| eu3 | Cloud - Europe | `https://eu3.api.anaplan.com` |
| eu4 | Cloud - Europe | `https://api.anaplan.com` |
| eu5 | Cloud - Europe | `https://eu5.api.anaplan.com` |
| gb1 | Cloud - UK | `https://gb1.api.anaplan.com` |
| ap1 | Cloud - Japan | `https://api.anaplan.com` |
| au1 | Cloud - Australia | `https://au1a.api2.anaplan.com` |
| ca1 | Cloud - Canada | `https://ca1a.api.anaplan.com` |
| sg1 | Cloud - Singapore | `https://sg1.api.anaplan.com` |
| ae1 | Cloud - UAE | `https://ae1.api.anaplan.com` |
| in1 | Cloud - India | `https://in1.api.anaplan.com` |
| id1 | Cloud - Indonesia | `https://id1.api.anaplan.com` |
| me1 | Cloud - Saudi Arabia | `https://me1.api.anaplan.com` |

## Authentication

Two schemes are declared in the spec. Live testing confirmed Bearer is accepted at the auth layer; AnaplanAuthToken acceptance is not yet confirmed due to the service-to-service token blocker (see below).

| Scheme | Format | Status |
|--------|--------|--------|
| AnaplanAuthToken | `Authorization: AnaplanAuthToken <token>` | Declared in Apiary docs; live confirmation pending |
| BearerAuth | `Authorization: Bearer <token>` | Confirmed accepted (issue #51); **service-to-service token required** |

### Service-to-service token requirement

Live testing returned `FAILURE_BAD_HEADER: token or apikey or Oauth service-to-service token is required` when a user authorization-code flow token was used. The API specifically requires a token obtained via the **client credentials grant** (`grant_type=client_credentials`), not a user-delegated token from the authorization code or device flows.

The existing `ANAPLAN_OAUTH_AUTHCODE_CLIENT_ID` client is not authorized for `client_credentials`. A separate OAuth client registered with the client credentials grant type is required. Register one at `manage.auth0.anaplan.com`.

## Base Path

All endpoints are prefixed with `/admin/1/0`. Example:

```
POST https://api.anaplan.com/admin/1/0/permissions/exception-users/search
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/permissions/exception-users/search` | Search for exception users by workspace or by user |
| PATCH | `/permissions/exception-users/users/{userGuid}` | Assign or unassign a user as an exception user |

### POST /permissions/exception-users/search

Accepts exactly one of `workspaceGuid` or `userGuid` in the request body.

- **By workspace** — returns all exception users in that workspace, including visitors.
- **By user** — returns all workspaces in the tenant where that user has exception-user access. Workspaces where the user has access as a visitor are excluded.

Returns a top-level `response` array of workspace result objects, each containing `workspaceGuid`, `workspaceName`, and a `users` array of `{ userGuid, email }` objects.

### PATCH /permissions/exception-users/users/{userGuid}

Request body requires `op` (`"assign"` or `"unassign"`) and `workspaceGuid`. The workspace must be SSO-enabled. A caller cannot modify their own exception-user status.

Returns 204 on success. Returns 400 if `op` is invalid or missing, `workspaceGuid` is invalid, or the workspace is not SSO-enabled.

## Testing Coverage

| Endpoint | Test | Result | Notes |
|----------|------|--------|-------|
| `POST /search` | Bearer auth accepted | ✓ | 400 (not 401) confirms auth layer recognized token (issue #51) |
| `POST /search` | Search by workspace — response shape | ✗ | Blocked: service-to-service client not yet registered |
| `POST /search` | Search by user — response shape | ✗ | Blocked: service-to-service client not yet registered |
| `PATCH /users/{userGuid}` | Invalid `op` returns 400 | ✓ | Confirmed via live test with `op: "invalid_op"` (issue #51) |

## Blocker: service-to-service OAuth client

The search contract tests and full auth confirmation require a client credentials OAuth token. The existing authcode client (`ANAPLAN_OAUTH_AUTHCODE_CLIENT_ID`) returns `unauthorized_client` for `grant_type=client_credentials`.

**To unblock:**
1. Register a new OAuth client at `manage.auth0.anaplan.com` with the `client_credentials` grant enabled.
2. Add `ANAPLAN_OAUTH_S2S_CLIENT_ID` and `ANAPLAN_OAUTH_S2S_CLIENT_SECRET` to `.env`.
3. The fixture in `tests/test_exception_live.py` will pick them up — update the env var names in the fixture.

Tracked in issue #51.

## Discrepancies and Notes

- **Apiary documents only AnaplanAuthToken**: Live testing confirmed the Bearer scheme is also accepted. BearerAuth has been added to the spec (issue #51).
- **Bearer requires service-to-service token**: Apiary and the Anaplan auth docs do not explicitly state this constraint. Discovered via live testing — user auth-code tokens are rejected with `FAILURE_BAD_HEADER`.
- **Error response field names unconfirmed**: The spec's `ErrorResponse` schema uses `status` and `message` fields inferred from Apiary. The live 400 response used `status` and `statusMessage`. The spec should be updated once confirmed across both endpoints.
