"""
Probe ALL CloudWorks GET endpoints with real tenant data.

Collects full sample payloads, then analyses every field value for:
  - ID format patterns (hex-32, UUID-4, numeric-string, ...)
  - Date/time format patterns (ISO 8601, epoch integer, other)
  - Enum candidate fields (low-cardinality string fields)
  - Naming conventions (camelCase vs snake_case keys)
  - Nullable fields and their null-vs-present distribution
  - Integer-coded fields (status codes, error codes)

Run with:
    uv run --env-file .env python scripts/probe_cloudworks_all_gets.py

Requires ANAPLAN_USERNAME and ANAPLAN_PASSWORD in .env (or environment).
"""

import base64
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from pprint import pformat

import httpx

# ── credentials ──────────────────────────────────────────────────────────────

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

USERNAME = os.environ.get("ANAPLAN_USERNAME", "")
PASSWORD = os.environ.get("ANAPLAN_PASSWORD", "")
BASE_URL = os.environ.get("ANAPLAN_CLOUDWORKS_BASE_URL", "https://api.cloudworks.anaplan.com/2/0").rstrip("/")

if not USERNAME or not PASSWORD:
    sys.exit("ERROR: ANAPLAN_USERNAME and ANAPLAN_PASSWORD must be set in .env")


# ── auth ─────────────────────────────────────────────────────────────────────

