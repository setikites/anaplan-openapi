"""
Validates that OpenAPI spec field ordering conforms to ADR 0002.
See docs/adr/0002-canonical-element-ordering.md
"""

_ADR = "docs/adr/0002-canonical-element-ordering.md"

_DOC_ORDER = [
    "openapi", "info", "externalDocs", "servers", "security", "tags", "paths", "components",
]
_INFO_ORDER = ["title", "version", "description", "contact", "license"]
_OP_ORDER = [
    "summary", "description", "operationId", "tags", "externalDocs",
    "parameters", "requestBody", "responses", "security", "deprecated",
]
_PARAM_FIELD_ORDER = ["name", "in", "description", "required", "schema", "example"]
_RESPONSE_ORDER = ["description", "headers", "content"]
_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})


def _check_key_order(obj: dict, canonical: list, context: str) -> str | None:
    present = [k for k in obj if k in canonical]
    expected = [k for k in canonical if k in obj]
    if present != expected:
        return (
            f"{context}: fields {present!r} are out of order; "
            f"expected {expected!r} — see {_ADR}"
        )
    return None


def _param_rank(param: dict) -> int:
    """0 = path, 1 = required non-path, 2 = optional."""
    if param.get("in") == "path":
        return 0
    return 1 if param.get("required") else 2


def check_spec_ordering(spec: dict, name: str) -> list[str]:
    """Return a list of ADR 0002 ordering violations (empty list = conforming)."""
    violations = []

    v = _check_key_order(spec, _DOC_ORDER, f"{name}: document-level")
    if v:
        violations.append(v)

    info = spec.get("info", {})
    if info:
        v = _check_key_order(info, _INFO_ORDER, f"{name}: info")
        if v:
            violations.append(v)

    for path_str, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            ctx = f"{name}: {method.upper()} {path_str}"

            v = _check_key_order(op, _OP_ORDER, ctx)
            if v:
                violations.append(v)

            params = op.get("parameters", [])
            inline = [p for p in params if isinstance(p, dict) and "$ref" not in p]

            for param in inline:
                v = _check_key_order(
                    param, _PARAM_FIELD_ORDER,
                    f"{ctx}: parameter '{param.get('name', '?')}'"
                )
                if v:
                    violations.append(v)

            # Array ordering: only enforceable when all params are inline
            if len(inline) == len(params) and len(inline) > 1:
                ranks = [_param_rank(p) for p in inline]
                if ranks != sorted(ranks):
                    violations.append(
                        f"{ctx}: parameters array — path params must come first, "
                        f"then required, then optional — see {_ADR}"
                    )

            for status_code, response in op.get("responses", {}).items():
                if not isinstance(response, dict) or "$ref" in response:
                    continue
                v = _check_key_order(
                    response, _RESPONSE_ORDER,
                    f"{ctx}: response {status_code}"
                )
                if v:
                    violations.append(v)

    return violations


def main() -> int:
    import json
    import pathlib
    import sys

    if len(sys.argv) > 1:
        spec_files = [pathlib.Path(a) for a in sys.argv[1:]]
    else:
        spec_files = sorted(pathlib.Path(".").glob("*/*-openapi.json"))

    if not spec_files:
        print("No spec files found.")
        return 1

    all_ok = True
    for path in spec_files:
        spec = json.loads(path.read_text(encoding="utf-8"))
        violations = check_spec_ordering(spec, path.parent.name)
        if violations:
            all_ok = False
            for v in violations:
                print(f"[FAIL] {v}")
        else:
            print(f"[OK] {path.parent.name}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
