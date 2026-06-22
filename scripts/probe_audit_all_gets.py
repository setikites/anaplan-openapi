"""
Probe all Audit API GET endpoints with real tenant data.

Collects full sample payloads, then analyses every field value for:
  - ID format patterns (hex-32, UUID-4, numeric-string, ...)
  - Date/time format patterns
  - Enum candidate fields (low-cardinality strings)
  - Nullable fields

Run with:
    uv run --env-file .env python scripts/probe_audit_all_gets.py

Requires ANAPLAN_USERNAME and ANAPLAN_PASSWORD in .env (or environment).
Optional:
    ANAPLAN_AUDIT_BASE_URL       - default: https://audit.anaplan.com/audit/api/1
    ANAPLAN_OAUTH_KEYRING_SERVICE - if set, uses OAuth access_token from keyring
                                    instead of basic-auth token (needed for
                                    Tenant Auditor role on OAuth-only tenants)
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
BASE_URL = os.environ.get("ANAPLAN_AUDIT_BASE_URL", "https://audit.anaplan.com/audit/api/1").rstrip("/")

if not USERNAME or not PASSWORD:
    sys.exit("ERROR: ANAPLAN_USERNAME and ANAPLAN_PASSWORD must be set in .env")


# ── auth ─────────────────────────────────────────────────────────────────────

def get_basic_token() -> str:
    auth_b64 = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
    r = httpx.post(
        "https://auth.anaplan.com/token/authenticate",
        headers={"Authorization": f"Basic {auth_b64}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["tokenInfo"]["tokenValue"]


def get_oauth_token() -> str | None:
    service = os.environ.get("ANAPLAN_OAUTH_KEYRING_SERVICE", "anaplan-oauth-authcode")
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from oauth.token_keyring import load_token  # type: ignore
        blob = load_token(service)
        if blob:
            return json.loads(blob).get("access_token")
    except Exception:
        pass
    return None


def probe_token() -> tuple[str, str]:
    """Return (token, label). Try OAuth first; fall back to basic auth."""
    oauth_tok = get_oauth_token()
    if oauth_tok:
        # Quick sanity check — verify the token is still valid
        test = httpx.get(
            f"{BASE_URL}/events",
            headers={"Authorization": f"AnaplanAuthToken {oauth_tok}", "Accept": "application/json"},
            params={"limit": 1},
            timeout=15,
        )
        if test.status_code != 401 or "Token verification failed" not in test.text:
            return oauth_tok, "OAuth access_token from keyring"
        print("OAuth token in keyring is stale — falling back to basic auth")
    token = get_basic_token()
    return token, "AnaplanAuthToken from basic auth"


TOKEN, AUTH_LABEL = probe_token()
print(f"Using {AUTH_LABEL}")

HDRS = {"Authorization": f"AnaplanAuthToken {TOKEN}", "Accept": "application/json"}
CLIENT = httpx.Client(timeout=httpx.Timeout(30.0))


def get(path: str, params: dict | None = None) -> dict | list | None:
    """GET an Audit API path; return parsed JSON or None on error."""
    url = f"{BASE_URL}{path}"
    r = CLIENT.get(url, headers=HDRS, params=params or {})
    qs = "?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else ""
    print(f"  GET {path}{qs} -> {r.status_code}")
    if r.status_code == 200:
        return r.json()
    print(f"    -> {r.text[:300]}")
    return None


# ── pattern detection helpers ─────────────────────────────────────────────────

HEX32_RE   = re.compile(r"^[0-9a-f]{32}$")
UUID4_RE   = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)
UUID_RE    = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
HEX_UPPER  = re.compile(r"^[0-9A-F]{32}$")
NUMERIC_ID = re.compile(r"^\d{9,}$")
ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
DATE_RE    = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


def classify_value(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        if v > 1_000_000_000_000:
            return "integer:epoch_ms"
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

field_stats: dict[str, Counter] = defaultdict(Counter)
field_examples: dict[str, list] = defaultdict(list)
MAX_EXAMPLES = 8


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
print("Audit GET probe — collecting sample data")
print(f"Base URL: {BASE_URL}")
print("=" * 70)

# 1. GET /events with no filter — first two pages for broad coverage
print("\n[1] GET /events — unfiltered (pages 0 and 1, limit=100 each)")
for offset in [0, 100]:
    data = get("/events", {"limit": 100, "offset": offset})
    if isinstance(data, dict):
        events = data.get("response", [])
        SAMPLES["events_unfiltered"].extend(events)
        walk(data)
        if len(events) < 100:
            break

# 2. GET /events by type — sample several type filters for field coverage
print("\n[2] GET /events -- per-type samples (limit=50 each)")
TYPES_TO_PROBE = ["user_activity", "access_control", "int", "conn_mgmt", "comment"]
for evt_type in TYPES_TO_PROBE:
    data = get("/events", {"type": evt_type, "limit": 50, "offset": 0})
    if isinstance(data, dict):
        events = data.get("response", [])
        SAMPLES[f"events_{evt_type}"].extend(events)
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

for path, counter in sorted(field_stats.items()):
    total = sum(counter.values())
    null_count = counter.get("null", 0)

    if "null" in counter and null_count < total:
        nullable_fields.append((path, null_count, total))

    if null_count == total:
        always_null.append(path)
        continue

    non_null = {k: v for k, v in counter.items() if k != "null"}
    non_null_dom = Counter(non_null).most_common(1)[0][0] if non_null else ""

    if non_null_dom in ("id:hex32", "id:hex32upper", "id:uuid4", "id:uuid", "id:numeric"):
        id_fields.append((path, non_null_dom, field_examples[path]))
    elif non_null_dom == "datetime:iso8601":
        datetime_fields.append(path)
    elif non_null_dom == "date:iso8601":
        date_fields.append(path)
    elif non_null_dom in ("integer:epoch_ms", "integer:epoch"):
        epoch_fields.append((path, non_null_dom))
    elif non_null_dom == "boolean":
        bool_fields.append(path)
    elif non_null_dom.startswith("integer:") and non_null_dom not in ("integer:epoch", "integer:epoch_ms"):
        int_fields.append((path, list(counter.keys())))

    if all(k.startswith("string:") and len(k) < 60 for k in non_null.keys()) and 0 < len(non_null) <= 10:
        enum_candidates.append((path, sorted(non_null.keys())))

print("\n-- ID Fields ------------------------------------------------------------------")
for path, fmt, examples in id_fields:
    print(f"  {path}")
    print(f"    format: {fmt}")
    if examples:
        print(f"    examples: {examples[:3]}")

print("\n-- Date-Time Fields (ISO 8601) ------------------------------------------------")
for path in datetime_fields:
    ex = field_examples.get(path, [])
    print(f"  {path}  e.g. {ex[0]!r}" if ex else f"  {path}")

print("\n-- Epoch Integer Fields -------------------------------------------------------")
for path, fmt in epoch_fields:
    ex = field_examples.get(path, [])
    print(f"  {path}  ({fmt})  e.g. {ex[0]!r}" if ex else f"  {path}  ({fmt})")

print("\n-- Boolean Fields -------------------------------------------------------------")
for path in bool_fields:
    ex = field_examples.get(path, [])
    print(f"  {path}  e.g. {ex}" if ex else f"  {path}")

print("\n-- Integer-coded Fields -------------------------------------------------------")
for path, types in int_fields:
    ex = field_examples.get(path, [])
    print(f"  {path}  values: {[str(e) for e in ex if e is not None][:5]}  types: {types}")

print("\n-- Enum Candidates (low-cardinality strings) ----------------------------------")
for path, values in enum_candidates:
    clean = [v.replace("string:", "").strip("'") for v in values]
    print(f"  {path}")
    print(f"    observed: {clean}")

print("\n-- Nullable Fields ------------------------------------------------------------")
for path, null_count, total in sorted(nullable_fields, key=lambda x: -x[1]):
    pct = 100 * null_count // total
    ex = field_examples.get(path, [])
    non_null_ex = [e for e in ex if e is not None]
    print(f"  {path}  null={null_count}/{total} ({pct}%)  non-null e.g. {non_null_ex[:2]}")

print("\n-- Always-null Fields ---------------------------------------------------------")
for path in always_null:
    print(f"  {path}")

# -- raw samples ------------------------------------------------------------------

print("\n" + "=" * 70)
print("RAW SAMPLE PAYLOADS (first item from each category)")
print("=" * 70)

for label, items in SAMPLES.items():
    if not items:
        continue
    print(f"\n-- {label} --")
    print(json.dumps(items[0], indent=2, default=str)[:2000])

print("\n[done]")
