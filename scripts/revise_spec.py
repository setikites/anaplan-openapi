"""Revise a hand-maintained OpenAPI 3.0 JSON spec:
- Remove header parameters made redundant by securitySchemes entries
- Normalize the root-level security array
- Remove redundant per-operation security arrays that match root
"""

import copy
import json
import sys
from pathlib import Path


def _redundant_header_names(spec: dict) -> set[str]:
    """Return header names that are covered by a securitySchemes entry."""
    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    covered: set[str] = set()
    for scheme in schemes.values():
        if scheme.get("type") == "apiKey" and scheme.get("in") == "header":
            covered.add(scheme["name"])
        elif scheme.get("type") == "http" and scheme.get("scheme") in ("bearer", "basic"):
            covered.add("Authorization")
    return covered


def _resolve_param(param: dict, components_params: dict) -> dict:
    """Resolve a $ref parameter to its component definition."""
    ref = param.get("$ref", "")
    if ref.startswith("#/components/parameters/"):
        name = ref.split("/")[-1]
        return components_params.get(name, param)
    return param


_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _strip_params(params: list, redundant: set[str], components_params: dict) -> tuple[list, list[str]]:
    """Remove redundant header params; return (kept, removed_names)."""
    kept, removed = [], []
    for p in params:
        resolved = _resolve_param(p, components_params)
        if resolved.get("in") == "header" and resolved.get("name") in redundant:
            removed.append(resolved["name"])
        else:
            kept.append(p)
    return kept, removed


def _collect_op_securities(spec: dict) -> list[list]:
    """Return all operation security values — explicit, or root if inherited."""
    root = spec.get("security")
    result = []
    for path_item in (spec.get("paths") or {}).values():
        for method in _HTTP_METHODS:
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            if "security" in op:
                result.append(op["security"])
            elif root is not None:
                result.append(root)
    return result


def _most_common_security(securities: list[list]) -> list | None:
    """Return the most frequent security value, or None if tied."""
    counts: dict[str, int] = {}
    order: dict[str, list] = {}
    for sec in securities:
        key = json.dumps(sec)
        counts[key] = counts.get(key, 0) + 1
        order.setdefault(key, sec)
    max_count = max(counts.values())
    winners = [k for k, v in counts.items() if v == max_count]
    return order[winners[0]] if len(winners) == 1 else None


def revise_spec(spec: dict) -> tuple[dict, list[str]]:
    """Return (revised_spec, summary_lines)."""
    spec = copy.deepcopy(spec)
    summary: list[str] = []

    redundant = _redundant_header_names(spec)
    components_params = (spec.get("components") or {}).get("parameters") or {}

    for path, path_item in (spec.get("paths") or {}).items():
        # path-level parameters
        if "parameters" in path_item:
            path_item["parameters"], removed = _strip_params(
                path_item["parameters"], redundant, components_params
            )
            for name in removed:
                summary.append(f"Removed header param '{name}' from path {path}")

        # operation-level parameters
        for method in _HTTP_METHODS:
            op = path_item.get(method)
            if not isinstance(op, dict) or "parameters" not in op:
                continue
            op["parameters"], removed = _strip_params(
                op["parameters"], redundant, components_params
            )
            for name in removed:
                summary.append(f"Removed header param '{name}' from {method.upper()} {path}")

    # Compute new root security:
    # - if operations carry explicit security, promote the most common value to root
    # - if no explicit op security exists, derive from securitySchemes (or [] if none)
    # - on a tie among op securities, leave root unchanged
    op_securities = _collect_op_securities(spec)
    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    if op_securities:
        new_root = _most_common_security(op_securities)
    elif schemes:
        new_root = [{name: []} for name in schemes]
    else:
        new_root = []

    if new_root is not None:
        old_root = spec.get("security")
        if new_root != old_root:
            spec["security"] = new_root
            label = [list(s.keys())[0] for s in new_root] if new_root else "[] (public)"
            summary.append(f"Set root security: {label}")

    # Remove per-operation security arrays that duplicate root
    root_security = spec.get("security")
    if root_security is not None:
        for path, path_item in (spec.get("paths") or {}).items():
            for method in _HTTP_METHODS:
                op = path_item.get(method)
                if not isinstance(op, dict) or "security" not in op:
                    continue
                if op["security"] == root_security:
                    del op["security"]
                    summary.append(f"Removed redundant security override from {method.upper()} {path}")

    return spec, summary


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path-to-openapi.json>")
        sys.exit(1)

    path = Path(sys.argv[1])
    original = json.loads(path.read_text(encoding="utf-8"))
    revised, lines = revise_spec(original)
    path.write_text(json.dumps(revised, indent=2), encoding="utf-8")
    for line in lines:
        print(line)
    if not lines:
        print("No changes.")
