# ADR 0006: Minimum-Role Annotations for Operations

**Status**: Accepted

**Date**: 2026-07-02

## Context

Each Anaplan API operation has a minimum tenant/workspace role a caller must
hold to execute it. Today this requirement, where it appears at all, is
inconsistent prose in the operation `description` ("Requires Workspace
Administrator role", "Requires tenant admin privilege; workspace admin access
alone is insufficient", "Requires the Tenant Auditor role"), and most
operations carry no role information: cloudworks 0/62, financial-consolidation
0/36, scim 0/19, integration ~39/97.

There is no closed role vocabulary and no machine-readable representation. That
blocks two things: consumers (human readers and LLM agents driving the API via
an MCP server generated from the spec) cannot reliably learn the role gate, and
maintainers cannot audit coverage or lint for drift across ten specs.

This ADR sets the repo-wide convention every per-API annotation slice follows.
It extends ADR 0003, which governs how description facts are written.

## Decision

### 1. Closed role vocabulary

Exactly these role names are used everywhere. No other value is valid.

| Role | Meaning |
|------|---------|
| `Standard User` | Authenticated user with no elevated role; ordinary workspace/model access is enough. |
| `Workspace Administrator` | Workspace Admin role on the target workspace. |
| `Tenant Auditor` | Tenant-level Auditor role (read-only audit surface). |
| `User Administrator` | Tenant User Admin role (user-management surface, e.g. workspace admins/visitors listings); narrower than full Tenant Admin. |
| `Tenant Administrator` | Tenant Admin privilege; workspace-admin access alone is insufficient. |
| `Tenant Security Admin` | Tenant Security Administrator (SCIM user/group provisioning). |
| `Integration Admin` | Tenant-level Integration Administrator (CloudWorks / Data Orchestrator): manages connections, integrations, notifications, and integration flows/schedules, and can move data across workspaces. Assigned by a Tenant Admin. |
| `Restricted Integration User` | Workspace-scoped restricted integration role: creates and manages CloudWorks connections and integrations within assigned workspaces only. The lower of the two CloudWorks roles; cannot act on tenant-level resources. |
| `None` | No role gate applies: token-issuing endpoints (authentication, oauth) where the caller is not yet an authenticated principal, and purely functional endpoints. |

Names match Anaplan's own administrative terminology (Workspace Administrator,
Tenant Administrator, Tenant Auditor, User Administrator, Security
Administrator, Integration Administrator, Restricted Integration User).
`Standard User`
and `None` are distinct: `Standard User` means "logged in, no elevated role";
`None` means "the role model does not apply to this endpoint at all". The two
CloudWorks roles are also distinct: `Restricted Integration User` is the
workspace-scoped minimum; `Integration Admin` is the tenant-wide superset
required only for cross-workspace or tenant-level integration operations.

### 2. Representation: extension **and** sentence

Both are recorded on every annotated operation.

- **`x-anaplan-min-role: <role>`** — the machine-readable source of truth.
  Placed immediately after `operationId`. Used by the lint check and by
  coverage/audit tooling. Vendor `x-*` extensions are ignored by stock
  codegen, Swagger UI, and MCP bridges, so this form never reaches consumers
  on its own — it exists for *us*.

- **Leading description sentence `Minimum role: <role>.`** — the only form that
  reaches consumers. It is the first line of the `description`, followed by a
  blank line, then the existing prose. Per ADR 0003 §1, LLM code generation is
  the tiebreaker and facts must be in-band: an MCP-driven agent sees the
  description text and nothing else, so the role must live there or the agent
  will call an admin-only endpoint as a standard user and get an unexplained
  403.

The lint check (`scripts/check_min_role.py`) enforces that the two agree and
that the role is in the vocabulary. This keeps the human/LLM sentence and the
machine extension from drifting.

#### Worked example

Before (alm `POST /models/{modelId}/onlineStatus`):

```json
"description": "Set a model online or offline. Requires Workspace Administrator role. Returns 400 if the status value is invalid or the model is locked, 422 if the model is archived.",
"operationId": "postModelOnlineStatus",
```

After:

```json
"description": "Minimum role: Workspace Administrator.\n\nSet a model online or offline. Returns 400 if the status value is invalid or the model is locked, 422 if the model is archived.",
"operationId": "postModelOnlineStatus",
"x-anaplan-min-role": "Workspace Administrator",
```

The redundant "Requires Workspace Administrator role" prose is removed; the
leading sentence replaces it.

### 3. Unknown role: best-known value plus `needs-info`

When the minimum role is not yet confirmed by live testing, record the
best-known value normally (extension + sentence) and add:

```json
"x-anaplan-min-role-needs-info": true
```

