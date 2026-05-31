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
- **Testing**: High (Postman available, expected to have thorough live testing)
- **Status**: Not yet started
- **Key Points**: 
  - Token generation is a prerequisite for other APIs
  - Supports both basic auth (username/password) and certificate-based auth

#### 2. OAuth API
- **Purpose**: OAuth 2.0 token generation
- **Auth**: OAuth 2.0 flow
- **Source of Truth**: Apiary docs + Postman collection
- **Testing**: High (Postman available, heavily used)
- **Status**: Not yet started
- **Key Points**: Alternative to basic auth; modern OAuth 2.0 standard

#### 3. Integration API
- **Purpose**: Core API for managing models, dimensions, modules, versions
- **Auth**: Bearer token (`Authorization: Bearer <token>`) OR `AnaplanAuthToken` header
- **Source of Truth**: Apiary docs + Postman collection + extracted JSON schemas
- **Testing**: High (most complete info; Postman available; schemas extracted from live API)
- **Status**: Not yet started
- **Key Points**:
  - Most mature API with extensive Apiary documentation
  - Postman collection covers common workflows
  - JSON schemas extracted from actual `/objects/` responses
  - Different endpoints may accept bearer token or Anaplan-specific auth

#### 4. CloudWorks API
- **Purpose**: Manage CloudWorks processes and tasks
- **Auth**: Likely bearer token (needs confirmation)
- **Source of Truth**: Apiary docs + (possibly) live testing
- **Testing**: Medium (high priority but no Postman yet)
- **Status**: Not yet started
- **Key Points**: Unknown pending investigation

### Medium Priority (Regularly Used)

#### 5. SCIM API
- **Purpose**: System for Cross-domain Identity Management (user/group provisioning)
- **Auth**: Bearer token (SCIM standard)
- **Source of Truth**: Apiary docs + SCIM ResourceTypes/ResourceSchema from live API
- **Testing**: Medium (API responses provide schema definitions)
- **Status**: Partially started (extracted API response schemas)
- **Key Points**:
  - SCIM is a standard (RFC 7644), so much behavior is expected
  - Live API returns ResourceTypes and ResourceSchema endpoints that define available resources
  - Postman collection does not cover SCIM

#### 6. ALM API
- **Purpose**: Application Lifecycle Management (source control, versioning)
- **Auth**: Likely bearer token or Anaplan-specific (needs confirmation)
- **Source of Truth**: Apiary docs + live testing
- **Testing**: Medium (no Postman, moderate usage)
- **Status**: Not yet started
- **Key Points**: Unknown pending investigation

#### 7. Audit API
- **Purpose**: Access audit logs and compliance data
- **Auth**: Likely bearer token (needs confirmation)
- **Source of Truth**: Apiary docs + live testing
- **Testing**: Medium (no Postman, moderate usage)
- **Status**: Not yet started
- **Key Points**: Unknown pending investigation

### Lower Priority (Rarely Used or Specialty)

#### 8. Financial Consolidation API
- **Purpose**: Specialized API for financial consolidation workflows
- **Auth**: Unknown (needs investigation)
- **Source of Truth**: Apiary docs only
- **Testing**: Low (lower priority; may have limited live testing)
- **Status**: Not yet started
- **Key Points**: 
  - Lower priority; may skip if insufficient documentation
  - No Postman collection available
  - May have limited live testing

#### 9. Exception Users API
- **Purpose**: Manage exception users (users who can bypass SSO enforcement)
- **Auth**: Likely bearer token or Anaplan-specific (needs confirmation)
- **Source of Truth**: Apiary docs + sample responses in `exception/README.md`
- **Testing**: Low (lower priority; limited or no live testing expected)
- **Status**: Partially started (sample responses documented)
- **Key Points**:
  - Lower priority; lower testing coverage
  - Some sample responses already extracted in exception/README.md

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

| API | Apiary | Postman | Extracted Schemas | Live Testing | Confidence |
|-----|--------|---------|-------------------|--------------|-----------|
| Authentication | ✓ | ✓ | — | High | High |
| OAuth | ✓ | ✓ | — | High | High |
| Integration | ✓ | ✓ | ✓ | High | High |
| CloudWorks | ✓ | — | — | Medium | Medium |
| SCIM | ✓ | — | ✓ | Medium | Medium |
| ALM | ✓ | — | — | Medium | Medium |
| Audit | ✓ | — | — | Medium | Medium |
| Financial Consolidation | ✓ | — | — | Low | Low |
| Exception Users | ✓ | — | ✓ | Low | Low |

## Project Structure

```
/
├── CONTEXT.md                                    (this file)
├── README.md                                     (project overview)
├── Official Anaplan Collection.postman_collection.json
├── authentication/
│   ├── README.md                                (Apiary docs + notes)
│   └── authentication-openapi.json              (OpenAPI 3.0 spec)
├── oauth/
│   ├── README.md
│   └── oauth-openapi.json
├── integration/
│   ├── README.md
│   ├── integration-openapi.json
│   ├── objectSchema.json                        (extracted schemas)
│   └── modelObjectschema.json
├── cloudworks/
│   ├── README.md
│   └── cloudworks-openapi.json
├── scim/
│   ├── README.md
│   ├── scim-openapi.json
│   └── SCIM-OpenAPISpec.json                    (reference only)
├── alm/
│   ├── README.md
│   └── alm-openapi.json
├── audit/
│   ├── README.md
│   └── audit-openapi.json
├── financial-consolidation/
│   ├── README.md
│   └── financial-consolidation-openapi.json
└── exception/
    ├── README.md
    └── exception-users-openapi.json
```

Each API folder contains:
- **README.md**: Apiary docs link, sample responses, testing notes, and any discovered discrepancies
- **`{api}-openapi.json`**: The OpenAPI 3.0 specification (canonical spec for code generation)

## Next Steps

1. **Start with Integration API** (most information available)
   - Compare Postman collection structure to Apiary docs
   - Validate endpoints and parameters against live instance
   - Document discovered fields/errors not in Apiary
   - Generate OpenAPI spec

2. **Work through high-priority APIs** in order (Authentication → OAuth → CloudWorks → SCIM → ALM → Audit)

3. **Handle low-priority APIs** last (Financial Consolidation, Exception Users)
   - May be lower confidence due to limited testing

4. **Document findings** in each README.md where specs differ from Apiary docs
