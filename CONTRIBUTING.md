# Contributing

Thanks for helping improve these specs. This file covers the tooling and
workflow for **maintaining** the repository. If you only want to *use* a spec,
see the [README](README.md) — you don't need any of this.

## Prerequisites

All Python tooling runs through [uv](https://github.com/astral-sh/uv):

```sh
uv run pytest                                  # run the test suite
uv run python scripts/<script>.py              # run a tooling script
```

The committed `uv.lock` and `.python-version` pin the environment.

## Repository layout

| Path | Contents |
|------|----------|
| `<api>/` | One folder per API: `README.md`, `<api>-openapi.json` (canonical), `<api>-openapi.yaml` (generated) |
| `scripts/` | Build and maintenance tooling (`build_spec.py`, `converter.py`, `schema_importer.py`, `revise_spec.py`, `validate.py`, `sync_yaml.py`, `check_ordering.py`, `remediate_ordering.py`) |
| `scripts/oauth/` | Interactive helpers for the manual OAuth flows |
| `sources/` | Raw source data: the official Postman collection, its OpenAPI export, Apiary blueprints/metadata, extracted schemas, reference PDFs |
| `tests/` | Pytest suite (unit/contract + `*_live.py` live tests) |
| `docs/` | `TESTING.md`, `PRD.md` (historical), `adr/` (decision records), `agents/` (agent skill docs) |
| `CONTEXT.md` | The API landscape, sources, confidence levels, and regional URLs |

## Spec lifecycle: bootstrap vs hand-maintained

`scripts/build_spec.py` generates an initial OpenAPI spec from Apiary or Postman
source data. It is a **one-time bootstrap per API** — run it once to create the
spec, then stop.

Once a spec has live tests (a `tests/test_<api>_live.py` file exists), the spec
is **hand-maintained**. Do **not** run `scripts/build_spec.py` against it again — doing
so overwrites response schemas, security declarations, and other edits derived
from live testing.

Hand-maintained specs (live tests exist — do not rebuild):
- `authentication/authentication-openapi.json`
- `oauth/oauth-openapi.json`
- `integration/integration-openapi.json`
- `cloudworks/cloudworks-openapi.json`
- `scim/scim-openapi.json`
- `alm/alm-openapi.json`
- `audit/audit-openapi.json`
- `financial-consolidation/financial-consolidation-openapi.json`
- `exception/exception-openapi.json`

## Editing a spec

The JSON file is canonical. After editing a hand-maintained JSON spec,
regenerate its YAML counterpart and validate:

```sh
uv run python scripts/sync_yaml.py <api>/<api>-openapi.json
uv run python scripts/validate.py <api>/<api>-openapi.json
```

## Element ordering

All specs must follow the canonical field ordering defined in
[docs/adr/0002-canonical-element-ordering.md](docs/adr/0002-canonical-element-ordering.md).
The key rules:

- **Document level**: `openapi → info → externalDocs → servers → security → tags → paths → components`
- **Operation level**: `summary → description → operationId → tags → externalDocs → parameters → requestBody → responses → security → deprecated`
- **`parameters` array**: path params first, then required params, then optional params
- **`parameter` object**: `name → in → description → required → schema → example`
- **`response` object**: `description → headers → content`

Check ordering before you push:

```sh
uv run python scripts/check_ordering.py <api>/<api>-openapi.json
```

If your edits introduced ordering violations, `scripts/remediate_ordering.py` will fix them automatically:

```sh
uv run python scripts/remediate_ordering.py <api>/<api>-openapi.json
```

## Testing

- **Unit/contract tests** need no credentials: `uv run pytest`.
- **Live tests** are skipped by default and require credentials and the `--live`
  flag. Setup and invocation are documented in [docs/TESTING.md](docs/TESTING.md).

When live testing reveals behavior that differs from the documented API (missing
error cases, fields marked optional that are actually required, etc.), record it
in the relevant `<api>/README.md` under "Discrepancies".

## CI checks

Every PR runs `.github/workflows/lint.yml`, which does two things:

1. **Schema validation** (`scripts/validate.py`) — confirms each spec is a valid OpenAPI 3.0 document.
2. **Tests** (`pytest -m "not live"`) — runs all unit and contract tests, including the element ordering checks.

Run both locally before opening a PR:

```sh
uv run python scripts/validate.py
uv run pytest
```

A PR that fails either check will not be merged.

## Issues and decisions

- Issues live in GitHub Issues; see `docs/agents/issue-tracker.md` and
  `docs/agents/triage-labels.md`.
- Architectural decisions are recorded in `docs/adr/`. Add a new ADR when a
  decision is hard to reverse, surprising, or involves trade-offs.
