"""
Probe ALL Financial Consolidation GET endpoints with real tenant data.

Collects full sample payloads, then analyses every field value for:
  - ID format patterns (UUID, numeric-string, ...)
  - Date/time format patterns
  - Enum candidate fields
  - Nullable fields

Run with:
    uv run --env-file .env python scripts/probe_fc_all_gets.py

Requires in .env (or environment):
    FC_API_TOKEN   - API token created in the FC Security module
    FC_TENANT      - Tenant name as shown in the FC UI

Optional:
    FC_BASE_URL    - default: https://fluenceapi-prod.fluence.app/api/v2305.1
    FC_TABLE_NAME  - staging table for /odata probe (default: Consolidation)
    FC_MODEL_NAME  - model name for /metadata/models probe (default: Consolidation)
    FC_WF_PATH     - workflow folder path (default: Workflows)
    FC_WF_NAME     - workflow name (default: Compliance)

NOTE: This API uses X_API_TOKEN + TENANT header authentication — standard
Anaplan username/password credentials will NOT work here. Tokens are created
in the Financial Consolidation Security module by an administrator.
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import httpx

# ── credentials ──────────────────────────────────────────────────────────────

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

FC_API_TOKEN = os.environ.get("FC_API_TOKEN", "")
FC_TENANT    = os.environ.get("FC_TENANT", "")
BASE_URL     = os.environ.get("FC_BASE_URL", "https://fluenceapi-prod.fluence.app/api/v2305.1").rstrip("/")
TABLE_NAME   = os.environ.get("FC_TABLE_NAME", "Consolidation")
MODEL_NAME   = os.environ.get("FC_MODEL_NAME", "Consolidation")
WF_PATH      = os.environ.get("FC_WF_PATH", "Workflows")
WF_NAME      = os.environ.get("FC_WF_NAME", "Compliance")

if not FC_API_TOKEN or not FC_TENANT:
    sys.exit("ERROR: FC_API_TOKEN and FC_TENANT must be set in .env")

HDRS = {
    "X_API_TOKEN": FC_API_TOKEN,
    "TENANT": FC_TENANT,
    "Accept": "application/json",
}
CLIENT = httpx.Client(timeout=30)


def get(path: str, params: dict | None = None) -> dict | list | None:
    """GET a Financial Consolidation path; return parsed JSON or None on error."""
    url = f"{BASE_URL}{path}"
    r = CLIENT.get(url, headers=HDRS, params=params or {})
    qs = "?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else ""
    print(f"  GET {path}{qs} -> {r.status_code}")
    if r.status_code == 200:
        try:
            return r.json()
        except Exception:
            print(f"    ↳ non-JSON body: {r.text[:200]}")
            return None
    print(f"    ↳ {r.text[:200]}")
    return None


# ── pattern detection helpers ─────────────────────────────────────────────────

UUID4_RE     = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)
UUID_RE      = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
HEX32_RE     = re.compile(r"^[0-9a-f]{32}$")
HEX_UPPER    = re.compile(r"^[0-9A-F]{32}$")
NUMERIC_ID   = re.compile(r"^\d{9,}$")
ISO8601_RE   = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
DATE_RE      = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


def classify_value(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        if v > 1_000_000_000:
            return "integer:epoch"
        return f"integer:{v}"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        if UUID4_RE.match(v):
            return "id:uuid4"
        if UUID_RE.match(v):
            return "id:uuid"
        if HEX32_RE.match(v):
            return "id:hex32"
        if HEX_UPPER.match(v):
            return "id:hex32upper"
        if NUMERIC_ID.match(v):
            return "id:numeric"
        if ISO8601_RE.match(v):
            return "datetime:iso8601"
        if DATE_RE.match(v):
            return "date:iso8601"
        if TIMESTAMP_RE.match(v):
            return "datetime:space-separated"
        if len(v) == 0:
            return "string:empty"
        return f"string:{v!r}" if len(v) < 40 else "string:long"
    if isinstance(v, list):
        return f"array[{len(v)}]"
    if isinstance(v, dict):
        return f"object{{{','.join(sorted(v.keys()))}}}"
    return type(v).__name__


# ── field accumulator ─────────────────────────────────────────────────────────

field_stats: dict[str, Counter] = defaultdict(Counter)
field_examples: dict[str, list] = defaultdict(list)
MAX_EXAMPLES = 5


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = f"{path}.{k}" if path else k
            cls = classify_value(v)
            field_stats[child][cls] += 1
            if not isinstance(v, (dict, list)):
                ex = field_examples[child]
                if v not in ex and len(ex) < MAX_EXAMPLES:
                    ex.append(v)
            walk(v, child)
    elif isinstance(obj, list):
        for item in obj:
            walk(item, path)


# ── collect all sample data ───────────────────────────────────────────────────

SAMPLES: dict[str, list] = defaultdict(list)

print("=" * 70)
print("Financial Consolidation GET probe — collecting sample data")
print(f"Base URL: {BASE_URL}")
print(f"Tenant:   {FC_TENANT}")
print("=" * 70)

# 1. GET /users
print("\n[1] Users")
data = get("/users")
first_username = None
if data and isinstance(data, list):
    SAMPLES["users"].extend(data)
    walk({"users": data})
    for u in data:
        if isinstance(u, dict) and u.get("userName"):
            first_username = u["userName"]
            break
elif data:
    walk(data)

# 2. GET /user/{username}/roles
print("\n[2] User roles")
if first_username:
    data = get(f"/user/{first_username}/roles")
    if data:
        SAMPLES["user_roles"].append(data)
        walk({"roles": data} if isinstance(data, list) else data)
else:
    print("  (no username from /users — skipping)")

# 3. GET /metadata/Dimensions (tenant-level)
print("\n[3] Tenant dimensions")
data = get("/metadata/Dimensions")
first_dimension_name = None
if data and isinstance(data, list):
    SAMPLES["dimensions"].extend(data)
    walk({"dimensions": data})
    if data:
        first_dimension_name = data[0].get("dimensionName")
elif data:
    walk(data)

# 4. GET /metadata/models/{modelName}/Dimensions
print(f"\n[4] Model dimensions (model={MODEL_NAME!r})")
data = get(f"/metadata/models/{MODEL_NAME}/Dimensions")
if data and isinstance(data, list):
    SAMPLES["model_dimensions"].extend(data)
    walk({"dimensions": data})
elif data:
    walk(data)

# 5. GET /metadata/Dimensions/{dimensionName}
print(f"\n[5] Dimension members (dimension={first_dimension_name or 'Account'!r})")
dim_name = first_dimension_name or "Account"
data = get(f"/metadata/Dimensions/{dim_name}", {"Page": 1, "PageSize": 25})
if data:
    SAMPLES["dimension_members"].append(data)
    walk(data)

# 6. GET /process/state/{path}/{name_of_workflow}
print(f"\n[6] Workflow state (path={WF_PATH!r}, name={WF_NAME!r})")
data = get(f"/process/state/{WF_PATH}/{WF_NAME}")
if data:
    SAMPLES["workflow_state"].append(data)
    walk(data)

# 7. GET /odata/{tableName} (small page to avoid large payloads)
print(f"\n[7] OData table rows (table={TABLE_NAME!r})")
data = get(f"/odata/{TABLE_NAME}", {"Page": 1, "PageSize": 5})
if data:
    if isinstance(data, list):
        SAMPLES["odata_rows"].extend(data[:5])
        walk({"rows": data[:5]})
    elif isinstance(data, dict):
        SAMPLES["odata_rows"].append(data)
        walk(data)

CLIENT.close()

# ── analysis ──────────────────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("PATTERN ANALYSIS")
print("=" * 70)

id_fields = []
datetime_fields = []
date_fields = []
epoch_fields = []
enum_candidates = []
bool_fields = []
int_fields = []
nullable_fields = []
always_null = []
space_datetime_fields = []

for path, counter in sorted(field_stats.items()):
    total = sum(counter.values())
    null_count = counter.get("null", 0)

    if "null" in counter and null_count < total:
        nullable_fields.append((path, null_count, total))

    if null_count == total:
        always_null.append(path)
        continue

    non_null = {k: v for k, v in counter.items() if k != "null"}
    non_null_dom = Counter(non_null).most_common(1)[0][0] if non_null else list(counter.keys())[0]

    if non_null_dom in ("id:hex32", "id:hex32upper", "id:uuid4", "id:uuid", "id:numeric"):
        id_fields.append((path, non_null_dom, field_examples[path]))
    elif non_null_dom == "datetime:iso8601":
        datetime_fields.append(path)
    elif non_null_dom == "date:iso8601":
        date_fields.append(path)
    elif non_null_dom == "integer:epoch":
        epoch_fields.append(path)
    elif non_null_dom == "datetime:space-separated":
        space_datetime_fields.append(path)
    elif non_null_dom == "boolean":
        bool_fields.append(path)
    elif non_null_dom.startswith("integer:") and non_null_dom != "integer:epoch":
        int_fields.append((path, list(counter.keys())))

    if all(k.startswith("string:") and len(k) < 60 for k in non_null.keys()) and len(non_null) <= 8:
        enum_candidates.append((path, sorted(non_null.keys())))

print("\n── ID Fields ──────────────────────────────────────────────────────────")
for path, fmt, examples in id_fields:
    print(f"  {path}")
    print(f"    format: {fmt}")
    if examples:
        print(f"    examples: {examples[:3]}")

print("\n── Date-Time Fields (ISO 8601) ─────────────────────────────────────────")
for path in datetime_fields:
    ex = field_examples.get(path, [])
    print(f"  {path}  e.g. {ex[0]!r}" if ex else f"  {path}")

print("\n── Date Fields (ISO 8601) ──────────────────────────────────────────────")
for path in date_fields:
    ex = field_examples.get(path, [])
    print(f"  {path}  e.g. {ex[0]!r}" if ex else f"  {path}")

print("\n── Epoch Integer Fields ────────────────────────────────────────────────")
for path in epoch_fields:
    ex = field_examples.get(path, [])
    print(f"  {path}  e.g. {ex[0]!r}" if ex else f"  {path}")

print("\n── Non-standard Datetime Fields (space-separated) ─────────────────────")
for path in space_datetime_fields:
    ex = field_examples.get(path, [])
    print(f"  {path}  e.g. {ex[0]!r}" if ex else f"  {path}")

print("\n── Boolean Fields ──────────────────────────────────────────────────────")
for path in bool_fields:
    ex = field_examples.get(path, [])
    print(f"  {path}  e.g. {ex}" if ex else f"  {path}")

print("\n── Integer-coded Fields ────────────────────────────────────────────────")
for path, types in int_fields:
    ex = field_examples.get(path, [])
    ex_clean = [str(e) for e in ex if e is not None]
    print(f"  {path}  values seen: {sorted(set(ex_clean))}  types: {types}")

print("\n── Enum Candidates (low-cardinality strings) ───────────────────────────")
for path, values in enum_candidates:
    clean = [v.replace("string:", "").strip("'") for v in values]
    print(f"  {path}")
    print(f"    observed: {clean}")

print("\n── Nullable Fields ─────────────────────────────────────────────────────")
for path, null_count, total in sorted(nullable_fields, key=lambda x: -x[1]):
    pct = 100 * null_count // total
    ex = field_examples.get(path, [])
    non_null_ex = [e for e in ex if e is not None]
    print(f"  {path}  null={null_count}/{total} ({pct}%)  non-null e.g. {non_null_ex[:2]}")

print("\n── Always-null Fields ──────────────────────────────────────────────────")
for path in always_null:
    print(f"  {path}")

print("\n" + "=" * 70)
print("RAW SAMPLE PAYLOADS (first item from each endpoint category)")
print("=" * 70)

for label, items in SAMPLES.items():
    if not items:
        continue
    print(f"\n── {label} ──")
    print(json.dumps(items[0], indent=2, default=str)[:2000])

print("\n[done]")
