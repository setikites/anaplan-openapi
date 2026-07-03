# Anaplan ALM API

## Sources

| Source | Location |
|--------|----------|
| Apiary docs | https://almapi.docs.apiary.io/ (identifier: `almapi`) |
| Postman collection | Official Anaplan Collection — top-level "ALM" folder (Model status, Revisions, Sync tasks, Comparison reports, Summary reports) |
| OpenAPI spec | `alm/alm-openapi.json` |

## Authentication

Apiary docs declare `AnaplanAuthToken` as the required scheme:

```
Authorization: AnaplanAuthToken {anaplan_auth_token}
```

The token is a JWT obtained from the Authentication API. SSO users must be designated as Exception Users to authenticate via basic auth; certificate-based auth has additional restrictions for certain user categories.

**Confirmed (live testing 2026-06-09).** Bearer and AnaplanAuthToken are interchangeable on ALM — both schemes are declared in the spec's `security[]` array.

## Base URL

The Apiary docs declare `https://api.anaplan.com/2/0/` as the production base URL. This matches the standard `_SERVERS_API` regional pattern used by Integration, SCIM, Audit, Exception Users, and CloudWorks.

| Source | Base URL |
|--------|----------|
| Apiary docs | `https://api.anaplan.com/2/0/` |
| CONTEXT.md regional pattern | `https://{region}.api.anaplan.com` |

No conflict — ALM follows the standard `api.anaplan.com` pattern. All regional variants apply (see CONTEXT.md for the full 19-region table).

## Endpoint Inventory

All endpoints require the **Workspace Administrator** role. The model must be unlocked and unarchived (archived models return 422).

### Online Status

| Method | Path | Description |
|--------|------|-------------|
| POST/PUT | `/models/{modelId}/onlineStatus` | Set a model online or offline |

### Revisions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/models/{modelId}/alm/latestRevision` | Retrieve the latest revision for a model |
| GET | `/models/{modelId}/alm/revisions` | List all revisions in a model (paginated, filterable by date) |
| POST | `/models/{modelId}/alm/revisions` | Create a new revision (model must have structural changes) |
| GET | `/models/{modelId}/alm/revisions/{revisionId}/appliedToModels` | List all models a revision has been applied to |

### Sync Tasks

| Method | Path | Description |
|--------|------|-------------|
| GET | `/models/{targetModelGuid}/alm/syncableRevisions` | Retrieve compatible source model revisions |
| POST | `/models/{modelId}/alm/syncTasks` | Create a model sync task |
| GET | `/models/{modelId}/alm/syncTasks` | List sync tasks for a model (tasks in progress or completed within 48 hrs) |
| GET | `/models/{modelId}/alm/syncTasks/{syncTaskId}` | Retrieve sync task status and result |

#### Finding the source model and next revision

`syncableRevisions` and `syncTasks` both need a `sourceModelId` — the model whose revisions are applied to the target. For a model already participating in ALM, the source model is discoverable entirely within this API:

1. `GET /models/{modelId}/alm/latestRevision` → the target's latest `revisionId`.
2. `GET /models/{modelId}/alm/revisions/{revisionId}/appliedToModels` → the **first** model in `appliedToModels` is the source model where revisions are created, a good default `sourceModelId`. Any model in the list can serve as `sourceModelId` for discovering and syncing this revision.
3. `GET /models/{modelId}/alm/syncableRevisions?sourceModelId=<source>` → compatible source revisions, newest first. The first entry's `sourceRevisionId` is the next available revision.
4. `POST /models/{modelId}/alm/syncTasks` with `{ "sourceModelId", "sourceRevisionId" }` → returns a `syncTaskId`; poll `GET .../syncTasks/{syncTaskId}` to completion.

### Comparison Reports

| Method | Path | Description |
|--------|------|-------------|
| POST | `/models/{targetModelId}/alm/comparisonReportTasks` | Start a full comparison report generation task |
| GET | `/models/{modelId}/alm/comparisonReportTasks/{taskId}` | Retrieve comparison report task status |
| GET | `/models/{modelId}/alm/comparisonReports/{targetRevisionId}/{sourceRevisionId}` | Download the full comparison report (TSV, available 48 hrs) |

### Summary Reports

| Method | Path | Description |
|--------|------|-------------|
| POST | `/models/{targetModelId}/alm/summaryReportTasks` | Start a summary report generation task |
| GET | `/models/{modelId}/alm/summaryReportTasks/{taskId}` | Retrieve summary report task status |
| GET | `/models/{modelId}/alm/summaryReports/{targetRevisionId}/{sourceRevisionId}` | Download the summary report (JSON, available 48 hrs) |

