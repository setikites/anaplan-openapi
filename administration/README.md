# Anaplan Administration API

## Sources

| Source | Available | Notes |
|--------|-----------|-------|
| Apiary docs | — | No Apiary documentation exists for this API |
| Postman collection | — | Not included in the official Anaplan Postman collection |
| Help docs | ✓ | Hand-authored from Anaplan help documentation (issue #119) |
| Live testing | — | Not yet performed |

## Purpose

Bulk user management for an Anaplan tenant. Two endpoints:

- **PUT /users/import** — upload a CSV file to bulk-create or update users
- **GET /users/export** — download all users as a CSV file

## Servers

The Administration API is served from `api.anaplan.com` under the `/admin/1/0` base path — the same host pattern as the Integration, SCIM, ALM, and Exception Users APIs.

The spec currently declares a single production server entry (`https://api.anaplan.com/admin/1/0`). Regional coverage has not been confirmed via live testing. The Exception Users API, which shares the same host and base path, carries 12 server entries (one per distinct regional host). It is likely that the Administration API follows the same regional pattern, but this has not been verified.

**Gap**: Until live testing confirms regional availability, the spec omits the regional server entries. When confirmed, add the same regional entries as the Exception Users API (`us9`, `eu3`, `eu5`, `gb1`, `ca1`, `sg1`, `ae1`, `in1`, `id1`, `au1`).

## Authentication

The API uses `AnaplanAuthToken` — the same scheme as the Integration, Exception Users, and Audit APIs.

| Scheme | Format | Status |
|--------|--------|--------|
| AnaplanAuthToken | `Authorization: AnaplanAuthToken <token>` | Expected (from help docs; not live-tested) |

Tokens are obtained from the Authentication API or via an OAuth Authorization Code flow. Per the pattern established by the Exception Users and Audit APIs, OAuth access tokens should use the `AnaplanAuthToken` prefix rather than `Bearer`.

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

## Discrepancies and Notes

- **No Apiary or Postman source**: This spec was hand-authored from Anaplan help documentation. Confidence is lower than for live-tested APIs.
- **Regional servers unconfirmed**: Only the legacy `api.anaplan.com` host is declared. Regional variants (same pattern as Exception Users API) are likely but unconfirmed.
- **207 response schema**: The `errors` array shape (`{ line, message }`) is inferred from the documentation description; the actual field names have not been confirmed via live testing.
- **Parameter casing**: The help docs specify `Limit` and `Offset` with a capital first letter, which is unusual. This is documented as-is; live testing should verify whether the API is case-sensitive on these names.
