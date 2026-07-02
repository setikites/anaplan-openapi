# Anaplan Audit API

## Sources

| Source | Available | Notes |
|--------|-----------|-------|
| Apiary docs | ✓ | https://auditservice.docs.apiary.io/ (identifier: `auditservice`) |
| Local metadata | ✓ | `sources/audit/apiary-blueprint.json` — Apiary API metadata cached locally |
| Postman collection | ✓ | Official Anaplan Collection — "Audit Service" folder (GET and POST variants for retrieving/searching audit events) |
| Live testing | ✓ | Events path confirmed end-to-end (issues #58–#61) — see [Discovered Discrepancies](#discovered-discrepancies) |

The Apiary blueprint is not publicly readable (anonymous access returns an empty blueprint), so the endpoints were discovered and confirmed via live testing against a tenant with the Tenant Auditor role. See the testing coverage and findings below.

## Purpose

The Audit API provides access to audit event logs from an Anaplan tenant. Intended for integration with SIEM (Security Information and Event Management) products for alerting, tracking, and compliance purposes.

## Authentication

Confirmed via live testing: requests authenticate with `Authorization: AnaplanAuthToken {token}`, where the token may be obtained from basic/certificate auth **or** an OAuth Authorization Code grant access token (Anaplan accepts an OAuth `access_token` under the same scheme). The audit host (`audit.anaplan.com`) does **not** accept the `Bearer` scheme — sending `Authorization: Bearer {token}` returns `401 "No valid token header found for the request"`. The account must hold the **Tenant Auditor** role — without it, `GET /events` returns `401 FAILURE_UNAUTHORIZED_USER_ACTION` (the token is accepted; the role is missing).

| Scheme | Format |
|--------|--------|
| Anaplan Auth Token | `Authorization: AnaplanAuthToken {token}` |

## Base URL

Confirmed via live testing: the Audit API is served from `https://audit.anaplan.com/audit/api/1` (a unique host, **not** the `api.anaplan.com` data-plane pattern used by Integration/ALM/SCIM). This matches the Apiary production URL.

## Endpoints

Confirmed via live testing (the Apiary blueprint is not publicly readable):

| Method | Path | Description |
|--------|------|-------------|
| GET | `/events` | Retrieve audit events. Supports `type` filtering, `dateFrom`/`dateTo` or `intervalInHours` (≤ 30 days), `limit`/`offset` paging, and JSON or CEF (`Accept: text/plain`) output. |
| POST | `/events/search` | Retrieve audit events using a JSON request body for the time range (`from`/`to` or `interval`). |

## Spec Lifecycle

Canonical lifecycle and confidence are in the [confidence table in CONTEXT.md](../CONTEXT.md#confidence-table).

The spec is **hand-maintained and live-tested** (`tests/test_audit_live.py`, issues #58–#61): the `/events` and `/events/search` paths were discovered and confirmed against the live API with a Tenant Auditor role. Do not rebuild from the bootstrap script.

## Discovered Discrepancies

### `GET /events` event records (live testing 2026-06-12, issue #59)

Confirmed against real records with a role-enabled OAuth token (Authorization
Code grant, sent as `AnaplanAuthToken`; the account holds the Tenant Auditor role). The response matches the
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
