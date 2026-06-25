# PRD: OpenAPI 3.0 Specifications for Anaplan APIs

> **Historical document.** This is the original product requirements document
> that kicked off the project, retained for context. Status fields and phasing
> below reflect the project's early plan, not its current state — see
> [`../CONTEXT.md`](../CONTEXT.md) for current per-API status and confidence.

## Problem Statement

Anaplan provides 10 publicly available REST APIs, but their official Apiary documentation is outdated and incomplete. There are no machine-readable OpenAPI specifications available, making it difficult to:

- Generate API client libraries in multiple languages (Python, Java, TypeScript, etc.)
- Build tools that depend on precise API contracts (like MCP servers)
- Create community-maintained, accurate API documentation
- Validate API behavior programmatically

Additionally, these APIs were built by different teams at different times and exhibit variations in authentication schemes (Bearer tokens vs. Anaplan-specific tokens), pagination patterns, and error response formats. This heterogeneity makes it harder to abstract over them without losing accuracy.

## Solution

Generate accurate, machine-readable OpenAPI 3.0 JSON specifications for all 10 Anaplan APIs by:

1. **Synthesizing multiple sources of truth**: Apiary documentation (canonical but outdated), Postman collection (for 3 APIs), extracted JSON schemas from actual API responses, and live API testing
2. **Testing against a live Anaplan instance** to validate specs and discover undocumented behaviors (error cases, required fields not mentioned in docs)
3. **Documenting each API as-is**, preserving their actual authentication, pagination, and error patterns rather than normalizing them
4. **Publishing specs as community documentation**, filling gaps left by outdated official docs

The resulting OpenAPI specs will be suitable for code generation tools (OpenAPI generators, MCP servers, etc.) and serve as authoritative community-maintained documentation.

## User Stories

1. As an API client code generator, I want accurate OpenAPI 3.0 specifications, so that the generated code matches actual API behavior
2. As a Python developer, I want to generate an Anaplan API client from an OpenAPI spec, so that I can use the API in my application
3. As a Node.js developer, I want to generate TypeScript typings from an Anaplan API spec, so that I can have type-safe API calls
4. As an MCP server developer, I want machine-readable API contracts, so that I can build Claude integrations for Anaplan APIs
5. As a developer using the Integration API heavily, I want comprehensive, tested specifications, so that I can trust generated code for production use
6. As a developer using the SCIM API, I want documentation of how Anaplan's SCIM implementation differs from the RFC, so that I can understand what to expect
7. As a developer working with Authentication API, I want to know which auth schemes are supported and exactly how they're enforced, so that I can implement correct authentication
8. As a developer using CloudWorks, I want accurate parameter documentation and error cases, so that I can handle edge cases properly
9. As a maintainer of low-priority APIs (Exception Users, Financial Consolidation), I want specs even with lower confidence, so that I have something better than nothing
10. As a community contributor, I want to know which APIs have been thoroughly tested and which have lower coverage, so that I can prioritize testing efforts
11. As a code generator, I want to detect authentication variations across APIs, so that my output can use the correct auth scheme for each API
12. As a code generator, I want to detect pagination patterns, so that my output can handle offset/limit, cursors, or SCIM list responses correctly
13. As a developer, I want a clear record of discrepancies between Apiary docs and actual API behavior, so that I can understand what's documented vs. what's real
14. As an API maintainer, I want to know which endpoints were tested against a live instance, so that I can gauge confidence in the spec
15. As a new contributor, I want clear instructions on how to extend or refine specs, so that I can add missing endpoints or fix errors

## Implementation Decisions

### API Coverage and Scope

- **10 APIs total**, documented in priority order: Authentication, OAuth, Integration, CloudWorks, SCIM, ALM, Audit, Financial Consolidation, Exception Users, Administration
- Each API gets its own folder with an OpenAPI 3.0 JSON spec and a README documenting sources, testing approach, and discrepancies
- Status tracking in CONTEXT.md will indicate completion level for each API (not-started, in-progress, complete)

### Source Hierarchy and Methodology

**Apiary is canonical** — the official (albeit outdated) source of truth for each API's endpoints, parameters, and general structure.

**Methodology varies by API based on available sources:**

- **Integration API**: Start with Postman collection structure → compare to Apiary → validate against live instance → extract and integrate JSON schemas
- **Authentication, OAuth**: Use Postman collection + Apiary → validate against live instance
- **SCIM**: Use SCIM ResourceTypes/ResourceSchema from live API + Apiary docs (SCIM is standardized, so live API defines the schema)
- **CloudWorks, ALM, Audit**: Apiary + live testing (no Postman available)
- **Financial Consolidation, Exception Users**: Apiary + limited/no live testing (lower priority, lower confidence)

