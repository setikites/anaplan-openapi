"""
Validates that every entry under components/ is referenced at least once.
A component is referenced if it appears as a $ref target or, for securitySchemes,
as a key in any security requirement object.
"""


def _collect_refs(obj: object, refs: set[str], security_names: set[str]) -> None:
    if isinstance(obj, dict):
        ref = obj.get("$ref")
        if ref and isinstance(ref, str) and ref.startswith("#/components/"):
            refs.add(ref)
        for k, v in obj.items():
            if k == "security" and isinstance(v, list):
                for req in v:
                    if isinstance(req, dict):
                        security_names.update(req.keys())
            _collect_refs(v, refs, security_names)
    elif isinstance(obj, list):
        for item in obj:
            _collect_refs(item, refs, security_names)


def check_spec(spec: dict, name: str) -> list[str]:
    """Return a list of unused-component violations (empty list = clean)."""
    comps = spec.get("components", {})
    if not comps:
        return []

    refs: set[str] = set()
    security_names: set[str] = set()
    _collect_refs(spec, refs, security_names)

    violations = []
    for section, entries in comps.items():
        if not isinstance(entries, dict):
            continue
        for key, entry_value in entries.items():
            # x-stub: true marks a schema as a known undocumented stub; skip it.
            if isinstance(entry_value, dict) and entry_value.get("x-stub"):
                continue
            if section == "securitySchemes":
                if key not in security_names:
                    violations.append(
                        f"{name}: #/components/{section}/{key} is defined but never used"
                    )
            else:
                if f"#/components/{section}/{key}" not in refs:
                    violations.append(
                        f"{name}: #/components/{section}/{key} is defined but never used"
                    )

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
        violations = check_spec(spec, path.parent.name)
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
