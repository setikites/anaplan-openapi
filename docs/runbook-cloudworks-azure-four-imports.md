# Runbook: sequence four Azure Blob imports across two models (D-style)

Load four files from Azure Blob Storage into Anaplan via CloudWorks, running all
four imports as one ordered sequence — two models (`Alice`, `Bob`), two imports
each, nothing configured in CloudWorks yet.

Written against the **D-style meta-programming** agent design in
[mcp-agent-access.md](./mcp-agent-access.md): the only tools are `search` /
`execute` plus the frozen composition primitives `pipe` / `map` / `project`. It
reads the `*-mcp.json` specs only. Assumes the MCP server is already
authenticated.

`pipe([opId...], bindings)` chains calls; `map(opId, listExpr, paramMapping)`
fans one op over a list; `project(expr)` is a JMESPath trim that keeps large
intermediate results off-context.

## Prerequisites

- CloudWorks connection-create + integration-create rights; imports pre-defined
  in both models.
- The Azure `fileId` lookup relies on the cross-reference hint added in
  **#214**: the CloudWorks `Job.targets[].fileId` description states an import's
  `fileId` is the import's own `importDataSourceId`, from
  `GET /models/{modelId}/imports/{importId}` — not the model-wide file list.

## Inputs (literals — not API-discoverable)

```
CONN = { storageAccountName, containerName, sasToken }     # Azure creds
JOBS_IN = [                                                 # which blob feeds which import (design choice)
  { model:"Alice", importName:"A1", blob:"alice1.csv" },
  { model:"Alice", importName:"A2", blob:"alice2.csv" },
  { model:"Bob",   importName:"B1", blob:"bob1.csv"   },
  { model:"Bob",   importName:"B2", blob:"bob2.csv"   },
]
```

The blob-to-import pairing is a design decision, not an API fact. Supply it.

## Phase 1 — resolve modelId + workspaceId (pipe + project)

```
getModels
  → project "models[?name=='Alice'||name=='Bob'].{name:name, modelId:id, wsId:currentWorkspaceId}"
# M = [{Alice,mA,wA},{Bob,mB,wB}]
```

`wsId` from each model's `currentWorkspaceId` — the built-in Integration→CloudWorks
chaining (see [ADR 0004](./adr/0004-id-source-path-descriptions.md)).

## Phase 2 — resolve each import's actionId + fileId (map + project)

Two models is fixed and small, so unroll per model — this removes the
parent→child join (carrying `modelId`/`wsId` down onto each import). The
general-N form would need a `zip` primitive D deliberately lacks.

```
# Alice
getModelsByModelidImports (modelId=mA)
  → project "imports[?name=='A1'||name=='A2'].{importId:id, name:name}"
map(getModelsByModelidImportsByImportid, <those>, {modelId:mA, importId:importId})
  → project "{importId:importId, fileId: importDataSourceId}"      # #214: fileId = importDataSourceId
# Bob — same with mB
```

Join Phase 1 (`wsId`) + Phase 2 (`importId`, `fileId`) + `JOBS_IN` (`blob`) by
(model, importName) into four flat units:

```
U = [
  {modelId:mA, wsId:wA, importId:iA1, fileId:fA1, blob:"alice1.csv"},
  {modelId:mA, wsId:wA, importId:iA2, fileId:fA2, blob:"alice2.csv"},
  {modelId:mB, wsId:wB, importId:iB1, fileId:fB1, blob:"bob1.csv"},
  {modelId:mB, wsId:wB, importId:iB2, fileId:fB2, blob:"bob2.csv"},
]
```

## Phase 3 — create the Azure connection (1 call)

```
createConnection { type:"AzureBlob", body:{
  name:"az-src", storageAccountName, containerName, auth_method:"SAS-based", sasToken }}
  → project "connectionId"   → C
```

If the auth account is a **restricted integration user** and Alice/Bob live in
different workspaces, set `body.workspaceId` and create **one connection per
workspace** — `C` becomes per-model.

## Phase 4 — one integration per import (map)

A single-element `jobs` array is a fixed template with scalar bindings, so
`createIntegration` stays inside `map` (no variable-length array to fold):

```
map(createIntegration, U, {
  name: "cw-" & modelId & "-" & importId,
  version: "2.0", workspaceId: wsId, modelId: modelId,
  jobs: [ { type:"AzureBlobToAnaplan",
            sources:[{ type:"AzureBlob", connectionId: C, file: blob }],
            targets:[{ type:"Anaplan", actionId: importId, fileId: fileId }] } ]
})
  → project "[].integrationId"   → IIDs   # ordered A1,A2,B1,B2
```

## Phase 5 — sequence them (integration flow owns ordering)

`steps[].dependsOn` chains each step to the previous, so ordering is enforced
server-side — no client-side poll-between-runs:

```
createIntegrationFlow { name:"alice-bob-seq", version:"2.0", type:"IntegrationFlow", steps:[
  { type:"Integration", referrer:IID[0], dependsOn:[],        isSkipped:false, exceptionBehavior:[{type:"failure",strategy:"stop"}] },
  { type:"Integration", referrer:IID[1], dependsOn:[step0Id], isSkipped:false, exceptionBehavior:[{type:"failure",strategy:"stop"}] },
  { type:"Integration", referrer:IID[2], dependsOn:[step1Id], isSkipped:false, exceptionBehavior:[{type:"failure",strategy:"stop"}] },
  { type:"Integration", referrer:IID[3], dependsOn:[step2Id], isSkipped:false, exceptionBehavior:[{type:"failure",strategy:"stop"}] },
]} → project "integrationFlowId" → F
```

`exceptionBehavior failure→stop` aborts the chain on any failure — no orphaned
later imports. The four-item `steps[]` is fine hand-written; a general-N version
is a fold (see W3 below), outside D.

## Phase 6 — run (1 call)

```
runIntegrationFlow(F)          # omit stepsToRun → all steps, in dependency order
```

## Phase 7 — confirm (the one punt)

`runIntegrationFlow` returns immediately. Terminal success means polling
`getRunHistory` per integration (or flow status) until done — a poll-until
predicate. That is control flow: outside D. Accept fire-and-forget, or hand this
tail to option C (code-mode).

## What each wall cost

| Wall | Kind | Status |
|------|------|--------|
| W1 parent→child join | join | dodged — unroll N=2 |
| W2 import→fileId | join | gone — `map`+`project` on `importDataSourceId` (#214) |
| W3 build `steps[]` | fold | written literal (N=4 fixed); general-N needs a fold |
| W4 confirm terminal | poll-until | punted → C |

Phases 1–6 run as `pipe`/`map`/`project` plus a literal flow. Only Phase 7
genuinely earns code-mode. #214 is what turned W2 from "guess the fileId" into a
documented lookup.
