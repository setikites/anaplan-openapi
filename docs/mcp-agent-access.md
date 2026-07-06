# Exposing the Anaplan APIs to an LLM Agent

How should an agent (Claude or similar) consume a large, multi-API surface like the
ten Anaplan REST APIs documented in this repo? This note compares the design options
and the trade-offs that matter when the surface is big and the workflows are chained.

It is an exploration, not a decision — no ADR is implied.

## Evaluation criteria

Three properties drive the comparison:

- **Completeness** — can the agent reach every data point a task needs? Failure modes:
  missing cross-API pointers (e.g. resolving a model name to a `modelId`), and large
  intermediate results truncated when round-tripped through the context window.
- **Efficiency** — does the agent solve the task without excessive turns or token use?
  Two distinct costs: the *tool catalog* (tool definitions sitting in context) and the
  *workflow* (turns + intermediate data dumped to context for multi-step tasks).
- **Factuality** — is the result exactly correct, with no invented fields and no extra
  prose? Direct, transparent calls are easy to audit; generated code can fail silently.

The poster-child workflow is the ALM model sync (`alm/alm-mcp.json`), which chains
several calls: `getLatestRevision` → `getAppliedToModels` → `getSyncableRevisions` →
`createSyncTask` → poll `getSyncTask` until terminal. Chained, list-heavy, and it ends
in a poll loop — it exercises every weakness below.

## The options

### A. Per-operation MCP

One MCP tool per API operation, generated from the spec. This repo already prepares for
it: `scripts/make_mcp.py` strips each spec to a minimal `<api>-mcp.json`
(operationId, summary, description, parameters, requestBody, security — response bodies
reduced to status + description, unreachable schemas dropped).

- The tool catalog grows with the API. Across ten APIs the definitions alone bloat context.
- Each step is a separate tool call (a turn); every intermediate result lands in context.
- Permissioning is fine-grained — allow or deny per operation.
- No SDK, no sandbox. Simplest infrastructure.

### B. Search / execute MCP

Two tools. `search` returns operation documentation for a query; `execute` makes **one**
direct API call by `opId` + params. Dynamic discovery replaces a static catalog.

- Fixes A's catalog bloat: two tool definitions, op docs loaded on demand.
- Still N turns for an N-step workflow, and intermediate lists still land in context.
  Only half of A's efficiency problem is solved.
- Permissioning stays fine-ish: `execute` carries the `opId`, so calls can be gated by it.
- No SDK, no sandbox — `execute` is a generic HTTP caller.

### C. Stainless code-mode (search / execute with generated code)

Two tools. `search` returns TypeScript SDK function documentation; `execute` runs
TypeScript that Claude writes against those SDK functions, composing **many** calls.

- Lean catalog (two tools) **and** chained workflows run in a single `execute` turn.
- Intermediate data stays in the JS runtime; only the final answer returns to context.
  This is the decisive win on chained, list-heavy tasks.
- Requires a generated SDK (Stainless builds it from the OpenAPI spec) and a sandbox to
  run agent-authored code with credentials. The heaviest infrastructure.
- Permissioning is coarse — one `execute` hides N calls behind opaque code.
- Generated code can fail silently; one layer removed from verification.

### D. Search / execute with meta-programming primitives

Design B plus a small, **closed, sub-Turing** set of composition tools that run inside the
MCP server's own trusted process — no code sandbox, no generated SDK:

- **`pipe([opId...], bindings)`** — sequential; bind an output field of step N into a
  parameter of step N+1.
- **`map(opId, listExpr, paramMapping)`** — fan-out: run one op over each item of a prior
  result.
- **`project(expr)`** — JMESPath/JSONPath trim, so an intermediate returns only the field
  the next step needs. This keeps large lists off-context — C's main advantage — using a
  query string instead of a runtime.

The ALM sync *discovery* phase becomes one `pipe`:

```
getLatestRevision     → project `revision.id`
  → getAppliedToModels → project `models[0].modelId` as sourceModelId
  → getSyncableRevisions → project `[0].sourceRevisionId`
  → createSyncTask
```

Six turns and five intermediate dumps collapse to one call, at near-zero context cost —
with no SDK and no sandbox.

## Scored against the criteria

