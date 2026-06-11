# Anaplan Audit API

## Sources

| Source | Available | Notes |
|--------|-----------|-------|
| Apiary docs | ✓ | https://auditservice.docs.apiary.io/ (identifier: `auditservice`) |
| Local metadata | ✓ | `sources/audit/apiary-blueprint.json` — Apiary API metadata cached locally |
| Postman collection | ✓ | Official Anaplan Collection — "Audit Service" folder (GET and POST variants for retrieving/searching audit events) |
| Live testing | ✗ | Not yet performed |

The Apiary blueprint is not publicly readable (anonymous access returns an empty blueprint). Resource groups ("Audit Events", "Examples") are present in the metadata but contain no endpoint definitions. Endpoints must be discovered via live testing or authenticated Apiary access.

## Purpose

The Audit API provides access to audit event logs from an Anaplan tenant. Intended for integration with SIEM (Security Information and Event Management) products for alerting, tracking, and compliance purposes.

## Authentication

The spec includes both standard Anaplan schemes as defaults — which one(s) the Audit API actually requires is unconfirmed pending live testing:

| Scheme | Format |
|--------|--------|
| Anaplan Auth Token | `Authorization: AnaplanAuthToken {token}` |
| Bearer Token | `Authorization: Bearer {token}` |

## Base URL (Open Question)

Two conflicting sources have been identified — live testing is needed to determine which is correct:

| Source | Base URL |
|--------|----------|
| Apiary production URL | `https://audit.anaplan.com/audit/api/1/` |
| CONTEXT.md allowlist table | `https://{region}.api.anaplan.com` (same pattern as Integration, ALM, SCIM) |

Both candidates are included in the spec's `servers[]` array. Remove the incorrect one and document the resolution here once confirmed via live testing.

If the `api.anaplan.com` pattern applies, the full regional server table (matching SCIM/Integration) is:

| Region | Description | Base URL |
|--------|-------------|----------|
| us1 | Data Center - US East | `https://api.anaplan.com` |
| us2 | Data Center - US West | `https://api.anaplan.com` |
| us5 | Cloud - US East | `https://api.anaplan.com` |
| us7 | Cloud - US | `https://api.anaplan.com` |
| us9 | Cloud - US | `https://us9.api.anaplan.com` |
| eu1 | Data Center - Netherlands | `https://api.anaplan.com` |
| eu2 | Data Center - Germany | `https://api.anaplan.com` |
| eu3 | Cloud - Europe | `https://eu3.api.anaplan.com` |
| eu4 | Cloud - Europe | `https://api.anaplan.com` |
| eu5 | Cloud - Europe | `https://eu5.api.anaplan.com` |
| gb1 | Cloud - UK | `https://gb1.api.anaplan.com` |
| ap1 | Cloud - Japan | `https://api.anaplan.com` |
| au1 | Cloud - Australia | `https://au1a.api2.anaplan.com` |
| ca1 | Cloud - Canada | `https://ca1a.api.anaplan.com` |
| sg1 | Cloud - Singapore | `https://sg1.api.anaplan.com` |
| ae1 | Cloud - UAE | `https://ae1.api.anaplan.com` |
| in1 | Cloud - India | `https://in1.api.anaplan.com` |
| id1 | Cloud - Indonesia | `https://id1.api.anaplan.com` |
| me1 | Cloud - Saudi Arabia | `https://me1.api.anaplan.com` |

## Resource Groups

The Apiary TOC lists two resource groups — "Audit Events" and "Examples" — but their endpoint definitions are not accessible without authenticated Apiary access. Known structural hints from the Apiary TOC:

- Paging is supported (referenced in the "Getting Started" section)
- The API follows standard HTTP verbs
- Response formats are documented (likely JSON)

Populate the endpoint table below as endpoints are discovered via live testing:

| Method | Path | Description |
|--------|------|-------------|
| — | — | Endpoints to be discovered via live testing |

## Spec Lifecycle

Canonical lifecycle and confidence are in the [confidence table in CONTEXT.md](../CONTEXT.md#confidence-table).

Note: the spec's paths are empty because the Apiary blueprint is not publicly readable — populate `audit/audit-openapi.json` by hand as endpoints are confirmed via live testing (`tests/test_audit_live.py`).

## Discovered Discrepancies

_Document differences between Apiary docs and live API behavior here as they are discovered._
