# Anaplan Integration API

## Sources

| Source | Location |
|--------|----------|
| Apiary docs | https://anaplan.docs.apiary.io/ (identifier: `anaplan`) |
| Postman collection | `sources/Official Anaplan Collection.postman_collection.json` |
| Extracted schemas | `sources/integration/objectSchema.json`, `sources/integration/modelObjectschema.json` |
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

### Legacy Endpoint Retirement

Anaplan previously served the Integration API at `https://us1a.app.anaplan.com/2` (and equivalent region-prefixed `app.anaplan.com/2` URLs). **These endpoints have been retired.** The modern `https://api.anaplan.com` endpoint (and its regional variants) is the sole supported base URL. The spec's `servers[]` array contains only modern `api.anaplan.com` entries.

## Extracted Schema Files

- **`sources/integration/objectSchema.json`** — Schema extracted from live `/objects/` API response. Documents the structure of Anaplan model objects.
- **`sources/integration/modelObjectschema.json`** — Schema extracted from live model object API response. Used to validate model-level object payloads.

These files were extracted from a live Anaplan instance and represent actual API response shapes.

## Auth Scheme Confirmation

Live testing (`test_auth_scheme_probe`) confirmed both schemes are accepted on `GET /users/me`, `GET /workspaces`, and `GET /models`:

| Scheme | Header format | Confirmed |
|--------|--------------|-----------|
| AnaplanAuthToken | `Authorization: AnaplanAuthToken <token>` | Yes |
| BearerAuth | `Authorization: Bearer <token>` | Yes — Bearer tokens obtained via the Auth API are accepted |

Both schemes are declared as `securitySchemes` and applied via the global `security` array.

## Live Test Coverage

Setup and how to run live tests (credentials, `.env`, flags) are documented in
[docs/TESTING.md](../docs/TESTING.md). The suite for this API is
`tests/test_integration_live.py`.

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
| `test_list_versions` | `GET /2/0/models/{modelId}/versions` |
| `test_get_workspace_current_period` | `GET /2/0/workspaces/{workspaceId}/models/{modelId}/currentPeriod` |
| `test_get_model_current_period` | `GET /2/0/models/{modelId}/currentPeriod` |
| `test_get_model_calendar` | `GET /2/0/workspaces/{workspaceId}/models/{modelId}/modelCalendar` |
| `test_get_fiscal_year` | `GET /2/0/models/{modelId}/modelCalendar/fiscalYear` (warns — 405) |
| `test_switchover_invalid_date_returns_400` | `PUT /2/0/models/{modelId}/versions/{versionId}/switchover` (guarded — requires `--allow-writes`) |

## Modern Endpoint Validation (post-legacy retirement)

The live suite was run against `https://api.anaplan.com` (2026-06-04), confirming
the modern endpoint is fully operational after retirement of the legacy
`app.anaplan.com/2` URLs. No regressions were detected.

Expected skips:
- `test_get_workspace_model` — `GET /workspaces/{workspaceId}/models/{modelId}` returns 405; endpoint is not implemented (documented below)
- `test_current_period_invalid_date_*_returns_400` — PUT blocked by the write-guard unless `--allow-writes` is passed (non-destructive by design)

## Discovered Discrepancies

_Document differences between Apiary docs, Postman collection, and live API behavior here as they are discovered._

### `GET /2/0/workspaces/{workspaceId}` returns 404 for non-admins

Live testing shows this endpoint returns `404 Resource not found` even when the workspace appears in `GET /workspaces`. The endpoint likely requires **Workspace Administrator** role. The spec documents both 200 and 404 responses; the live test accepts 404 with a warning rather than failing.

### `pages` and `sort` query parameters (issue #31)

**`pages` on `GET /2/0/models/{modelId}/views/{viewId}/data`**

Live testing confirmed the `pages` parameter is accepted and returns 200 with a `text/csv` response (when `format=v1` is used). Both multi-value forms work:
- Repeated-key form: `?pages=dimId:itemId&pages=dimId2:itemId2`
- Comma-separated form: `?pages=dimId:itemId,dimId2:itemId2`

