"""
Remediate path parameter placement across all OpenAPI specs to conform to ADR 0002.

Rule: path parameters (in: path) must be declared once, inline, at the path item level.
They must not appear inside individual operations, and must not be $refs to
components/parameters. Any components/parameters entries that are in: path are
inlined and the component entry is deleted.
"""

import json
import re
import sys
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


def _resolve_param(spec: dict, param: dict) -> dict:
    """Resolve a $ref parameter to its actual definition."""
    if "$ref" in param:
        ref = param["$ref"]
        if ref.startswith("#/components/parameters/"):
            name = ref.split("/")[-1]
            return spec.get("components", {}).get("parameters", {}).get(name, param)
    return param


def remediate_spec(spec: dict) -> dict:
    """Return a new spec dict with path parameters moved to path item level."""
    spec = json.loads(json.dumps(spec))  # deep copy

    # Collect names of components/parameters that are in: path
    comp_params = spec.get("components", {}).get("parameters", {})
    path_comp_param_names = {
        name for name, defn in comp_params.items() if defn.get("in") == "path"
    }

    for path_str, path_item in spec.get("paths", {}).items():
        expected_param_names = set(_PATH_PARAM_RE.findall(path_str))
        if not expected_param_names:
            continue

        # Gather all path param definitions from path item level and operations.
        # Key: param name → resolved (inline) definition
        collected: dict[str, dict] = {}

        # From path item level parameters
        item_params = path_item.get("parameters", [])
        remaining_item_params = []
        for param in item_params:
            resolved = _resolve_param(spec, param)
            if resolved.get("in") == "path":
                name = resolved.get("name")
                if name and name not in collected:
                    collected[name] = resolved
            else:
                remaining_item_params.append(param)

        # From each operation's parameters
        for method in _HTTP_METHODS:
            if method not in path_item:
                continue
            operation = path_item[method]
            op_params = operation.get("parameters", [])
            non_path_params = []
            for param in op_params:
                resolved = _resolve_param(spec, param)
                if resolved.get("in") == "path":
                    name = resolved.get("name")
                    if name and name not in collected:
                        collected[name] = resolved
                else:
                    non_path_params.append(param)
            if non_path_params:
                operation["parameters"] = non_path_params
            elif "parameters" in operation:
                del operation["parameters"]

        # Build inline path param dicts in path-segment order
        path_segments_order = _PATH_PARAM_RE.findall(path_str)
        inline_path_params = []
        for name in path_segments_order:
            if name in collected:
                defn = dict(collected[name])
            else:
                # Fallback: minimal definition
                defn = {"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
            defn["name"] = name
            defn["in"] = "path"
            defn["required"] = True
            inline_path_params.append(_reorder_param(defn))

        # Rebuild path item parameters: inline path params first, then non-path item params
        new_item_params = inline_path_params + remaining_item_params
        if new_item_params:
            path_item["parameters"] = new_item_params
        elif "parameters" in path_item:
            del path_item["parameters"]

    # Remove in: path entries from components/parameters
    if path_comp_param_names and "components" in spec and "parameters" in spec["components"]:
        for name in path_comp_param_names:
            spec["components"]["parameters"].pop(name, None)
        if not spec["components"]["parameters"]:
            del spec["components"]["parameters"]
        if not spec["components"]:
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


if __name__ == "__main__":
    sys.exit(main())
