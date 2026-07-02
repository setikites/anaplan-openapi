# Path-parameter sources for the endpoint access scan

`scripts/scan_endpoint_access.py` fills GET path parameters with **real IDs**
harvested from earlier list responses, so a GET reflects the caller's
authorization to a resource rather than a 404 for a fabricated ID. This file
documents, per path parameter, which endpoint's response supplies a real value
and the exact JSON field to read.

Rules the table encodes:

- **GET only.** Mutating verbs (POST/PUT/PATCH/DELETE) always use the fabricated
  ID `00000000000000000000000000000000`, so they fail before changing state.
- **Field name is not always `id`.** CloudWorks and SCIM use different field
  names (`integrationId`, `connectionId`, `Resources[].id`). Reading only `id`
  was the bug that left these parameters fabricated.
- **Same param name, different source.** `taskId` comes from whichever `.../tasks`
  endpoint sits directly above it — action tasks and import tasks are distinct
  sources. Resolve by the path prefix, not by the bare name.
- **Cross-API fallback.** SCIM `{id}` and exception `{userGuid}` are the same
  Anaplan hex-32 user GUID (both specs say so). If their own API's list is not
  reachable, fall back to `integration /users`, then to `integration /users/me`,
  which always returns the caller's own GUID. Feeding your own GUID still measures
  access correctly — the role gate (403) is checked before the resource lookup.
- **`chunkId` defaults to `0`.** Files are chunked `0..n`; chunk 0 exists whenever
  the file has any content, so no harvest is needed.

## Harvestable parameters (real IDs for GET)

| Parameter | Source endpoint (GET) | Field to read | Notes |
|-----------|----------------------|---------------|-------|
| `workspaceId` | `integration /workspaces` | `workspaces[].id` | |
| `modelId` | `integration /models` | `models[].id` | also `/workspaces/{workspaceId}/models` → `models[].id`; prefer the model's `currentWorkspaceId` to pair the two |
| `userId` | `integration /users` | `users[].id` | also `/users/me` → `user.id` |
| `listId` | `integration /models/{modelId}/lists` | `lists[].id` | |
| `viewId` | `integration /models/{modelId}/views` | `views[].id` | |
| `moduleId` | `integration /models/{modelId}/modules` | `modules[].id` | |
| `importId` | `integration /models/{modelId}/imports` | `imports[].id` | |
| `exportId` | `integration /models/{modelId}/exports` | `exports[].id` | |
| `actionId` | `integration /models/{modelId}/actions` | `actions[].id` | |
| `processId` | `integration /models/{modelId}/processes` | `processes[].id` | also embedded: CloudWorks `integrations[].processId` |
| `fileId` | `integration /models/{modelId}/files` | `files[].id` | |
| `lineItemId` | `integration /models/{modelId}/lineItems` | `items[].id` | list key is `items`, not `lineItems` |
| `dimensionId` | `integration /models/{modelId}/lineItems/{lineItemId}/dimensions` | `items[].id` | also `.../views/{viewId}/dimensions` |
| `versionId` | `integration /models/{modelId}/versions` | `versionMetadata[].id` | list key is `versionMetadata` |
| `chunkId` | — | — | default `"0"`; no harvest |
| `taskId` (action) | `integration /workspaces/{workspaceId}/models/{modelId}/actions/{actionId}/tasks` | `tasks[].taskId` | field is `taskId`, not `id` |
| `taskId` (import) | `integration .../imports/{importId}/tasks` | `task.taskId` | single `task` object, not a list |
| `taskId` (process) | `integration .../processes/{processId}/tasks` | `tasks[].taskId` | |
| `taskId` (export) | `integration .../exports/{exportId}/tasks` | `tasks[].taskId` | |
| `revisionId` | `alm /models/{modelId}/alm/revisions` | `revisions[].id` | |
| `syncTaskId` | `alm /models/{modelId}/alm/syncTasks` | `tasks[].taskId` | list key `tasks`, field `taskId` |
| `targetRevisionId` | `alm /models/{modelId}/alm/revisions` | `revisions[].id` | alias of `revisionId` |
| `sourceRevisionId` | `alm /models/{modelId}/alm/revisions` | `revisions[].id` | alias of `revisionId` |
| `integrationId` | `cloudworks /integrations` | `integrations[].integrationId` | **field is `integrationId`, not `id`** |
| `integrationFlowId` | `cloudworks /integrationflows` | `integrationFlows[].id` | |
| `connectionId` | `cloudworks /integrations/connections` | `connections[].connectionId` | field is `connectionId` |
| `notificationId` | `cloudworks /integrations` | `integrations[].notificationId` | embedded in the integration item |
| `runId` | `cloudworks /integrations/runs/{integrationId}` | `history_of_runs.runs[].id` | nested; needs `integrationId` first |
| `id` (SCIM) | `scim /Users` | `Resources[].id` | SCIM `ListResponse` array is `Resources`; needs SCIM User Admin to return 200. Fallbacks: `integration /users` → `users[].id`, then `integration /users/me` → `user.id` |
| `userGuid` (exception) | `integration /users` | `users[].id` | cross-API; exception has no user-list GET. Fallback: `integration /users/me` → `user.id` |

## Parameters that stay fabricated (no reachable GET source)

| Parameter | Why |
|-----------|-----|
| `status` (cloudworks schedule) | path enum, not an ID |
| `requestId`, `pageNo` (view read requests) | created by POST; no list endpoint to harvest |
| `taskId` (alm comparisonReportTasks / summaryReportTasks) | created by POST; no list endpoint |
| `actionId` (cloudworks `run/{runId}/process/import/{actionId}/dumps`) | deep cross-API; low value, left fabricated |

Rows whose path used any fabricated ID are marked `confidence = fabricated-id`
in the CSV and do **not** count toward the guessed access level.
