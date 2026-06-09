# Anaplan CloudWorks API

## Sources

| Source | Location |
|--------|----------|
| Apiary docs | https://cloudworks.docs.apiary.io/ (identifier: `cloudworks`) |
| Postman collection | None available |
| OpenAPI spec | `cloudworks/cloudworks-openapi.json` |

## Authentication

Apiary docs declare `AnaplanAuthToken` as the required scheme:

```
Authorization: AnaplanAuthToken {token}
```

**Unconfirmed — pending live testing.** The Integration API accepts both `AnaplanAuthToken` and `Bearer` token; whether CloudWorks does the same is unknown.

## Base URL (Open Question)

Two conflicting patterns have been identified — live testing is needed to determine which is correct:

| Source | Base URL |
|--------|----------|
| Apiary docs | `https://api.cloudworks.anaplan.com/2/0/` |
| CONTEXT.md regional pattern | `https://{region}.api.anaplan.com` (same pattern as Integration, ALM, SCIM, Audit, Exception Users) |

The spec's `servers[]` array uses `https://api.cloudworks.anaplan.com` per Apiary. If live testing confirms the standard regional pattern applies, update `servers[]` to match the other API specs and note the resolution here.

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

## Spec Lifecycle

Bootstrap-only — spec generated from Apiary via `build_spec.py`. No live test harness exists yet. Once live tests are added, the spec transitions to hand-maintained (do not re-run `build_spec.py`).

## Discovered Discrepancies

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
