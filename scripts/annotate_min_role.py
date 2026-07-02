"""
One-shot minimum-role annotator (ADR 0006).
See docs/adr/0006-minimum-role-annotations.md

Stamps `x-anaplan-min-role` + a leading "Minimum role: <role>." description
sentence across the operations of one spec, so the per-operation repetition of
a mostly-uniform role is written once, mechanically, and every operation still
ends self-contained (extension + in-band sentence).

Idempotent: re-running with the same role is a no-op (no sentence stacking).
Changing an already-set role requires --force, so a bulk run never silently
clobbers a curated or confirmed annotation.

Example — stamp all ALM operations Workspace Administrator, flagging the two
report-task endpoints whose role is not yet confirmed:

    uv run python scripts/annotate_min_role.py alm/alm-openapi.json \
      --role "Workspace Administrator" \
      --needs-info "GET /models/{modelId}/alm/comparisonReportTasks/{taskId}" \
      --needs-info "GET /models/{modelId}/alm/summaryReportTasks/{taskId}"
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from check_min_role import (
    ROLE_VOCABULARY,
    _EXT,
    _NEEDS_INFO,
    _SENTENCE,
    _HTTP_METHODS,
    check_spec_min_roles,
)
from check_ordering import check_spec_ordering

# Redundant legacy role prose the sentence replaces, e.g. "Requires Workspace
# Administrator role." — stripped so the annotation does not duplicate it.
_REQUIRES = re.compile(r"\s*Requires [^.]+? role\.?", re.IGNORECASE)


def _op_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def _norm(op_ref: str) -> str:
    """Normalize a 'METHOD path' CLI token to _op_key form (uppercase method)."""
    method, _, path = op_ref.strip().partition(" ")
    return f"{method.upper()} {path}"


def _reorder(op: dict) -> None:
    """Move the role extension(s) to immediately after operationId (ADR 0002)."""
    role = op.pop(_EXT, None)
    if role is None:
        return
    ni = op.pop(_NEEDS_INFO, None)
    rebuilt: dict = {}
    for k, v in op.items():
        rebuilt[k] = v
        if k == "operationId":
            rebuilt[_EXT] = role
            if ni is not None:
                rebuilt[_NEEDS_INFO] = ni
    if _EXT not in rebuilt:  # no operationId — append at end
        rebuilt[_EXT] = role
        if ni is not None:
            rebuilt[_NEEDS_INFO] = ni
    op.clear()
    op.update(rebuilt)


def _apply(op: dict, role: str, needs_info: bool, force: bool) -> str | None:
    """Annotate one operation in place. Returns a note if skipped, else None."""
    existing = op.get(_EXT)
    if existing is not None and existing != role and not force:
        return f"has {_EXT}={existing!r}, requested {role!r}; left as-is (use --force)"

    desc = op.get("description") or ""
    desc = _SENTENCE.sub("", desc, count=1).lstrip("\n")   # drop prior "Minimum role:" line
    desc = _REQUIRES.sub("", desc).strip()                 # drop redundant "Requires X role."
    sentence = f"Minimum role: {role}."
    op["description"] = f"{sentence}\n\n{desc}" if desc else sentence

    op[_EXT] = role
    if needs_info:
        op[_NEEDS_INFO] = True
    else:
        op.pop(_NEEDS_INFO, None)
    _reorder(op)
    return None


def annotate(spec: dict, default: str | None, overrides: dict,
             needs_info: set, force: bool = False) -> tuple[int, list[str]]:
    """Annotate a spec in place. Returns (count changed, notes)."""
    notes = []
    changed = 0
    seen = set()
    for path_str, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            key = _op_key(method, path_str)
            seen.add(key)
            role = overrides.get(key, default)
            if role is None:
                if key in needs_info:
                    notes.append(f"{key}: --needs-info given but no role (no --role/--except) — skipped")
                continue
            note = _apply(op, role, key in needs_info, force)
            if note:
                notes.append(f"{key}: {note}")
            else:
                changed += 1

    # Warn on flags that matched no operation (likely a typo in method/path).
    for key in sorted(set(overrides) | needs_info):
        if key not in seen:
            notes.append(f"{key}: matched no operation — check method/path spelling")
    return changed, notes


def _parse_except(values: list[str]) -> dict:
    """['Standard User=GET /a,POST /b'] -> {'GET /a': 'Standard User', 'POST /b': ...}."""
    out = {}
    for spec in values or []:
        role, _, ops = spec.partition("=")
        role = role.strip()
        if not ops:
            raise SystemExit(f"--except '{spec}' must be ROLE=METHOD path[,METHOD path...]")
        if role not in ROLE_VOCABULARY:
            raise SystemExit(f"--except role {role!r} not in vocabulary {sorted(ROLE_VOCABULARY)}")
        for op in ops.split(","):
            out[_norm(op)] = role
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Stamp ADR 0006 minimum-role annotations across a spec.")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--role", help="Default minimum role applied to every operation.")
    ap.add_argument("--except", dest="excepts", action="append", default=[],
                    help="ROLE=METHOD path[,METHOD path] — operations that differ from --role. Repeatable.")
    ap.add_argument("--needs-info", dest="needs_info", action="append", default=[],
                    help="METHOD path — mark an operation's role provisional. Repeatable.")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite an operation that already has a conflicting x-anaplan-min-role.")
    args = ap.parse_args()

    if args.role is not None and args.role not in ROLE_VOCABULARY:
        raise SystemExit(f"--role {args.role!r} not in vocabulary {sorted(ROLE_VOCABULARY)}")
    if args.role is None and not args.excepts:
        raise SystemExit("nothing to do: pass --role and/or --except")

    overrides = _parse_except(args.excepts)
    needs_info = {_norm(ni) for ni in args.needs_info}

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    changed, notes = annotate(spec, args.role, overrides, needs_info, args.force)

    for n in notes:
        print(f"[NOTE] {n}")

    # Validate before writing — never emit a spec that fails the standards.
    violations = check_spec_min_roles(spec, args.spec.parent.name) \
        + check_spec_ordering(spec, args.spec.parent.name)
    if violations:
        for v in violations:
            print(f"[FAIL] {v}")
        print("Not written — fix the above (e.g. an operation left in a conflicting state).")
        return 1

    args.spec.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[OK] annotated {changed} operation(s) in {args.spec}")

    yaml_rc = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("sync_yaml.py")), str(args.spec)]
    ).returncode
    if yaml_rc != 0:
        print("[WARN] YAML sync failed — regenerate manually with scripts/sync_yaml.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
