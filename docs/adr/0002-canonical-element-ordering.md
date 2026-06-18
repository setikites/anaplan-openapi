# ADR 0002: Canonical Element Ordering for OpenAPI Specs

**Status**: Accepted

**Date**: 2026-06-12

## Context

The 9 Anaplan OpenAPI specs were authored independently, resulting in inconsistent field ordering within operations. For example, `operationId`, `tags`, and `description` appear in at least four distinct sequences across the specs. This makes the specs harder to skim, complicates diffs, and prevents automated lint enforcement.

## Decision

We will adopt a single canonical field ordering for each OpenAPI object type and apply it uniformly across all 9 specs. The standard is defined below and will be enforced by a Spectral lint rule (see ADR 0002 follow-on issues).

### Document level (OpenAPI Object)

```
openapi
info
externalDocs
servers
security
tags
paths
components
```

### `info` object

```
title
version
description
contact
license
```

### Path Item Object

```
summary
description
parameters
get
post
put
patch
delete
```

Path parameters (`in: path`) must be declared once in the path item's `parameters` list, **before** any HTTP verb object. They must not be repeated inside individual operations. `components/parameters` is not used for path parameters; definitions are always inline at the path item level.

Non-path parameters (`in: query`, `in: header`, `in: cookie`) are declared inside the operation that uses them, not at the path item level.

HTTP verbs follow the order above: reads before writes, safe before destructive.

### Operation level (Operation Object)

```
summary
description
operationId
tags
externalDocs
parameters
requestBody
responses
security
deprecated
```

### `parameter` object (field order)

```
name
in
description
required
schema
example
```

### `parameters` array (entry order)

Within any `parameters` list, entries must appear in this sequence:

1. `in: path` parameters (always required; listed in path-segment order)
2. `in: query` or `in: header` parameters where `required: true`
3. `in: query`, `in: header`, or `in: cookie` parameters where `required: false` or `required` is absent

### `response` object

```
description
headers
content
```

## Rationale

The ordering rule is **"human-readable fields first, identity second, inputs before outputs."**

- `summary` and `description` appear first so a reader scanning the YAML immediately understands the operation's purpose without hunting.
- `operationId` and `tags` follow as identity/grouping metadata.
- `parameters` and `requestBody` describe what goes in; `responses` describes what comes out.
- `security` and `deprecated` are modifiers that apply after the primary contract is established.

Required path parameters are listed first because they are structurally part of the URL and mandatory; required query parameters follow because they must be supplied for a valid call; optional parameters come last.

**Path parameters at path item level**: a path parameter is a structural property of the URL, not of any individual verb — `{integrationId}` is part of the path regardless of whether you GET, PUT, or DELETE it. Declaring it once at the path item level makes this relationship explicit and eliminates per-operation repetition. Inlining the definition (rather than `$ref`-ing from `components/parameters`) keeps each path item self-contained and readable without jumping to the components section. `components/parameters` is reserved for non-path parameters that genuinely need reuse across unrelated paths, which has not yet arisen in these specs.

The chosen ordering matches the implicit order of field tables in the OpenAPI 3.0 Specification and aligns with the Redocly style guide, reducing friction when contributors cross-reference the spec.

## Alternatives Considered

### A. Follow the OpenAPI Specification field-table order exactly

The OAS field tables define a de-facto order (e.g., `operationId` appears before `summary` in the spec text). We chose not to follow this exactly because it is counterintuitive for human readers — `summary` is more useful at a glance than `operationId`.

**Rejected because**: readability for contributors matters more than mirroring the formal spec layout.

### B. Allow per-spec discretion

Each spec team chooses its own ordering.

**Rejected because**: it is the status quo and the problem we are solving.

### C. Keep path parameters in `components/parameters` and `$ref` them per operation

Each verb lists `parameters: [$ref: "#/components/parameters/integrationId"]`. This avoids repeating the parameter definition.

**Rejected because**: it requires per-operation repetition (GET, PUT, and DELETE on the same path all `$ref` the same component), and forces a reader to jump to `components` to see a parameter that is structurally part of the URL. Path item level parameters express the same intent with no repetition and no cross-referencing.

### D. Alphabetical ordering

Tools like `prettier` can sort YAML keys alphabetically, making diffs predictable.

**Rejected because**: alphabetical order puts `deprecated` before `description` and `responses` before `security`, which reads unnaturally.

## Consequences

### Positive

- Specs are consistent and easier to skim
- Diffs are cleaner (field moves don't appear as unrelated changes)
- Lint enforcement is possible with a deterministic rule
- New contributors have a clear standard to follow

### Negative

- All 9 existing specs require remediation (tracked in a follow-on issue)
- One-time churn in git history when specs are reformatted
- Path parameter definitions are duplicated across path items that share the same parameter name (e.g., `integrationId` appears in multiple path items). This is intentional: each path item is self-contained, and the duplication is small relative to the clarity gained.

## Related Decisions

- **ADR 0001**: Specs document each API as-is; this ADR governs *how* they are authored, not *what* they document.
- **Issue #72**: Adds a Spectral lint rule to enforce this ordering in CI.
- **Issue #73**: Remediates all 9 specs to conform to this standard.
