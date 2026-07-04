# Input ID source map (chaining reference + endpoint access scan)

This file is the authoritative source map for **every input ID an MCP tool
consumes** across the ten specs — path, query, and header parameters *and*
request-body fields. When a spec is exposed as MCP tools, anything that becomes
an input to an API entry point belongs here, together with the prior operation's
output field that supplies it.

The map is **dual-purpose**:

1. **Chaining reference.** It is the source of truth the spec `description` edits
   cite (ADR 0004 §2/§3): for each input ID, which operation's output field
   supplies it. This is exactly the binding a composition primitive needs — see
   the `pipe()` / `map()` / `project()` design in
   [mcp-agent-access.md](mcp-agent-access.md) (option D). A `pipe` binds an output
   field of step N into an input of step N+1; each row below is one such binding
   made explicit. Example from that note:

   ```
   getLatestRevision     → project `revision.id`
     → getAppliedToModels → project `models[0].modelId` as sourceModelId
     → getSyncableRevisions → project `[0].sourceRevisionId`
     → createSyncTask
   ```

   Every arrow above is a row in the tables below.

2. **Live-scanner fill rules.** `scripts/scan_endpoint_access.py` fills GET path
   parameters with **real IDs** harvested from earlier list responses, so a GET
   reflects the caller's authorization to a resource rather than a 404 for a
   fabricated ID. The [harvestable-parameters](#harvestable-parameters-real-ids-for-get)
   table below is the scanner's fill map.

Cross-API sources (IDs minted by one API and consumed by another — e.g. `modelId`
minted by Integration, consumed by ALM/CloudWorks/Audit) name the owning API,
consistent with [ADR 0004](adr/0004-id-source-path-descriptions.md) §3. Cite the
owner's canonical anaplan.com link from the
[CONTEXT.md table](../CONTEXT.md#canonical-api-reference-links); do not hardcode
URLs here.

## Scanner fill rules

Rules the harvest table encodes:

- **GET only.** Mutating verbs (POST/PUT/PATCH/DELETE) always use the fabricated
  ID `00000000000000000000000000000000`, so they fail before changing state. Body
  and query IDs consumed by mutating verbs are **not** scanner-harvested; they
  appear in the [chaining-only table](#request-body-and-query-parameter-id-inputs-chaining)
  for description authoring, not for the scan.
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

Path parameters the scanner fills, and the chaining source for the same IDs when
they appear as path inputs to any operation.

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

## Request-body and query-parameter ID inputs (chaining)

Input IDs consumed by mutating verbs (in the request body) or by query
parameters. The scanner uses fabricated IDs for these (it never mutates state),
so these rows exist for **description authoring** — they tell the `pipe`/`map`
author which prior output binds into each field. `Consumed by` is the operation
that takes the input; `Field` is the JSON path to write inside its body (or the
query parameter name); `Source` is the operation whose output supplies the value.

| Input ID | Location | Consumed by | Source endpoint (GET) | Field to read | Cross-API owner |
|----------|----------|-------------|----------------------|---------------|-----------------|
| `sourceModelId` | query | `alm GET /models/{modelId}/alm/syncableRevisions` | `integration /models` | `models[].id` | Integration |
| `sourceModelId` | body | `alm POST /models/{modelId}/alm/syncTasks`, `.../comparisonReportTasks`, `.../summaryReportTasks` | `integration /models` | `models[].id` | Integration |
| `sourceRevisionId` | body | `alm POST /models/{modelId}/alm/syncTasks`, `.../comparisonReportTasks`, `.../summaryReportTasks` | `alm /models/{sourceModelId}/alm/revisions` (or `.../syncableRevisions`) | `revisions[].id` / `[].sourceRevisionId` | — |
| `targetRevisionId` | body | `alm POST /models/{modelId}/alm/syncTasks` (optional), `.../comparisonReportTasks`, `.../summaryReportTasks` (required) | `alm /models/{modelId}/alm/revisions` | `revisions[].id` | — |
| `workspaceGuid` | body | `exception POST /permissions/exception-users/search` (`oneOf`), `PATCH .../users/{userGuid}` | `integration /workspaces` | `workspaces[].id` | Integration |
| `userGuid` | body | `exception POST /permissions/exception-users/search` (`oneOf`, alternative to `workspaceGuid`) | `integration /users` | `users[].id` | Integration |
| `workspaceId` | body | `cloudworks POST /integrations`, `PUT /integrations/{integrationId}` | `integration /workspaces` | `workspaces[].id` | Integration |
| `modelId` | body | `cloudworks POST /integrations`, `PUT /integrations/{integrationId}` | `integration /models` | `models[].id` | Integration |
| `processId` | body | `cloudworks POST /integrations`, `PUT /integrations/{integrationId}` | `integration /models/{modelId}/processes` | `processes[].id` | Integration |
| `connectionId` | body | `cloudworks POST /integrations`, `PUT /integrations/{integrationId}` (inside `jobs[].sources[]` / `jobs[].targets[]`) | `cloudworks /integrations/connections` | `connections[].connectionId` | — |
| `integrationIds[]` | body | `cloudworks POST /integrations/notification`, `PUT /integrations/notification/{notificationId}` | `cloudworks /integrations` | `integrations[].integrationId` | — |

Note on `exception` `workspaceGuid`/`userGuid`: the search body is `oneOf` — supply
exactly one. Both are the same hex-32 identifiers minted by Integration
(`GET /workspaces`, `GET /users`); exception has no own list GET, matching the
cross-API fallback used for the `{userGuid}` path parameter above.

## Parameters that stay fabricated (no reachable GET source)

| Parameter | Why |
|-----------|-----|
| `status` (cloudworks schedule) | path enum, not an ID |
| `requestId`, `pageNo` (view read requests) | created by POST; no list endpoint to harvest |
| `taskId` (alm comparisonReportTasks / summaryReportTasks) | created by POST; no list endpoint |
| `actionId` (cloudworks `run/{runId}/process/import/{actionId}/dumps`) | deep cross-API; low value, left fabricated |

Rows whose path used any fabricated ID are marked `confidence = fabricated-id`
in the CSV and do **not** count toward the guessed access level.
</content>
</invoke>