### Document APIs As-Is, Not Normalized

Rather than abstracting over authentication variations, pagination differences, and error formats, **each spec documents the actual API behavior**. This decision is captured in ADR 0001.

- **Authentication**: Some APIs use Bearer tokens, others use Anaplan-specific tokens; the spec documents which scheme(s) each API uses
- **Pagination**: Different APIs use different pagination patterns (offset/limit, cursors, SCIM list responses); each spec documents its actual pattern
- **Error responses**: Error response shapes vary; each spec documents the actual format

Code generators that consume these specs can detect these variations and generate appropriate client code.

### Validation and Testing

- **OpenAPI 3.0 validation**: Each spec is validated using `openapi-spec-validator` (Python library) in YAML format
- **Live API testing**: All endpoints are tested against a live Anaplan instance using Python test clients (anaplan-sdk for high-level methods, httpx for low-level endpoints)
- **Testing coverage**: High-priority APIs get comprehensive testing; lower-priority APIs may have limited testing
- **Discrepancies documentation**: When live testing reveals behavior not documented in Apiary (missing error cases, required fields marked optional, etc.), this is documented in the API's README.md

### Tooling and Automation

**Postman → OpenAPI Converter**: 
- Scaffolds the Integration API's OpenAPI spec from the Postman collection JSON
- Reduces manual transcription; output requires refinement (schema definitions, response documentation, error cases)
- Applicable only to APIs with Postman coverage (Integration, Authentication, OAuth)

**OpenAPI Validator**:
- Python script using `openapi-spec-validator`
- Validates specs in YAML format
- Runs as quality gate before marking specs complete

**Python Test Framework**:
- Standardized template for systematic endpoint testing
- Uses anaplan-sdk (where available) or httpx (for endpoints not exposed in SDK)
- Tests all endpoints, documents what was tested, and captures actual responses for validation

### Status Tracking

CONTEXT.md includes a status column in the 10 APIs table:
- `not-started` — No spec yet
- `in-progress` — Spec is being written/tested
- `complete` — Spec is validated and ready for use

## Testing Decisions

### What Makes a Good Test

A good test exercises external API behavior (endpoints, parameters, responses) without testing implementation details of the OpenAPI spec generator or test framework.

### Modules to Test

1. **Postman → OpenAPI Converter**
   - Unit tests on conversion logic (path mapping, parameter extraction, schema reference generation)
   - Test against the actual Postman collection to ensure correct output structure

2. **OpenAPI 3.0 Validator**
   - Integration test: validate each generated spec
   - Success criteria: spec passes `openapi-spec-validator` without errors

3. **Python Test Framework Template**
   - Example integration test against live API for a representative API (Integration or SCIM)
   - Demonstrates endpoint testing, response capture, error case handling

4. **API Specs** (validation, not unit tests)
   - Each spec is validated by the OpenAPI validator
   - Live endpoint testing confirms spec accuracy

## Out of Scope

- **Adapter/wrapper services**: Creating a unified API layer that normalizes authentication or pagination
- **Non-OpenAPI formats**: Only OpenAPI 3.0 JSON is produced (no RAML, GraphQL, gRPC specs)
- **SDKs or client libraries**: This project produces specs; code generation and SDKs are downstream
- **Normalization**: We document APIs as-is; normalization happens in code generators that consume the specs
- **Private or undocumented APIs**: Only publicly documented Anaplan APIs are included
- **Real-time API monitoring**: No ongoing monitoring or alerting if actual API behavior diverges from specs

## Further Notes

### Priority and Phased Delivery

- **Phase 1 (High Priority)**: Authentication, OAuth, Integration APIs (heavily used, Postman available)
- **Phase 2 (Medium Priority)**: CloudWorks, SCIM, ALM, Audit (important but less frequently used)
- **Phase 3 (Lower Priority)**: Financial Consolidation, Exception Users (specialized/rarely used, lower confidence acceptable)

### Maintenance and Community Contributions

Once published, specs can be refined by the community:
- Report missing endpoints or parameters as GitHub issues
- Contribute live testing results and discrepancy findings
- Submit pull requests with improved specs

### Related Artifacts

- **CONTEXT.md**: Overview of all 10 APIs, their sources, and confidence levels
- **docs/adr/0001-document-apis-as-is.md**: Rationale for documenting variations rather than normalizing
- **Per-API READMEs**: Testing notes, discrepancies, and source references for each API
