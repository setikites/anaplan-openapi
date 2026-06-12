# Anaplan Exception Users API

## Sources

| Source | Available | Notes |
|--------|-----------|-------|
| Apiary docs | ✓ | https://exceptionusersapi2.docs.apiary.io/ — primary source |
| Local blueprint | ✓ | `sources/exception/apiary-blueprint.json` — Apiary blueprint cached locally |
| Postman collection | ✓ | Official Anaplan Collection — top-level "Exception Users" folder, 4 requests |
| Live testing | ✓ | Auth schemes, search contract (by workspace and by user), and PATCH error probe confirmed via OAuth Authorization Code grant (issue #51) |

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

All three schemes were probed via live testing using both API key and OAuth Authorization Code credentials.

| Scheme | Format | Status |
|--------|--------|--------|
| AnaplanAuthToken | `Authorization: AnaplanAuthToken <token>` | **Confirmed accepted** — works with both Authentication API tokens and OAuth Authorization Code access tokens |
| AnaplanApiKey | `Authorization: AnaplanApiKey auk_<region>_<value>` | **Confirmed accepted** — API keys accepted (issue #51) |
| Bearer | `Authorization: Bearer <token>` | **Rejected** — returns `400 FAILURE_BAD_HEADER` even for valid OAuth tokens |

The error message returned when the auth header is invalid: `FAILURE_BAD_HEADER: Request header invalid, token or apikey or Oauth service-to-service token is required`.

OAuth access tokens must use the `AnaplanAuthToken` prefix, not `Bearer`. This is consistent with the Audit API behavior.

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

Live tests run with OAuth Authorization Code grant (`AnaplanAuthToken {access_token}`), Tenant Security Admin role. Run with `--live --allow-writes`.

| Endpoint | Test | Result | Notes |
|----------|------|--------|-------|
| `POST /search` | AnaplanAuthToken (OAuth) accepted | ✓ | Auth confirmed; non-401, non-FAILURE_BAD_HEADER response |
| `POST /search` | Bearer (OAuth) rejected | ✓ | 400 FAILURE_BAD_HEADER — Bearer not accepted even for valid OAuth tokens |
| `POST /search` | AnaplanApiKey accepted | ✓ | 400 without FAILURE_BAD_HEADER confirms auth layer accepted key |
| `POST /search` | Search by workspace — response shape | ✓ | 200 with `response` array of `{ workspaceGuid, workspaceName, users }` objects |
| `POST /search` | Search by user — response shape | ✓ | 200 with `response` array |
| `PATCH /users/{userGuid}` | Invalid `op` returns 400 | ✓ | `op: "invalid_op"` returns 400 as expected |

## Postman Collection

The official Anaplan Postman collection contains a top-level "Exception Users" folder with 4 requests. All use `{{baseUrl}}/admin/1/0/permissions/exception-users/...` and authenticate via `{{authHeader}}`.

| Request | Method | Path | Body |
|---------|--------|------|------|
| Assign user as exception user | PATCH | `/admin/1/0/permissions/exception-users/users/{{userGuid}}` | `{"op": "assign", "workspaceGuid": "{{workspaceGuid}}"}` |
| Unassign user as exception user | PATCH | `/admin/1/0/permissions/exception-users/users/{{userGuid}}` | `{"op": "unassign", "workspaceGuid": "{{workspaceGuid}}"}` |
| List exception users per workspace | POST | `/admin/1/0/permissions/exception-users/search` | `{"workspaceGuid": "{{workspaceGuid}}"}` |
| List workspaces with exception users | POST | `/admin/1/0/permissions/exception-users/search` | `{}` |

The collection description adds a note not present in Apiary: *"To use this API, you must enable a tenant-settings switch in the Anaplan Administration console. The switch is called 'Limit exception user assignment to Administration only.'"*

**Discrepancy — "List workspaces with exception users" body**: The Postman collection sends an empty `{}` body for this request. Apiary documents the by-user search as requiring `{"userGuid": "..."}`. It is unclear whether the empty body is a Postman authoring error, or whether the endpoint supports a third mode (return all exception users across all workspaces). This should be confirmed via live testing with Tenant Security Admin credentials.

## Discrepancies and Notes

- **Apiary documents only AnaplanAuthToken**: Confirmed correct. Bearer is rejected even for valid OAuth tokens (`FAILURE_BAD_HEADER`). BearerAuth was initially added to the spec but removed after live testing confirmed it is not accepted (issue #51).
- **OAuth tokens use AnaplanAuthToken prefix**: Contrary to the OAuth 2.0 convention (`Bearer`), Anaplan's admin APIs (Exception Users, Audit) require OAuth access tokens to be sent with the `AnaplanAuthToken` prefix rather than `Bearer`.
- **Error response uses `statusMessage` not `message`**: The live 400 response body contains `{ "status": "FAILURE_BAD_HEADER", "statusMessage": "..." }`. The spec's `ErrorResponse` schema models both fields correctly; the `message` field documented in Apiary appears to be `statusMessage` in practice.
- **Postman "List workspaces" empty body**: The Postman collection sends `{}` for the by-user search. Live testing confirms `userGuid` is required — the empty body case is likely a Postman authoring error. The spec correctly documents `userGuid` as required for by-user search.
