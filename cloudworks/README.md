# Anaplan CloudWorks API

## Sources

| Source | Location |
|--------|----------|
| Apiary docs | https://cloudworks.docs.apiary.io/ (identifier: `cloudworks`) |
| Postman collection | Official Anaplan Collection — top-level "CloudWorks" folder (Connections, Integrations, Process integrations, Schedules, Runs and error logs, Notifications, Integration flows) |
| OpenAPI spec | `cloudworks/cloudworks-openapi.json` |

## Authentication

**Confirmed (live testing June 2026)**: Both `AnaplanAuthToken` and `Bearer` (using an AnaplanAuthToken value) are accepted:

```
Authorization: AnaplanAuthToken {token}
Authorization: Bearer {token}
```

## Base URL (Confirmed)

Both base URLs respond with 200 (live-tested June 2026):

| Source | Base URL | Status |
|--------|----------|--------|
| Apiary docs | `https://api.cloudworks.anaplan.com/2/0/` | ✅ Active |
| Apiary production URL field | `https://api.anaplan.com/cloudworks/2/0/` | ✅ Also active |

The `api.cloudworks.anaplan.com` form is listed first in `servers[]` as it matches Apiary curl examples. Set `ANAPLAN_CLOUDWORKS_BASE_URL=https://api.cloudworks.anaplan.com/2/0` in `.env` to skip the probe.

## Resource Groups

The CloudWorks API exposes seven resource groups:

| Group | Description |
|-------|-------------|
| **Connections** | Create and manage connections to Amazon S3, Google BigQuery, and Azure Blob Storage |
| **Integrations** | Create, run, cancel, and delete import/export integrations; also covers Process Integrations (same paths, `processId` in body) |
| **Schedules** | Configure recurring execution schedules (weekly or monthly) with timezone support; enable/disable schedule status |
| **History & Monitoring** | Retrieve run history, run status, and per-run errors for an integration |
| **Notifications** | Configure alert notifications for integration completion events |
| **Error Logs** | Retrieve import-error and process-error logs for a specific run |
| **Integration Flows** | Create and manage multi-step workflows with step-level error control and conditional execution |

## Minimum Role (live-confirmed July 2026)

Every CloudWorks operation requires the **Restricted Integration User** role — live-confirmed with a three-phase certificate-auth A/B run (ADR 0006):

| Role held by cert account | Result across all 30 live endpoints |
|---|---|
| None (Standard User) | `403 Not Permitted` (or `452 Tenant not entitled` on the schedule/dumps paths) — denied everywhere |
| **Restricted Integration User** | reaches the app on every endpoint (200 / field-validation 400 / dummy-id 404) — no 403 |
| Integration Admin | same endpoint access as Restricted Integration User |

Findings:

- **Restricted Integration User is the minimum for the whole API**, including the six `/integrationflows` operations (initially annotated Integration Admin — corrected). `Integration Admin` gates **no endpoint**; it only widens *data scope* (tenant-wide vs assigned-workspace). Under Restricted Integration User the list endpoints returned empty arrays (`connections: []`, `integrations: []`, `integrationFlows: []`) because this account's role is scoped to workspaces holding no CloudWorks resources — the endpoints are still fully reachable.
- **Two components are required to authorize a CloudWorks call: the Restricted Integration User role *and* a workspace assignment.** The role alone admits the caller to the endpoints; workspace assignment determines which resources are visible/actionable. An account with the role but no assigned workspace reaches every endpoint yet sees an empty result set — the role is necessary but not sufficient for actual data access.
- `GET /integrations/anaplanModels/{modelId}` returns an nginx `404` at the routing layer in **every** case tested — regular user, Restricted Integration User, and Integration Admin, with both a valid modelId (`6A64DE2AB2964642AFB051B4B21143A5`, in an assigned workspace) and a dummy one. The endpoint is removed, not role- or resource-gated, so it is marked `deprecated: true` in the spec (no `needs-info`). Retained in the spec per Apiary for historical completeness; do not call it.
- The `452 "Tenant not entitled"` seen for a role-less caller on the four schedule operations and `GET /integrations/run/{runId}/dumps` is role denial, not a tenant entitlement gap: the Restricted Integration User role clears it to the normal 400/404.

## Spec Lifecycle

