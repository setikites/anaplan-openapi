# Anaplan Administration API

## Sources

| Source | Available | Notes |
|--------|-----------|-------|
| Apiary docs | — | No Apiary documentation exists for this API |
| Postman collection | — | Not included in the official Anaplan Postman collection |
| Help docs | ✓ | Hand-authored from Anaplan help documentation (issue #119) |
| Live testing | Partial | Auth schemes, regional servers, and role-denied behavior confirmed (issue #120, #191). The 200 and 207 paths need an account with the Tenant Administrator role — see Testing Coverage below |

## Purpose

Bulk user management for an Anaplan tenant. Two endpoints:

- **PUT /users/import** — upload a CSV file to bulk-create or update users
- **GET /users/export** — download all users as a CSV file

## Servers

The Administration API is served from the regional `api.anaplan.com` hosts under the `/admin/1/0` base path — the same pattern as the Exception Users API.

Live testing (2026-06-23, issue #120) probed all 12 regional servers from the Exception Users spec. 11/12 responded with `ACCESS_CONTROL_DENIED` (auth accepted, role-check blocked), confirming the Administration API is available across all standard regional hosts. The AU1 host (`au1a.api2.anaplan.com`) returned a connection error and could not be verified — this may be a network routing restriction rather than an API gap.

All 12 server entries are now declared in the spec (matching the Exception Users API).

## Authentication

The API uses `AnaplanAuthToken` — the same scheme as the Integration, Exception Users, and Audit APIs.

| Scheme | Format | Status |
|--------|--------|--------|
| AnaplanAuthToken | `Authorization: AnaplanAuthToken <token>` | ✓ Confirmed (live testing 2026-06-23) |
| Bearer | `Authorization: Bearer <token>` | ✗ Rejected — 401 with empty body; auth layer rejects before the app runs |

Tokens are obtained from the Authentication API or via an OAuth Authorization Code flow. The `AnaplanAuthToken` prefix is required; `Bearer` is not accepted. This was confirmed by probing the same OAuth access_token with both schemes simultaneously — `AnaplanAuthToken` reached the application layer (returned `ACCESS_CONTROL_DENIED` JSON), while `Bearer` was rejected at the auth layer (401 with empty body).

## Endpoints

### PUT /users/import

Upload a CSV file (`multipart/form-data`) to bulk-create or update users. Users are matched by `username` (email address).

**CSV columns**: `username`, `first_name`, `last_name`, `licenses`

**Constraints**:
- At least one data row
- No more than 500 rows
- No duplicate email addresses
- No empty cells
- Multiple licenses must be quoted and comma-separated within the cell

Returns **207 Multi-Status** with `accepted`, `created`, `updated` counts and a `errors` array of `{ line, message }` objects for rejected rows.

### GET /users/export

Downloads all users in the tenant as a CSV file.

**CSV columns**: `username`, `first_name`, `last_name`, `licenses`

Optional query parameters: `Limit` (maximum rows to return) and `Offset` (rows to skip).

## Testing Coverage

Live tests are in `tests/test_administration_live.py` (5 tests). Run them with:

```
uv run --env-file .env pytest tests/test_administration_live.py --live
```

The import test also needs `--allow-writes` and `ADMINISTRATION_EMAIL`. It re-imports one exported user with unchanged values, so the tenant does not change.

| Test | Endpoint | Status |
|------|----------|--------|
| `test_auth_scheme_probe` | `GET /users/export` | ✓ Confirmed — AnaplanAuthToken reaches the application, Bearer gets an empty 401 |
| `test_regional_server_probe` | `GET /users/export` | ✓ Confirmed — 11 of 12 regional hosts respond, `au1a.api2.anaplan.com` unreachable |
| `test_export_users` | `GET /users/export` | ⚠ Warns and returns early without the Tenant Administrator role. The 200 `text/csv` body and its four columns stay unconfirmed |
| `test_user_csv_row` | `GET /users/export` | ⚠ Skips without the Tenant Administrator role or `ADMINISTRATION_EMAIL` |
| `test_import_users` | `PUT /users/import` | ⚠ Skips with `test_user_csv_row`. The 207 body and its `accepted`, `created`, and `updated` counts stay unconfirmed |

The minimum role for both operations is **Tenant Administrator** (`x-anaplan-min-role` in the spec). No account with that role has run the suite yet, so the happy paths of both endpoints remain untested against live data.

## Discrepancies and Notes

- **No Apiary or Postman source**: This spec was hand-authored from Anaplan help documentation. Confidence is lower than for live-tested APIs.
- **AU1 regional server unverified**: `au1a.api2.anaplan.com` returned a connection error during live testing. All other 11 regional servers responded. The AU1 entry is included in the spec (matching the Exception Users API) but its reachability may depend on network routing.
- **207 response schema**: The `errors` array shape (`{ line, message }`) is inferred from the documentation description; the actual field names have not been confirmed via live testing.
- **Parameter casing**: The help docs specify `Limit` and `Offset` with a capital first letter, which is unusual. This is documented as-is; live testing should verify whether the API is case-sensitive on these names.
- **Non-standard role-denied codes**: The spec documents 403 for callers lacking the Tenant Administrator role. Live testing confirmed two different codes depending on token type: a basic-auth token receives 500 `INTERNAL_SERVER_ERROR`; an OAuth access_token receives 401 `ACCESS_CONTROL_DENIED`. In both cases the `AnaplanAuthToken` scheme was accepted — the error originates from the application's role check, not the auth layer. This matches the discrepancy observed on the Integration API's `/workspaces/{workspaceId}/admins`.
- **Bearer scheme not accepted**: Live testing confirmed that `Authorization: Bearer <token>` is rejected at the auth layer with 401 and an empty body. The `AnaplanAuthToken` prefix is required for both basic-auth tokens and OAuth access tokens.
