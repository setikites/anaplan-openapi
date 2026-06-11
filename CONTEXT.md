# Anaplan OpenAPI Specification Project

## Purpose

This project generates OpenAPI 3.0 JSON specifications for the 9 publicly available Anaplan REST APIs. These specs are intended for:
- **API client code generation** (via MCP servers and other tools)
- **Community-maintained documentation** (since official Anaplan docs are outdated)

## The 9 Anaplan APIs

Anaplan has 9 publicly documented REST APIs, each with different characteristics, authentication schemes, and documentation quality. This project documents them as-is rather than normalizing across them, since they were built by different teams at different times.

### High Priority (Heavily Used)

#### 1. Authentication API
- **Purpose**: Generate authentication tokens for other Anaplan APIs
- **Auth**: HTTP Basic credentials → returns token (different from other APIs)
- **Source of Truth**: Apiary docs + Postman collection
- **Testing**: High (Postman available; thorough live testing done)
- **Status**: Complete — hand-maintained (live-tested; do not rebuild)
- **Key Points**: 
  - Token generation is a prerequisite for other APIs
  - Supports both basic auth (username/password) and certificate-based auth

#### 2. OAuth API
- **Purpose**: OAuth 2.0 token generation
- **Auth**: OAuth 2.0 flow
- **Source of Truth**: Apiary docs only (no Postman collection available for OAuth)
- **Testing**: Partial — device flow initiation and error cases automated; end-to-end device approval and Authorization Code Grant login require browser interaction and cannot be automated
- **Status**: complete
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
- **Testing**: High (most complete info; Postman available; schemas extracted from live API)
- **Status**: Complete — hand-maintained (live-tested; do not rebuild)
- **Key Points**:
  - Most mature API with extensive Apiary documentation
  - Postman collection covers common workflows
  - JSON schemas extracted from actual `/objects/` responses
  - Different endpoints may accept bearer token or Anaplan-specific auth

#### 4. CloudWorks API
- **Purpose**: Manage CloudWorks processes and tasks
- **Auth**: Likely bearer token (needs confirmation)
- **Source of Truth**: Apiary docs + (possibly) live testing
- **Testing**: Medium
- **Status**: Spec generated; live test file present (`tests/test_cloudworks_live.py`) — see `cloudworks/README.md`
- **Key Points**: Unknown pending investigation

### Medium Priority (Regularly Used)

#### 5. SCIM API
- **Purpose**: System for Cross-domain Identity Management (user/group provisioning)
- **Auth**: Bearer token (SCIM standard)
- **Source of Truth**: Apiary docs + SCIM ResourceTypes/ResourceSchema from live API
- **Testing**: Medium (API responses provide schema definitions)
- **Status**: Spec generated (response schemas extracted); live test file present (`tests/test_scim_live.py`)
- **Key Points**:
  - SCIM is a standard (RFC 7644), so much behavior is expected
  - Live API returns ResourceTypes and ResourceSchema endpoints that define available resources
  - Postman collection does not cover SCIM

#### 6. ALM API
- **Purpose**: Application Lifecycle Management (source control, versioning)
- **Auth**: Likely bearer token or Anaplan-specific (needs confirmation)
- **Source of Truth**: Apiary docs + live testing
- **Testing**: Medium (moderate usage)
- **Status**: Hand-maintained — live tests at `tests/test_alm_live.py` (see `alm/README.md`)
- **Key Points**: Unknown pending investigation

#### 7. Audit API
- **Purpose**: Access audit logs and compliance data (SIEM integration, compliance tracking)
- **Auth**: Likely bearer token (needs confirmation via live testing)
- **Source of Truth**: Apiary (`auditservice`) + live testing
- **Testing**: Medium (no Postman, moderate usage)
- **Status**: Spec generated (`audit/audit-openapi.json`); live test file present (`tests/test_audit_live.py`)
- **Key Points**:
  - Apiary blueprint is not publicly readable; spec has empty paths — populate via live testing
  - Apiary lists production URL as `https://audit.anaplan.com/audit/api/1/` (unique host, not `api.anaplan.com`)
  - Both `audit.anaplan.com` and `api.anaplan.com` servers listed in spec; resolve correct base URL during live testing

### Lower Priority (Rarely Used or Specialty)

#### 8. Financial Consolidation API
- **Purpose**: Specialized API for financial consolidation workflows
- **Auth**: Unknown (needs investigation)
- **Source of Truth**: Apiary docs only
- **Testing**: Low (lower priority; limited live testing)
- **Status**: Spec generated; minimal live test (`tests/test_financial_consolidation_live.py`); lowest confidence
- **Key Points**: 
  - Lower priority; may skip if insufficient documentation
  - No Postman collection available
  - May have limited live testing

