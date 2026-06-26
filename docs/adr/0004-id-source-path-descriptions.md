# ADR 0004: ID Parameter Source-Path Descriptions and Shared Parameter Components

**Status**: Accepted

**Date**: 2026-06-26

## Context

ADR 0003 §5 governs how opaque Anaplan ID fields are described (`description` +
`example`, no `pattern` until confirmed) but says nothing about *what* the
description should say. Review of the Integration spec found ID parameter
descriptions that restate the field name ("The view ID") or carry useless
examples — adding length without telling a consumer the one thing they need:
**where the ID value comes from**, so calls can be chained.

The same review exposed a structural problem. Path parameters are defined
**inline, per operation**: `modelId` is duplicated 72 times in the Integration
spec, `workspaceId` 48 times, `viewId` 7 times. There are zero
`components.parameters`. Attaching a source-path description to every inline
occurrence would duplicate the same sentence dozens of times per spec — exactly
the cross-location drift ADR 0003 §4 forbids. Common query parameters (`s`,
`sort`, `tenantDetails`, `includeAll`) have the same duplication and the same
"needs identical text everywhere" problem.

Many IDs are also **cross-API**: CloudWorks, Audit, and ALM consume IDs
(`modelId`, `workspaceId`) that are minted by the Integration API. A consumer
reading those specs needs a pointer to the *other* API's reference docs, not
just a path template that doesn't exist in the spec they're reading.

## Decision

Applies to **all 10 specs**.

### 1. Extract repeated parameters to `components.parameters` and `$ref` them

Repeated ID path parameters (`modelId`, `workspaceId`, `viewId`, …) and common
query parameters (`s`, `sort`, `tenantDetails`, `includeAll`) are defined once in
`components.parameters` and referenced via `$ref`. The description and canonical
`example` live in exactly one place per spec. This satisfies ADR 0003 §4 (one
authoritative location per fact) and incidentally fixes the inconsistent-example
complaints from the review (one canonical example per ID type).

### 2. ID input parameters carry a source-path chaining description

Every ID **input** parameter (path param, and ID-typed query/request-body field)
describes where its value comes from, using the HTTP verb + the spec's own path
template in backticks. Response ID fields are the *source* and need no chaining
note. List **all** real sources when more than one exists.

- List-sourced: `` "The view ID. From `GET /models/{modelId}/views`." ``
- Two parents: `` "The view ID. From `GET /models/{modelId}/views` or `GET /modules/{moduleId}/views`." ``
- Created-resource (`taskId`, `requestId`): `` "The task ID returned by `POST /models/{modelId}/.../tasks`." ``

### 3. Cross-API-sourced IDs add a canonical anaplan.com reference link

When an ID is sourced from a **different** API (e.g. `modelId` in CloudWorks,
sourced from Integration), the description adds a curated anaplan.com reference
link **in addition** to the verb + path template:

`` "The model ID. From `GET /models` in the [Integration API](https://help.anaplan.com/integration-api-v20-3107aa54-d12b-4c48-9550-3561c84adbb2)." ``

The canonical link for each API is maintained in a single table in
[CONTEXT.md](../../CONTEXT.md#canonical-api-reference-links). Cite by reference;
do not hardcode the URL in more than one spec location.

### 4. Apiary blueprint links dropped; curated anaplan.com links sanctioned

Inline links to Apiary blueprint documentation are removed from all specs. The
curated per-API anaplan.com reference links (decision 3) are the **only**
sanctioned external documentation links — a spec auditor must not strip them as
"doc links."

## Rationale

- An ID description that names its source is the only ID description worth its
  tokens; it turns a flat list of endpoints into a chainable workflow.
- Inline duplication of a maintained sentence across 72 occurrences guarantees
  drift. A single `components.parameters` definition is the smaller diff forever,
  even though the one-time extraction is larger.
- A path template alone is useless in a spec where that path doesn't exist
  (cross-API IDs); the anaplan.com link bridges the gap without fabricating a
  unified API surface (consistent with ADR 0001).

## Consequences

### Positive

- ID parameter descriptions are uniformly useful and maintained in one place.
- Specs shrink: dozens of inline parameter blocks collapse to `$ref`s.
- Cross-API chaining is discoverable from within each spec.

### Negative

- One-time structural refactor per spec (inline params → `components` + `$ref`)
  before the description rules can be applied cleanly.
- A second source of truth (CONTEXT.md link table) must be consulted to author a
  cross-API ID description — but it is one table, not N inline URLs.

## Related Decisions

- **ADR 0001**: Document APIs as-is. Cross-API links reference the real owning
  API rather than fabricating a unified surface.
- **ADR 0002**: Canonical element ordering applies to the new `components.parameters`.
- **ADR 0003 §4/§5**: This ADR is the concrete application — §4's one-location
  rule is *why* parameters are shared; §5's ID-field rule is *what* the shared
  description says.
