"""
Probe Exception Users (POST /search) and SCIM GET endpoints with real tenant data.

Exception Users has no GET endpoints; uses POST /search to collect samples.
SCIM uses GET /Users and GET /Users/{id}.

Analyses every ID-shaped field value and reports format classifications.

Run with:
    uv run --env-file .env python scripts/probe_exception_scim_all_gets.py

Requires ANAPLAN_USERNAME and ANAPLAN_PASSWORD in .env (or environment).
Optional:
    ANAPLAN_EXCEPTION_WORKSPACE_GUID  - workspace to query in exception search
    ANAPLAN_EXCEPTION_USER_GUID       - user to query in exception search
    ANAPLAN_EXCEPTION_BASE_URL        - default: https://api.anaplan.com/admin/1/0
    ANAPLAN_SCIM_BASE_URL             - default: https://api.anaplan.com/scim/1/0/v2
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
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

USERNAME = os.environ.get("ANAPLAN_USERNAME", "")
PASSWORD = os.environ.get("ANAPLAN_PASSWORD", "")
EXCEPTION_BASE = os.environ.get("ANAPLAN_EXCEPTION_BASE_URL", "https://api.anaplan.com/admin/1/0").rstrip("/")
SCIM_BASE = os.environ.get("ANAPLAN_SCIM_BASE_URL", "https://api.anaplan.com/scim/1/0/v2").rstrip("/")
EXCEPTION_WORKSPACE_GUID = os.environ.get("ANAPLAN_EXCEPTION_WORKSPACE_GUID", "")
EXCEPTION_USER_GUID = os.environ.get("ANAPLAN_EXCEPTION_USER_GUID", "")

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
AUTH_HDRS = {"Authorization": f"AnaplanAuthToken {TOKEN}", "Accept": "application/json"}
SCIM_HDRS = {"Authorization": f"AnaplanAuthToken {TOKEN}", "Accept": "application/scim+json"}
CLIENT = httpx.Client(timeout=30)


def api_get(base: str, path: str, params: dict | None = None, hdrs: dict | None = None) -> dict | list | None:
    url = f"{base}{path}"
    r = CLIENT.get(url, headers=hdrs or AUTH_HDRS, params=params or {})
    qs = "?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else ""
    print(f"  GET {path}{qs} -> {r.status_code}")
    if r.status_code == 200:
        return r.json()
    print(f"    -> {r.text[:300]}")
    return None


def api_post(base: str, path: str, body: dict, hdrs: dict | None = None) -> dict | list | None:
    url = f"{base}{path}"
    r = CLIENT.post(url, headers=hdrs or AUTH_HDRS, json=body)
    print(f"  POST {path} -> {r.status_code}")
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


# ── collect exception users data ──────────────────────────────────────────────

SAMPLES: dict[str, list] = defaultdict(list)

print("=" * 70)
print("Exception Users + SCIM probe — collecting sample data")
print("=" * 70)

print("\n[Exception Users] POST /permissions/exception-users/search")
print(f"  Exception Base URL: {EXCEPTION_BASE}")

if EXCEPTION_WORKSPACE_GUID:
    print(f"\n  [A] Search by workspaceGuid = {EXCEPTION_WORKSPACE_GUID!r}")
    data = api_post(EXCEPTION_BASE, "/permissions/exception-users/search",
                    {"workspaceGuid": EXCEPTION_WORKSPACE_GUID})
    if data:
        SAMPLES["exception_by_workspace"].append(data)
        walk(data)
else:
    print("  [A] ANAPLAN_EXCEPTION_WORKSPACE_GUID not set — skipping by-workspace search")

if EXCEPTION_USER_GUID:
    print(f"\n  [B] Search by userGuid = {EXCEPTION_USER_GUID!r}")
    data = api_post(EXCEPTION_BASE, "/permissions/exception-users/search",
                    {"userGuid": EXCEPTION_USER_GUID})
    if data:
        SAMPLES["exception_by_user"].append(data)
        walk(data)
else:
    print("  [B] ANAPLAN_EXCEPTION_USER_GUID not set — skipping by-user search")

# ── collect SCIM data ─────────────────────────────────────────────────────────

print(f"\n[SCIM] Base URL: {SCIM_BASE}")

print("\n  [1] GET /Users (first page, count=10)")
data = api_get(SCIM_BASE, "/Users", {"count": "10"}, hdrs=SCIM_HDRS)
first_user_id = None
if data:
    SAMPLES["scim_list_users"].append(data)
    walk(data)
    resources = data.get("Resources", []) if isinstance(data, dict) else []
    if resources:
        first_user_id = resources[0].get("id")
        print(f"    -> {len(resources)} users returned; first id = {first_user_id!r}")

print("\n  [2] GET /Users/{id} — fetch first user by ID")
if first_user_id:
    data = api_get(SCIM_BASE, f"/Users/{first_user_id}", hdrs=SCIM_HDRS)
    if data:
        SAMPLES["scim_get_user"].append(data)
        walk(data)
else:
    print("    (no user ID available — skipping)")

print("\n  [3] GET /ResourceTypes")
data = api_get(SCIM_BASE, "/ResourceTypes", hdrs=SCIM_HDRS)
if data:
    SAMPLES["scim_resource_types"].append(data)
    walk(data)

print("\n  [4] GET /ServiceProviderConfig")
data = api_get(SCIM_BASE, "/ServiceProviderConfig", hdrs=SCIM_HDRS)
if data:
    SAMPLES["scim_service_provider_config"].append(data)
    walk(data)

CLIENT.close()

# ── analysis ──────────────────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("PATTERN ANALYSIS")
print("=" * 70)

id_fields = []
datetime_fields = []
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
