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

### `GET /events` event records (live testing 2026-06-12, issue #59)

Confirmed against real records with a role-enabled OAuth bearer token (Authorization
Code grant; the account holds the Tenant Auditor role). The response matches the
`AuditEventsResponse` envelope — a top-level `response` array of `AuditEvent` records
plus `meta.paging` (`AuditPaging`). Field reconciliations:

- **`additionalAttributes` was undocumented** — real events carry an
  `additionalAttributes` object (a free-form, event-type-specific map; e.g.
  `{"clientName": "..."}` on token events). Added to the `AuditEvent` schema.
- **`checksum` is not a SHA-256 hash** — the spec described it as a "SHA-256
  checksum", but the live value is a short numeric string (e.g. `"1118902891"`).
  The type (string) is correct; the description has been corrected.
- **Conditional fields not seen in the sample** — `objectTypeId`, `errorNumber`,
  `sessionId`, and `serviceVersion` did not appear on any record in the sample.
  They are kept in the spec as optional: they are expected to surface
  conditionally (e.g. `errorNumber` on failed actions, `sessionId` on
  session-scoped events) rather than being absent from the API.

Core fields present on every record (verified across a multi-day sample): `id`
(int), `eventTypeId`, `userId`, `tenantId`, `objectId`, `message`, `success`
(bool), `ipAddress`, `userAgent`, `hostName`, `eventDate` (int, Unix ms),
`eventTimeZone`, `createdDate` (int, Unix ms), `createdTimeZone`, `checksum`,
`additionalAttributes`.

These are asserted (not skipped) by `tests/test_audit_live.py` when a role-enabled
token is present.

### `GET /events` filtering and pagination (live testing 2026-06-12, issue #60)

Confirmed against real, multi-record data with a role-enabled token:

- **`type` filter** — the documented enum (`all`, `byok`, `user_activity`) is
  **incomplete**. Each `type` value filters to events whose `eventTypeId` carries
  a matching prefix, and live probing confirmed nine recognized values. **The enum
  is not enforced**: an unrecognised value returns `200` and is treated as `all`
  rather than rejected — which is how the recognized values were discovered (a
  recognised value filters to a strict subset; an ignored one returns the full
  `all` count). The spec enum has been expanded to the confirmed set:

  | `type` value | `eventTypeId` prefix | Notes |
  |--------------|----------------------|-------|
  | `all` | (every event) | |
  | `user_activity` | `USR-*` | ~79% of events in the test tenant |
  | `access_control` | `AUTHZ-*` | ~17% |
  | `int` | `INT-*` | integrations (~4%) |
  | `conn_mgmt` | `CONN-*` | connection / SAML management |
  | `comment` | `COMMENT-*` | |
  | `byok` | (BYOK) | `0` events without BYOK encryption |
  | `plan_iq` | (PlanIQ) | recognized; `0` events in window |
  | `forecaster` | (Forecaster) | recognized; `0` events in window |

  Naming is not mechanical — some values are abbreviations of the prefix (`int`,
  `conn_mgmt`), others are full names (`user_activity` for `USR-*`,
  `access_control` for `AUTHZ-*`). Wrong-format guesses (`integration`, `planiq`,
  `comments`, `connection`, `saml*`, `workflow`, `guardpoint`, `host`, …) are all
  ignored and fall back to `all`. A **`workflow`** category exists for the Workflow
  product but could not be confirmed on the test tenant (product not enabled), so
  it is omitted from the enum.
- **Date range** — `dateFrom`/`dateTo` (Unix-ms) constrain results to the window
  (verified: every returned event's `eventDate` falls within range). The
  `intervalInHours` rolling window likewise returns only events from the previous
  N hours. **The queried range cannot exceed 30 days** — a wider span returns
  `400 FAILURE_BAD_REQUEST` (`"Date range cannot exceed 30 days"`). This cap
  applies to both forms: `dateFrom`/`dateTo` more than 30 days apart, and
  `intervalInHours` above `720` (30 days), are both rejected.
- **Default window** — if no date filter (`dateFrom`/`dateTo` or `intervalInHours`)
  is supplied, the server returns the **previous 30 days** (confirmed: the
  `meta.paging.nextUrl` of an otherwise-unfiltered request carries an
  auto-populated `dateFrom`/`dateTo` spanning exactly 30 days).
- **Pagination** — `limit` caps the page size (`meta.paging.currentPageSize`
  matches), `offset` advances cleanly (consecutive pages are disjoint). `meta.paging`
  exposes `nextOffset`/`nextUrl` when more results exist, and **`previousUrl`** once
  paging past the first page. `previousUrl` was undocumented and has been added to
  the `AuditPaging` schema.
- **`limit` max not enforced** — the docs state a cap of 10000, but the server
  honors larger limits (`limit=15000` returned 15000 records). The spec's hard
  `maximum: 10000` constraint was removed and the description updated to match.

All of the above are asserted by `tests/test_audit_live.py` when a role-enabled
token is present.

### `GET /events` CEF (text/plain) output (live testing 2026-06-12, issue #61)

`GET /events` with `Accept: text/plain` returns `200` with `Content-Type: text/plain`
and a non-JSON body in Common Event Format (CEF), one event per line. The spec's
`text/plain` media-type declaration is confirmed accurate.

Representative line (IDs / IP redacted):

```
2026-06-12T07:35:27.000Z  CEF:0|Anaplan, Inc.||null|USR-8|User login success|id=2598676438 userId=<user-guid> tenantId=<tenant-guid> eventTimeZone=UTC createdDate=1781249727000 createdTimeZone=UTC success=true objectId=<object-guid> additionalAttributes={"clientName":"<client>"} ipAddress=<ip> userAgent=Mozilla/5.0 (...)
```

Line structure: a leading ISO-8601 timestamp, two spaces, then the CEF header
`CEF:0|Anaplan, Inc.||null|<eventTypeId>|<message>|` followed by the event fields
as `key=value` extension pairs. (Note: Anaplan's CEF omits the standard CEF
severity field — the extension follows directly after the name/message.)

- **CEF output is not paginated** — unlike the JSON envelope, the `text/plain`
  response ignores `limit`/`offset` and returns **every** matching event (confirmed
  with `type=conn_mgmt`: `limit=5`, `limit=50`, and no limit all returned the same
  211 CEF lines, while JSON `limit=5` returned 5 records out of `totalSize=211`).
  There is no `meta`/paging block. Documented on the spec's `text/plain` media type.
