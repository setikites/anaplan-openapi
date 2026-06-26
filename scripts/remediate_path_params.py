"""
Remediate path parameter placement across all OpenAPI specs to conform to ADR 0005
(which supersedes the inline-path-param rule of ADR 0002).

Rule: a path parameter (in: path) that appears in more than one path item is
defined once in components/parameters and referenced via $ref at the path item
level. Path-item-level placement (ADR 0002) still holds; only the
inline-definition requirement is superseded.

Pattern uniformity (ADR 0005 §2): when collapsing N occurrences into one
component, a schema.pattern is kept only if every occurrence carried it
identically. Disagreeing occurrences drop the pattern rather than asserting a
guarantee the inputs never had. This script never *adds* a pattern.

Single-use path parameters (appearing in exactly one path item) stay inline.
"""

import json
import re
import sys
import collections
from pathlib import Path

_PATH_PARAM_RE = re.compile(r"\{(\w+)\}")

# ADR 0002 canonical field order for a parameter object
_PARAM_FIELD_ORDER = ["name", "in", "description", "required", "schema", "example"]

_HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
)


def _reorder_param(param: dict) -> dict:
    ordered = {k: param[k] for k in _PARAM_FIELD_ORDER if k in param}
    for k in param:
        if k not in ordered:
            ordered[k] = param[k]
    return ordered


def _pascal(name: str) -> str:
    return name[0].upper() + name[1:]


def _resolve_param(spec: dict, param: dict) -> dict:
    """Resolve a $ref parameter to its actual definition."""
    if "$ref" in param:
        ref = param["$ref"]
        if ref.startswith("#/components/parameters/"):
            name = ref.split("/")[-1]
            return spec.get("components", {}).get("parameters", {}).get(name, param)
    return param


def _canonical_schema(schemas: list[dict]) -> dict:
    """Reconcile occurrence schemas. Identical -> that schema. Differ only by
    'pattern' -> drop pattern (ADR 0005 §2). Otherwise raise."""
    keyed = {json.dumps(s, sort_keys=True) for s in schemas}
    if len(keyed) == 1:
        return schemas[0]
    no_pattern = {
        json.dumps({k: v for k, v in s.items() if k != "pattern"}, sort_keys=True)
        for s in schemas
    }
    if len(no_pattern) == 1:
        s = dict(schemas[0])
        s.pop("pattern", None)
        return s
    raise SystemExit(f"non-reconcilable path-param schemas: {keyed}")


def _best(values: list, *, prefer_long=False):
    present = [v for v in values if v not in (None, "")]
    if not present:
        return None
    return max(present, key=len) if prefer_long else present[0]


