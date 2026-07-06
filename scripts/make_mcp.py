"""Transform <api>-openapi.json -> minimal <api>-mcp.json for MCP tool generation.

Keeps what an MCP server needs to expose one tool per operation: operationId (synthesized
when absent), summary, description, parameters, requestBody, security, plus servers,
top-level security, and securitySchemes. Strips response bodies to bare status+description
and drops every component schema not reachable from a parameter or requestBody.

Dedup: where the same operation is reachable both model-direct (`/models/{modelId}/X`) and
workspace-scoped (`/workspaces/{workspaceId}/models/{modelId}/X`), the longer workspace path
is dropped. Specs without that duality are unaffected (regex just never matches).

Descriptions are kept verbatim — prose can't be auto-summarized reliably; trim by hand if needed.

Usage: uv run python scripts/make_mcp.py integration/integration-openapi.json
"""

import json
import re
import sys

METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
KEEP = ("summary", "description", "parameters", "requestBody", "security")
WS = re.compile(r"^/workspaces/\{workspaceId\}(/models/\{modelId\}/.*)$")
ID_PARAM = re.compile(r"Id$")  # opaque IDs (modelId, exportId, ...): agent copies real values from prior calls


def strip_id_constraints(parameters):
    """Drop example/pattern/format on opaque-ID params; the agent copies those from prior
    responses, never builds them from a regex. The format hint stays in the description."""
    for p in parameters:
        if isinstance(p, dict) and ID_PARAM.search(p.get("name", "")):
            p.pop("example", None)
            if isinstance(p.get("schema"), dict):
                for k in ("example", "pattern", "format"):
                    p["schema"].pop(k, None)


def opid(method, path):
    parts = [method]
    for seg in path.strip("/").split("/"):
        parts.append("By" + seg[1:-1].capitalize() if re.fullmatch(r"\{.+\}", seg) else seg.capitalize())
    return "".join(parts)


