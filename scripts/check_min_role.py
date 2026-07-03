"""
Validates minimum-role annotations against ADR 0006.
See docs/adr/0006-minimum-role-annotations.md

Enforces consistency, not coverage: an operation with no role annotation is
legal (not yet annotated). An operation that IS annotated must carry both the
`x-anaplan-min-role` extension and a matching leading "Minimum role: <role>."
description sentence, with the role drawn from the closed vocabulary.
"""

import re

_ADR = "docs/adr/0006-minimum-role-annotations.md"

# Closed role vocabulary — the only accepted values (ADR 0006 §1).
ROLE_VOCABULARY = frozenset({
    "Standard User",
    "Workspace Administrator",
    "Tenant Auditor",
    "User Administrator",
    "Tenant Administrator",
    "Tenant Security Admin",
    "Integration Admin",
    "Restricted Integration User",
    "None",
})

_EXT = "x-anaplan-min-role"
_NEEDS_INFO = "x-anaplan-min-role-needs-info"
_SENTENCE = re.compile(r"^Minimum role: (?P<role>[^.\n]+)\.")
_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})


def _check_op(op: dict, ctx: str) -> list[str]:
    ext = op.get(_EXT)
    desc = op.get("description") or ""
    m = _SENTENCE.match(desc)
    sentence_role = m.group("role") if m else None
    out = []

    if ext is None and sentence_role is None and _NEEDS_INFO not in op:
        return out  # not yet annotated — legal

    if ext is not None and ext not in ROLE_VOCABULARY:
        out.append(f"{ctx}: {_EXT} '{ext}' not in role vocabulary — see {_ADR}")

    if sentence_role is not None and sentence_role not in ROLE_VOCABULARY:
        out.append(f"{ctx}: description role '{sentence_role}' not in role vocabulary — see {_ADR}")

    if ext is not None and sentence_role is None:
        out.append(f"{ctx}: has {_EXT} but no leading 'Minimum role: {ext}.' sentence — see {_ADR}")

    if sentence_role is not None and ext is None:
        out.append(f"{ctx}: has 'Minimum role:' sentence but no {_EXT} extension — see {_ADR}")

    if ext is not None and sentence_role is not None and ext != sentence_role:
        out.append(
            f"{ctx}: {_EXT} '{ext}' disagrees with description role "
            f"'{sentence_role}' — see {_ADR}"
        )

    if _NEEDS_INFO in op:
        if op[_NEEDS_INFO] is not True:
            out.append(f"{ctx}: {_NEEDS_INFO} must be boolean true when present — see {_ADR}")
        if ext is None:
            out.append(f"{ctx}: {_NEEDS_INFO} set but no best-known {_EXT} recorded — see {_ADR}")

    return out


def check_spec_min_roles(spec: dict, name: str) -> list[str]:
    """Return a list of ADR 0006 violations (empty list = conforming)."""
    violations = []
    for path_str, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            op = path_item.get(method)
            if isinstance(op, dict):
                violations.extend(_check_op(op, f"{name}: {method.upper()} {path_str}"))
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
        violations = check_spec_min_roles(spec, path.parent.name)
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
