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

## Python tooling

Always use `uv` to run Python scripts in this project. Examples:
- `uv run main.py`
- `uv run pytest tests/`

## GitHub CLI

The `gh` CLI is installed at: `C:\Program Files\GitHub CLI\gh.exe`

When running `gh` commands, use the full path since it may not be in the PATH for non-interactive shells.