#### 9. Exception Users API
- **Purpose**: Manage exception users (users who can bypass SSO enforcement)
- **Auth**: `AnaplanApiKey` (confirmed via live testing); Bearer (service-to-service only); AnaplanAuthToken rejected for API key credentials
- **Source of Truth**: Apiary docs + Postman collection (top-level "Exception Users" folder, 4 requests) + sample responses in `exception/README.md`
- **Testing**: Low (lower priority; limited or no live testing expected)
- **Status**: Spec complete (`exception/exception-openapi.json`); auth scheme confirmed via live testing; search contract blocked pending Tenant Security Admin role
- **Key Points**:
  - Requires Tenant Security Admin role
  - Two endpoints: `PATCH` assign/unassign a user, `POST` search (by workspace or by user)
  - POST search uses `oneOf` request body — `workspaceGuid` or `userGuid` (mutually exclusive)
  - Error response body shape modeled from Apiary descriptions; confirm field names via live testing (issue #51)

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

### Accessing the Postman collection

The official Anaplan Postman collection is published and maintained by Anaplan at:

**https://www.postman.com/apiplan/official-anaplan-collection/**

It covers 8 of the 9 APIs (all except Financial Consolidation) and is the primary source for endpoint discovery for those APIs. As Anaplan migrates documentation away from Apiary, the Postman collection is becoming the authoritative reference.

#### Local copy

A local copy of the collection is saved at `sources/Official Anaplan Collection.postman_collection.json`. Use this file for offline reference and scripted processing rather than hitting the Postman API repeatedly.

#### postman-spec.yaml

`sources/postman-spec.yaml` is a YAML conversion of the collection generated from a personal fork of the official Anaplan collection. It is produced by exporting the forked collection from Postman in OpenAPI format. This file captures the collection state at a point in time and may lag behind updates to the official collection.

### Regional server URLs

Each API has region-specific base URLs. Source: [URL, IP, and allowlist requirements](https://support.anaplan.com/url-ip-and-allowlist-requirements-c8235c7d-8af2-413b-a9ff-d465978806b9) (also saved as `sources/oauth/URL, IP, and allowlist requirements _ Anaplan Support.pdf`).

The URL pattern varies by API type:

| API type | URL pattern |
|----------|-------------|
| OAuth 2.0 API | `https://{region}.app.anaplan.com` |
| Integration, ALM, SCIM, Audit, Exception Users, CloudWorks | `https://{region}.api.anaplan.com` |
| Authentication (Auth) API | `https://{region}.auth.anaplan.com` |

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
| CloudWorks | ✓ | ✓ | — | Medium | Medium | bootstrap only |
| SCIM | ✓ | ✓ | ✓ | Medium | Medium | bootstrap only |
| ALM | ✓ | ✓ | — | Medium | Medium | bootstrap only |
| Audit | ✓ | ✓ | — | Medium | Medium | bootstrap only |
| Financial Consolidation | ✓ | — | — | Low | Low | bootstrap only |
| Exception Users | ✓ | ✓ | ✓ | Low | Low | hand-maintained (do not rebuild) |

## Project Structure

```
/
├── README.md                 (audience-first overview: what the specs are, how to use them)
├── CONTRIBUTING.md           (tooling, build pipeline, how to run tests)
├── CONTEXT.md                (this file)
├── CLAUDE.md                 (agent instructions)
├── LICENSE  NOTICE           (Apache-2.0 + Anaplan disclaimer)
├── docs/
│   ├── TESTING.md            (live-test setup, env vars, flags)
│   ├── PRD.md                (original PRD, historical)
│   ├── adr/                  (architecture decision records)
│   └── agents/               (agent skill docs)
├── scripts/                  (build/maintenance tooling)
│   ├── build_spec.py  converter.py  schema_importer.py
│   ├── revise_spec.py  validate.py  sync_yaml.py
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
    ├── <api>-openapi.json     financial-consolidation, exception)
    └── <api>-openapi.yaml
```

Each API folder contains:
- **README.md**: sources, auth scheme(s), and behavior discovered during live testing
- **`<api>-openapi.json`**: the canonical OpenAPI 3.0 spec (for code generation)
- **`<api>-openapi.yaml`**: YAML counterpart, regenerated from the JSON

## Maintenance

All 9 specs now exist. Ongoing work is refinement rather than initial authoring:

- **Hand-maintained specs** (Authentication, OAuth, Integration) have live tests
  and must be edited by hand — do **not** re-run `scripts/build_spec.py` against
  them (see [CONTRIBUTING.md](CONTRIBUTING.md)).
- **Bootstrap specs** (CloudWorks, SCIM, ALM, Audit, Financial Consolidation,
  Exception Users) can be improved by adding live tests and graduating them to
  hand-maintained as coverage grows.
- Record any behavior that differs from the official docs in the relevant
  `<api>/README.md` under "Discrepancies".
- Live-test setup is documented in [docs/TESTING.md](docs/TESTING.md).
