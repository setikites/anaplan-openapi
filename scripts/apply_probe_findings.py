"""
Apply live-probe findings from issue #90 Phase 1 to integration-openapi.json.

Findings from probing all GET endpoints against the live Integration API:
- Import.importType confirmed enum values
- Export.exportType confirmed enum values
- Export list items include exportFormat, encoding, layout (missing from spec)
- ExportMetadata missing layout field
- Action items include actionType field (missing from spec)
- ImportMetadata.type actual values are FILE and MODEL only (description was wrong)
- File.firstDataRow can be 0 (description said "1-based", which is misleading)
- File.encoding observed values: ISO-8859-1, UTF-16LE, UTF-8
- CurrentPeriod schema has empty properties but API returns periodText/lastDay/calendarType
"""

import json
import sys

PATH = "integration/integration-openapi.json"


def main() -> None:
    with open(PATH, encoding="utf-8") as f:
        spec = json.load(f)

    schemas = spec["components"]["schemas"]

    # ── Import.importType: add confirmed enum ──────────────────────────────────
    schemas["Import"]["properties"]["importType"] = {
        "type": "string",
        "description": "Category of data the import processes.",
        "enum": ["HIERARCHY_DATA", "LINE_ITEM_DEFINITION", "MODULE_DATA", "USERS"],
    }

    # ── Export.exportType: add confirmed enum ──────────────────────────────────
    schemas["Export"]["properties"]["exportType"] = {
        "type": "string",
        "description": "Shape and scope of the exported data.",
        "enum": [
            "AUDIT_LOG",
            "GRID_CURRENT_PAGE",
            "TABULAR_ALL_LINE_ITEMS",
            "TABULAR_CURRENT_LINE_ITEM",
            "TABULAR_MULTI_COLUMN",
        ],
    }

    # ── Export schema: add fields present in live list responses ───────────────
    # Live GET /exports returns encoding, exportFormat, layout alongside id/name/exportType/code
    schemas["Export"]["properties"]["encoding"] = {"type": "string"}
    schemas["Export"]["properties"]["exportFormat"] = {"type": "string"}
    schemas["Export"]["properties"]["layout"] = {"type": "string"}

    # ── ExportMetadata: add layout field (present in live GET /exports/{id}) ──
    schemas["ExportMetadata"]["properties"]["layout"] = {"type": "string"}

    # ── Action: add actionType field (present in live GET /actions) ────────────
    # Observed value: DELETE_BY_SELECTION
    schemas["Action"]["properties"]["actionType"] = {"type": "string"}

    # ── ImportMetadata.type: fix description and add confirmed enum ────────────
    # Live values are FILE (file-based import source) and MODEL (model-to-model).
    # The old description listed USERS, HIERARCHY_DATA etc., which are importType values.
    schemas["ImportMetadata"]["properties"]["type"] = {
        "type": "string",
        "description": (
            "Data source type for this import: "
            "'FILE' for file-based imports, 'MODEL' for model-to-model imports."
        ),
        "enum": ["FILE", "MODEL"],
    }

    # ── File.firstDataRow: fix description — 0 is observed, not strictly 1-based
    schemas["File"]["properties"]["firstDataRow"] = {
        "type": "integer",
        "description": (
            "Row number of the first data row. "
            "0 means no data rows are configured; "
            "otherwise 1-based (row 1 = first row of the file)."
        ),
    }

    # ── File.encoding: add description with observed values ───────────────────
    schemas["File"]["properties"]["encoding"] = {
        "type": "string",
        "description": "Character encoding of the file. Observed values: ISO-8859-1, UTF-16LE, UTF-8.",
    }

    # ── CurrentPeriod: add properties observed in live responses ───────────────
    # GET /workspaces/{wsId}/models/{mId}/currentPeriod returns
    # { "currentPeriod": { "periodText": "", "lastDay": "", "calendarType": "..." } }
    schemas["CurrentPeriod"]["properties"] = {
        "calendarType": {"type": "string"},
        "lastDay": {"type": "string"},
        "periodText": {
            "type": "string",
            "description": (
                "Human-readable label for the current period "
                "(e.g. 'Jan 24'). Empty string when no current period is set."
            ),
        },
    }

    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("Done. Changes applied to", PATH)


if __name__ == "__main__":
    sys.exit(main())