def get_token() -> str:
    auth_b64 = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
    r = httpx.post(
        "https://auth.anaplan.com/token/authenticate",
        headers={"Authorization": f"Basic {auth_b64}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["tokenInfo"]["tokenValue"]


TOKEN = get_token()
HDRS = {"Authorization": f"AnaplanAuthToken {TOKEN}", "Accept": "application/json"}
CLIENT = httpx.Client(timeout=30)


def get(path: str, params: dict | None = None) -> dict | list | None:
    """GET a CloudWorks path; return parsed JSON or None on error."""
    url = f"{BASE_URL}{path}"
    r = CLIENT.get(url, headers=HDRS, params=params or {})
    qs = "?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else ""
    print(f"  GET {path}{qs} -> {r.status_code}")
    if r.status_code == 200:
        return r.json()
    print(f"    ↳ {r.text[:200]}")
    return None


# ── pattern detection helpers ─────────────────────────────────────────────────

HEX32_RE   = re.compile(r"^[0-9a-f]{32}$")
UUID4_RE   = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)
UUID_RE    = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
HEX_UPPER  = re.compile(r"^[0-9A-F]{32}$")
NUMERIC_ID = re.compile(r"^\d{9,}$")        # e.g. "118000000114"
ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
DATE_RE    = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")  # "2023-10-24 14:36:45.074157+00:00"

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
        if HEX32_RE.match(v):
            return "id:hex32"
        if UUID4_RE.match(v):
            return "id:uuid4"
        if UUID_RE.match(v):
            return "id:uuid"
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

# field_path -> Counter of classified values
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
        for i, item in enumerate(obj):
            walk(item, path)


# ── collect all sample data ───────────────────────────────────────────────────

SAMPLES: dict[str, list] = defaultdict(list)   # endpoint → list of raw response objects

print("=" * 70)
print("CloudWorks GET probe — collecting sample data")
print(f"Base URL: {BASE_URL}")
print("=" * 70)

# 1. GET /integrations/connections
print("\n[1] Connections")
data = get("/integrations/connections")
if data:
    SAMPLES["connections"].extend(data.get("connections", []))
    walk(data)

# 2. GET /integrations (paginated — multiple pages for enum coverage)
print("\n[2] Integrations (pages 0–2, limit 50 each)")
all_integrations = []
for offset in [0, 50, 100]:
    data = get("/integrations", {"offset": offset, "limit": 50})
    if data:
        page = data.get("integrations", [])
        all_integrations.extend(page)
        walk(data)
        if len(page) < 50:
            break  # last page
SAMPLES["integrations"].extend(all_integrations)

# 3. GET /integrations/{id} — sample a Process, Export, and Import
print("\n[3] Integration details — sampling by integrationType")
by_type: dict[str, dict] = {}
for integ in all_integrations:
    t = integ.get("integrationType", "Unknown")
    if t not in by_type:
        by_type[t] = integ
    if len(by_type) >= 3:
        break

for t, integ in by_type.items():
    iid = integ["integrationId"]
    print(f"  → integrationType={t!r}")
    data = get(f"/integrations/{iid}")
    if data:
        SAMPLES[f"integration_detail_{t}"].append(data)
        walk(data)

# 4. GET /integrations/anaplanModels/{modelId}
print("\n[4] Integrations by model ID")
if all_integrations:
    model_id = all_integrations[0].get("modelId")
    if model_id:
        data = get(f"/integrations/anaplanModels/{model_id}")
        if data:
            SAMPLES["integrations_by_model"].extend(data.get("integrations", []))
            walk(data)

# 5. GET /integrations/runs/{integrationId} — use the first integration with runs
print("\n[5] Run history")
run_integration = None
run_id = None
for integ in all_integrations[:20]:
    if integ.get("latestRun"):
        run_integration = integ
        break

if run_integration:
    iid = run_integration["integrationId"]
    data = get(f"/integrations/runs/{iid}", {"offset": 0, "limit": 5})
    if data:
        SAMPLES["run_history"].extend(data.get("history_of_runs", {}).get("runs", []))
        walk(data)
        runs = data.get("history_of_runs", {}).get("runs", [])
        if runs:
            run_id = runs[0].get("id")

# 6. GET /integrations/runerror/{runId}
print("\n[6] Run errors")
if run_id:
    data = get(f"/integrations/runerror/{run_id}")
    if data:
        SAMPLES["run_errors"].append(data)
        walk(data)
else:
    print("  (no run_id available — skipping)")

# 7. GET /integrations/notification/{notificationId}
print("\n[7] Notifications")
notif_ids_seen = set()
for integ in all_integrations[:30]:
    nid = integ.get("notificationId")
    if nid and nid not in notif_ids_seen:
        notif_ids_seen.add(nid)
        data = get(f"/integrations/notification/{nid}")
        if data:
            SAMPLES["notifications"].append(data.get("notifications", {}))
            walk(data)
        if len(notif_ids_seen) >= 3:
            break

# 8. GET /integrationflows
print("\n[8] Integration flows")
data = get("/integrationflows")
all_flows = []
if data:
    all_flows = data.get("integrationFlows", [])
    SAMPLES["integration_flows"].extend(all_flows)
    walk(data)

# 9. GET /integrationflows/{id} — sample first flow
print("\n[9] Integration flow details")
for flow in all_flows[:3]:
    fid = flow.get("id")
    if fid:
        data = get(f"/integrationflows/{fid}")
        if data:
            SAMPLES[f"integration_flow_detail"].append(data)
            walk(data)

# 10. GET /integrations/run/{runId}/dumps (import error log)
print("\n[10] Import error log")
# Find a run from an Import integration
import_integ = by_type.get("Import")
if import_integ and run_id:
    # try to get a run from the import integration
    data = get(f"/integrations/runs/{import_integ['integrationId']}", {"offset": 0, "limit": 3})
    import_run_id = None
    if data:
        runs = data.get("history_of_runs", {}).get("runs", [])
        if runs:
            import_run_id = runs[0].get("id")
    if import_run_id:
        data = get(f"/integrations/run/{import_run_id}/dumps")
        if data:
            SAMPLES["import_dumps"].append(data)
            walk(data)
    else:
        print("  (no import runs found — skipping)")
else:
    print("  (no Import integration or run_id — skipping)")

CLIENT.close()

# ── analysis ──────────────────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("PATTERN ANALYSIS")
print("=" * 70)

# Group field paths by their dominant value class
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
    dominant = counter.most_common(1)[0][0]
    null_count = counter.get("null", 0)

    if "null" in counter and null_count < total:
        nullable_fields.append((path, null_count, total))

    if null_count == total:
        always_null.append(path)
        continue

    non_null = {k: v for k, v in counter.items() if k != "null"}
    non_null_dom = Counter(non_null).most_common(1)[0][0] if non_null else dominant

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

    # Enum candidate: all values are short strings with cardinality <= 8
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

# ── raw samples for manual inspection ────────────────────────────────────────

print("\n" + "=" * 70)
print("RAW SAMPLE PAYLOADS (first item from each endpoint category)")
print("=" * 70)

for label, items in SAMPLES.items():
    if not items:
        continue
    print(f"\n── {label} ──")
    print(json.dumps(items[0], indent=2, default=str)[:2000])

print("\n[done]")