| | A. Per-op | B. Search/execute | C. Code-mode | D. Meta-primitives |
|---|---|---|---|---|
| Tools | N (one per op) | 2 | 2 | 2 + small primitive set |
| `execute` does | n/a (direct call) | one API call | runs generated code, many calls | declarative compose, many calls |
| Tool-catalog context | bloats with API | lean | lean | lean |
| Chained task (ALM sync) | N turns | N turns | 1 turn | 1 turn (discovery) |
| Intermediate data | dumped to context | dumped to context | off-context (runtime) | off-context (`project`) |
| Infra | spec → tools | spec + search + HTTP exec | SDK gen + sandbox | spec + search + primitives |
| SDK needed | no | no | yes | no |
| Sandbox needed | no | no | yes | no |
| Permissioning | fine (per tool) | fine-ish (by opId) | coarse (whole script) | fine-ish (per opId in plan) |

**Efficiency:** C and D solve both the catalog and the workflow cost. B fixes only the
catalog. A fixes neither and is worst at scale. Rank: **C ≈ D > B > A**.

**Factuality:** A and B make transparent, auditable direct calls. D fills a declarative
template referencing real typed fields — inspectable before execution. C's generated code
is the most powerful but the least transparent and can fail silently.
Rank: **A ≈ B ≈ D > C** (slight).

**Completeness:** C and D compose and trim server-side, so large lists are not truncated
through context. A and B depend on cross-reference hints in descriptions and risk
truncation when round-tripping. Rank: **C ≈ D > B ≈ A**.

In all four, completeness also depends on the cross-API discovery hints baked into the
spec descriptions (e.g. the ALM `modelId` parameter points to `GET /models` in the
Integration API). Those hints are what let an agent reach every data point without loading
an unrelated spec, and they survive the MCP slimming intact.

## The meta-programming boundary

Option D is attractive because it recovers most of C's efficiency while keeping B's safety
and auditability. But it has a sharp boundary worth naming, because crossing it quietly is
the main risk.

- **Greenspun creep.** Once `map` exists, the next ask is `filter`, then conditionals, then
  `reduce`, then variables, then error handling. Each rung is new surface; the endpoint is a
  reinvented, buggy programming language. The discipline *is* freezing the primitive set.
- **The poll loop is the canary.** The ALM sync cannot finish in pure `pipe` + `map`:
  `createSyncTask` must be followed by polling until a terminal state. That needs a
  predicate — a boolean expression — and the moment a primitive (`pollUntil(op, condition)`)
  needs one, the DSL starts wanting real control flow. That is the line.
- **Fan-out is server policy.** `map` over 50 items is 50 real calls: rate limits,
  concurrency, and partial failure (item 7 fails — abort, continue, or return partials?).
  Code-mode pushes these to the agent; meta-primitives force the server to choose and own a
  policy.
- **Binding-expression factuality.** A wrong JMESPath (`appliedToModels[0].modelId`) yields
  a silent empty result — a failure mode B does not have.

This gives a clean demarcation: **meta-primitives handle data composition (pipe, fan-out,
projection); they punt control flow (conditionals, loops, aggregation, poll predicates).**

Decision rule:

- Workflow is pipe + map + project → **D** wins (C's efficiency, B's safety and audit).
- Workflow needs branching, aggregation, poll-until, or retry logic → you have **earned C**.

## Recommendation

There is no single winner; the right rung depends on workflow shape and infrastructure
appetite.

1. **A** only for a small surface or when strict per-operation permissioning is required and
   code execution is unacceptable.
2. **B** as the cheapest real upgrade over A — kills the catalog bloat with no SDK and no
   sandbox — when tasks are mostly single calls.
3. **D** when chained, list-heavy workflows dominate (Anaplan's ALM sync and integration
   pipelines do) but a code sandbox is unwanted. Ship a frozen three-primitive set
   (`pipe`, `map`, `project`) and route genuinely procedural tasks — anything past the poll
   loop — to C.
4. **C** when chained workflows with real control flow are common and a sandbox plus
   generated SDK are acceptable. Migrate the spec's cross-reference description hints into
   SDK docstrings so `search` surfaces them.

These are not mutually exclusive: search/execute (B or D) for workflows, a few gated
direct tools (A) for the high-risk operations you want permissioned individually.

A practical path: **B now** for the immediate catalog fix, add **D's primitives** as
chained-workflow token cost shows up, and reserve **C** for the procedural tasks the
primitives deliberately refuse to handle.