def collect_refs(node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(v) if k == "$ref" and isinstance(v, str) else collect_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_refs(v, out)


def transform(d):
    paths = d["paths"]
    norm = lambda s: s.rstrip("/")
    known = {norm(p) for p in paths}

    out_paths, ids = {}, set()
    for path, item in paths.items():
        m = WS.match(path)
        if m and norm(m.group(1)) in known:
            continue  # duplicate: shorter model-direct twin exists -> drop workspace-scoped
        new_item = {}
        for key, op in item.items():
            if key not in METHODS or not isinstance(op, dict):
                if key == "parameters" and isinstance(op, list):
                    strip_id_constraints(op)  # path-item-level params, shared across methods
                new_item[key] = op
                continue
            oid = op.get("operationId") or opid(key, path)
            assert oid not in ids, f"duplicate operationId: {oid}"
            ids.add(oid)
            nop = {"operationId": oid}
            nop.update({f: op[f] for f in KEEP if f in op})
            if isinstance(nop.get("parameters"), list):
                strip_id_constraints(nop["parameters"])
            nop["responses"] = {
                c: {"description": r.get("description", "")} if isinstance(r, dict) else r
                for c, r in op.get("responses", {}).items()
            }
            new_item[key] = nop
        out_paths[path] = new_item

    out = {"openapi": d.get("openapi", "3.0.0"), "info": d["info"]}
    for top in ("servers", "security"):
        if top in d:
            out[top] = d[top]
    out["paths"] = out_paths

    comps = d.get("components", {})
    schemas = comps.get("schemas", {})
    comp_params = comps.get("parameters", {})
    seed = set()
    collect_refs(out_paths, seed)

    # Carry the referenced shared parameters (paths $ref them post-ADR-0005);
    # prune unreferenced ones like schemas, and strip ID constraints to match
    # the inline treatment. Schemas a carried param references stay reachable.
    kept_params = {}
    for ref in seed:
        if ref.startswith("#/components/parameters/"):
            name = ref.rsplit("/", 1)[-1]
            if name in comp_params and name not in kept_params:
                kept_params[name] = comp_params[name]
    strip_id_constraints(list(kept_params.values()))
    collect_refs(kept_params, seed)

    queue, seen, kept = list(seed), set(), {}
    while queue:
        ref = queue.pop()
        if ref in seen:
            continue
        seen.add(ref)
        if ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[-1]
            if name in schemas and name not in kept:
                kept[name] = schemas[name]
                sub = set()
                collect_refs(schemas[name], sub)
                queue.extend(sub)

    out_comps = {}
    if kept:
        out_comps["schemas"] = kept
    if kept_params:
        out_comps["parameters"] = kept_params
    if "securitySchemes" in comps:
        out_comps["securitySchemes"] = comps["securitySchemes"]
    if out_comps:
        out["components"] = out_comps
    return out


def main(src):
    if not src.endswith("-openapi.json"):
        sys.exit(f"expected a *-openapi.json file, got: {src}")
    dst = src.replace("-openapi.json", "-mcp.json")
    d = json.load(open(src, encoding="utf-8"))
    out = transform(d)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    n_tools = sum(1 for it in out["paths"].values() for k in it if k in METHODS)
    print(f"{dst}: {len(out['paths'])} paths, {n_tools} tools, {len(out.get('components', {}).get('schemas', {}))} schemas")


def _selfcheck():
    d = {
        "openapi": "3.0.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/models/{modelId}/exports": {
                "parameters": [{"name": "modelId", "in": "path", "schema": {"type": "string", "pattern": "^[0-9A-F]{32}$"}, "example": "A1B2"}],
                "get": {"responses": {"200": {"description": "ok", "content": {"x": 1}}}},
            },
            "/workspaces/{workspaceId}/models/{modelId}/exports": {"get": {"responses": {"200": {"description": "dup"}}}},
            "/x": {"post": {
                "operationId": "doX",
                "parameters": [
                    {"name": "modelId", "in": "path", "schema": {"type": "string", "example": "ABC123"}},
                    {"name": "type", "in": "query", "schema": {"type": "string", "example": "all"}},
                ],
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Req"}}}},
                "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Resp"}}}}},
            }},
            "/y/{fooId}": {
                "parameters": [{"$ref": "#/components/parameters/FooId"}],
                "get": {"responses": {"200": {"description": "ok"}}},
            },
        },
        "components": {
            "schemas": {
                "Req": {"type": "object", "properties": {"n": {"$ref": "#/components/schemas/Sub"}}},
                "Sub": {"type": "string"},
                "Resp": {"type": "object"},
            },
            "parameters": {
                "FooId": {"name": "fooId", "in": "path", "schema": {"type": "string", "pattern": "^X$"}, "example": "x1"},
                "Unused": {"name": "unused", "in": "query", "schema": {"type": "string"}},
            },
            "securitySchemes": {"B": {"type": "http", "scheme": "bearer"}},
        },
    }
    out = transform(d)
    assert "/workspaces/{workspaceId}/models/{modelId}/exports" not in out["paths"]  # dup dropped
    assert out["paths"]["/models/{modelId}/exports"]["get"]["operationId"] == "getModelsByModelidExports"  # synthesized
    p0 = out["paths"]["/models/{modelId}/exports"]["parameters"][0]
    assert "example" not in p0 and "pattern" not in p0["schema"]  # path-level ID example + pattern stripped
    assert out["paths"]["/x"]["post"]["responses"]["200"] == {"description": "ok"}  # response body stripped
    px = {p["name"]: p for p in out["paths"]["/x"]["post"]["parameters"]}
    assert "example" not in px["modelId"]["schema"]  # opaque ID example stripped
    assert px["type"]["schema"]["example"] == "all"  # non-ID example kept
    assert set(out["components"]["schemas"]) == {"Req", "Sub"}  # Resp (response-only) pruned, Sub kept transitively
    cp = out["components"]["parameters"]
    assert set(cp) == {"FooId"}  # referenced param carried, Unused pruned
    assert "example" not in cp["FooId"] and "pattern" not in cp["FooId"]["schema"]  # ID constraints stripped on carried param
    assert "securitySchemes" in out["components"]
    print("selfcheck OK")


if __name__ == "__main__":
    _selfcheck() if len(sys.argv) == 1 else main(sys.argv[1])
