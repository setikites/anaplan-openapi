"""
Probe ALL ALM GET endpoints with real tenant data.

Collects full sample payloads, then analyses every field value for:
  - ID format patterns (hex-32 lowercase, hex-32 uppercase, UUID, numeric-string, ...)
  - Date/time format patterns
  - Enum candidate fields
  - Nullable fields

Run with:
    uv run --env-file .env python scripts/probe_alm_all_gets.py

Requires ANAPLAN_USERNAME and ANAPLAN_PASSWORD in .env (or environment).
Optional:
    ANAPLAN_MODEL_ID      - default: 0939A1C8E7FB46799372EC24A72FE93B
    ANAPLAN_ALM_BASE_URL  - default: https://api.anaplan.com/2/0
"""

import base64
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

USERNAME = os.environ.get("ANAPLAN_USERNAME", "")
PASSWORD = os.environ.get("ANAPLAN_PASSWORD", "")
BASE_URL = os.environ.get("ANAPLAN_ALM_BASE_URL", "https://api.anaplan.com/2/0").rstrip("/")
MODEL_ID = os.environ.get("ANAPLAN_MODEL_ID", "B1A963FFC71D4DC69DC2C087824BE619")

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
    """GET an ALM path; return parsed JSON or None on error."""
    url = f"{BASE_URL}{path}"
    r = CLIENT.get(url, headers=HDRS, params=params or {})
    qs = "?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else ""
    print(f"  GET {path}{qs} -> {r.status_code}")
    if r.status_code == 200:
        return r.json()
    print(f"    -> {r.text[:300]}")
    return None


# ── pattern detection ─────────────────────────────────────────────────────────

