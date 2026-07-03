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
- `GET /integrations/anaplanModels/{modelId}` returns an nginx `404` in all three phases (never reaches the app-layer role check), so its role is unconfirmable — it carries `x-anaplan-min-role-needs-info` and is likely deprecated.
- The `452 "Tenant not entitled"` seen for a role-less caller on the four schedule operations and `GET /integrations/run/{runId}/dumps` is role denial, not a tenant entitlement gap: the Restricted Integration User role clears it to the normal 400/404.

## Spec Lifecycle

Canonical lifecycle and confidence are in the [confidence table in CONTEXT.md](../CONTEXT.md#confidence-table).

Live tests run against real tenant data (June 2026). All previously-open questions on auth, base URL, connection shapes, integration shapes, run history, notifications, and integration flows are now confirmed — see the Discoveries section below.

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
