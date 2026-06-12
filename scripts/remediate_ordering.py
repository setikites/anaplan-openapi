"""
Reorder fields in all OpenAPI spec JSON files to conform to ADR 0002.
See docs/adr/0002-canonical-element-ordering.md
"""

import json
import pathlib
import sys

from check_ordering import check_spec_ordering, reorder_spec


def main() -> int:
    if len(sys.argv) > 1:
        spec_files = [pathlib.Path(a) for a in sys.argv[1:]]
    else:
        spec_files = sorted(pathlib.Path(".").glob("*/*-openapi.json"))

    if not spec_files:
        print("No spec files found.")
        return 1

    changed = 0
    for path in spec_files:
        original = path.read_text(encoding="utf-8")
        spec = json.loads(original)
        spec = reorder_spec(spec)
        updated = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
            violations = check_spec_ordering(spec, path.parent.name)
            if violations:
                print(f"[WARN] {path.parent.name}: {len(violations)} remaining violation(s)")
                for v in violations:
                    print(f"  {v}")
            else:
                print(f"[OK]   {path.parent.name}: reordered")
        else:
            print(f"[OK]   {path.parent.name}: already conforming")

    print(f"\n{changed} spec(s) updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
