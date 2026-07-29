"""Transform <api>-openapi.json -> <api>-ptc.json for programmatic tool calling.

Sibling of scripts/make_mcp.py, not a replacement. MCP gives the model one tool per
operation and the response reaches the model anyway, so make_mcp strips response bodies.
Programmatic tool calling inverts that: a downstream consumer exposes two tools, `catalog`
and `anaplan_op`, and the agent writes Python that reads the response body before any
response exists. Every field name in that code is a guess unless the response shape is
known, and a write operation cannot be probed to learn it. So the 2xx response schema is
dereferenced and kept here.

Output holds the two payloads the downstream tools return, so no document assembly runs at
request time:
  - `catalog` — array, one compact entry per operation (op_id, method, path, parameters,
    summary, request-body field names). Always loaded by the consumer.
  - `detail`  — map keyed by op_id (description, resolved parameter / request-body / 2xx
    response schemas). Fetched on demand for the few operations a script uses.

Carried over from make_mcp unchanged: operationId synthesis, workspace-scoped path dedup,
opaque-ID constraint stripping, verbatim prose, source-order emission.

Dropped relative to make_mcp: `security` and `securitySchemes`. Auth is host-side.

Three APIs are excluded at build time and get no -ptc.json at all — see EXCLUDED. A
consumer must not be able to reach an excluded operation through a config mistake.

Response `$ref` graphs in these specs are recursive, so the resolver carries a per-branch
cycle guard and a depth cap. Truncation is marked in the committed artifact (an
`x-ptc-truncated` node in the schema plus `response_truncated` on the detail entry): a
lossy dereference lands in a diff a reviewer sees, not silently inside a script that is
already calling a production tenant.

Usage: uv run python scripts/make_ptc.py integration/integration-openapi.json
"""

import json
import pathlib
import re
import sys

from make_mcp import METHODS, WS, opid, strip_id_constraints

# authentication + oauth: token minting is host-side and stays outside the agent surface.
# financial-consolidation: its paging is not implemented downstream.
EXCLUDED = {"authentication", "oauth", "financial-consolidation"}

MAX_DEPTH = 40  # ponytail: deepest real schema here is far under this; raise if one grows
TRUNC = "x-ptc-truncated"
JSON_CT = re.compile(r"\bjson\b")  # application/json and application/scim+json
NO_RESPONSE = "no documented 2xx JSON response schema — probe a read operation to learn it"