## Response Envelope

All successful responses wrap their payload in a standard envelope:

```json
{
  "meta": {
    "schema": "https://api.anaplan.com/2/0/objects/{type}",
    "paging": { "currentPageSize": 0, "offset": 0, "totalSize": 0 }
  },
  "status": {
    "code": 200,
    "message": "Success"
  },
  "data": {}
}
```

## Revision Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Revision identifier |
| `name` | string | Revision name (max 60 chars) |
| `description` | string | Optional description (max 250 chars) |
| `createdOn` | string | ISO 8601 timestamp |
| `createdBy` | string | User who created the revision |
| `creationMethod` | string | How the revision was created |
| `appliedOn` | string | When revision was last applied |
| `appliedBy` | string | Who last applied the revision |

## Sync Task States

| State | Meaning |
|-------|---------|
| `IN_PROGRESS` | Task is running |
| `COMPLETE` | Task finished (check `result.successful`) |

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid JSON, missing required fields, name/description too long) |
| 403 | Forbidden (user lacks Workspace Administrator role) |
| 404 | Not found (invalid model/revision/task ID, or no access) |
| 422 | Model is archived |

## Spec Lifecycle

Canonical lifecycle and confidence are in the [confidence table in CONTEXT.md](../CONTEXT.md#confidence-table). Live tests: `tests/test_alm_live.py`.

Run live tests with:
```
uv run --env-file .env pytest tests/test_alm_live.py --live
```

Required `.env` variables: `ANAPLAN_USERNAME`, `ANAPLAN_PASSWORD`.
Optional: `ANAPLAN_WORKSPACE_ID` (default: `8a868cdb8b7841a2018beedb91d644d7`), `ANAPLAN_MODEL_ID` (default: `0939A1C8E7FB46799372EC24A72FE93B`), `ANAPLAN_ALM_BASE_URL`, `ANAPLAN_OAUTH_ACCESS_TOKEN`.

## Discovered Discrepancies

### Empty-result responses omit payload keys (live testing 2026-06-09)

`GET /alm/syncTasks` and `GET /alm/latestRevision` return 200 with only `meta` and `status` when no data exists — the `tasks` / `revision` key is omitted entirely rather than returning an empty array or null. This applies to:

- `GET /models/{modelId}/alm/syncTasks` → no `tasks` key when no tasks in last 48 hours
- `GET /models/{modelId}/alm/latestRevision` → no `revision` key when model has no revisions

Documented in the `SyncTaskListResponse` and `RevisionResponse` schema descriptions.

### Report tasks require `targetRevisionId` (live testing 2026-07-02)

`POST /alm/comparisonReportTasks` and `POST /alm/summaryReportTasks` reject the request with `400 "Expected mandatory fields 'sourceRevisionId', 'sourceModelId' and 'targetRevisionId'"` unless all three are present — unlike `POST /alm/syncTasks`, where `targetRevisionId` is optional. The spec models this with a dedicated `ReportTaskRequest` schema (all three required) for the report endpoints, leaving `SyncTaskRequest` unchanged for sync tasks.

### Role denial returns 424, not 403 (live testing 2026-07-02)

The comparison/summary report endpoints return `424 Failed Dependency` (empty message) when the caller lacks the Workspace Administrator role, rather than the `403` the spec documents. Confirmed by an A/B run: the identical dummy-id request returned `404`/`201` for a Workspace Administrator and `424` after the role was removed from the same certificate account, so `424` is driven by the missing role, not the missing resource. This established Workspace Administrator as the minimum role for all six report endpoints:

- `POST /alm/comparisonReportTasks`, `POST /alm/summaryReportTasks`
- `GET /alm/comparisonReportTasks/{taskId}`, `GET /alm/summaryReportTasks/{taskId}`
- `GET /alm/comparisonReports/{targetRevisionId}/{sourceRevisionId}`
- `GET /alm/summaryReports/{targetRevisionId}/{sourceRevisionId}`

### Comparison-report result requires an octet-stream Accept (live testing 2026-07-02)

`GET /alm/comparisonReports/{targetRevisionId}/{sourceRevisionId}` serves the report only as `application/octet-stream` (a TSV download, as the spec's 200 response documents). It returns a role-blind `406 Not Acceptable` to `Accept: application/json` or `text/plain` — content negotiation precedes the role check, which initially masked its role gate. Probed with `Accept: application/octet-stream` the role signal appears normally (admin dummy-id `404`, non-admin `424`), confirming Workspace Administrator; its `needs-info` flag is cleared.
