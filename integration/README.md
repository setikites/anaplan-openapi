# Anaplan Integration API

## Sources

| Source | Location |
|--------|----------|
| Apiary docs | https://anaplan.docs.apiary.io/ (identifier: `anaplan`) |
| Postman collection | `Official Anaplan Collection.postman_collection.json` (repo root and `integration/`) |
| Extracted schemas | `integration/objectSchema.json`, `integration/modelObjectschema.json` |
| OpenAPI spec | `integration/integration-openapi.json` |

## Authentication

The Integration API supports two authentication schemes:

1. **Bearer Token** (standard, RFC 6750)
   ```
   Authorization: Bearer <access_token>
   ```
   Obtain an access token from the OAuth API (`oauth/oauth-openapi.json`).

2. **AnaplanAuthToken** (proprietary)
   ```
   Authorization: AnaplanAuthToken <token>
   ```
   Obtain a token from the Authentication API (`authentication/authentication-openapi.json`).

Both schemes are declared in `securitySchemes` and applied globally. Individual endpoints may restrict which scheme is accepted.

## Regional Server URLs

The Integration API uses `api.anaplan.com` endpoints. Legacy regions (US1, US2, US5, US7, EU1, EU2, EU4, AP1) share the unqualified `api.anaplan.com` base URL. Newer cloud regions have region-prefixed URLs (e.g., `us9.api.anaplan.com`). See the `servers[]` array in the spec for the full list.

## Extracted Schema Files

- **`objectSchema.json`** — Schema extracted from live `/objects/` API response. Documents the structure of Anaplan model objects.
- **`modelObjectschema.json`** — Schema extracted from live model object API response. Used to validate model-level object payloads.

These files were extracted from a live Anaplan instance and represent actual API response shapes.

## Auth Scheme Confirmation

Live testing (`test_auth_scheme_probe`) confirmed both schemes are accepted on `GET /users/me`, `GET /workspaces`, and `GET /models`:

| Scheme | Header format | Confirmed |
|--------|--------------|-----------|
| AnaplanAuthToken | `Authorization: AnaplanAuthToken <token>` | Yes |
| BearerAuth | `Authorization: Bearer <token>` | Yes — Bearer tokens obtained via the Auth API are accepted |

Both schemes are declared as `securitySchemes` and applied via the global `security` array.

## Live Test Harness

```
uv run --env-file .env pytest tests/test_integration_live.py --live
```

Credentials required (cert preferred, basic fallback):

| Variable | Description |
|----------|-------------|
| `ANAPLAN_CA_CERT_PATH` | Path to CA certificate (PEM) |
| `ANAPLAN_CA_KEY_PATH` | Path to private key (PEM) |
| `ANAPLAN_CA_KEY_PASSWORD` | Key password (if encrypted) |
| `ANAPLAN_USERNAME` | Username (basic auth fallback) |
| `ANAPLAN_PASSWORD` | Password (basic auth fallback) |
| `ANAPLAN_API_BASE_URL` | Override base URL (default: `https://api.anaplan.com`) |

Endpoints covered:

| Test | Endpoint |
|------|----------|
| `test_get_current_user` | `GET /2/0/users/me` |
| `test_get_user_by_id` | `GET /2/0/users/{userId}` |
| `test_list_workspaces` | `GET /2/0/workspaces` |
| `test_get_workspace` | `GET /2/0/workspaces/{workspaceId}` |
| `test_list_models` | `GET /2/0/models` |
| `test_get_model` | `GET /2/0/models/{modelId}` |
| `test_list_workspace_models` | `GET /2/0/workspaces/{workspaceId}/models` |
| `test_get_workspace_model` | `GET /2/0/workspaces/{workspaceId}/models/{modelId}` (skipped — 405) |
| `test_auth_scheme_probe` | Probes Bearer vs AnaplanAuthToken on 3 endpoints |

## Discovered Discrepancies

_Document differences between Apiary docs, Postman collection, and live API behavior here as they are discovered._

### `GET /2/0/workspaces/{workspaceId}` returns 404 for non-admins

Live testing shows this endpoint returns `404 Resource not found` even when the workspace appears in `GET /workspaces`. The endpoint likely requires **Workspace Administrator** role. The spec documents both 200 and 404 responses; the live test accepts 404 with a warning rather than failing.

### `PUT /2/0/models/{modelId}/currentPeriod` — date parameter interface (issue #30)

Live testing confirmed `date` is accepted as **either** a query parameter (`?date=YYYY-MM-DD`) **or** a request body field (`{"date": "YYYY-MM-DD"}`), but not both simultaneously. Sending both returns:

```
400: "use query parameter or body to set date, not both"
```

Confirmed 400 error cases:
- Invalid format: `"Invalid ISO date format '{date}'. Date should match format YYYY-MM-DD"`
- Out of range: `"Specified date '{date}' is out of timescale range {start} - {end}"`

The spec declares `date` as a query parameter and documents the 400 response. The request body (`Schema2`) already declared `date` as a body field.

### Workspace-scoped model paths (issue #25)

Two paths absent from the original spec were probed via live testing:

| Path | Status | Finding |
|------|--------|---------|
| `GET /2/0/workspaces/{workspaceId}/models` | **200 OK** | Valid — workspace-filtered model list |
| `GET /2/0/workspaces/{workspaceId}/models/{modelId}` | **405 Method Not Allowed** | Endpoint does not support GET |

**`GET /workspaces/{workspaceId}/models`** is a working endpoint. Its response shape is **identical** to `GET /models` (top-level keys: `meta`, `status`, `models`; model object fields: `id`, `name`, `activeState`, `currentWorkspaceId`, `currentWorkspaceName`, `modelUrl`, `categoryValues`). The only behavioral difference is that results are scoped to the specified workspace. This path has been added to the spec.

**`GET /workspaces/{workspaceId}/models/{modelId}`** returns `405 Method Not Allowed` with body `{"status": {"code": 405, "message": "Method Not Allowed"}, "path": "...", "timestamp": "..."}`. This is not a permissions issue (unlike the 404 on `GET /workspaces/{workspaceId}`) — the method simply does not exist on this path. Use `GET /2/0/models/{modelId}` for model detail lookups. This path is not added to the spec.

### Response key naming (confirmed via live tests)

- `GET /users/me` and `GET /users/{userId}`: response key is `user` (singular object) ✓
- `GET /workspaces`: response key is `workspaces` (array) ✓
- `GET /models`: response key is `models` (array) ✓
- `GET /models/{modelId}`: response key is `model` (singular object) ✓
- `GET /workspaces/{workspaceId}/models`: response key is `models` (array), identical shape to `GET /models` ✓
- `GET /workspaces/{workspaceId}`: not confirmed (returns 404 — see above)
