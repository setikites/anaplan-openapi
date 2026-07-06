# Building the Anaplan MCP Server (Option D)

Build guide for a **new repo** (`anaplan-mcp`) that exposes the Anaplan APIs to an
LLM agent using the meta-programming primitives of Option D in
[`mcp-agent-access.md`](./mcp-agent-access.md). This repo (`anaplan-openapi`) is a
**read-only data resource** — the MCP server consumes its `*-mcp.json` files and
adds nothing back.

## Core idea

Operations are **data**, `execute` is **generic**. No code generation, no SDK, no
sandbox. Load the 10 MCP specs at startup into one `opId → OperationDef` dict;
every tool works off that dict. That dict *is* the metaprogramming.

## Ownership split

- **`anaplan-openapi` (this repo)** owns the specs. `scripts/make_mcp.py` produces
  the 10 `*-mcp.json`. They are generated artifacts (currently untracked). Pick one
  and stick to it: **commit them** or **publish on a git tag**. The MCP server needs a
  stable pinned copy, never a live regen.
- **`anaplan-mcp` (new repo)** vendors the specs as a **git submodule** pinned to a tag
  here. Upstream regenerates → bump the submodule. No copied files, no drift.

## Layout

```
anaplan-mcp/
  specs/          # git submodule → anaplan-openapi, pinned tag (read-only)
  registry.py     # load specs, resolve $ref, build {opId: OperationDef}
  auth.py         # token from env; refresh via postTokenRefresh on 401
  execute.py      # opId + params → httpx call → {status, body}
  compose.py      # pipe / map / project — the 3 FROZEN primitives
  server.py       # MCP entrypoint: registers search, execute, pipe, map, project
  test_registry.py
```

Python — official MCP SDK, matches the `uv` toolchain. Deps: `mcp`, `httpx`, `jmespath`.
Nothing else.

## The load-bearing piece: `registry.py`

Everything hangs off this. Read each `specs/*/*-mcp.json`, walk `paths`, and for
each operation record method, path template, parameters, requestBody schema, the
`servers[]` list, and `security`. Resolve local `$ref` (`#/components/...`) at load so
downstream code never chases pointers.

```python
# registry.py — sketch
import glob, json
from dataclasses import dataclass

@dataclass
class Op:
    op_id: str
    method: str          # "get" | "post" | ...
    path: str            # "/models/{modelId}/onlineStatus"
    params: list         # resolved parameter objects
    request_body: dict | None
    summary: str
    description: str      # keep intact — holds the cross-API discovery hints

def load(specs_glob="specs/*/*-mcp.json") -> dict[str, Op]:
    reg = {}
    for path in glob.glob(specs_glob):
        spec = json.load(open(path))
        base_params = ...  # path-item-level parameters, $ref-resolved against spec
        for url, item in spec["paths"].items():
            for method in ("get", "post", "put", "patch", "delete"):
                if method not in item:
                    continue
                op = item[method]
                reg[op["operationId"]] = Op(
                    op_id=op["operationId"], method=method, path=url,
                    params=resolve_refs(base_params + op.get("parameters", []), spec),
                    request_body=resolve_refs(op.get("requestBody"), spec),
                    summary=op.get("summary", ""),
                    description=op.get("description", ""),
                )
    return reg
```

Keep `description` verbatim — the cross-API hints (ALM `modelId` → `GET /models` in
Integration) live there and are what let the agent chain across APIs. `search` surfaces
them for free.

## The 5 tools

- **`search(query)`** — substring/fuzzy match over `op_id + summary + description` across
  the registry. Returns matching op docs on demand. Keeps the tool catalog lean (this is
  what beats Option A's bloat).
- **`execute(op_id, params)`** — registry lookup; fill path template + query + body from
  `params`; add auth header; `httpx` call; return `{status, body}`.
- **`pipe`, `map`, `project`** — data composition, below.

## The 3 primitives — and the freeze

From `mcp-agent-access.md`:

- **`pipe([op_id...], bindings)`** — sequential; bind an output field of step N into a
  param of step N+1.
- **`map(op_id, list_expr, param_mapping)`** — fan-out one op over each item of a prior
  result.
- **`project(expr)`** — trim an intermediate to just the next step's field. Use
  **JMESPath** (the `jmespath` lib) — do not write a query parser.

**This set is frozen. Adding a fourth is the failure mode.**

- **No `filter`, `reduce`, conditionals, variables, retry.** Each is new surface; the
  endpoint is a reinvented buggy language (Greenspun creep).
- **The poll loop is the line.** ALM sync's `createSyncTask` → poll `getSyncTask` until
  terminal **cannot** be Option D — it needs a boolean predicate. When someone asks for
  `pollUntil`, stop: that task has *earned Option C* (a code sandbox). Route it there or
  to a human. Do not grow the DSL to reach it.
- **Fan-out is server policy, not agent policy.** `map` over 50 items is 50 real calls.
  Own one partial-failure policy in `map` itself — abort / continue / return-partials —
  plus a concurrency cap and rate-limit handling. Don't push it to the agent.
- **Binding factuality.** A wrong JMESPath yields a silent empty result — a failure mode
  plain `execute` doesn't have. Validate that a binding path resolves non-empty before
  feeding the next step; surface an error instead of calling with a null param.

Mark the freeze in `compose.py` so future-you doesn't quietly cross it:

```python
# ponytail: FROZEN primitive set — pipe, map, project only.
# Adding filter/reduce/conditionals/pollUntil means the task earned Option C (sandbox).
# Route it there; do NOT grow this DSL. See docs/mcp-agent-access.md "meta-programming boundary".
```

## Auth

Token from env (`ANAPLAN_TOKEN` or credentials → `postTokenAuthenticate`). On a 401 from
`execute`, refresh once via `postTokenRefresh`, retry once, then fail. Don't build a
session manager — one refresh-on-401 wrapper covers it.

## Build order — don't build it all at once

1. `registry.py` + `execute.py` + `auth.py` + **`search` and `execute` only**. That is
   Option **B** — shippable and useful on its own. Stop here until chained-workflow token
   cost actually shows up.
2. Add **`pipe` + `project`** when it does.
3. Add **`map`** last — it drags in the fan-out policy problem, so pay that cost only when
   fan-out is real.

## The one runnable check

`test_registry.py`: load the real `specs/`, assert a known op resolves fully — e.g.
`getSyncTask` has method `get`, its path contains `{taskId}`, and its `modelId` param
description still mentions the Integration `GET /models` source. That single assert fails
loudly if `$ref` resolution breaks or the specs move.

```
skipped: SDK codegen, sandbox, custom query parser, session manager, filter/reduce/pollUntil.
add when: a workflow needs real control flow → it earned Option C, a separate build.
```
