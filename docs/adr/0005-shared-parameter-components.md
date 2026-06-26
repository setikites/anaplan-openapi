# ADR 0005: Shared Parameter Components for Repeated Path and Query Parameters

**Status**: Accepted

**Date**: 2026-06-26

**Supersedes**: ADR 0002 (path-parameter rule only)

## Context

ADR 0002 §"Path item level" mandated that path parameters be defined **inline**
at the path item level and explicitly forbade `components/parameters` for them
(Alternative C, rejected). Its rationale rested on two claims:

1. A reader should not have to jump to `components` to see a parameter that is
   structurally part of the URL.
2. `components/parameters` is "reserved for non-path parameters that genuinely
   need reuse across unrelated paths, **which has not yet arisen** in these
   specs."

Both claims have since been overtaken:

- **Claim 2 is already false.** The financial-consolidation spec defines and
  `$ref`s a shared `TenantHeader` parameter component, enforced by contract
  tests (`test_fc_*_reference_tenant_header`). Shared parameter components are
  already in use.
- ADR 0004 requires every repeated ID parameter to carry a maintained
  source-path chaining description (ADR 0004 §2) and one canonical `example`
  (ADR 0004 §1). In the Integration spec `modelId` recurs 72 times, `workspaceId`
  48 times. Inline duplication of a *maintained sentence* across dozens of
  occurrences guarantees the cross-location drift ADR 0003 §4 forbids — a cost
  ADR 0002 did not weigh because at the time path-param descriptions were
  throwaway ("The model ID").

The inline rule was correct when path-param descriptions were disposable. Once
they became maintained, single-source content, the trade-off inverts.

## Decision

Applies to **all 10 specs**. This is the structural mechanism for ADR 0004 §1.

### 1. Repeated path parameters move to `components/parameters` and are `$ref`'d

A path parameter that appears in more than one path item is defined once in
`components/parameters` and referenced via `$ref` at the **path item level**
(not per operation — ADR 0002's path-item-level placement still holds; only the
inline-definition requirement is superseded). The canonical `description` and
`example` live in exactly one place per spec.

### 2. A pattern survives to the shared component only if uniform across all occurrences

When collapsing N inline occurrences into one component, a `schema.pattern` is
kept **only if every occurrence carried it identically**. If occurrences
disagree (some have the pattern, some don't, or they differ), the pattern is
dropped from the shared component rather than asserted over inputs that were
never validated against it.

- Confirmed **hex** ID patterns are kept and applied uniformly: `modelId`,
  `workspaceId`, `userId` are 32-char hex IDs scoped **larger than one model**
  (tenant/workspace scope) and carry their confirmed pattern.
- **Non-hex**, model-scope IDs (12–13 digit prefixed numerics: `listId`,
  `moduleId`, `importId`, `exportId`, `processId`, …) carry **no** pattern
  unless and until confirmed per ADR 0003 §5.

This keeps the CI pattern paper trail (`tests/confirmed_patterns.json` +
`test_no_unconfirmed_patterns`) honest after extraction.

### 3. A query parameter is shared only if it is uniform across every use

Common query parameters extract to `components/parameters` only when their
schema, description, and `example` are identical at every call site. `s`,
`tenantDetails`, and `includeAll` qualify. **`sort` does not**: its `example`
and sortable-field set vary per endpoint (task lists sort `-creationDate`,
object lists sort `+name`), and an OpenAPI 3.0 `$ref` parameter object cannot
override the sibling `example`/`description` of its target. `sort` stays inline.

## Rationale

- A maintained, single-source description is only single-source if it lives in
  one place; `$ref` is the only mechanism that delivers that in OpenAPI 3.0.
- The "reader must not jump to components" cost is real but small, and is the
  same cost already accepted for `TenantHeader` — consistency beats relitigating
  it per parameter kind.
- Asserting a pattern that only some occurrences ever carried would fabricate a
  validation guarantee; the uniformity rule prevents that.

## Consequences

### Positive

- ADR 0004 §1/§2 become enforceable: one description, one example per ID.
- Specs shrink: dozens of inline parameter blocks collapse to `$ref`s.
- Parameter-shape contract tests resolve `$ref`s (see
  `_resolve_param`/`_all_params` in `tests/test_spec_contract.py`), so both
  reference-presence and resolved-shape assertions hold.

### Negative

- A reader must consult `components/parameters` to see a path parameter's full
  definition — the readability cost ADR 0002 sought to avoid, now accepted.
- One-time structural refactor per spec (`scripts/remediate_path_params.py`
  inverted from inline-enforcement to extract-and-`$ref`).

## Related Decisions

- **ADR 0002**: Superseded for path parameters only. Path-item-level *placement*
  and all field/array ordering rules remain in force; the inline-definition
  requirement and Alternative-C rejection are overruled.
- **ADR 0003 §4/§5**: §4 (one authoritative location) is *why* parameters are
  shared; §5 (no unconfirmed patterns) drives the uniformity rule in §2.
- **ADR 0004**: This ADR is the structural mechanism for ADR 0004 §1.
