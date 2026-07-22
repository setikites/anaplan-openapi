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

## Pagination

List endpoints accept `offset` and `limit` query parameters and return paging
state in `meta.paging`. The spec originally declared neither the params nor the
full paging schema; both were added from live testing (issue #220).

Live-tested against `GET /models` (cert auth, 3847-model tenant, 2026-07-08):

| Query | Rows returned | `meta.paging` |
|-------|:-:|--------|
| (none) | 3847 | `offset=0`, `next=?limit=20&offset=20` |
| `?limit=2` | 2 | `offset=0`, `next=?limit=2&offset=2` |
| `?limit=2&offset=2` | 2 | `offset=2`, `previous=?limit=2&offset=0`, `next=?limit=2&offset=4` |
| `?limit=3&offset=0` | 3 | `offset=0`, `next=?limit=3&offset=3` |

Confirmed behavior:

- **Both params are honored** — `limit` bounds the page, `offset` skips rows.
- The server **echoes** the applied `limit`/`offset` in the `next` (and, once
  `offset > 0`, `previous`) URLs, so a client can page by following those URLs
  without constructing them.
- `meta.paging` carries `currentPageSize`, `totalSize`, `offset`, `next`, and
  `previous`. `previous` appears only past the first page.
- **Default page size is 5000** when `limit` is omitted. This tenant's 3847
  models fit under the cap and all returned; the larger tenant in issue #220
  (7370 models) was truncated to 5000 with a `next` URL for the remainder.

`offset`/`limit` are documented on the 39 GET list endpoints whose response
carries `meta.paging`. They are **not** added to the `.../dimensions/{dimensionId}/items`
bulk reads (documented "returns all", hard 1,000,000-item cap, no paging), the
`/views/{viewId}` axis-metadata reads (single object, not a collection), or the
list-item write endpoints.

## Live Test Coverage

Setup and how to run live tests (credentials, `.env`, flags) are documented in
[docs/TESTING.md](../docs/TESTING.md). The suite for this API is
`tests/test_integration_live.py`.

Endpoints covered (all paths relative to the `/2/0` base URL):

| Test | Endpoint |
|------|----------|
| `test_get_current_user` | `GET /users/me` |
| `test_get_user_by_id` | `GET /users/{userId}` |
| `test_list_workspaces` | `GET /workspaces` |
| `test_get_workspace` | `GET /workspaces/{workspaceId}` |
| `test_get_workspace_admins` | `GET /workspaces/{workspaceId}/admins` (warns — 500 without tenant admin privilege) |
| `test_get_workspace_visitors` | `GET /workspaces/{workspaceId}/visitors` (warns — 500 without tenant admin privilege) |
| `test_list_models` | `GET /models` |
| `test_models_pagination` | `GET /models?limit=&offset=` (offset/limit paging — issue #220) |
| `test_get_model` | `GET /models/{modelId}` |
| `test_list_workspace_models` | `GET /workspaces/{workspaceId}/models` |
| `test_get_workspace_model` | `GET /workspaces/{workspaceId}/models/{modelId}` (skipped — 405) |
| `test_auth_scheme_probe` | Probes Bearer vs AnaplanAuthToken on 3 endpoints |
| `test_list_modules` | `GET /models/{modelId}/modules` |
| `test_list_module_line_items` | `GET /models/{modelId}/modules/{moduleId}/lineItems` |
| `test_list_module_views` | `GET /models/{modelId}/modules/{moduleId}/views` |
| `test_list_model_views` | `GET /workspaces/{workspaceId}/models/{modelId}/views` |
| `test_get_view` | `GET /models/{modelId}/views/{viewId}` |
| `test_list_model_line_items` | `GET /models/{modelId}/lineItems` |
| `test_list_line_item_dimensions` | `GET /models/{modelId}/lineItems/{lineItemId}/dimensions` |
| `test_list_line_item_dimension_items` | `GET /models/{modelId}/lineItems/{lineItemId}/dimensions/{dimensionId}/items` |
| `test_list_view_dimension_items` | `GET /models/{modelId}/views/{viewId}/dimensions/{dimensionId}/items` |
| `test_list_workspace_dimension_items` | `GET /workspaces/{workspaceId}/models/{modelId}/dimensions/{dimensionId}/items` |
| `test_list_lists` | `GET /workspaces/{workspaceId}/models/{modelId}/lists` |
| `test_get_list` | `GET /workspaces/{workspaceId}/models/{modelId}/lists/{listId}` |
| `test_get_list_items` | `GET /workspaces/{workspaceId}/models/{modelId}/lists/{listId}/items` |
| `test_post_and_put_list_items` | `POST` + `PUT /workspaces/{workspaceId}/models/{modelId}/lists/{listId}/items` (write-guarded) |
| `test_list_versions` | `GET /models/{modelId}/versions` |
| `test_get_workspace_current_period` | `GET /workspaces/{workspaceId}/models/{modelId}/currentPeriod` |
| `test_get_model_current_period` | `GET /models/{modelId}/currentPeriod` |
| `test_get_model_calendar` | `GET /workspaces/{workspaceId}/models/{modelId}/modelCalendar` |
| `test_get_fiscal_year` | `GET /models/{modelId}/modelCalendar/fiscalYear` (warns — 405) |
| `test_switchover_invalid_date_returns_400` | `PUT /models/{modelId}/versions/{versionId}/switchover` (write-guarded) |
| `test_view_data_csv` | `GET /models/{modelId}/views/{viewId}/data` (default: `text/csv`) |
| `test_view_data_json` | `GET /models/{modelId}/views/{viewId}/data?format=v1` (`Accept: application/json`) |
| `test_view_read_request_lifecycle` | `POST` / `GET` / `DELETE /workspaces/{workspaceId}/models/{modelId}/views/{viewId}/readRequests` (write-guarded) |
| `test_list_model_files` | `GET /models/{modelId}/files` |
| `test_download_file_content` | `GET /workspaces/{workspaceId}/models/{modelId}/files/{fileId}` (200+octet-stream, or 404 when `chunkCount` is 0) |
| `test_list_file_chunks` | `GET /workspaces/{workspaceId}/models/{modelId}/files/{fileId}/chunks` |
| `test_download_first_chunk` | `GET /workspaces/{workspaceId}/models/{modelId}/files/{fileId}/chunks/0` (skips when no content) |
| `test_upload_single_chunk` | `PUT /workspaces/{workspaceId}/models/{modelId}/files/{fileId}` + `DELETE` (write-guarded) |
| `test_upload_and_complete_cycle` | `POST` (set chunk count) + `PUT /chunks/0` + `POST /complete` (write-guarded) |
| `test_run_process_and_poll_task` | `POST /workspaces/{workspaceId}/models/{modelId}/processes/{processId}/tasks` + `GET .../tasks/{taskId}` (write-guarded) |
| `test_run_action_and_poll_task` | `POST /workspaces/{workspaceId}/models/{modelId}/actions/{actionId}/tasks` + `GET .../tasks/{taskId}` (write-guarded) |
| `test_export_import_cycle` | Full export → download → stage → import cycle (write-guarded; see details below) |
| `test_model_direct_list_actions` | `GET /models/{modelId}/actions` (model-direct form — issue #28) |
| `test_model_direct_list_imports` | `GET /models/{modelId}/imports` (model-direct form — issue #28) |
| `test_model_direct_list_exports` | `GET /models/{modelId}/exports` (model-direct form — issue #28) |
| `test_model_direct_list_processes` | `GET /models/{modelId}/processes` (model-direct form — issue #28) |
| `test_model_direct_get_export_metadata` | `GET /models/{modelId}/exports/{exportId}` (model-direct form — issue #28) |
| `test_model_direct_get_import_metadata` | `GET /models/{modelId}/imports/{importId}` (model-direct form — issue #28) |
| `test_workspace_prefixed_get_process_detail` | `GET /workspaces/{workspaceId}/models/{modelId}/processes/{processId}` (workspace form — issue #28) |
| `test_path_duality[files-list]` | `GET /workspaces/{workspaceId}/models/{modelId}/files` (workspace form — issue #27) |
| `test_path_duality[versions]` | `GET /workspaces/{workspaceId}/models/{modelId}/versions` (workspace form — issue #27) |
| `test_path_duality[file-chunks]` | `GET /models/{modelId}/files/{fileId}/chunks` (model-direct form — issue #27) |
| `test_path_duality[modelCalendar]` | `GET /models/{modelId}/modelCalendar` (model-direct form — issue #27) |

## Modern Endpoint Validation (post-legacy retirement)

The live suite was run against `https://api.anaplan.com` (2026-06-04), confirming
the modern endpoint is fully operational after retirement of the legacy
`app.anaplan.com/2` URLs. No regressions were detected.

Expected skips:
- `test_get_workspace_model` — `GET /workspaces/{workspaceId}/models/{modelId}` returns 405; endpoint is not implemented (documented below)
- `test_current_period_invalid_date_*_returns_400` — PUT blocked by the write-guard unless `--allow-writes` is passed (non-destructive by design)

## Discovered Discrepancies

_Document differences between Apiary docs, Postman collection, and live API behavior here as they are discovered._

### NO ACCESS model role is masked as `404` (issue #225)

Live testing with a certificate principal holding the **NO ACCESS** role on model
`EBP Request DEV` confirmed that Anaplan returns `404 Not Found` — never `403` — from
model-scoped operations, so that the existence of an unreachable model is not confirmed
to the caller. All 66 model-scoped `GET` operations in this spec were probed:

- **61 returned `404`** with the `{ status, path, timestamp }` error envelope
  (`components/schemas/ErrorResponse`). These now declare
  `components/responses/NotFoundOrNoAccess`.
- **`GET /models/{modelId}` returned `200`** with full metadata (name, `activeState`,
  workspace). The model also remained listed by `GET /workspaces/{workspaceId}/models`,
  though it was absent from the tenant-wide `GET /models` listing for this principal.
  Whether it appears there varies — the issue reporter observed the opposite.
- **The four task-list endpoints returned `200` with an empty list**
  (`.../actions|exports|imports|processes/{id}/tasks`). They neither mask as `404` nor
  confirm the parent object exists; a fabricated parent ID against a *reachable* model
  behaves the same way. These deliberately do **not** declare a `404`.

For 18 of the sub-resource paths the masking is directly provable: a fabricated child ID
against a reachable model returns `200` (or `500` for `imports/{importId}`) while the same
request against the NO ACCESS model returns `404`. For the remaining sub-resource paths
both arms return `404`, so the 404 is consistent with the masking but not independently
distinguishable from a genuinely missing child.

Non-`GET` model-scoped operations are **not** live-verified — the live-test harness blocks
writes to `api.anaplan.com` without `--allow-writes`. They declare the same `404` by
inference from the read behaviour.

### `Admin` and `Visitor` schema email regex is over-escaped

The `email` property on both `Admin` and `Visitor` uses the pattern inherited verbatim from `sources/integration/objectSchema.json`:

```
^[_A-Za-z0-9-\\+]+(\.[_A-Za-z0-9-]+)*@[A-Za-z0-9-]+(\.[A-Za-z0-9]+)*(\.[A-Za-z]{2,})$
```

After JSON double-escaping, the decoded regex pattern contains `\\.` (two characters: backslash + dot) where `\.` (escaped dot = literal dot) was almost certainly intended. In Python's `re` module, `\\.` means "literal backslash followed by any character" rather than "literal dot", making the pattern reject standard emails like `user.name@example.com`. The pattern is retained as-is to preserve fidelity to the source schema; inline examples in the spec omit the `email` field to avoid failing the example/schema contract test.

### `GET .../files/{fileId}` returns file content, not metadata (issues #111, #228)

The spec originally documented this endpoint as "Get file metadata" returning a `{meta, status, file}` JSON envelope. It does not. Live testing on 2026-07-21 swept every file in two models (58 and 215 files) with two principals:

- Files with `chunkCount` >= 1 return **200 `application/octet-stream`** carrying the raw file body. Verified against a 452,495-byte CSV; the bytes were identical to the single chunk fetched from `.../files/{fileId}/chunks/0`.
- Files with `chunkCount` of 0 return **404** — every one of them, for both principals, including for the account that could read the file with content in the same model. The discriminator is content presence, not only role.
- The media type is `application/octet-stream` even for a `.csv` file whose listed `format` is `txt`. The server does not negotiate `text/csv` here.

Per-file metadata is only available from the file list endpoint `GET /models/{modelId}/files`.

A NO ACCESS role on the model also produces 404 (see the NO ACCESS masking section), so a 404 alone does not distinguish "no such file", "no content", and "no access".

### `GET /workspaces/{workspaceId}` returns 404 for non-admins

Live testing shows this endpoint returns `404 Resource not found` even when the workspace appears in `GET /workspaces`. The endpoint likely requires **Workspace Administrator** role. The spec documents both 200 and 404 responses; the live test accepts 404 with a warning rather than failing.

### `pages` and `sort` query parameters (issue #31)

**`pages` on `GET /models/{modelId}/views/{viewId}/data`**

Live testing confirmed the `pages` parameter is accepted and returns 200 with a `text/csv` response (when `format=v1` is used). Both multi-value forms work:
- Repeated-key form: `?pages=dimId:itemId&pages=dimId2:itemId2`
- Comma-separated form: `?pages=dimId:itemId,dimId2:itemId2`

Key findings:
- Valid page selectors must correspond to dimensions on the *pages axis* of the view (not rows or columns). Use `GET /models/{modelId}/views/{viewId}` to identify row/column axes; any model dimension not on those axes may be a page dimension.
- Dimension items must be fetched from `GET /workspaces/{workspaceId}/models/{modelId}/dimensions/{dimensionId}/items`, not from the view-scoped `GET /models/{modelId}/views/{viewId}/dimensions/{dimensionId}/items` endpoint (the latter returns items usable for row/column navigation, not page selectors).
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

### `sort` on generic list endpoints (issue #161)

Live testing against a populated tenant revealed **two distinct `sort` behaviors** across the generic (non-task) list endpoints. Ordering was verified by comparing the returned ID sequence under `+field` against `-field`.

**Class 1 — top-level collections: `/models`, `/users`, `/workspaces`.** The field name **is** validated and the prefix **is mandatory**:

- A bare field name (no `+`/`-`) returns `400 "Bad sort order format: '<field>'. Please follow (-){column_name_1},(+){column_name_2}.. format"`.
- An unknown field returns `400 "Failed to parse sort parameter"`.
- Multiple comma-separated columns are accepted.

Confirmed sortable fields (every other response property tested returned 400, including `id`):

| Endpoint | Sortable fields |
|----------|-----------------|
| `GET /models` | `name`, `activeState` |
| `GET /users` | `firstName`, `lastName`, `email`, `active`, `lastLoginDate` |
| `GET /workspaces` | `name`, `sizeAllowance` |

**Class 2 — model resource lists: `/models/{modelId}/files`, `.../actions`, `.../imports`, `.../exports`, `.../processes`** (and their `/workspaces/{workspaceId}/...` forms). These behave exactly like the task-list endpoints above: the field name is **not** validated (unknown fields, e.g. `+zzzNoSuchField`, return 200 and fall back to default ordering), the prefix is optional (omitted = ascending), and comma-separated columns are accepted. `name` and `id` were observed to genuinely re-order results. Because field names are not validated, no definitive sortable-field list exists; the spec documents the no-validation behavior instead.

`/workspaces/{workspaceId}/models` declares no `sort` parameter (unlike `/models`).

### `PUT /models/{modelId}/currentPeriod` — date parameter interface (issue #30)

Live testing confirmed `date` is accepted as **either** a query parameter (`?date=YYYY-MM-DD`) **or** a request body field (`{"date": "YYYY-MM-DD"}`), but not both simultaneously. Sending both returns:

```
400: "use query parameter or body to set date, not both"
```

Confirmed 400 error cases:
- Invalid format: `"Invalid ISO date format '{date}'. Date should match format YYYY-MM-DD"`
- Out of range: `"Specified date '{date}' is out of timescale range {start} - {end}"`

The spec declares `date` as a query parameter and documents the 400 response. The request body (`Schema2`) already declared `date` as a body field.

### `GET /models/{modelId}/modelCalendar/fiscalYear` returns 405

Live testing confirmed this path only supports `PUT` (update fiscal year). `GET` returns `405 Method Not Allowed`. Fiscal year data is available via `GET /workspaces/{workspaceId}/models/{modelId}/modelCalendar`, which returns the full `modelCalendar` object including `fiscalYear`. The spec retains only `PUT` on this path.

### Files, versions, and calendar GET path duality (issue #27)

Probed 2026-06-25 with live credentials using `WORKSPACE_ID=8a868cd885f53bd201860f5a4fea1ff1` and `MODEL_ID=09F86E3942A84353892853BE3BE82280`.

**Confirmed valid (200 OK — identical response shape):**

| Baseline form | Alternate form | Status |
|---------------|----------------|--------|
| `GET /models/{modelId}/files` | `GET /workspaces/{workspaceId}/models/{modelId}/files` | **200 OK** — identical `files` array response |
| `GET /models/{modelId}/versions` | `GET /workspaces/{workspaceId}/models/{modelId}/versions` | **200 OK** — identical `versionMetadata` array response |
| `GET /workspaces/{workspaceId}/models/{modelId}/files/{fileId}/chunks` | `GET /models/{modelId}/files/{fileId}/chunks` | **200 OK** — identical `chunks` array response (key omitted when `chunkCount` is 0) |
| `GET /workspaces/{workspaceId}/models/{modelId}/modelCalendar` | `GET /models/{modelId}/modelCalendar` | **200 OK** — identical `modelCalendar` object response |

All 4 valid paths have been added to `integration-openapi.json`.

**Not added (invalid or unconfirmed):**

| Probe | Result | Notes |
|-------|--------|-------|
| `GET /workspaces/{workspaceId}/models/{modelId}/views/{viewId}/data` | **500** | Server error for the probed view (module default view with no data). Both baseline and alternate returned 500 — path likely exists but 200 response shape could not be confirmed. Not added to spec. |
| `GET /workspaces/{workspaceId}/models/{modelId}/modules/{moduleId}/data` | **405** | Only `POST` is supported on this path; `GET` is not valid on either form. Not added. |
| `GET /workspaces/{workspaceId}/models/{modelId}/modelCalendar/fiscalYear` | **405** | Only `PUT` is supported (see above). Not added. |
| `GET /models/{modelId}/files/{fileId}` | **200** | Re-probed 2026-07-21 against a file with content: the model-direct form returns the same 200 `application/octet-stream` body as the workspace-prefixed form, byte for byte. The earlier 404 came from probing files with `chunkCount` of 0. Path duality is confirmed; adding the model-direct path to the spec is tracked separately. |

### Action/import/export/process GET path duality (issue #28)

Probed 2026-06-25 with live credentials. All 7 alternate-form GETs returned **200 OK** with response shapes identical to their counterpart form.

**Listing endpoints** — model-direct forms confirmed valid:

| Workspace form | Model-direct form | Status |
|----------------|-------------------|--------|
| `GET /workspaces/{workspaceId}/models/{modelId}/actions` | `GET /models/{modelId}/actions` | **200 OK** — identical response shape (`actions` array) |
| `GET /workspaces/{workspaceId}/models/{modelId}/imports` | `GET /models/{modelId}/imports` | **200 OK** — identical response shape (`imports` array) |
| `GET /workspaces/{workspaceId}/models/{modelId}/exports` | `GET /models/{modelId}/exports` | **200 OK** — identical response shape (`exports` array) |
| `GET /workspaces/{workspaceId}/models/{modelId}/processes` | `GET /models/{modelId}/processes` | **200 OK** — identical response shape (`processes` array) |

**Individual-resource GETs** — both forms confirmed valid:

| Model-direct form | Workspace form | Status |
|-------------------|----------------|--------|
| `GET /models/{modelId}/exports/{exportId}` | `GET /workspaces/{workspaceId}/models/{modelId}/exports/{exportId}` | **200 OK** — identical `exportMetadata` response |
| `GET /models/{modelId}/imports/{importId}` | `GET /workspaces/{workspaceId}/models/{modelId}/imports/{importId}` | **200 OK** — identical `importMetadata` response |
| `GET /models/{modelId}/processes/{processId}` | `GET /workspaces/{workspaceId}/models/{modelId}/processes/{processId}` | **200 OK** — identical `processMetadata` response |

All 7 new paths have been added to `integration/integration-openapi.json`.

### Workspace-scoped model paths (issue #25)

Two paths absent from the original spec were probed via live testing:

| Path | Status | Finding |
|------|--------|---------|
| `GET /workspaces/{workspaceId}/models` | **200 OK** | Valid — workspace-filtered model list |
| `GET /workspaces/{workspaceId}/models/{modelId}` | **405 Method Not Allowed** | Endpoint does not support GET |

**`GET /workspaces/{workspaceId}/models`** is a working endpoint. Its response shape is **identical** to `GET /models` (top-level keys: `meta`, `status`, `models`; model object fields: `id`, `name`, `activeState`, `currentWorkspaceId`, `currentWorkspaceName`, `modelUrl`, `categoryValues`). The only behavioral difference is that results are scoped to the specified workspace. This path has been added to the spec.

**`GET /workspaces/{workspaceId}/models/{modelId}`** returns `405 Method Not Allowed` with body `{"status": {"code": 405, "message": "Method Not Allowed"}, "path": "...", "timestamp": "..."}`. This is not a permissions issue (unlike the 404 on `GET /workspaces/{workspaceId}`) — the method simply does not exist on this path. Use `GET /models/{modelId}` for model detail lookups. This path is not added to the spec.

### Response key naming (confirmed via live tests)

- `GET /users/me` and `GET /users/{userId}`: response key is `user` (singular object) ✓
- `GET /workspaces`: response key is `workspaces` (array) ✓
- `GET /models`: response key is `models` (array) ✓
- `GET /models/{modelId}`: response key is `model` (singular object) ✓
- `GET /workspaces/{workspaceId}/models`: response key is `models` (array), identical shape to `GET /models` ✓
- `GET /workspaces/{workspaceId}`: not confirmed (returns 404 — see above)

### Empty collections omit their key (issue #234)

Several list endpoints drop the collection key entirely on a `200` rather than returning an empty
array. Consumers must treat the key as optional.

| Endpoint | Key | Omitted when |
|----------|-----|--------------|
| `GET .../dimensions/{dimensionId}/items` (all five path forms) | `items` | The dimension has no items |
| `GET .../files/{fileId}/chunks` | `chunks` | `chunkCount` is `0` |
| `POST/PUT .../lists/{listId}/items` | `failures` | No per-item errors (see [List item write response schemas](#list-item-write-response-schemas-issue-109)) |
| `POST /workspaces/{workspaceId}/bulkDeleteModels` | `bulkDeleteModelsFailures` | All models deleted |

Confirmed live 2026-07-21 against dimension `101000000055` (list "UAM Bulk Upload Users", empty).
Both the model-scoped and line-item-scoped forms returned, byte for byte:

```json
{
  "meta" : { "schema" : "https://api.anaplan.com/2/0/objects/dimension" },
  "status" : { "code" : 200, "message" : "Success" }
}
```

No `items` key and no `meta.paging`. None of the affected spec schemas mark the collection as
`required`, so the specs already permit this shape; the operation descriptions now state it
explicitly.

### View data response formats (issue #110)

**`GET /models/{modelId}/views/{viewId}/data`** supports two response formats:

| Request | Response content-type | Shape |
|---------|----------------------|-------|
| No `format` param (default) | `text/csv` | Raw CSV rows |
| `?format=v1` + `Accept: application/json` | `application/json` | `{columnCoordinates, rows:[{rowCoordinates, cells}]}` |

The JSON format (`format=v1`) returns a `ViewData` object with:
- `columnCoordinates` — array of column dimension item identifiers
- `rows` — array of row objects, each with `rowCoordinates` and `cells`

### View read-request lifecycle (issue #110)

**`POST /workspaces/{workspaceId}/models/{modelId}/views/{viewId}/readRequests`** initiates an async read:
- Returns 200 with `{requestId, requestState, ...}`
- Poll `GET .../readRequests/{requestId}` until `requestState == "COMPLETE"`
- Download pages via `GET .../readRequests/{requestId}/pages/{pageNo}` — returns `text/csv`
- **`DELETE .../readRequests/{requestId}`** returns **200** with `{meta, status, viewReadRequest}` where `viewReadRequest.requestState` is `"CANCELLED"` or `"COMPLETE"`

Note: `POST /complete` (mark multi-chunk upload complete) returns **500** for standard Integration API users on the test model. Set chunk count, PUT chunk, and GET chunks all succeed. This is a known limitation of the test account.

### List item write response schemas (issue #109)

**`POST /workspaces/{workspaceId}/models/{modelId}/lists/{listId}/items`** returns:
```json
{
  "meta": {...},
  "status": {...},
  "added": 2,
  "ignored": 0,
  "total": 2,
  "failures": []
}
```

**`PUT /workspaces/{workspaceId}/models/{modelId}/lists/{listId}/items`** returns:
```json
{
  "meta": {...},
  "status": {...},
  "updated": 2,
  "ignored": 0,
  "total": 2
}
```

Key findings:
- The `failures` key is **omitted entirely** when there are no per-item errors (not present as an empty list).
- When present, each failure object contains `requestIndex`, `failureType`, and `failureMessageDetails`.
- PUT does not include a `failures` key in its response (only POST does).

### Action execution and task polling (issue #18)

`GET /workspaces/{workspaceId}/models/{modelId}/actions/{actionId}/tasks/{taskId}` was the only endpoint missing from the issue list; it has been added to the spec.

Terminal task states: `COMPLETE`, `CANCELLED`, `CANCELLING`. Completed tasks always include a `result` object with a `successful` boolean field.

### Export → import cycle (issue #18)

**Export output file ID equals the export action ID.** When an export runs, the output is written to a file whose ID matches `INTEGRATION_EXPORT`. Download chunks from `GET /files/{INTEGRATION_EXPORT}/chunks/{chunkId}`, not from `INTEGRATION_FILE`.

Full cycle confirmed:
1. `POST /exports/{exportId}/tasks` → poll to `COMPLETE`
2. `GET /files/{exportId}/chunks` → download each chunk
3. `PUT /files/{fileId}` (single-chunk) → stage for import (uses `INTEGRATION_FILE`)
4. `POST /imports/{importId}/tasks` → poll to `COMPLETE`
5. Probe dump endpoints: `GET /imports/{importId}/tasks/{taskId}/dump` returns 200/204/404; `GET .../dump/chunks` returns 200/400/404 depending on whether `failureDumpAvailable` is true.

### Linking an import to its source file

Each import in `GET /workspaces/{workspaceId}/models/{modelId}/imports/` carries an `importDataSourceId`. When the import's source is an **uploaded file**, `importDataSourceId` is that file's id (prefix `113`) — match it to an `id` from `GET .../files`. This is the binding between the file you upload and the import that loads it: upload to the file whose id equals `importDataSourceId`, then run that import via `POST .../imports/{importId}/tasks`. This is the primary reason to upload a file, so `importDataSourceId` is documented as a source for the `fileId` path parameter.

Imports sourced from another model, list, or saved view instead carry a non-file `importDataSourceId` and populate the nested `importDataSource` object (`sourceModelId`, `sourceWorkspaceId`, …). Only file-sourced imports (`importDataSourceId` prefix `113`) correspond to an upload.

### File management response shapes (issue #111)

Live probe results for `INTEGRATION_FILE` (`113000001109`, Users.csv):

| Endpoint | Method | Response |
|----------|--------|----------|
| `/workspaces/{wid}/models/{mid}/files/{fileId}` | `PUT` | **204 No Content** |
| `/workspaces/{wid}/models/{mid}/files/{fileId}` | `DELETE` | **204 No Content** |
| `/workspaces/{wid}/models/{mid}/files/{fileId}/chunks/0` | `GET` | **200 `application/octet-stream`** |

`INTEGRATION_FILE` is an import source file. After `DELETE` teardown in write tests, the file has no content. The `chunkCount` field in the model-level file list (`GET /models/{modelId}/files`) may still show a non-zero value after DELETE (stale metadata), while `GET /chunks/0` returns 404. `test_download_first_chunk` handles this with a skip.

### Open-question resolutions (issue #145)

Decisions resolving review questions that block #147/#148. Several were already
answered by prior live probes — cross-referenced rather than re-derived.

- **ID types are `string`, always** (Q1/Q2). Every Anaplan ID is an opaque
  identifier — 32-char hex or 12/13-digit prefixed numeric (see
  [ID Format by Object Type](#id-format-by-object-type)). Even all-numeric IDs
  (`viewId`, `listId`, model-level objects) are modelled `type: string`, not
  `integer`: numeric typing causes int32 overflow, JS `double` precision loss
  above 2^53, and wire-format mismatch if the API quotes them. The `integer`
  occurrences for `viewId`/`listId` in `sources/integration/modelObjectschema.json`
  are source bugs to normalise to `string`, not signal. No `pattern`/range
  constraint until confirmed (ADR 0003 §5); the prefix families above are
  descriptive, not enforced.
- **Line items have no numeric ID range** (Q1). Line items are keyed by `code`,
  not an `id` (see ID Format note). No `lineItemId` numeric range to document.
- **Boolean query parameters are `type: boolean`** (Q3), consistently across all
  paths. The wire is always text; the spec types them boolean for codegen.
- **No workspace-scoped `/users` endpoint is needed** (Q4). The spec already
  exposes `GET /workspaces/{workspaceId}/admins` and
  `GET /workspaces/{workspaceId}/visitors` (with `Admin`/`Visitor` schemas).
  `GET /users` is tenant-scoped ("all users within the tenant") and has no
  `expand` parameter; visitors/admins are separate workspace-scoped resources,
  not a projection of `/users` (Q5). `/users` description should point to the
  two workspace endpoints rather than imply visitor inclusion.
- **`s` search parameter semantics** (feeds #147). Shared component, generic
  wording (mechanics are identical across `/users`, `/workspaces`, …; only the
  filtered noun changes, so "items" covers all). Behaviour: undocumented
  feature, may behave unpredictably; requires the **Tenant Admin** role and is
  **ignored for non-admin users**; case-insensitive; matches items whose name or
  ID *contains* the string; supports SQL-LIKE wildcards `%` (0-n characters) and
  `_` (exactly 1 character); omitted (default) returns all items. Canonical
  shared description:

  > Optional case-insensitive filter. Matches items whose name or ID contains
  > this string. Supports wildcards `%` (0-n characters) and `_` (exactly 1
  > character). Omit to return all items. **Undocumented and may behave
  > unpredictably; requires the Tenant Admin role and is ignored for non-admin
  > users.**

- **`Accept`/`Content-Type` are modelled via `content` media-type maps, not
  header parameters** (Q6). OpenAPI 3.0 expresses them through
  `requestBody.content.<media-type>` and `responses.<code>.content.<media-type>`.
  When `Accept` selects an alternate response format (e.g. `views/data`
  `format=v1` → `text/csv`, see [pages section](#pages-and-sort-query-parameters-issue-31)),
  model each as a separate media-type key. Add an explicit `Accept`/`Content-Type`
  header parameter only where the API deviates from standard content negotiation
  in a way the `content` map cannot express.

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

## Live Probe Findings (issue #90 Phase 1)

Probed all GET endpoints against the live Integration API (2026-06-18) using `scripts/probe_integration_responses.py` and `scripts/probe_id_patterns.py`. Sample sizes: 5,000 users, 3,810 models, 100 workspaces, 836 imports, 104 exports, 18 actions, 120 processes, 450 files, 223 lists, 983 modules, 1,533 views, 32 dashboards.

### ID Format by Object Type

Anaplan uses two distinct ID families in the Integration API:

**32-character hexadecimal** (users, workspaces, models):

| Type | Format | Example |
|------|--------|---------|
| User | 32-char hex, lowercase | `8a868cdb8b7841a2018bf2c183307cd7` |
| Workspace | 32-char hex, lowercase | `8a8194824045c4240140750bf15a5574` |
| Model | 32-char hex, uppercase | `173564909BDC4A2CBC803B486AC7B4A8` |

**12-digit numeric with type prefix** (all model-level objects):

| Type | Prefix | Example | Notes |
|------|--------|---------|-------|
| List | 101 | `101000000203` | |
| Module | 102 | `102000001442` | |
| Import | 112 | `112000000017` | |
| File (upload) | 113 | `113000000000` | Import source files |
| Dashboard | 115 | `115000000009` | |
| Export / export file | 116 | `116000000001` | Export ID = export output file ID |
| Action | 117 | `117000000020` | |
| Process | 118 | `118000000144` | |

Views: 12 digits (prefix 102–922 for module default views) or 13 digits (prefix 1,012–4,296 for named saved views).

Line items do not have an `id` field; `code` is their primary key.

### Confirmed Enum Values

| Field | Confirmed values |
|-------|----------------|
| `Import.importType` | `HIERARCHY_DATA`, `LINE_ITEM_DEFINITION`, `MODULE_DATA`, `USERS` |
| `Export.exportType` | `AUDIT_LOG`, `GRID_CURRENT_PAGE`, `TABULAR_ALL_LINE_ITEMS`, `TABULAR_CURRENT_LINE_ITEM`, `TABULAR_MULTI_COLUMN` |
| `ImportMetadata.type` | `FILE` (file-based source), `MODEL` (model-to-model) |
| `File.encoding` | `ISO-8859-1`, `UTF-16LE`, `UTF-8` |
| `File.separator` | `` (none), `\t` (tab), `,` (comma) |
| `File.delimiter` | `` (none), `"` (double-quote) |
| `File.format` | `txt` |

### Fields Absent from Live Responses

These fields are defined in the spec but were never returned by the live API across all probe samples. Descriptions are retained as they appear in Apiary/Postman documentation, but the fields cannot be confirmed as currently active.

| Field | Probe sample size |
|-------|-------------------|
| `File.origin` | 450 files — 0 occurrences |
| `File.country` | 450 files — 0 occurrences |
| `File.language` | 450 files — 0 occurrences |
| `Workspace.currentSize` | 100 workspaces — 0 occurrences |
| `ModelCalendar.extraWeekMonth` | 1 model calendar (Calendar Months type) — not applicable |

`ModelCalendar.extraWeekMonth` is specific to 4-4-5 calendar models. The probed model uses Calendar Months; the field appears for 4-4-5 models only.

### `POST /workspaces/{workspaceId}/bulkDeleteModels` — endpoint shape (issue #116)

Live testing confirmed this endpoint exists and accepts `POST` (not `DELETE`). Key findings:

- **Method**: `POST` — `OPTIONS` returns `Allow: POST,OPTIONS`. There is no `DELETE /workspaces/{workspaceId}/models` endpoint.
- **Request body field**: `modelIdsToDelete` (not `modelIds`). Sending `modelIds` returns `400: "Identified an unrecognized 'modelIds'. Amend the content so it only contains applicable fields."` Sending an empty body returns `400: "Expected mandatory field 'modelIdsToDelete' to be present and not empty."`.
- **Success response** (all models deleted): `bulkDeleteModelsFailures` is **omitted entirely** — it is not present as an empty array.
- **Partial failure response** (some models not deleted): `bulkDeleteModelsFailures` array is present with `{modelId, message}` objects. Known failure messages:
  - `"Model is open. Please close the model before trying again."`
  - `"Model ID does not exist."`

Full success response shape:
```json
{
  "meta": {"schema": "https://api.anaplan.com/2/0/objects/bulkDeleteModels"},
  "status": {"code": 200, "message": "Success"},
  "modelsDeleted": 1
}
```

### `SummaryReport` stub retired from integration spec (issue #116)

The `SummaryReport` schema was present in the integration spec as an empty stub (`x-stub: true`, no properties, no description). Live probing of export and import task results found no `summaryReport` field in any integration API response. The ALM API has the real summary-report concept — `SummaryReportResponse` is wired to `GET /workspaces/{workspaceId}/alm/models/{modelId}/summaryReport`. The integration stub has been removed.

### Schema Additions from Probe

Fields observed in live responses that were missing from the spec:

| Schema | Added fields |
|--------|-------------|
| `Export` (list item) | `encoding`, `exportFormat`, `layout` |
| `ExportMetadata` | `layout` |
| `Action` | `actionType` (observed: `DELETE_BY_SELECTION`) |
| `Process` | `code`, `id`, `name` (schema was empty) |
| `CurrentPeriod` | `calendarType`, `lastDay`, `periodText` (schema was empty) |