HEX32_LOWER = re.compile(r"^[0-9a-f]{32}$")
HEX32_UPPER = re.compile(r"^[0-9A-F]{32}$")
HEX32_MIXED = re.compile(r"^[0-9a-fA-F]{32}$")
UUID4_RE    = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)
UUID_RE     = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
NUMERIC_ID  = re.compile(r"^\d{9,}$")
ISO8601_RE  = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
DATE_RE     = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def classify_value(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer:epoch" if v > 1_000_000_000 else f"integer:{v}"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        if HEX32_LOWER.match(v):
            return "id:hex32lower"
        if HEX32_UPPER.match(v):
            return "id:hex32upper"
        if HEX32_MIXED.match(v):
            return "id:hex32mixed"
        if UUID4_RE.match(v):
            return "id:uuid4"
        if UUID_RE.match(v):
            return "id:uuid"
        if NUMERIC_ID.match(v):
            return "id:numeric"
        if ISO8601_RE.match(v):
            return "datetime:iso8601"
        if DATE_RE.match(v):
            return "date:iso8601"
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


# ── collect sample data ───────────────────────────────────────────────────────

SAMPLES: dict[str, list] = defaultdict(list)

print("=" * 70)
print("ALM GET probe — collecting sample data")
print(f"Base URL: {BASE_URL}")
print(f"Model ID: {MODEL_ID}")
print("=" * 70)

# 1. GET /models/{modelId}/alm/latestRevision
print("\n[1] Latest revision")
data = get(f"/models/{MODEL_ID}/alm/latestRevision")
latest_revision_id = None
if data:
    walk(data)
    SAMPLES["latest_revision"].append(data)
    revision = data.get("revision")
    if revision:
        latest_revision_id = revision.get("id")
        print(f"  -> revision.id = {latest_revision_id!r}")

# 2. GET /models/{modelId}/alm/revisions (paginated)
print("\n[2] Revisions list")
all_revisions = []
for offset in [0, 10]:
    data = get(f"/models/{MODEL_ID}/alm/revisions", {"limit": 10, "offset": offset})
    if data:
        page = data.get("revisions", [])
        all_revisions.extend(page)
        walk(data)
        if len(page) < 10:
            break
SAMPLES["revisions"].extend(all_revisions)
print(f"  -> collected {len(all_revisions)} revisions")

# 3. GET /models/{modelId}/alm/revisions/{revisionId}/appliedToModels
print("\n[3] Applied-to-models for each revision (up to 3)")
revision_ids_seen = []
for rev in all_revisions[:5]:
    rid = rev.get("id")
    if rid and rid not in revision_ids_seen:
        revision_ids_seen.append(rid)
        data = get(f"/models/{MODEL_ID}/alm/revisions/{rid}/appliedToModels")
        if data:
            walk(data)
            SAMPLES["applied_to_models"].append(data)
        if len(revision_ids_seen) >= 3:
            break

if not revision_ids_seen and latest_revision_id:
    revision_ids_seen.append(latest_revision_id)
    data = get(f"/models/{MODEL_ID}/alm/revisions/{latest_revision_id}/appliedToModels")
    if data:
        walk(data)
        SAMPLES["applied_to_models"].append(data)

# 4. GET /models/{modelId}/alm/syncableRevisions?sourceModelId={MODEL_ID}
print("\n[4] Syncable revisions (using same model as source — may return empty)")
data = get(f"/models/{MODEL_ID}/alm/syncableRevisions", {"sourceModelId": MODEL_ID})
if data:
    walk(data)
    SAMPLES["syncable_revisions"].append(data)

# 5. GET /models/{modelId}/alm/syncTasks
print("\n[5] Sync tasks")
data = get(f"/models/{MODEL_ID}/alm/syncTasks")
all_sync_tasks = []
if data:
    walk(data)
    SAMPLES["sync_tasks"].append(data)
    all_sync_tasks = data.get("tasks", [])
    print(f"  -> {len(all_sync_tasks)} task(s) found")

# 6. GET /models/{modelId}/alm/syncTasks/{syncTaskId}
print("\n[6] Sync task detail")
for task in all_sync_tasks[:2]:
    tid = task.get("taskId")
    if tid:
        data = get(f"/models/{MODEL_ID}/alm/syncTasks/{tid}")
        if data:
            walk(data)
            SAMPLES["sync_task_detail"].append(data)

CLIENT.close()

# ── analysis ──────────────────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("PATTERN ANALYSIS")
print("=" * 70)

id_fields = []
datetime_fields = []
date_fields = []
bool_fields = []
nullable_fields = []
always_null = []

for path, counter in sorted(field_stats.items()):
    total = sum(counter.values())
    null_count = counter.get("null", 0)

    if "null" in counter and null_count < total:
        nullable_fields.append((path, null_count, total))
    if null_count == total:
        always_null.append(path)
        continue

    non_null = {k: v for k, v in counter.items() if k != "null"}
    non_null_dom = Counter(non_null).most_common(1)[0][0] if non_null else None

    if non_null_dom in ("id:hex32lower", "id:hex32upper", "id:hex32mixed", "id:uuid4", "id:uuid", "id:numeric"):
        id_fields.append((path, non_null_dom, field_examples[path]))
    elif non_null_dom == "datetime:iso8601":
        datetime_fields.append((path, field_examples.get(path, [])))
    elif non_null_dom == "date:iso8601":
        date_fields.append((path, field_examples.get(path, [])))
    elif non_null_dom == "boolean":
        bool_fields.append(path)

print("\n-- ID Fields ------------------------------------------------------------------")
for path, fmt, examples in id_fields:
    print(f"  {path}")
    print(f"    format: {fmt}")
    if examples:
        print(f"    examples: {examples[:3]}")

print("\n-- Date-Time Fields -----------------------------------------------------------")
for path, ex in datetime_fields:
    print(f"  {path}  e.g. {ex[0]!r}" if ex else f"  {path}")

print("\n-- Boolean Fields -------------------------------------------------------------")
for path in bool_fields:
    print(f"  {path}")

print("\n-- Nullable Fields ------------------------------------------------------------")
for path, null_count, total in sorted(nullable_fields, key=lambda x: -x[1]):
    ex = [e for e in field_examples.get(path, []) if e is not None]
    print(f"  {path}  null={null_count}/{total}  non-null e.g. {ex[:2]}")

print("\n-- Always-null Fields ---------------------------------------------------------")
for path in always_null:
    print(f"  {path}")

print("\n" + "=" * 70)
print("RAW SAMPLE PAYLOADS (first item from each endpoint category)")
print("=" * 70)

for label, items in SAMPLES.items():
    if not items:
        continue
    print(f"\n-- {label} --")
    print(json.dumps(items[0], indent=2, default=str)[:3000])

print("\n[done]")