Canonical lifecycle and confidence are in the [confidence table in CONTEXT.md](../CONTEXT.md#confidence-table).

Live tests run against real tenant data (June and July 2026). The suite is `tests/test_cloudworks_live.py` (15 tests). Run it with:

```
uv run --env-file .env pytest tests/test_cloudworks_live.py --live
```

All earlier open questions on auth, base URL, connection shapes, integration shapes, run history, notifications, and integration flows are confirmed — see the Discoveries section below. Two mutation tests need extra setup and skip without it: the connection lifecycle test needs `CLOUDWORKS_DISPOSABLE_CONNECTION_ID`, and the mutation lifecycle test needs `--allow-writes` and the named target workspace and model in the tenant. Three response shapes stay unconfirmed: `PUT` and `PATCH` on a connection, and the `200` from `POST /integrations/{integrationId}/cancel`.

## Discoveries from Live Testing (June 2026)

### General — confirmed shapes

| Observation | Confirmed |
|---|---|
| `integrationType` field in IntegrationSummary: enum `"Process"`, `"Export"`, `"Import"` | ✅ |
| `triggerSource` in `latestRun` and RunRecord: `"scheduled"`, `"manual"`, `"scheduled_inf"`, `"manual_inf"`, `"nux_dashboard"` | ✅ |
| `executionErrorCode` is an integer (not string), null on success | ✅ |
| Known `executionErrorCode` values: `12` (import data-type mismatch), `35`, `38` (partial success), `39` | ✅ |
| `RunRecord.lastRun` is a Unix timestamp integer (not ISO 8601) | ✅ |
| `RunRecord.traceId` present on all run records | ✅ |
| IntegrationSummary includes `schedule`, `modelId`, `workspaceId` | ✅ |
| `integrationId`, `workspaceId`, `notificationId`, `connectionId`, run `id`, `traceId`, `userGuid`: 32-char **lowercase** hex | ✅ |
| `modelId`: 32-char **uppercase** hex (the only uppercase ID in the API) | ✅ |
| `processId`, `actionId`, `fileId`: numeric string, e.g. `"118000000114"` | ✅ |
| `startDate`/`endDate` on runs: ISO 8601 UTC milliseconds — `YYYY-MM-DDTHH:MM:SS.sssZ` | ✅ |
| `createdDate`/`modifiedDate` on flow steps: space-separated — `YYYY-MM-DD HH:MM:SS.uuuuuu+00:00` | ✅ |
| `schedule.status` enum: `"Active"`, `"Inactive"` | ✅ |
| ConnectionSummary includes `authMethod`, `integrationErrorCode`, `workspaceId` at root level | ✅ |
| `authMethod` appears in camelCase in GET responses; `auth_method` in snake_case in create/update requests | ✅ |
| GET /integrations meta includes `tenantCurrentCount` and `tenantMaxAllowed` | ✅ |
| IntegrationFlowSummary uses `id` (not `integrationFlowId`) | ✅ |
| IntegrationFlowSummary includes `stepsCount` | ✅ |
| GET /integrationflows/{id} is a valid endpoint (not documented in Apiary) | ✅ |
| IntegrationFlowDetail steps have `referrer`, `name`, `type`, `dependsOn`, `isSkipped`, `exceptionBehavior`, `latestRun` | ✅ |
| Job sources and targets both include `connectionName`, `isConnectionDeleted`, `bucketName` (GET responses) | ✅ |
| `connection.status` is integer: 1=active, 0=error | ✅ |
| `integrationErrorCode` = 46 observed for a connection with status=0 | ✅ |
| `schedule.type` observed: `"hourly"`, `"weekly"` | ✅ (monthly not observed in this tenant) |
| GET /integrations/anaplanModels/{modelId}: returns HTML 404 from nginx — likely deprecated | ⚠️ |
| GET /integrations/runerror/{runId}: returns `"runs": {}` (empty object, not array) when no errors | ⚠️ |

### `GET /integrations/run/{runId}` — recorded from the `anaplan-sdk` client

This path is absent from the Postman collection in `sources/`. It was found in the
[`anaplan-sdk`](https://github.com/VinzenzKlass/anaplan-sdk) client, which calls it as
`get_run_status`, and its **200** shape is live-confirmed (August 2026) by
`test_cloudworks_get_run_status_shape`.

It earns its place next to `GET /integrations/runs/{integrationId}` because it takes a run
ID alone and returns `run.integrationId`. `POST /integrations/{integrationId}/run` hands
back a bare run ID, and run history is keyed by integration, so without this endpoint a
caller holding only a run ID cannot resolve it.

`RunStatus` holds six fields that `RunRecord` does not: `integrationId`, `creationDate`,
`modificationDate`, `createdBy`, `modifiedBy`, and `flowGroupId`. It omits `RunRecord`'s
`lastRun` and `triggeredBy`. Its `meta.schema` cites a `1/0` URL
(`https://api.cloudworks.anaplan.com/1/0/integrations/objects/run`) even though the
endpoint is served under `2/0`.

### The integration-level error dump path is `/dumps`, not `/dump`

The `anaplan-sdk` client requests `GET /integrations/run/{runId}/dump` (singular) in
`get_error_dump`. That path is not routed. The spec's plural `/dumps` is correct, and the
two 404s differ in a way that settles it:

| Path | Response |
|---|---|
| `/integrations/run/{runId}/dumps` | JSON 404 from the API — `{"status": {"code": 404, "message": "Your integration run was successful / no errors"}, ...}` |
| `/integrations/run/{runId}/dump` | HTML 404 from the web server — `<title>404 Not Found</title>`, `Content-Type: text/html` |

An API-shaped JSON envelope means the route exists and the resource does not. An HTML 404
means the route itself is unrouted. `test_cloudworks_run_dumps_path_is_plural` asserts
both, so the test fails if Anaplan later adds the singular alias. The client's
process-level call, `GET /integrations/run/{runId}/process/import/{actionId}/dumps`, is
already plural and agrees with the spec.

This is a bug in the client, not a gap in the spec. No spec change was made for it.

### Connection lifecycle response shapes (issue #254)

Live-tested July 2026 by `test_cloudworks_connection_lifecycle_response_shapes`, which runs only against `CLOUDWORKS_DISPOSABLE_CONNECTION_ID` and deletes that connection.

| Operation | Confirmed | Observed |
|---|---|---|
| `DELETE /integrations/connections/{connectionId}` | ✅ | `200` with `{"status": {"code": 200, "message": "Success"}}` — matches `SuccessStatus` |
| `PUT /integrations/connections/{connectionId}` | ⚠️ unconfirmed | `400 "Invalid request body"` for a body carrying only `name` |
| `PATCH /integrations/connections/{connectionId}` | ⚠️ unconfirmed | `400 "Invalid request body"` for a body carrying only `name`, with or without a `type` key |

Findings:

- **The 13 mutating operations that appear to declare an empty `200` are not gaps.** They reference `#/components/responses/SuccessStatus`, which carries a JSON schema. A contract check that reads response objects without resolving `$ref` reports every one of them as schema-less; the check in `tests/test_spec_contract.py` resolves them.
- **`POST /integrations/connections` validates third-party credentials server-side.** A well-formed AzureBlob body with a fake storage account and SAS token is rejected with `400 "Credentials are invalid"`. Tests cannot create a disposable connection to work against, which is why the lifecycle test requires one to be supplied.
- **`PUT` and `PATCH` want the complete connection body, not a partial one.** A name-only update fails for both. Since `GET` never returns a connection's secret, neither can be exercised against a connection whose credentials the caller does not already hold — so their success envelopes remain unconfirmed and are documented from `SuccessStatus`.
- **`DELETE` returned `200`, not `409`**, for a connection not referenced by any integration.

### Integration, flow, schedule, and notification mutation response shapes (issue #255)

Live-tested July 2026 by `test_cloudworks_mutation_lifecycle_response_shapes`, which builds its own disposable integrations, schedule, notification, and flow in the `Crash Test Dummy` model, exercises all eleven operations, and destroys them again.

| Operation | Confirmed | Observed |
|---|---|---|
| `PUT /integrations/{integrationId}` | ✅ | `200` with `{"status": {"code": 200, "message": "Success"}}` — matches `SuccessStatus` |
| `DELETE /integrations/{integrationId}` | ✅ | as above |
| `PUT /integrationflows/{integrationFlowId}` | ✅ | as above |
| `DELETE /integrationflows/{integrationFlowId}` | ✅ | as above |
| `POST /integrations/{integrationId}/schedule` | ✅ | as above |
| `PUT /integrations/{integrationId}/schedule` | ✅ | as above |
| `DELETE /integrations/{integrationId}/schedule` | ✅ | as above |
| `POST /integrations/{integrationId}/schedule/status/{status}` | ✅ | as above |
| `PUT /integrations/notification/{notificationId}` | ✅ | as above |
| `DELETE /integrations/notification/{notificationId}` | ✅ | as above |
| `POST /integrations/{integrationId}/cancel` | ⚠️ unconfirmed | `409 "Integration {id} is not in running state"` against an idle integration; `404 "Resource not found"` while a run is queued; `409` again once `latestRun.message` reads `Running` |

Findings:

- **All ten confirmed operations return the `SuccessStatus` envelope**, so the schema the spec already declared for them is correct.
- **`POST /integrations` returns the new ID wrapped in an `integration` object** — `{"status": {...}, "integration": {"integrationId": "..."}}`, mirroring the `integrationFlow` wrapper on flow creation. The spec previously declared a top-level `integrationId`, which no live response carries.
- **Creating an integration also creates its notification configuration.** The new integration's record already carries a `notificationId`, and a `POST /integrations/notification` for that same integration is rejected with `400 "Duplicate resource name not allowed"`. `editNotification` and `deleteNotification` are therefore exercised against the auto-created configuration.
- **`updateSchedule` requires `integrationId` in the request body as well as the path.** Sending only `schedule` draws `400 "Invalid value for integration_id"`, even though the path already names the integration.
- **`cancelIntegration`'s success body could not be observed.** For a process integration the success path appears unreachable: the API answers `404` while the run is queued and `409 "is not in running state"` once `latestRun` reports `Running`. Its `200` is documented as `SuccessStatus` — every other CloudWorks 2/0 mutation returns that envelope, and cancel's own error responses use the same `{"status": {...}, "path", "timestamp"}` shape. The Apiary blueprint instead showed `{"success": true, "message": {"integration_id": ..., "state": "cancelled"}}`; no live response has corroborated that shape, and it is not carried into the spec.
- **A run in flight blocks `DELETE /integrations/{integrationId}`** with `409 "Integration is already running"`, and a process run in this model takes about six minutes. The lifecycle test therefore never starts a run — doing so leaks its disposable integrations for the duration.

### Azure Blob Storage: `auth_method` is now required (undocumented)

A recent CloudWorks update added support for connecting to Azure Blob Storage via OAuth 2.0. As a side effect, the `body` object for `AzureBlob` connections now **requires** an `auth_method` field that is absent from the Apiary docs.

- **Backwards-compatible value**: `"SAS-based"` — existing connections using a SAS token must pass `auth_method: "SAS-based"` (or the API returns an error).
- **OAuth 2.0 variant**: A second form of the body exists where `sasToken` is not required. Based on the Anaplan UI ([Connect CloudWorks to Azure Blob Storage with OAuth 2.0](https://help.anaplan.com/connect-cloudworks-to-azure-blob-storage-with-oauth-20-e09eed6f-f78d-4f71-a53a-686fbe0a71b0)), the UI dropdown selects `"Oauth2"` as the auth type. **The exact API-level value for `auth_method` has not been confirmed via live testing.**

#### OAuth 2.0 connection properties (inferred from UI docs)

The Anaplan UI documentation indicates the following fields for OAuth 2.0 connections. **Property names are inferred from UI labels and have not been confirmed against the raw API.**

| UI label | Suspected API property | Source |
|---|---|---|
| Client ID | `clientId` | Microsoft Entra ID app registration → Overview |
| Client Secret | `clientSecret` | Microsoft Entra ID app registration → Certificates & secrets |
| Tenant ID | `tenantId` | Microsoft Entra ID app registration → Overview |

#### Azure app registration prerequisites

Per Anaplan UI docs, the following Azure setup is required before creating an OAuth 2.0 connection:

1. Register an application in Microsoft Entra ID with a **Web** redirect URI (Anaplan's CloudWorks callback URL).
2. Under **API permissions**, add **Azure Storage** → **Delegated permissions** → `user_impersonation` (Access Azure Storage scope).
3. Grant admin consent for the tenant.

#### What needs live testing

- Exact `auth_method` enum value accepted by the API (`"Oauth2"` suspected)
- Actual JSON property names for `clientId`, `clientSecret`, `tenantId` (may differ from UI labels, e.g., `client_id` vs `clientId`)
- Whether any additional properties are required

**Source**: Anaplan Support (reported June 2026); Anaplan UI documentation ([link](https://help.anaplan.com/connect-cloudworks-to-azure-blob-storage-with-oauth-20-e09eed6f-f78d-4f71-a53a-686fbe0a71b0)).
