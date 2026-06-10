# Anaplan Exception Users API

## Sources

| Source | Available | Notes |
|--------|-----------|-------|
| Apiary docs | ✓ | https://exceptionusersapi2.docs.apiary.io/ — primary source |
| Local blueprint | ✓ | `exception/apiary-blueprint.json` — Apiary blueprint cached locally |
| Postman collection | ✓ | Official Anaplan Collection — top-level "Exception Users" folder, 4 requests |
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

Three schemes were probed via live testing. The `AnaplanApiKey` prefix is the correct format for Anaplan API keys; Bearer and AnaplanAuthToken are rejected for API key credentials.

| Scheme | Format | Status |
|--------|--------|--------|
| AnaplanApiKey | `Authorization: AnaplanApiKey auk_<region>_<value>` | **Confirmed accepted** (issue #51) — use this for API key auth |
| AnaplanAuthToken | `Authorization: AnaplanAuthToken <token>` | Rejected (401 FAILURE_INVALID_TOKEN) when used with an API key |
| BearerAuth | `Authorization: Bearer <token>` | Rejected (400 FAILURE_BAD_HEADER) when used with an API key; may work for OAuth service-to-service tokens |

The error message returned when auth fails: `FAILURE_BAD_HEADER: Request header invalid, token or apikey or Oauth service-to-service token is required`. This confirms three distinct auth methods exist; API keys use the `AnaplanApiKey` prefix, not `Bearer`.

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
| `POST /search` | AnaplanApiKey auth accepted | ✓ | 400 FAILURE_BAD_REQUEST (not FAILURE_BAD_HEADER) confirms auth layer accepted key |
| `POST /search` | Bearer prefix rejected for API keys | ✓ | 400 FAILURE_BAD_HEADER confirms Bearer does not work for API key credentials |
| `POST /search` | AnaplanAuthToken prefix rejected | ✓ | 401 FAILURE_INVALID_TOKEN |
| `POST /search` | Search by workspace — response shape | ✗ | Blocked: API key account lacks Tenant Security Admin role (400 FAILURE_BAD_REQUEST) |
| `POST /search` | Search by user — response shape | ✗ | Blocked: API key account lacks Tenant Security Admin role (400 FAILURE_BAD_REQUEST) |
| `PATCH /users/{userGuid}` | Invalid `op` returns 400 | ✓ | Confirmed via live test with `op: "invalid_op"` (issue #51) |

## Blocker: Tenant Security Admin role for API key account

The search contract tests require the API key's account to hold the **Tenant Security Admin** role. Live testing returns `FAILURE_BAD_REQUEST: Invalid request` for both workspace and user search using `ANAPLAN_API_KEY`, indicating the key account lacks this role.

**To unblock:**
1. Grant the account associated with `ANAPLAN_API_KEY` the Tenant Security Admin role in Anaplan.
2. Re-run `uv run --env-file .env pytest tests/test_exception_live.py --live --allow-writes`.

The OAuth service-to-service blocker from issue #51 is now resolved — API keys with the `AnaplanApiKey` prefix are the preferred auth method for this API.

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

- **Apiary documents only AnaplanAuthToken**: Live testing confirmed the Bearer scheme is also accepted. BearerAuth has been added to the spec (issue #51).
- **Bearer requires service-to-service token**: Apiary and the Anaplan auth docs do not explicitly state this constraint. Discovered via live testing — user auth-code tokens are rejected with `FAILURE_BAD_HEADER`.
- **Error response field names unconfirmed**: The spec's `ErrorResponse` schema uses `status` and `message` fields inferred from Apiary. The live 400 response used `status` and `statusMessage`. The spec should be updated once confirmed across both endpoints.
