# ADR 0001: Document Each Anaplan API As-Is Rather Than Normalizing Across Them

**Status**: Accepted

**Date**: 2026-05-28

## Context

Anaplan has 10 publicly available REST APIs, each built by different teams at different times. They exhibit significant variations in:

- **Authentication**: Some use standard Bearer tokens (`Authorization: Bearer <token>`), others use Anaplan-specific tokens (`Authorization: AnaplanAuthToken <token>` or `AnaplanAuthToken` header)
- **Pagination**: Different schemes (offset/limit, cursors, SCIM list responses with `startIndex`/`itemsPerPage`)
- **Error responses**: Varying formats and error codes
- **Field naming**: Inconsistent conventions across APIs

These variations exist because the APIs were designed independently, not as a coordinated platform.

## Decision

We will **document each API in its OpenAPI 3.1 spec exactly as it exists**, preserving these variations rather than attempting to normalize them into a unified interface.

## Rationale

### 1. Accuracy Over Abstraction
Normalizing the specs would require either:
- Fabricating a unified authentication or pagination scheme that doesn't actually exist in the API
- Creating adapter layers or transformation logic that obscures what the API actually does

Both would make the specs less useful for code generation, since generated code would need to differ from the actual API behavior.

### 2. Respect API Reality
These APIs have evolved independently and have real clients already using their actual patterns. Documenting them as-is is more honest and useful than imposing an artificial uniformity.

### 3. Clear Discoverability of Differences
By documenting each API's actual patterns in its spec and README, users (and code generators) can:
- Quickly see that SCIM uses Bearer tokens while Integration uses Anaplan-specific tokens
- Understand that pagination differs and adjust their client code accordingly
- Make informed decisions about which APIs to use

## Alternatives Considered

### A. Normalize to a Single Authentication Scheme
Create OpenAPI specs that present all APIs as using Bearer tokens, with adapter logic in code generators to translate to the actual Anaplan-specific tokens where needed.

**Rejected because**: 
- Adds hidden complexity in code generators
- Specs no longer match actual API behavior
- Harder for users to understand what the real API expects

### B. Create Adapter/Wrapper Services
Build a thin translation layer that presents all APIs with unified auth, pagination, etc.

**Rejected because**:
- Out of scope for this project (spec generation, not service development)
- Would require maintaining additional infrastructure
- Users still need to understand the underlying APIs

### C. Create Separate Specs for a "Normalized" API Surface
Publish both "as-is" specs (faithful to actual APIs) and "normalized" specs (unified interface).

**Rejected because**:
- Doubles maintenance burden
- Confusing to users which to use
- The "normalized" version would still require adapters in real code

## Consequences

### Positive
- **Accurate**: Specs match actual API behavior
- **Useful for code generation**: Generators see real patterns and can handle them correctly
- **Transparent**: Users know exactly what to expect from each API
- **Lower maintenance**: No need to maintain abstraction layers or adapters

### Negative
- **Complexity for code generators**: Must handle multiple authentication schemes, pagination patterns, error formats
- **Complexity for users**: Must understand that not all APIs work the same way
- **Documentation burden**: Must document each API's specific patterns clearly

## Related Decisions

- **CONTEXT.md**: Documents all 10 APIs, their authentication schemes, pagination patterns, and data sources so users understand the landscape
- **Per-API READMEs**: Each API folder documents its specific patterns and any discrepancies found during testing

## Notes

The decision to document APIs as-is does not preclude code generators from later creating normalized clients on top of these specs. A generator could:
- Read the "as-is" OpenAPI specs
- Detect which auth scheme, pagination, or error pattern each API uses
- Generate client code that handles those patterns correctly
- Optionally expose a normalized interface to users

But that normalization happens in the generated code, not in the specs themselves.