Key findings:
- Valid page selectors must correspond to dimensions on the *pages axis* of the view (not rows or columns). Use `GET /2/0/models/{modelId}/views/{viewId}` to identify row/column axes; any model dimension not on those axes may be a page dimension.
- Dimension items must be fetched from `GET /2/0/workspaces/{workspaceId}/models/{modelId}/dimensions/{dimensionId}/items`, not from the view-scoped `GET /models/{modelId}/views/{viewId}/dimensions/{dimensionId}/items` endpoint (the latter returns items usable for row/column navigation, not page selectors).
- Supplying a dimension ID that is not a page-axis dimension for the given view returns `400: "Invalid page selector [{dimensionId}]"`.
- Spec models `pages` as `style: form, explode: true` (repeated-key canonical form; comma-separated also accepted).

**`sort` on task list endpoints**

Live testing confirmed the following on all four task list endpoints (imports, exports, processes, actions):

| Sort value | Status |
|-----------|--------|
| `creationDate`, `-creationDate`, `+creationDate` | 200 |
| `taskId`, `-taskId`, `+taskId` | 200 |
| `taskState`, `-taskState`, `+taskState` | 200 |
| `progress`, `-progress`, `+progress` | 200 |
| `invalid_field`, `-invalid_field` | 200 |

Format: `[prefix]field` where prefix is `-` (descending), `+` (ascending), or omitted (ascending). The API does not validate the field name — unknown fields also return 200 and appear to fall back to default ordering. Actual sort ordering could not be verified because the test model's task lists were empty at the time of testing.

### `PUT /2/0/models/{modelId}/currentPeriod` — date parameter interface (issue #30)

Live testing confirmed `date` is accepted as **either** a query parameter (`?date=YYYY-MM-DD`) **or** a request body field (`{"date": "YYYY-MM-DD"}`), but not both simultaneously. Sending both returns:

```
400: "use query parameter or body to set date, not both"
```

Confirmed 400 error cases:
- Invalid format: `"Invalid ISO date format '{date}'. Date should match format YYYY-MM-DD"`
- Out of range: `"Specified date '{date}' is out of timescale range {start} - {end}"`

The spec declares `date` as a query parameter and documents the 400 response. The request body (`Schema2`) already declared `date` as a body field.

### `GET /2/0/models/{modelId}/modelCalendar/fiscalYear` returns 405

Live testing confirmed this path only supports `PUT` (update fiscal year). `GET` returns `405 Method Not Allowed`. Fiscal year data is available via `GET /2/0/workspaces/{workspaceId}/models/{modelId}/modelCalendar`, which returns the full `modelCalendar` object including `fiscalYear`. The spec retains only `PUT` on this path.

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

## ADR 0003 Description Sweep (issue #90)

Applied ADR 0003 description standards to `integration-openapi.json` (2026-06-18).

**Removed** tautological schema-level descriptions (`"user"`, `"model"`, `"workspace"`, etc.) and tautological property descriptions that literally copy the field name (e.g. `User.id: "id"`, `Model.name: "name"`).

**Fixed** incorrect schema descriptions on `ListReadRequest` and `ViewReadRequest`, which incorrectly said "A task tracking the execution of a export" — these schemas track list/view read operations, not exports.

**Added** descriptions to:
- `Status` and `Meta` schemas (envelope names alone do not convey their purpose)
- `ModelCalendar.calendarType` and `extraWeekMonth` (calendar model type and 4-4-5 extra week placement are non-obvious)
- `Version.isActual` and `isCurrent` (actual-vs-forecast and current-version semantics)
- `File.firstDataRow`, `headerRow`, `origin` (row indexing and source type require context)
- `Task.result` (conditionally absent until terminal state — non-obvious from name alone)
- `TaskResult.failureDumpAvailable`, `objectId`, `objectName` (dump availability and which object was processed)
- `Meta.schema` (a URL, not a JSON Schema object)
- `Status.code` and `message` (Anaplan-specific code distinct from HTTP status)

**Fixed** encoding: `Task.progress` description had a mojibaked en-dash (`â€"` → `–`).
