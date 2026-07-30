# ADR 0007: Simplified Technical English for Spec Descriptions

**Status**: Accepted

**Date**: 2026-07-29

## Context

ADR 0003 says what a description must contain. It does not say how the
description must read. The result is ten specs with the same facts written in
ten voices. Some descriptions use semicolons to join two ideas. Some use
contractions. Some use long Latinate verbs ("obtain", "initiate", "utilize")
where a short common word says the same thing. Some run to 40 words.

The specs feed two consumers: a human reader in a Swagger or Redoc UI, and an
LLM code generator that reads the spec through an MCP server. Both consumers
read better when the prose is short, active, and uses one word for one thing.
An LLM that reads "enables you to initiate a process" must map that phrase back
to "starts a process". Plain prose removes that step.

ASD-STE100 (Simplified Technical English) is a published controlled-language
standard for technical writing. It gives a small set of mechanical rules that a
test can check.

## Decision

Spec `description` and `summary` text follows ASD-STE100 in STE-flavored mode.

### 1. Prose rules

- No semicolons. Write two sentences.
- No contractions. Write "does not", not "doesn't".
- Active voice when the sentence has a known actor.
- Short common words. Use *get* (not obtain), *start* (not initiate), *lets
  you* (not enables you to), *make sure* (not ensure), *about* (not regarding).
- American spelling.
- One sentence per idea. A descriptive sentence stays at or below 25 words.

### 2. Exemptions

A checker that flags correct text is worse than no checker. These spans are
outside the prose rules:

- Code spans, identifiers, and enum tokens such as `CANCELLED`.
- The possessive `'s`. It is not a contraction.
- The `servers[].description` region lists. They are comma lists, not prose.
- Markdown table rows and bullet lines.
- Actor-less passive voice such as "are returned" or "is supported". There is
  no actor to promote. A rewrite churns the specs for no gain.

### 3. Where the rules live

The rules live in `tests/test_description_standards.py`, next to the ADR 0003
sweeps. A prose-extraction helper walks every `description` and `summary` in
the ten specs, removes the exempt spans, and yields one sentence at a time with
its spec name and JSON path. Each prose rule is one sweep test over that
helper. No new script goes under `scripts/`.

## Rationale

### Form is separate from content

ADR 0003 governs content: whether a description exists at all, and what fact it
carries. This ADR governs form: how that fact reads. The two are complementary.
A description can pass ADR 0003 and fail this ADR, and the reverse is also
true.

### Mechanical rules are testable

Each rule above is a regular expression away from a test. A style guide that
nobody can check drifts back to ten voices within a few pull requests. A style
guide with a sweep test does not.

### The exemption list is the load-bearing part

A false positive costs more than a missed violation. A maintainer who sees the
checker flag `CANCELLED` as a spelling error stops trusting the checker. The
exemptions above come from real spans in the current specs.

## Alternatives Considered

### A. Full strict-mode STE

Strict mode adds the ~900-word approved dictionary and the 20-word instruction
cap.

**Rejected because**: the specs describe an API domain with its own nouns
(workspace, revision tag, chunk, action). A closed dictionary rejects them.
STE-flavored mode keeps the mechanical rules and drops the dictionary lockdown.

### B. A prose linter under `scripts/`

A separate script could run outside the test suite.

**Rejected because**: the ADR 0003 sweeps already live in
`tests/test_description_standards.py` and run in CI. A second entry point that
CI does not run is a rule nobody enforces.

### C. No prose standard

Leave the descriptions as they are.

**Rejected because**: the specs are the product. Ten voices in one artifact
read as ten authors, and the LLM consumer pays for the inconsistency on every
generation.

## Consequences

### Positive

- Description prose reads the same across the ten specs.
- New descriptions get checked at pull-request time, not at review time.
- The exemption list is explicit, so a contributor knows why a span passes.

### Negative

- Existing descriptions need a sweep to reach the standard. The follow-up
  issues do that work one rule at a time.
- A contributor who writes natural English gets a test failure for a semicolon.
  The failure message must name the rule and the fix.

## Related Decisions

- **ADR 0003**: Description standards. ADR 0003 governs content. This ADR
  governs form.
- **ADR 0006**: Minimum-role annotations. The role sentences it adds to
  operation descriptions follow this ADR.
