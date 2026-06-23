# Anaplan OpenAPI Specifications

Community-maintained OpenAPI 3.0 specifications for the 9 publicly documented
Anaplan REST APIs.

Anaplan's official API documentation is spread across an outdated
Apiary site and a new Postman collection, without detailed
machind-readable OpenAPI specs. This project fills that gap: accurate,
testable OpenAPI 3.0 specs you can feed directly to code generators,
MCP server tooling, and your own documentation.

## Who this is for

- **Client code generation** — point an OpenAPI generator at a spec to produce a
  typed client in Python, TypeScript, Java, Go, etc.
- **MCP server / tooling developers** — build integrations against precise,
  machine-readable API contracts.
- **Developers integrating with Anaplan** — use the specs (and per-API READMEs)
  as accurate reference documentation, including behaviors not in the official
  docs.

The specs document each API **as it actually behaves**, validated against a live
Anaplan instance where possible — including auth schemes, pagination, and error
shapes that differ from API to API (see [ADR 0001](docs/adr/0001-document-apis-as-is.md)).

## Using a spec

Each API has its own directory containing the canonical JSON spec and a generated
YAML copy:

```
<api>/<api>-openapi.json   # canonical OpenAPI 3.0 spec
<api>/<api>-openapi.yaml   # YAML equivalent (generated from the JSON)
```

Download the file and point your tool at it, e.g.:

```sh
openapi-generator-cli generate -i integration/integration-openapi.json -g python -o ./client
```

## APIs

| API | Directory | Spec | Confidence |
|-----|-----------|------|------------|
| Authentication | [`authentication/`](authentication/) | [`authentication-openapi.json`](authentication/authentication-openapi.json) | High — live-tested |
| OAuth 2.0 | [`oauth/`](oauth/) | [`oauth-openapi.json`](oauth/oauth-openapi.json) | High — live-tested |
| Integration | [`integration/`](integration/) | [`integration-openapi.json`](integration/integration-openapi.json) | High — live-tested |
| CloudWorks | [`cloudworks/`](cloudworks/) | [`cloudworks-openapi.json`](cloudworks/cloudworks-openapi.json) | Medium |
| SCIM | [`scim/`](scim/) | [`scim-openapi.json`](scim/scim-openapi.json) | Medium |
| ALM | [`alm/`](alm/) | [`alm-openapi.json`](alm/alm-openapi.json) | Medium |
| Audit | [`audit/`](audit/) | [`audit-openapi.json`](audit/audit-openapi.json) | High — live-tested |
| Financial Consolidation | [`financial-consolidation/`](financial-consolidation/) | [`financial-consolidation-openapi.json`](financial-consolidation/financial-consolidation-openapi.json) | Low |
| Exception Users | [`exception/`](exception/) | [`exception-openapi.json`](exception/exception-openapi.json) | High — live-tested |
| Administration | [`administration/`](administration/) | [`administration-openapi.json`](administration/administration-openapi.json) | Low — live-tested (role-gated; full 200 path requires Tenant Administrator) |

Each API directory's **README** documents its sources, auth scheme(s), and any
behavior discovered during live testing that differs from the official docs.
The Confidence column above mirrors the canonical [confidence table in
`CONTEXT.md`](CONTEXT.md#confidence-table) (which also covers sources, spec
lifecycle, and regional server URLs); a test keeps the two in sync.

## Authentication at a glance

Anaplan APIs use three authentication schemes depending on the API. Each spec's
`securitySchemes` is authoritative; this is a summary:

| Scheme | Header | Used by |
|--------|--------|---------|
| HTTP Basic | `Authorization: Basic <base64>` | Authentication API (to obtain a token) |
| Bearer Token | `Authorization: Bearer <token>` | OAuth, Integration, CloudWorks, SCIM, ALM, Audit |
| AnaplanAuthToken | `Authorization: AnaplanAuthToken <token>` | Integration, Exception Users |

Tokens are obtained via the [Authentication API](authentication/) or
[OAuth 2.0 API](oauth/).

## Documentation sources

Anaplan is migrating its API documentation from [Apiary](https://apiary.io) to an
official [Postman collection](https://www.postman.com/apiplan/official-anaplan-collection/).
Specs here are built from both sources and augmented by live API testing. Raw
source data is kept under [`sources/`](sources/).

## Contributing & local development

Tooling, the spec build pipeline, and how to run the test suite (including live
tests) are documented in [CONTRIBUTING.md](CONTRIBUTING.md) and
[docs/TESTING.md](docs/TESTING.md).

## License & disclaimer

Licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE).

This is a community-maintained project and is **not affiliated with, endorsed by,
or sponsored by Anaplan, Inc.** "Anaplan" is a trademark of Anaplan, Inc.
