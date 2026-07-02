# Anaplan OpenAPI Specification Project

## Purpose

This project generates OpenAPI 3.0 JSON specifications for the 10 publicly available Anaplan REST APIs. These specs are intended for:
- **API client code generation** (via MCP servers and other tools)
- **Community-maintained documentation** (enhancing official Anaplan docs)

## The 10 Anaplan APIs

Anaplan has 10 publicly documented REST APIs, each with different characteristics, authentication schemes, and documentation quality. This project documents them as-is rather than normalizing across them, since they were built by different teams at different times.

> **Confidence and spec lifecycle for every API are consolidated in the [Confidence table](#confidence-table) below — the single source of truth for those facts.** The per-API notes here cover purpose, authentication, sources, and key behaviors only.

### High Priority (Heavily Used)

#### 1. Authentication API
- **Purpose**: Generate authentication tokens for other Anaplan APIs
- **Auth**: HTTP Basic credentials → returns token (different from other APIs)
- **Source of Truth**: Apiary docs + Postman collection
- **Key Points**: 
  - Token generation is a prerequisite for other APIs
  - Supports both basic auth (username/password) and certificate-based auth

#### 2. OAuth API
- **Purpose**: OAuth 2.0 token generation
- **Auth**: OAuth 2.0 flow
- **Source of Truth**: Apiary docs only (no Postman collection available for OAuth)
- **Key Points**:
  - Alternative to basic auth; modern OAuth 2.0 standard
  - Supports Authorization Code Grant (`/auth/authorize`) and Device Authorization Grant (`/oauth/device/code`)
  - `/auth/prelogin` endpoint discovered via live testing (not in Apiary docs)
  - Token refresh happy path requires a live refresh_token from a completed flow; only invalid-token error cases are CI-testable
  - No Postman collection exists for this API; spec is sourced from Apiary only

#### 3. Integration API
- **Purpose**: Core API for managing models, dimensions, modules, versions
- **Auth**: Bearer token (`Authorization: Bearer <token>`) OR `AnaplanAuthToken` header
- **Source of Truth**: Apiary docs + Postman collection + extracted JSON schemas
- **Key Points**:
  - Most mature API with extensive Apiary documentation
  - Postman collection covers common workflows
  - JSON schemas extracted from actual `/objects/` responses
  - Different endpoints may accept bearer token or Anaplan-specific auth

#### 4. CloudWorks API
- **Purpose**: Manage CloudWorks processes and tasks
- **Auth**: Likely bearer token (needs confirmation)
- **Source of Truth**: Apiary docs + (possibly) live testing
- **Key Points**: Auth scheme and server URL still unconfirmed — see `cloudworks/README.md`

### Medium Priority (Regularly Used)

#### 5. SCIM API
- **Purpose**: System for Cross-domain Identity Management (user/group provisioning)
- **Auth**: Bearer token (SCIM standard)
- **Source of Truth**: Apiary docs + SCIM ResourceTypes/ResourceSchema from live API
- **Key Points**:
  - SCIM is a standard (RFC 7644), so much behavior is expected
  - Live API returns ResourceTypes and ResourceSchema endpoints that define available resources
  - Postman collection does not cover SCIM

#### 6. ALM API
- **Purpose**: Application Lifecycle Management (source control, versioning)
- **Auth**: Likely bearer token or Anaplan-specific (needs confirmation)
- **Source of Truth**: Apiary docs + live testing
- **Key Points**: Unknown pending investigation

#### 7. Audit API
- **Purpose**: Access audit logs and compliance data (SIEM integration, compliance tracking)
- **Auth**: `AnaplanAuthToken` / OAuth bearer access token; requires the **Tenant Auditor** role (confirmed via live testing)
- **Source of Truth**: Apiary (`auditservice`) + live testing
- **Key Points**:
  - **Live-tested end-to-end (issues #58–#61)**: `GET /events` role/OAuth auth, the `AuditEvent` envelope and field contract, `type` filtering, date-range and pagination, and CEF (`text/plain`) output. Paths are populated and hand-maintained.
  - Base URL confirmed as `https://audit.anaplan.com/audit/api/1` (unique host, not `api.anaplan.com`)
  - Behaviors confirmed: the `type` filter recognizes more values than originally documented; the queried date range is capped at 30 days (default 30-day window); `limit` over 10000 is honored; CEF output is unpaginated — see `audit/README.md`

### Lower Priority (Rarely Used or Specialty)

#### 8. Financial Consolidation API
- **Purpose**: Specialized API for financial consolidation workflows
- **Auth**: Unknown (needs investigation)
- **Source of Truth**: Apiary docs only
- **Key Points**: 
  - Lower priority; may skip if insufficient documentation
  - No Postman collection available
  - May have limited live testing

#### 9. Administration API
- **Purpose**: Bulk user management — import users from CSV, export all users to CSV
- **Auth**: `AnaplanAuthToken` only — `Bearer` rejected with empty 401 (confirmed via live testing); accepts both basic-auth tokens and OAuth Authorization Code access tokens under the `AnaplanAuthToken` scheme; requires the **Tenant Administrator** role
- **Source of Truth**: Anaplan help documentation (no Apiary or Postman source)
- **Key Points**:
  - Two endpoints: `PUT /users/import` (207 Multi-Status) and `GET /users/export` (text/csv)
  - CSV columns: `username, first_name, last_name, licenses`; max 500 rows per import
  - **Live-tested (issue #120)**: auth schemes, regional server coverage, and role-gated error behavior all confirmed
  - 11/12 regional servers confirmed via probe (`au1a.api2.anaplan.com` unreachable); all 12 entries now in spec
  - Confirmed discrepancies: role-denied returns `500 INTERNAL_SERVER_ERROR` (basic-auth token) or `401 ACCESS_CONTROL_DENIED` (OAuth token) instead of the spec-documented 403; full 200 path requires an account with Tenant Administrator role — see `administration/README.md`

#### 10. Exception Users API
- **Purpose**: Manage exception users (users who can bypass SSO enforcement)
- **Auth**: `AnaplanAuthToken` (confirmed — works with both Authentication API tokens and OAuth Authorization Code access tokens); `AnaplanApiKey` (confirmed); `Bearer` rejected with `FAILURE_BAD_HEADER` even for valid OAuth tokens
- **Source of Truth**: Apiary docs + Postman collection (top-level "Exception Users" folder, 4 requests) + live testing (issue #51)
- **Key Points**:
  - Requires Tenant Security Admin role
  - **Fully live-tested (issue #51)**: auth schemes, search by workspace, search by user, and PATCH invalid-op error probe all confirmed
  - Two endpoints: `PATCH` assign/unassign a user, `POST` search (by workspace or by user)
  - POST search uses `oneOf` request body — `workspaceGuid` or `userGuid` (mutually exclusive)
  - Error response body confirmed: `{ "status": "...", "statusMessage": "..." }` (Apiary called it `message`; live testing shows `statusMessage`)

## Key Patterns and Variations

### Authentication

Anaplan APIs use **at least two different authentication schemes**:

1. **Bearer Token** (standard, RFC 6750)
   ```
   Authorization: Bearer <token>
   ```
   Used by: OAuth, SCIM, and most modern Anaplan APIs

2. **Anaplan-Specific Token** (proprietary)
   ```
   Authorization: AnaplanAuthToken <token>
   ```
   OR
   ```
   AnaplanAuthToken: <token>
   ```
   Used by: Integration API (and possibly others)

3. **HTTP Basic Auth** (for token generation only)
   Used by: Authentication API to generate tokens

Each API spec documents which scheme(s) it supports. Code generators should check the spec for the correct auth pattern rather than assuming consistency.
Every spec must contain securitySchemes that it supports and global security if standard across all paths or path-level security.

### Schema Extraction

Schemas are extracted to `components/schemas` only if they are actually reused/duplicated in the spec. Single-use schemas stay inline for readability. This keeps specs lean and avoids unnecessary indirection for one-off objects.

### Pagination

Pagination patterns differ across APIs. Some may use:
- Query parameters (`offset`, `limit`)
- Link headers
- Cursor-based pagination
- SCIM list responses (`startIndex`, `itemsPerPage`)

Each spec documents pagination for its endpoints.

### Error Responses

Error response formats vary. Apiary docs and live testing will reveal the actual format for each API.

## Sources and Confidence Levels

### Accessing Apiary documentation

Each Anaplan API is documented on Apiary. The public documentation page renders via JavaScript, but the underlying content can be fetched as JSON directly:

```
https://jsapi.apiary.io/apis/{api-identifier}.json
```

For example, the OAuth API (`anaplanoauth2service`) is at:
`https://jsapi.apiary.io/apis/anaplanoauth2service.json`

The Apiary identifier is the subdomain from the API's documentation URL (e.g. `https://{identifier}.docs.apiary.io/`). This JSON endpoint is readable by automated tools without a browser and returns structured endpoint documentation.

| API | Apiary identifier |
|-----|------------------|
| Authentication | `anaplauthentication` *(verify)* |
| OAuth | `anaplanoauth2service` |
| Integration | `anaplan` *(verify)* |
| CloudWorks | *(verify)* |
| SCIM | `scimapi` |
| ALM | `almapi` |
| Audit | `auditservice` |
| Financial Consolidation | *(verify)* |
| Exception Users | *(verify)* |
| Administration | — (no Apiary documentation exists) |

### Accessing the Postman collection

The official Anaplan Postman collection is published and maintained by Anaplan at:

**https://www.postman.com/apiplan/official-anaplan-collection/**

It covers 8 of the 10 APIs (all except Financial Consolidation and Administration) and is the primary source for endpoint discovery for those APIs. As Anaplan migrates documentation away from Apiary, the Postman collection is becoming the authoritative reference.

#### Local copy

A local copy of the collection is saved at `sources/Official Anaplan Collection.postman_collection.json`. Use this file for offline reference and scripted processing rather than hitting the Postman API repeatedly.

#### postman-spec.yaml

`sources/postman-spec.yaml` is a YAML conversion of the collection generated from a personal fork of the official Anaplan collection. It is produced by exporting the forked collection from Postman in OpenAPI format. This file captures the collection state at a point in time and may lag behind updates to the official collection.

### Canonical API reference links

Single source of truth for each API's official anaplan.com reference page. Spec
parameter descriptions cite these when an ID is **sourced from a different API**
(e.g. `modelId` consumed by CloudWorks/Audit/ALM but minted by Integration) —
see [ADR 0004](docs/adr/0004-id-source-path-descriptions.md). When a URL changes,
edit it here only.

| API | Canonical reference |
|-----|---------------------|
| Integration | https://help.anaplan.com/integration-api-v20-3107aa54-d12b-4c48-9550-3561c84adbb2 |
| CloudWorks | https://help.anaplan.com/cloudworks-api-94bfcdc3-fff0-48d6-be9c-0e1bba2e889c |
| SCIM | https://help.anaplan.com/scim-api-f6a801cd-c253-4ab9-ba03-dac09fd71f7c |
| ALM | https://help.anaplan.com/application-lifecycle-management-api-2565cfa6-e0c2-4e24-884e-d0df957184d6 |
| Audit | https://help.anaplan.com/audit-api-0dbbe4be-d5b7-4075-89ad-fa922f88e855 |
| Financial Consolidation | https://help.anaplan.com/anaplan-financial-consolidation-api-e83345d8-0509-4228-b532-679ee398a9d5 |
| Exception Users | https://help.anaplan.com/exception-users-api--814cd4ae-0e80-4910-8500-988ad089eef1 |
| Administration | https://help.anaplan.com/administration-api-34c09687-9110-4672-b31b-0f959f67ea32 |
| Authentication | https://help.anaplan.com/authentication-service-api-4060eddf-fe4e-4220-96f6-267d54502ed6 |
| OAuth | https://help.anaplan.com/authentication-service-api-4060eddf-fe4e-4220-96f6-267d54502ed6 |

OAuth and Authentication share the **Authentication service API** page; both mint
tokens rather than chainable resource IDs, so they are rarely cited as a
cross-API ID source. These are anaplan.com landing pages, not Apiary blueprint
links — Apiary links are dropped from specs (ADR 0004), these replace them.

### Regional server URLs

Each API has region-specific base URLs. Source: [URL, IP, and allowlist requirements](https://support.anaplan.com/url-ip-and-allowlist-requirements-c8235c7d-8af2-413b-a9ff-d465978806b9) (also saved as `sources/oauth/URL, IP, and allowlist requirements _ Anaplan Support.pdf`).

The URL pattern varies by API type:

| API type | URL pattern |
|----------|-------------|
| OAuth 2.0 API | `https://{region}.app.anaplan.com` |
| Integration, ALM, SCIM, Exception Users, Administration, CloudWorks | `https://{region}.api.anaplan.com` |
| Authentication (Auth) API | `https://{region}.auth.anaplan.com` |
| Audit API | `https://audit.anaplan.com/audit/api/1` (single dedicated global host — **not** regional `api.anaplan.com`; confirmed via live testing) |

Full regional URL table (19 regions):

| Region | Description | App (OAuth) | API | Auth |
|--------|-------------|-------------|-----|------|
| us1 | Data Center - US East | `us1a.app.anaplan.com` | `api.anaplan.com` | `auth.anaplan.com` |
| us2 | Data Center - US West | `us1a.app.anaplan.com` | `api.anaplan.com` | `auth.anaplan.com` |
| us5 | Cloud - US East | `us1a.app.anaplan.com` | `api.anaplan.com` | `auth.anaplan.com` |
| us7 | Cloud - US | `us1a.app.anaplan.com` | `api.anaplan.com` | `auth.anaplan.com` |
| us9 | Cloud - US | `us9.app.anaplan.com` | `us9.api.anaplan.com` | `us9.auth.anaplan.com` |
| eu1 | Data Center - Netherlands | `us1a.app.anaplan.com` | `api.anaplan.com` | `auth.anaplan.com` |
| eu2 | Data Center - Germany | `us1a.app.anaplan.com` | `api.anaplan.com` | `auth.anaplan.com` |
| eu3 | Cloud - Europe | `eu3.app.anaplan.com` | `eu3.api.anaplan.com` | `eu3.auth.anaplan.com` |
| eu4 | Cloud - Europe | `us1a.app.anaplan.com` | `api.anaplan.com` | `auth.anaplan.com` |
| eu5 | Cloud - Europe | `eu5.app.anaplan.com` | `eu5.api.anaplan.com` | `eu5.auth.anaplan.com` |
| gb1 | Cloud - UK | `gb1.app.anaplan.com` | `gb1.api.anaplan.com` | `gb1.auth.anaplan.com` |
| ap1 | Cloud - Japan | `us1a.app.anaplan.com` | `api.anaplan.com` | `auth.anaplan.com` |
| au1 | Cloud - Australia | `au1a.app2.anaplan.com` | `au1a.api2.anaplan.com` *(verify)* | `au1a.app2.anaplan.com` |
| ca1 | Cloud - Canada | `ca1a.app.anaplan.com` | `ca1a.api.anaplan.com` *(verify)* | `ca1a.auth.anaplan.com` |
| sg1 | Cloud - Singapore | `sg1.app.anaplan.com` | `sg1.api.anaplan.com` | `sg1.auth.anaplan.com` |
| ae1 | Cloud - UAE | `ae1.app.anaplan.com` | `ae1.api.anaplan.com` | `ae1.auth.anaplan.com` |
| in1 | Cloud - India | `in1.app.anaplan.com` | `in1.api.anaplan.com` | `in1.auth.anaplan.com` |
| id1 | Cloud - Indonesia | `id1.app.anaplan.com` | `id1.api.anaplan.com` | `id1.auth.anaplan.com` |
| me1 | Cloud - Saudi Arabia | `me1.app.anaplan.com` | `me1.api.anaplan.com` | `me1.auth.anaplan.com` |

Legacy regions (us1–us7, eu1, eu2, eu4, ap1) share the older non-prefixed `api.anaplan.com` / `auth.anaplan.com` / `us1a.app.anaplan.com` endpoints. Newer cloud regions have fully independent regional endpoints.

> **Legacy Integration API endpoint retired**: The Integration API (and related APIs: ALM, SCIM, Audit, Exception Users, CloudWorks) was historically also accessible via `https://us1a.app.anaplan.com/2` and equivalent region-prefixed `app.anaplan.com/2` URLs. Anaplan has retired these legacy endpoints. The modern `api.anaplan.com` endpoints listed above are the sole supported base URLs. All specs use the modern endpoints.

### Confidence table

`scripts/build_spec.py` is a one-time bootstrap per API. Once live tests exist the spec is hand-maintained — do not run it against that spec again (see `CLAUDE.md`).

| API | Apiary | Postman | Extracted Schemas | Live Testing | Confidence | Spec lifecycle |
|-----|--------|---------|-------------------|--------------|------------|----------------|
| Authentication | ✓ | ✓ | — | High | High | hand-maintained (do not rebuild) |
| OAuth | ✓ | Partial | — | Partial (device flow happy path + error cases; auth code flow not automatable) | High | hand-maintained (do not rebuild) |
| Integration | ✓ | ✓ | ✓ | High | High | hand-maintained (do not rebuild) |
| CloudWorks | ✓ | ✓ | — | Medium | Medium | hand-maintained (do not rebuild) |
| SCIM | ✓ | ✓ | ✓ | Medium | Medium | hand-maintained (do not rebuild) |
| ALM | ✓ | ✓ | — | Medium | Medium | hand-maintained (do not rebuild) |
| Audit | ✓ | ✓ | — | High (events path: auth/role, event contract, filtering/pagination, CEF — issues #58–#61) | High | hand-maintained (do not rebuild) |
| Financial Consolidation | ✓ | — | — | Low | Low | hand-maintained (do not rebuild) |
| Exception Users | ✓ | ✓ | ✓ | High (auth schemes, search by workspace/user, PATCH error probe — issue #51) | High | hand-maintained (do not rebuild) |
| Administration | — | — | — | Low (auth schemes, regional servers, role-gated error behavior — issue #120; full 200 path requires Tenant Administrator) | Low | hand-maintained (do not rebuild) |

## Project Structure

```
/
├── README.md                 (audience-first overview: what the specs are, how to use them)
├── CONTRIBUTING.md           (tooling, build pipeline, how to run tests)
├── CONTEXT.md                (this file)
├── CLAUDE.md                 (agent instructions)
├── SCAN.md                   (how to run the live endpoint access scanner)
├── LICENSE  NOTICE           (Apache-2.0 + Anaplan disclaimer)
├── docs/
│   ├── TESTING.md            (live-test setup, env vars, flags)
│   ├── PRD.md                (original PRD, historical)
│   ├── adr/                  (architecture decision records)
│   └── agents/               (agent skill docs)
├── scripts/                  (build/maintenance tooling)
│   ├── build_spec.py  converter.py  schema_importer.py
│   ├── revise_spec.py  validate.py  sync_yaml.py
│   ├── scan_endpoint_access.py  (live per-endpoint access scan -> CSV; see SCAN.md)
│   └── oauth/                (interactive OAuth flow helpers)
├── sources/                  (raw source data)
│   ├── Official Anaplan Collection.postman_collection.json
│   ├── postman-spec.yaml     (OpenAPI export from forked collection)
│   ├── audit/  alm/  exception/   (Apiary blueprints/metadata)
│   ├── integration/          (objectSchema.json, modelObjectschema.json)
│   ├── scim/                 (scim-schema.json)
│   └── oauth/                (reference PDFs)
├── tests/                    (pytest suite: unit/contract + *_live.py)
└── <api>/                    (one per API: authentication, oauth, integration,
    ├── README.md              cloudworks, scim, alm, audit,
    ├── <api>-openapi.json     financial-consolidation, exception, administration)
    └── <api>-openapi.yaml
```

Each API folder contains:
- **README.md**: sources, auth scheme(s), and behavior discovered during live testing
- **`<api>-openapi.json`**: the canonical OpenAPI 3.0 spec (for code generation)
- **`<api>-openapi.yaml`**: YAML counterpart, regenerated from the JSON

## Maintenance

All 10 specs now exist. Ongoing work is refinement rather than initial authoring:

- **All 10 specs are hand-maintained** and must be edited by hand — do **not**
  re-run `scripts/build_spec.py` against any of them
  (see [CONTRIBUTING.md](CONTRIBUTING.md)).
- Record any behavior that differs from the official docs in the relevant
  `<api>/README.md` under "Discrepancies".
- Live-test setup is documented in [docs/TESTING.md](docs/TESTING.md).
- To confirm the minimum role / access level required by each endpoint, run the
  live access scanner (`scripts/scan_endpoint_access.py`): it authenticates a
  user via OAuth, probes every operation across the seven resource APIs, and
  writes a per-endpoint CSV of authorization outcomes. Run it from accounts with
  different roles to establish the gates empirically. See [SCAN.md](SCAN.md).