def resolve(doc, ref):
    """Resolve a local JSON pointer ('#/components/schemas/Foo') against the document."""
    if not ref.startswith("#/"):
        raise ValueError(f"non-local $ref: {ref}")
    node = doc
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def deref(node, doc, marks, chain=(), depth=0):
    """Inline every local $ref. `chain` holds the refs open on this branch only, so a shape
    reused by two siblings resolves twice but a shape that contains itself terminates.
    Each truncation is recorded in `marks` and marked in place."""
    if depth > MAX_DEPTH:
        marks.append(f"depth limit {MAX_DEPTH}")
        return {TRUNC: f"depth limit {MAX_DEPTH}"}
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            if ref in chain:
                marks.append(ref)
                return {TRUNC: f"recursive schema, truncated at {ref}"}
            return deref(resolve(doc, ref), doc, marks, chain + (ref,), depth + 1)
        return {k: deref(v, doc, marks, chain, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [deref(v, doc, marks, chain, depth + 1) for v in node]
    return node


def merge_params(item, op, doc, marks):
    """Path-item parameters plus operation parameters, resolved, with the operation's own
    winning on a (name, in) clash — the OpenAPI override rule."""
    merged = {}
    for src in (item.get("parameters"), op.get("parameters")):
        for p in src if isinstance(src, list) else []:
            p = deref(p, doc, marks)
            merged[(p.get("name"), p.get("in"))] = p
    out = list(merged.values())
    strip_id_constraints(out)
    return out


def request_body(op, doc, marks):
    rb = op.get("requestBody")
    if not isinstance(rb, dict):
        return None
    rb = deref(rb, doc, marks)
    content = rb.get("content") or {}
    ct = next((c for c in content if JSON_CT.search(c)), next(iter(content), None))
    if ct is None or not isinstance(content[ct], dict) or "schema" not in content[ct]:
        return None
    return {"media_type": ct, "required": bool(rb.get("required")), "schema": content[ct]["schema"]}


def body_fields(schema):
    """Top-level field names of a request body, for the compact catalog entry. Unwraps an
    array body to its item shape and unions allOf members."""
    while isinstance(schema, dict) and isinstance(schema.get("items"), dict):
        schema = schema["items"]
    if not isinstance(schema, dict):
        return []
    names = list(schema.get("properties") or {})
    for member in schema.get("allOf") or []:
        names.extend(n for n in body_fields(member) if n not in names)
    return names


def response_schema(op, doc, marks):
    """First 2xx response with a JSON media type, dereferenced. None when the spec
    documents no such schema — 36 of the 134 operations do not."""
    for code, resp in (op.get("responses") or {}).items():
        if not code.startswith("2") or not isinstance(resp, dict):
            continue
        for _ in range(5):  # components/responses entries are reached by $ref
            if not isinstance(resp.get("$ref"), str):
                break
            resp = resolve(doc, resp["$ref"])
        for ct, media in (resp.get("content") or {}).items():
            if JSON_CT.search(ct) and isinstance(media, dict) and "schema" in media:
                return {"status": code, "media_type": ct, "schema": deref(media["schema"], doc, marks)}
    return None


def transform(doc):
    paths = doc["paths"]
    norm = lambda s: s.rstrip("/")
    known = {norm(p) for p in paths}

    catalog, detail = [], {}
    for path, item in paths.items():
        m = WS.match(path)
        if m and norm(m.group(1)) in known:
            continue  # duplicate: shorter model-direct twin exists -> drop workspace-scoped
        for method, op in item.items():
            if method not in METHODS or not isinstance(op, dict):
                continue
            op_id = op.get("operationId") or opid(method, path)
            assert op_id not in detail, f"duplicate operationId: {op_id}"

            marks = []
            params = merge_params(item, op, doc, marks)
            body = request_body(op, doc, marks)
            body_marks = len(marks)
            response = response_schema(op, doc, marks)

            entry = {
                "op_id": op_id,
                "method": method.upper(),
                "path": path,
                "summary": op.get("summary", ""),
                "parameters": [
                    {
                        "name": p.get("name"),
                        "in": p.get("in"),
                        "required": bool(p.get("required")),
                        "type": (p.get("schema") or {}).get("type"),
                    }
                    for p in params
                ],
            }
            if body is not None:
                entry["body_fields"] = body_fields(body["schema"])
            catalog.append(entry)

            det = {
                "description": op.get("description", ""),
                "parameters": params,
                "request_body": body,
                "response": response,
            }
            if response is None:
                det["response_note"] = NO_RESPONSE
            elif len(marks) > body_marks:
                det["response_truncated"] = True
            detail[op_id] = det

    return {"catalog": catalog, "detail": detail}


def render_ptc(spec):
    """Serialize a *-openapi.json spec dict to its canonical *-ptc.json text. Single source
    of truth so the drift check (scripts/check_generated.py) and the writer never diverge."""
    return json.dumps(transform(spec), indent=2) + "\n"


def main(src):
    if not src.endswith("-openapi.json"):
        sys.exit(f"expected a *-openapi.json file, got: {src}")
    api = pathlib.Path(src).parent.name
    if api in EXCLUDED:
        sys.exit(f"{api} is excluded from the PTC surface — no -ptc.json is produced")
    dst = src.replace("-openapi.json", "-ptc.json")
    spec = json.load(open(src, encoding="utf-8"))
    text = render_ptc(spec)
    pathlib.Path(dst).write_text(text, encoding="utf-8")
    out = transform(spec)
    n_resp = sum(1 for d in out["detail"].values() if d["response"] is not None)
    n_trunc = sum(1 for d in out["detail"].values() if d.get("response_truncated"))
    print(f"{dst}: {len(out['catalog'])} operations, {n_resp} with a 2xx JSON schema, {n_trunc} truncated")


def _selfcheck():
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/models/{modelId}/exports": {
                "parameters": [{"name": "modelId", "in": "path", "required": True, "schema": {"type": "string", "pattern": "^[0-9A-F]{32}$"}, "example": "A1B2"}],
                "get": {"summary": "s", "description": "d", "responses": {"200": {"description": "ok"}}},
            },
            "/workspaces/{workspaceId}/models/{modelId}/exports": {"get": {"responses": {"200": {"description": "dup"}}}},
            "/x": {"post": {
                "operationId": "doX",
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Req"}}}},
                "responses": {"200": {"$ref": "#/components/responses/Rec"}},
            }},
        },
        "components": {
            "schemas": {
                "Req": {"type": "object", "properties": {"n": {"type": "string"}}},
                "Node": {"type": "object", "properties": {"kids": {"type": "array", "items": {"$ref": "#/components/schemas/Node"}}}},
            },
            "responses": {"Rec": {"description": "ok", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Node"}}}}},
        },
    }
    out = transform(doc)
    ids = [e["op_id"] for e in out["catalog"]]
    assert ids == ["getModelsByModelidExports", "doX"], ids  # dup path dropped, id synthesized
    p0 = out["detail"]["getModelsByModelidExports"]["parameters"][0]
    assert "example" not in p0 and "pattern" not in p0["schema"]  # opaque ID constraints stripped
    assert out["detail"]["getModelsByModelidExports"]["response"] is None
    assert out["detail"]["getModelsByModelidExports"]["response_note"] == NO_RESPONSE
    assert out["catalog"][1]["body_fields"] == ["n"]
    doX = out["detail"]["doX"]
    assert doX["response_truncated"] is True  # recursive Node terminated and marked
    assert doX["response"]["schema"]["properties"]["kids"]["items"][TRUNC].startswith("recursive schema")
    assert "$ref" not in json.dumps(out) and "security" not in json.dumps(out)
    assert render_ptc(doc) == render_ptc(doc)
    print("selfcheck OK")


if __name__ == "__main__":
    _selfcheck() if len(sys.argv) == 1 else main(sys.argv[1])
