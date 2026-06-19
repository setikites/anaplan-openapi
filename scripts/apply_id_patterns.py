"""
Apply confirmed ID format patterns to integration-openapi.json.

Findings from probe_id_patterns.py (5000 users, 3810 models, 100 workspaces,
836 imports, 104 exports, 18 actions, 120 processes, 450 files, 223 lists,
983 modules, 1533 views, 32 dashboards):

Hex IDs (32 chars): User, Workspace, Model
Numeric IDs (12–13 digits, type-prefixed):
  101xxx = List
  102xxx = Module; module-default views also share this prefix
  112xxx = Import
  113xxx = File (upload/import source)
  115xxx = Dashboard
  116xxx = Export AND export output files (same ID)
  117xxx = Action
  118xxx = Process
  Views: 12-digit (prefix 102–922) or 13-digit (prefix 1012–4296)

Approach:
  - Hex IDs: add pattern (no description — id fields are in MUST_NOT_HAVE_DESCRIPTION)
  - Numeric IDs: add description noting the 12-digit format and type prefix;
    these id fields are NOT in _MUST_NOT_HAVE_DESCRIPTION
  - Process schema: populate id, code, name properties (currently empty)
"""

import json
import sys

PATH = "integration/integration-openapi.json"

HEX32_PATTERN = "^[0-9a-fA-F]{32}$"


def main() -> None:
    with open(PATH, encoding="utf-8") as f:
        spec = json.load(f)

    schemas = spec["components"]["schemas"]

    # ── Hex IDs: pattern only, no description (MUST_NOT_HAVE_DESCRIPTION) ─────
    for name in ("User", "Workspace", "Model"):
        schemas[name]["properties"]["id"] = {
            "type": "string",
            "pattern": HEX32_PATTERN,
        }

    # ── Numeric IDs: description with type prefix ─────────────────────────────

    schemas["Import"]["properties"]["id"] = {
        "type": "string",
        "description": (
            "12-digit numeric identifier. "
            "The prefix 112 marks this as an import definition."
        ),
    }

    schemas["Export"]["properties"]["id"] = {
        "type": "string",
        "description": (
            "12-digit numeric identifier. "
            "The prefix 116 marks this as an export definition; "
            "the export output file shares this same ID."
        ),
    }

    schemas["Action"]["properties"]["id"] = {
        "type": "string",
        "description": (
            "12-digit numeric identifier. "
            "The prefix 117 marks this as an action."
        ),
    }

    schemas["File"]["properties"]["id"] = {
        "type": "string",
        "description": (
            "12-digit numeric identifier. "
            "Import source files use the prefix 113; "
            "export output files use 116, matching their parent export's ID."
        ),
    }

    schemas["List"]["properties"]["id"] = {
        "type": "string",
        "description": (
            "12-digit numeric identifier. "
            "The prefix 101 marks this as a list."
        ),
    }

    schemas["Module"]["properties"]["id"] = {
        "type": "string",
        "description": (
            "12-digit numeric identifier. "
            "The prefix 102 marks this as a module."
        ),
    }

    schemas["Dashboard"]["properties"]["id"] = {
        "type": "string",
        "description": (
            "12-digit numeric identifier. "
            "The prefix 115 marks this as a dashboard."
        ),
    }

    schemas["View"]["properties"]["id"] = {
        "type": "string",
        "description": (
            "12- or 13-digit numeric identifier. "
            "Default views share the module prefix 102; "
            "named saved views use higher-range prefixes (up to 13 digits)."
        ),
    }

    # ── Process schema: was empty; populate with observed fields ──────────────
    # Live probe showed 120 process objects with id, name, code, and no other fields.
    schemas["Process"]["properties"] = {
        "code": {"type": "string"},
        "id": {
            "type": "string",
            "description": (
                "12-digit numeric identifier. "
                "The prefix 118 marks this as a process."
            ),
        },
        "name": {"type": "string"},
    }

    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("Done. ID pattern changes applied to", PATH)


if __name__ == "__main__":
    sys.exit(main())
