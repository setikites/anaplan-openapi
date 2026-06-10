# Anaplan OpenAPI Specifications

Community-maintained OpenAPI 3.0 specifications for the 9 publicly documented Anaplan REST APIs. Intended for API client code generation, MCP server tooling, and developer reference.

## APIs

| API | Directory | Spec | Status |
|-----|-----------|------|--------|
| Authentication | [`authentication/`](authentication/) | [`authentication-openapi.json`](authentication/authentication-openapi.json) | Hand-maintained (live-tested) |
| OAuth 2.0 | [`oauth/`](oauth/) | [`oauth-openapi.json`](oauth/oauth-openapi.json) | Hand-maintained (live-tested) |
| Integration | [`integration/`](integration/) | [`integration-openapi.json`](integration/integration-openapi.json) | Hand-maintained (live-tested) |
| CloudWorks | [`cloudworks/`](cloudworks/) | [`cloudworks-openapi.json`](cloudworks/cloudworks-openapi.json) | Bootstrap |
| SCIM | [`scim/`](scim/) | [`scim-openapi.json`](scim/scim-openapi.json) | Bootstrap |
| ALM | [`alm/`](alm/) | [`alm-openapi.json`](alm/alm-openapi.json) | Bootstrap |
| Audit | [`audit/`](audit/) | [`audit-openapi.json`](audit/audit-openapi.json) | Bootstrap |
| Financial Consolidation | [`financial-consolidation/`](financial-consolidation/) | [`financial-consolidation-openapi.json`](financial-consolidation/financial-consolidation-openapi.json) | Bootstrap |
| Exception Users | [`exception/`](exception/) | [`exception-openapi.json`](exception/exception-openapi.json) | Hand-maintained |

Each directory contains:
- **README.md** — sources, authentication details, live testing notes, and discovered API behavior
- **`{api}-openapi.json`** — canonical OpenAPI 3.0 spec (JSON)
- **`{api}-openapi.yaml`** — YAML counterpart (generated from JSON)

## Documentation sources

Anaplan is migrating their API documentation from [Apiary](https://apiary.io) to their official [Postman collection](https://www.postman.com/apiplan/official-anaplan-collection/). Specs here are built from both sources, augmented by live API testing where possible. See each API's README for source details and confidence level.

## Authentication

Anaplan APIs use three authentication schemes depending on the API:

| Scheme | Header | Used by |
|--------|--------|---------|
| HTTP Basic | `Authorization: Basic <base64>` | Authentication API (to obtain a token) |
| Bearer Token | `Authorization: Bearer <token>` | OAuth, Integration, CloudWorks, SCIM, ALM, Audit |
| AnaplanAuthToken | `Authorization: AnaplanAuthToken <token>` | Integration, Exception Users |

Tokens are obtained via the [Authentication API](authentication/) or [OAuth 2.0 API](oauth/). See each spec's `securitySchemes` for details.

## Project documentation

- [`CONTEXT.md`](CONTEXT.md) — detailed overview of all 9 APIs, source confidence levels, regional server URLs, and project structure
- [`docs/adr/`](docs/adr/) — architecture decision records

## Tooling

Python scripts require [uv](https://github.com/astral-sh/uv):

```sh
uv run build_spec.py   # one-time bootstrap from Apiary/Postman source
uv run sync_yaml.py <api>/<api>-openapi.json  # regenerate YAML from JSON
uv run pytest tests/   # run test suite
```

Live integration tests require credentials in a `.env` file. See each API's README for required variables.