This is a machine-only flag: it drives creation of `needs-info` GitHub issues
for later live-test confirmation and lets audit tooling separate confirmed from
provisional annotations. It does not change the consumer-facing sentence — the
best-known role is usually correct, and hedging every sentence would add the
noise ADR 0003 forbids. When live testing confirms (or corrects) the role, the
flag is removed.

### 4. Consistency, not coverage

The lint enforces *consistency*, not *completeness*. An operation with neither
the extension nor the sentence is legal — it is simply not yet annotated. This
lets the per-API slices land incrementally without the check failing on
specs that are mid-migration. Coverage (how many operations are annotated) is
tracked separately by audit tooling, not by this lint.

## Rationale

### Two forms because two audiences

The sentence is the only thing consumers receive; the extension is the only
thing that is cleanly machine-auditable. Neither covers both jobs, so both are
kept and pinned together by the lint. A prose-only convention cannot be audited
without brittle grepping; an extension-only convention is invisible to the very
LLM agents ADR 0003 names as the tiebreaker audience.

### Closed vocabulary because open prose already failed

The specs already demonstrate what happens without a fixed set: "Workspace
Admin", "Workspace Administrator role", "tenant admin privilege" all denote
role gates in incompatible phrasings. A closed set makes the annotation
lintable and lets `x-anaplan-min-role` be queried exactly.

### Lint because ten specs drift

With one source of truth (extension) and one delivery form (sentence) on
hundreds of operations across ten specs, the only defense against silent
divergence is a mechanical check. It runs in the same test suite as ADR 0002
ordering and ADR 0003 description standards.

## Alternatives Considered

### A. Standardized description sentence only

Follows ADR 0003's existing prose pattern with no new extension.

**Rejected because**: it is not cleanly machine-auditable. Coverage reporting
and "list every operation requiring Tenant Administrator" would depend on
parsing prose, and there is no structured field to lint the sentence against.

### B. Structured extension only (`x-anaplan-min-role`)

Machine-readable and easy to lint.

**Rejected because**: vendor extensions do not reach consumers. Stock
openapi-generator templates, Swagger UI, and typical OpenAPI→MCP bridges do not
surface `x-*` to the generated client or to the model. The LLM agent — ADR
0003's tiebreaker audience — would never see the role.

### C. Open prose, no vocabulary

Least work; annotate in whatever words fit.

**Rejected because**: this is the status quo that produced the inconsistency
this ADR exists to fix.

### D. Promote a uniform role to an API-wide default

Where a whole spec shares one role (e.g. ALM is Workspace Administrator on
nearly every operation), declare it once at API scope (`info` or a spec-level
extension) and override per-operation only where it differs.

**Rejected because**: the *sentence* cannot be promoted — it is the only form a
per-operation MCP/codegen consumer receives, so an API-scope statement is
invisible to a single tool call, and the sentence must still be written on
every operation. That leaves only the extension to promote, which saves one
line per operation while making the source no longer self-contained and, worse,
inviting a blanket default to silently stamp operations whose role is not
actually confirmed (ALM has such operations) — guessing, against ADR 0001. The
per-operation repetition is instead handled at write time by
`scripts/annotate_min_role.py`, which stamps the extension and sentence across a
spec from a default plus an exceptions list; the annotations then stand alone.

### E. Hedge every provisional sentence with "(unconfirmed)"

Surface uncertainty to consumers directly.

**Rejected because**: it adds noise to every not-yet-live-tested operation,
against ADR 0003's signal-over-noise principle. The best-known role is usually
right; the `needs-info` flag captures the uncertainty for maintainers without
degrading the consumer sentence.

## Consequences

### Positive

- Every annotated operation carries the role in both a form consumers read and
  a form tooling audits, guaranteed consistent by the lint.
- Per-API annotation slices proceed mechanically against a fixed vocabulary and
  a worked example.
- Coverage and "which operations need role X" become exact queries over
  `x-anaplan-min-role`.
- Provisional annotations are distinguishable from confirmed ones via
  `x-anaplan-min-role-needs-info`.

### Negative

- Two fields to keep in sync per operation; mitigated by the lint, which fails
  the build on any mismatch.
- The role appears in two places in the source, which contributors unfamiliar
  with this ADR may read as duplication — it is deliberate (source of truth vs.
  delivery form).

## Related Decisions

- **ADR 0001**: Document each API as-is. This ADR records an existing access
  fact; it does not invent role requirements.
- **ADR 0002**: Canonical element ordering. `x-anaplan-min-role` is placed
  immediately after `operationId`; the ordering checker ignores vendor
  extensions, so placement here is convention, not enforced order.
- **ADR 0003**: Description standards. This ADR extends it: the "Minimum role:"
  sentence is a required leading description line, and the extension is the
  authoritative source per ADR 0003's one-authoritative-location principle.