def remediate_spec(spec: dict) -> dict:
    """Return a new spec dict with repeated path parameters extracted to
    components/parameters and $ref'd at the path item level."""
    spec = json.loads(json.dumps(spec))  # deep copy
    paths = spec.get("paths", {})

    # ---- collect occurrences of each path param across all path items ----
    occ = collections.defaultdict(
        lambda: {"schemas": [], "descs": [], "examples": [], "items": set()}
    )

    def _scan(path_str, param):
        resolved = _resolve_param(spec, param)
        if resolved.get("in") != "path" or "name" not in resolved:
            return
        name = resolved["name"]
        acc = occ[name]
        acc["schemas"].append(resolved.get("schema", {"type": "string"}))
        acc["descs"].append(resolved.get("description"))
        acc["examples"].append(resolved.get("example"))
        acc["items"].add(path_str)

    for path_str, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for param in path_item.get("parameters", []):
            _scan(path_str, param)
        for method in _HTTP_METHODS:
            op = path_item.get(method)
            if isinstance(op, dict):
                for param in op.get("parameters", []):
                    _scan(path_str, param)

    # Names that appear in more than one path item are extracted.
    extract = {name for name, acc in occ.items() if len(acc["items"]) > 1}

    # ---- build / merge components.parameters ----
    components = spec.setdefault("components", {})
    comp_params = components.setdefault("parameters", {})
    key_of = {}
    for name in extract:
        acc = occ[name]
        schema = _canonical_schema(acc["schemas"])
        defn = {"name": name, "in": "path", "required": True, "schema": schema}
        desc = _best(acc["descs"], prefer_long=True)
        if desc:
            defn["description"] = desc
        example = _best(acc["examples"])
        if example is not None:
            defn["example"] = example
        key = _pascal(name)
        comp_params[key] = _reorder_param(defn)
        key_of[name] = key

    # ---- rewrite path items: $ref extracted path params at item level ----
    for path_str, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        segments = _PATH_PARAM_RE.findall(path_str)

        # strip path params from operations (and swap nothing else)
        for method in _HTTP_METHODS:
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            kept = [
                p for p in op.get("parameters", [])
                if _resolve_param(spec, p).get("in") != "path"
            ]
            if kept:
                op["parameters"] = kept
            elif "parameters" in op:
                del op["parameters"]

        # rebuild path-item params: path params (refs for extracted, inline for
        # single-use) in segment order, then surviving non-path item params
        existing = path_item.get("parameters", [])
        non_path = [p for p in existing if _resolve_param(spec, p).get("in") != "path"]
        inline_defs = {}  # name -> inline def, for single-use params
        for p in existing:
            r = _resolve_param(spec, p)
            if r.get("in") == "path" and "name" in r:
                inline_defs.setdefault(r["name"], r)
        # also pull single-use inline defs that were declared only in operations
        for name in segments:
            if name in inline_defs or name in extract:
                continue
            if name in occ:
                acc = occ[name]
                defn = {"name": name, "in": "path", "required": True,
                        "schema": _canonical_schema(acc["schemas"])}
                d = _best(acc["descs"], prefer_long=True)
                if d:
                    defn["description"] = d
                ex = _best(acc["examples"])
                if ex is not None:
                    defn["example"] = ex
                inline_defs[name] = defn

        ordered = []
        for name in segments:
            if name in extract:
                ordered.append({"$ref": f"#/components/parameters/{key_of[name]}"})
            elif name in inline_defs:
                ordered.append(_reorder_param(dict(inline_defs[name])))
        new_params = ordered + non_path
        if new_params:
            path_item["parameters"] = new_params
        elif "parameters" in path_item:
            del path_item["parameters"]

    if not comp_params:
        del components["parameters"]
    if not components:
        del spec["components"]

    return spec


def main() -> int:
    repo_root = Path(__file__).parent.parent
    if len(sys.argv) > 1:
        spec_files = [Path(a) for a in sys.argv[1:]]
    else:
        spec_files = sorted(repo_root.glob("*/*-openapi.json"))

    if not spec_files:
        print("No spec files found.")
        return 1

    changed = 0
    for path in spec_files:
        original = path.read_text(encoding="utf-8")
        spec = json.loads(original)
        updated_spec = remediate_spec(spec)
        updated = json.dumps(updated_spec, indent=2, ensure_ascii=False) + "\n"
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
            print(f"[UPDATED] {path.parent.name}")
        else:
            print(f"[OK]      {path.parent.name}")

    print(f"\n{changed} spec(s) updated.")
    return 0


def _demo() -> None:
    """Self-check: repeated param extracted to $ref; single-use stays inline;
    disagreeing pattern dropped."""
    spec = {
        "paths": {
            "/a/{modelId}": {"get": {"parameters": [
                {"name": "modelId", "in": "path", "required": True,
                 "schema": {"type": "string", "pattern": "^X$"}}]}},
            "/b/{modelId}": {"get": {"parameters": [
                {"name": "modelId", "in": "path", "required": True,
                 "schema": {"type": "string"}}]}},  # no pattern -> drop
            "/c/{loneId}": {"get": {"parameters": [
                {"name": "loneId", "in": "path", "required": True,
                 "schema": {"type": "string"}}]}},
        }
    }
    out = remediate_spec(spec)
    comp = out["components"]["parameters"]
    assert "ModelId" in comp, "repeated param must extract"
    assert "pattern" not in comp["ModelId"]["schema"], "disagreeing pattern must drop"
    assert out["paths"]["/a/{modelId}"]["parameters"] == [
        {"$ref": "#/components/parameters/ModelId"}], "repeated -> $ref at item level"
    assert "get" not in out["paths"]["/a/{modelId}"] or \
        "parameters" not in out["paths"]["/a/{modelId}"]["get"], "op path param stripped"
    lone = out["paths"]["/c/{loneId}"]["parameters"]
    assert lone == [{"name": "loneId", "in": "path", "required": True,
                     "schema": {"type": "string"}}], "single-use stays inline"
    assert "LoneId" not in comp, "single-use not extracted"
    print("_demo ok")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        _demo()
    else:
        sys.exit(main())
