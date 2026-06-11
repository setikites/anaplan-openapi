# Anaplan OpenAPI Specification Project

## Overview

This project generates OpenAPI 3.0 JSON specifications for the 9 publicly available Anaplan REST APIs, intended for API client code generation and community documentation.

See [CONTEXT.md](./CONTEXT.md) for an overview of all 9 APIs, their sources, and testing coverage.

## Agent skills

### Issue tracker

Issues live in GitHub Issues. Skills create and read issues via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Standard triage labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.

## Repository layout

- `scripts/` — build and maintenance tooling; `scripts/oauth/` — interactive OAuth helpers
- `sources/` — raw source data (Postman collection + OpenAPI export, Apiary blueprints, extracted schemas, PDFs)
- `<api>/` — per-API spec (`<api>-openapi.json` canonical, `<api>-openapi.yaml` generated) + README
- `docs/` — `TESTING.md`, `PRD.md`, `adr/`, `agents/`
- Contributor workflow: [CONTRIBUTING.md](./CONTRIBUTING.md); live testing: [docs/TESTING.md](./docs/TESTING.md)

## Spec build pipeline

`scripts/build_spec.py` generates an initial OpenAPI spec from Apiary or Postman source data. It is a **one-time bootstrap** per API — run it once to create the spec, then stop.

Once a spec has live tests (a `tests/test_*_live.py` file exists for that API), the spec is **hand-maintained**. Do not run `scripts/build_spec.py` against it again — doing so will overwrite response schemas, security declarations, and any other edits derived from live testing.

After editing a hand-maintained JSON spec, regenerate its YAML counterpart with:
```
uv run python scripts/sync_yaml.py <api>/<api>-openapi.json
```

The current hand-maintained specs (live tests exist — do not rebuild):
- `authentication/authentication-openapi.json`
- `oauth/oauth-openapi.json`
- `integration/integration-openapi.json`

## Python tooling

Always use `uv` to run Python scripts in this project. Examples:
- `uv run python scripts/build_spec.py ...`
- `uv run pytest`

## GitHub CLI

The `gh` CLI is installed at: `C:\Program Files\GitHub CLI\gh.exe`

When running `gh` commands, use the full path since it may not be in the PATH for non-interactive shells.
