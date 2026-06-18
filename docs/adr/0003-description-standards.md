# ADR 0003: Description Standards for OpenAPI Spec Fields

**Status**: Accepted

**Date**: 2026-06-18

## Context

The 9 Anaplan OpenAPI specs were authored by extracting information from Apiary documentation, Postman collections, and live testing. This process left the specs in an inconsistent state:

- Some fields have no description at all
- Some descriptions restate the field name verbatim and add no value
- Some `string` fields carry no information about valid values or format, while others list known values in prose that duplicates a sibling `enum`
- Descriptions accumulated maintainer provenance notes ("confirmed via live testing", "Apiary called this `message`") regardless of whether those notes are consumer-facing or internal history
- The same information appears in multiple locations within a spec (e.g., auth scheme behavior in both `info.description` and `securitySchemes`)

The specs are used for both human reading (in Swagger/Redoc UIs) and LLM-based code generation via MCP servers. Inconsistent description quality degrades both use cases: humans cannot tell whether a blank description is intentional or an omission; code generators lack the context needed to produce correct client code.

## Decision

### 1. Primary audience

Descriptions serve both human readers and LLM code generators. LLM code generation is the tiebreaker: descriptions must be self-contained and in-band — no assumption that the reader has access to external docs.

### 2. Write descriptions only when they add value

A description is required only when it says something the field name and type do not already express. A field with no description is intentionally undescribed (self-evident). A field with a description must earn its place.

**Do not write**: `name: string, description: "Name of the connection."` — the name and context already say this.

**Do write**: `message: string, description: "Outcome message for this run, e.g. 'Success'."` — without the description, a reader cannot distinguish a success message from an error message or a log string.

### 3. Enums and descriptions are complementary, not redundant

An `enum` lists valid values; a description explains what they *do* or adds behavioral context the enum cannot express. If a description would only restate the enum values, omit it. If it maps values to behavior, keep it.

**Omit**: `type: string, enum: [weekly, daily, hourly], description: "Schedule type."` — the description adds nothing.

**Keep**: `type: string, enum: [assign, unassign], description: "Operation to perform: 'assign' grants exception-user access; 'unassign' revokes it."` — the description explains the effect of each value.

### 4. Cross-location duplication: one authoritative location per fact

`securitySchemes` holds the authoritative detail for each auth scheme (header format, token type, accepted values). `info.description` may contain a one-line summary per scheme and any cross-cutting behavioral note that belongs to the API as a whole rather than to a single scheme (e.g., "Bearer tokens are rejected even for valid OAuth tokens" on an API that only accepts `AnaplanAuthToken`).

`info.description` must not repeat the full auth detail that already appears in `securitySchemes`.

### 5. String ID fields: `description` + `example` until a `pattern` is confirmed

For opaque Anaplan ID fields (workspace GUIDs, model IDs, integration IDs, etc.), use `description` and `example` to communicate the expected format. Do not add a `pattern` constraint until the regex has been confirmed via live testing, since a wrong `pattern` actively misleads code generators by causing them to reject valid IDs.

Once a pattern is confirmed for a field class, apply it consistently across all specs.

### 6. Maintainer provenance notes

- **Unconfirmed field names or values**: keep the warning in the description. A consumer coding against an unconfirmed field name needs to know the risk.
- **Confirmed-history notes** (e.g., "Apiary documented this as `message`; confirmed field name via live testing is `statusMessage`"): move to the relevant `<api>/README.md` under "Discrepancies" once the field is confirmed. The description becomes clean for consumers.

## Rationale

### Noise degrades signal

A spec full of tautological descriptions ("Connection ID", "Schedule type") trains both human readers and LLMs to ignore descriptions. When a genuinely important description appears — one that explains a behavioral nuance or an unexpected constraint — it is lost in the noise.

### Omission is preferable to tautology

A missing description signals "this field is self-evident." A tautological description signals "someone wrote a description" but delivers nothing. The former is correct; the latter is misleading about the spec's documentation completeness.

### Enum and description serve different consumers

Code generators use `enum` for validation and exhaustiveness checks. Human readers use `description` to understand what each value causes. Both are needed, but only when they are not saying the same thing.

### Wrong constraints are worse than absent constraints

A `pattern: "^[0-9a-f]{32}$"` on a field that accepts a different format will cause generated validators to reject valid input. The spec's primary job is accuracy; an unverified constraint is a spec defect, not a spec improvement.

## Alternatives Considered

### A. Describe every field regardless of self-evidence

Ensures no field is ever "undescribed," which some linters enforce.

**Rejected because**: it produces tautological descriptions that degrade the signal-to-noise ratio for both human readers and LLMs. Code generators do not benefit from "Name of the connection" on a field called `name` in a connection object.

### B. Duplicate auth detail in both `info.description` and `securitySchemes`

Ensures a reader finds the full picture regardless of which location they read first.

**Rejected because**: duplication creates maintenance burden and drift. When auth behavior changes (as it did for the Exception API when `Bearer` was confirmed rejected), a single source of truth is easier to update correctly.

### C. Keep all provenance notes in descriptions indefinitely

Preserves audit history inline without requiring readers to cross-reference READMEs.

**Rejected because**: confirmed-history notes are maintainer context, not consumer context. Once a field name is confirmed, a consumer does not need to know what Apiary called it. Leaving the note in the description adds length without adding value for the primary audience.

### D. Add `pattern` constraints based on observed examples

Adds structured validation immediately, without waiting for live-test confirmation.

**Rejected because**: Anaplan ID fields appear to follow a consistent format, but the exact pattern has not been confirmed across all ID types and API versions. A speculative `pattern` that happens to be wrong is a regression, not an improvement.

## Consequences

### Positive

- Descriptions in the specs are meaningful by construction — a reader can trust that every description says something the field name does not
- LLM code generators receive the context they need without wading through noise
- The distinction between "intentionally undescribed" and "not yet described" is explicit in this ADR and can be enforced in review
- Confirmed `pattern` constraints, when added, are trustworthy

### Negative

- Fields without descriptions may be mistaken for documentation gaps by contributors unfamiliar with this ADR — contributors must read it before auditing specs
- Some historical context moves out of spec files into READMEs, requiring readers to consult two files for full provenance history

## Related Decisions

- **ADR 0001**: Specs document each API as-is. This ADR governs *how* those facts are described, not which facts are included.
- **ADR 0002**: Canonical element ordering. Descriptions are an element; their content standards are defined here.
- CloudWorks spec is the first spec remediated against this standard.
