"""Scan live Anaplan API endpoints to map a user's access level, emit a CSV report.

Authenticates with the OAuth Authorization Code flow on the command line (token
kept in memory only — never stored), fetches the caller's Anaplan user id,
discovers a workspace + model the user can actually reach, then probes every
operation across seven APIs (integration, cloudworks, scim, alm, audit,
exception, administration) and records the status / outcome / response body for
each. From the role-gated APIs it guesses the user's access level.

Path parameters are filled with real IDs where possible (see
docs/scan-path-parameter-sources.md for the full map). GET requests are
read-only, so real IDs are safe: GETs run first (shallow paths before deep) and
each 2xx response is harvested two ways —

  1. source-linked: the response of the endpoint prefix directly above a param
     supplies it, so `.../actions/{actionId}/tasks` feeds
     `.../actions/{actionId}/tasks/{taskId}` while `.../imports/{importId}/tasks`
     feeds the import taskId — same param name, distinct sources, never crossed;
  2. field pool: embedded IDs are scraped by name (cloudworks
     `integrations[].integrationId`, `.../notificationId`), used as a fallback.

Aliases cover shared identities (scim `{id}` / exception `{userGuid}` are the
caller's user GUID; alm target/sourceRevisionId are a revisionId), `chunkId`
defaults to `0`, and task IDs resolve *only* by source-link (never the flat pool)
so an action's taskId can't leak into an unrelated endpoint. Mutating verbs
(POST/PUT/PATCH/DELETE) *always* use a fabricated non-existent ID for safety.
Anything unresolved falls back to the fabricated ID. Each row carries a
`confidence`:

  real           param-free, or every path param filled from a real ID — the
                 status reflects the user's authorization to that endpoint
  fabricated-id  a param fell back to a non-existent ID, so a 404 means "resource
                 not found", NOT that the user is authorized — do not trust
                 role_held on these rows

Only `real`-confidence endpoints count toward the guessed access level.

Probing is tiered so it cannot mutate data by default:

  default            GET endpoints + the two search POSTs (harmless)
  --include-writes   also POST/PUT/PATCH, with fabricated non-existent IDs and
                     empty bodies so the call fails validation before any state
                     change; only the auth/authorization status is read
  --include-deletes  also DELETE, same fabricated-ID approach (404 before delete)

Outcome is read from the HTTP status alone, because Anaplan checks auth (401) and
authorization/role (403) *before* resolving the resource or acting on the body:

  ACCESS      2xx                      -> role held
  AUTHORIZED  400/404/405/409/415/422  -> passed the gate, our fake input failed
                                          -> role held
  ROLE_DENIED 403 (admin also 401/500) -> authenticated, role NOT held
  AUTH_FAIL   401                       -> token rejected
  NOT_ENTITLED 452                      -> tenant lacks the entitlement

    uv run python scripts/scan_endpoint_access.py [--include-writes] [--include-deletes]

Reads ANAPLAN_OAUTH_AUTHCODE_CLIENT_ID / _SECRET from .env or prompts for them.

# ponytail: us1 region hardcoded (via oauth helper); add --region if multi-region needed.
"""
import argparse
import csv
import datetime as dt
import getpass
import json
import os
import pathlib
import re
import secrets
import sys

import httpx

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts" / "oauth"))
from oauth_authcode import (  # noqa: E402  (reuse the tested auth-code flow)
    _load_env,
    build_auth_url,
    exchange_code_for_token,
    extract_code,
)

APIS = ["integration", "cloudworks", "scim", "alm", "audit", "exception", "administration"]

# OAuth access tokens ride as Bearer on api.anaplan.com (integration/cloudworks/
# scim/alm). The audit, exception, and administration hosts reject Bearer and
# require the AnaplanAuthToken scheme (the anaplan-sdk sends it for every call).
AUTH_SCHEME = {
    "audit": "AnaplanAuthToken",
    "exception": "AnaplanAuthToken",
    "administration": "AnaplanAuthToken",
}

# Each API's role gate, for the access-level guess. Short code used in the filename.
ROLE = {
    "audit": ("Tenant Auditor", "auditor"),
    "administration": ("Tenant Administrator", "admin"),
    "exception": ("Tenant Security Admin", "secadmin"),
    "scim": ("SCIM User Admin", "scim"),
    "integration": ("Model access", "model"),
    "cloudworks": ("CloudWorks access", "cw"),
    "alm": ("ALM model access", "alm"),
}

FAKE_ID = "00000000000000000000000000000000"  # fabricated, non-existent

# Valid-shaped bodies for the search POSTs so the role check is the discriminator.
SEARCH_BODY = {
    "/permissions/exception-users/search": {"workspaceGuid": FAKE_ID},
    "/events/search": {"interval": 1},
}

_PARAM = re.compile(r"\{[^}]+\}")
_HELD = {"ACCESS", "AUTHORIZED"}

# A param that has no direct source resolves via an equivalent one instead.
# scim {id} / exception {userGuid} are the caller's user GUID; alm compare
# revisions are ordinary revision IDs (see docs/scan-path-parameter-sources.md).
PARAM_ALIAS = {
    "id": "userId",
    "userGuid": "userId",
    "targetRevisionId": "revisionId",
    "sourceRevisionId": "revisionId",
}

# Task IDs are scoped to the parent that launched them (an action's taskId is not
# valid under a process), so they resolve *only* by source-link, never the flat
# field pool — otherwise one context's task would leak into another.
TASK_PARAMS = {"taskId", "syncTaskId"}


def classify_kind(method, path):
    if method == "get":
        return "read"
    if method == "post" and path.endswith("/search"):
        return "search"
    if method == "delete":
        return "delete"
    return "write"


def classify_outcome(status, api):
    """Map HTTP status to an access outcome (per-API overrides for administration)."""
    if api == "administration" and status in (401, 500):
        return "ROLE_DENIED"  # admin role-denial returns 401 (OAuth) / 500, not 403
    if status == 403:
        return "ROLE_DENIED"
    if status == 401:
        return "AUTH_FAIL"
    if status == 452:
        return "NOT_ENTITLED"  # tenant lacks the entitlement (not a user-auth signal)
    if 200 <= status < 300:
        return "ACCESS"
    if status in (400, 404, 405, 409, 415, 422):
        return "AUTHORIZED"  # gate passed; failure is our fabricated input
    if status >= 500:
        return "SERVER_ERROR"
    return "OTHER"


def fill_path(path, real_ids):
    """Substitute real discovered IDs into a path; fabricate the rest.

    Returns (filled_path, confidence). ``confidence`` is "real" when every path
    parameter was filled from a real ID the user can reach (or the path has none),
    and "fabricated-id" when any parameter fell back to a non-existent value — in
    which case a 404 means "resource not found" and says nothing about the user's
    authorization to that endpoint.
    """
    fabricated = False

    def repl(m):
        nonlocal fabricated
        name = m.group(0)[1:-1]
        if real_ids.get(name):
            return real_ids[name]
        fabricated = True
        return FAKE_ID

    filled = _PARAM.sub(repl, path)
    return filled, ("fabricated-id" if fabricated else "real")


def _singular(name):
    """Naive collection -> singular for the "<collection> -> <singular>Id" rule."""
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("s"):
        return name[:-1]
    return name  # ponytail: naive; fix if a collection name breaks it


def _param_names():
    """All path-parameter names across the in-scope specs (used to scrape IDs)."""
    names = set()
    for api in APIS:
        spec = json.loads((REPO / api / f"{api}-openapi.json").read_text(encoding="utf-8"))
        for path in spec["paths"]:
            names.update(m[1:-1] for m in _PARAM.findall(path))
    return names


def _pick(item, param):
    """Read a param's value from a harvested item dict, tolerant of field names.

    Anaplan is inconsistent: the id field may be ``integrationId`` (cloudworks),
    ``id`` (integration/scim), or ``taskId`` (alm syncTasks). Try the param's own
    name first, then the two generic id fields.
    """
    for key in (param, "id", "taskId"):
        val = item.get(key)
        if val:
            return str(val)
    return None


def _best(items):
    """Pick a usable item from a list, skipping archived / inactive ones.

    ``GET /models`` can return an archived model first; using it makes every
    sub-resource list fail 422 ("Model is archived"), so nothing downstream can be
    harvested. Prefer the first item that is neither archived (``activeState``) nor
    inactive (``active``); fall back to the first item for lists without those keys.
    """
    for item in items:
        state = str(item.get("activeState", "")).upper()
        if state == "ARCHIVED" or item.get("active") is False:
            continue
        return item
    return items[0]


def _first_item(data):
    """Return the representative item dict from a GET response, or None.

    First list-of-dicts found (``{"models": [{...}]}``, SCIM ``Resources``, nested
    ``history_of_runs.runs``); failing that, the first nested dict that carries an
    id-ish key (the import tasks response is a single ``{"task": {"taskId": ...}}``).
    """
    queue = [data]
    fallback = None
    while queue:
        node = queue.pop(0)
        if isinstance(node, dict):
            for key, val in node.items():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    return _best(val)
                queue.append(val)
            if fallback is None and any(k == "id" or k.endswith("Id") for k in node):
                fallback = node
        elif isinstance(node, list):
            queue.extend(node[:5])
    return fallback


def _scrape(node, field_pool, known):
    """Recursively collect IDs from a GET response into the flat fallback pool.

    Two forms: a list under key K yields ``{singular(K)}Id`` from its first item;
    a scalar whose key is itself a known param name is taken as that ID. Task IDs
    are skipped (they must stay source-linked). First value wins (setdefault).
    """
    if isinstance(node, dict):
        for key, val in node.items():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                param = _singular(key) + "Id"
                if param not in TASK_PARAMS:
                    got = _pick(_best(val), param)
                    if got:
                        field_pool.setdefault(param, got)
            elif (key in known and key not in TASK_PARAMS
                  and isinstance(val, (str, int)) and str(val)):
                field_pool.setdefault(key, str(val))
            _scrape(val, field_pool, known)
    elif isinstance(node, list):
        for item in node[:5]:
            _scrape(item, field_pool, known)


def harvest(api, template, data, items_by_source, field_pool, known):
    """Record IDs from one GET response: source-linked item + flat field pool."""
    item = _first_item(data)
    if item:
        items_by_source[(api, template)] = item
    _scrape(data, field_pool, known)


def fill_get(api, template, items_by_source, field_pool):
    """Fill a GET path with real IDs; return (filled_path, confidence).

    Each param is resolved in order: (1) source-linked — the item harvested from
    the endpoint prefix directly above it; (2) the flat field pool, directly or via
    PARAM_ALIAS; (3) ``chunkId`` defaults to ``0``. Otherwise the fabricated ID,
    which marks the row ``fabricated-id`` (a 404 then means "not found", not
    "authorized").
    """
    fabricated = False

    def repl(m):
        nonlocal fabricated
        param = m.group(0)[1:-1]
        prefix = template[:m.start()].rstrip("/")
        item = items_by_source.get((api, prefix))
        val = _pick(item, param) if item else None
        if not val:
            val = field_pool.get(param) or field_pool.get(PARAM_ALIAS.get(param, ""))
        if not val and param == "chunkId":
            val = "0"
        if val:
            return val
        fabricated = True
        return FAKE_ID

    filled = _PARAM.sub(repl, template)
    return filled, ("fabricated-id" if fabricated else "real")


def build_probes(include_writes, include_deletes):
    """Yield raw probe dicts (path unfilled) for every in-scope operation."""
    for api in APIS:
        spec = json.loads(
            (REPO / api / f"{api}-openapi.json").read_text(encoding="utf-8")
        )
        base = spec["servers"][0]["url"]
        scheme = AUTH_SCHEME.get(api, "Bearer")
        for path, ops in spec["paths"].items():
            for method in ops:
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                kind = classify_kind(method, path)
                if kind == "write" and not include_writes:
                    continue
                if kind == "delete" and not include_deletes:
                    continue
                if kind == "search":
                    body = SEARCH_BODY.get(path, {})
                elif kind == "write":
                    body = {}
                else:
                    body = None
                yield {
                    "api": api,
                    "method": method.upper(),
                    "path": path,
                    "kind": kind,
                    "expected_role": ROLE[api][0],
                    "base": base,
                    "scheme": scheme,
                    "body": body,
                }


def fetch_user_id(client, token):
    """Return the caller's Anaplan user id via integration GET /users/me."""
    base = json.loads(
        (REPO / "integration" / "integration-openapi.json").read_text(encoding="utf-8")
    )["servers"][0]["url"]
    r = client.get(f"{base}/users/me", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    body = r.json()
    user = body.get("user", body)
    return user.get("id") or user.get("userId") or "unknown"


def run_probe(client, token, probe):
    headers = {"Authorization": f"{probe['scheme']} {token}"}
    data = None
    try:
        r = client.request(
            probe["method"], probe["url"], headers=headers, json=probe["body"]
        )
        status, text = r.status_code, r.text
        if 200 <= status < 300:
            try:
                data = r.json()
            except ValueError:
                pass
    except httpx.HTTPError as e:
        status, text = 0, f"REQUEST_ERROR: {e}"
    outcome = classify_outcome(status, probe["api"]) if status else "REQUEST_ERROR"
    snippet = " ".join(text.split())[:300]
    return status, outcome, snippet, data


def guess_level(roles_held):
    """Filename access tag from the set of APIs whose gate the user passed."""
    codes = [ROLE[a][1] for a in APIS if a in roles_held]
    return "+".join(codes) if codes else "basic"


def authenticate():
    _load_env()
    client_id = os.getenv("ANAPLAN_OAUTH_AUTHCODE_CLIENT_ID") or input("Client ID: ").strip()
    client_secret = os.getenv("ANAPLAN_OAUTH_AUTHCODE_CLIENT_SECRET") or getpass.getpass(
        "Client secret: "
    )
    state = secrets.token_urlsafe(16)
    print("\nOpen this URL in your browser and approve access:")
    print(f"  {build_auth_url(client_id, state=state)}\n")
    print("After approving you are redirected to https://www.anaplan.com — paste the full URL.\n")
    code = extract_code(input("Redirect URL: ").strip(), expected_state=state)
    r = exchange_code_for_token(code, client_id, client_secret)
    if r.status_code != 200:
        raise SystemExit(f"Token exchange failed ({r.status_code}): {r.text}")
    return r.json()["access_token"]  # in memory only; never stored


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--include-writes", action="store_true",
                    help="probe POST/PUT/PATCH with fabricated IDs / empty bodies")
    ap.add_argument("--include-deletes", action="store_true",
                    help="probe DELETE with fabricated non-existent IDs")
    ap.add_argument("--out", default=".", help="output directory for the CSV")
    ap.add_argument("--selftest", action="store_true", help="run offline self-checks and exit")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return

    token = authenticate()

    rows = []
    roles_held = set()
    known = _param_names() - {"id"}  # 'id' too generic to scrape safely
    items_by_source = {}   # (api, source-template) -> first harvested item dict
    field_pool = {}        # param name -> value, flat fallback for embedded IDs
    with httpx.Client(timeout=30) as client:
        user_id = fetch_user_id(client, token)
        if user_id != "unknown":
            # Seed the caller's own GUID so scim {id} / exception {userGuid} resolve
            # even when their user-list endpoints are not reachable.
            field_pool["userId"] = str(user_id)
        print(f"\nUser id: {user_id}")

        probes = list(build_probes(args.include_writes, args.include_deletes))
        # Run GETs first, shallow paths before deep, so a list endpoint's IDs are
        # harvested before the item endpoint that needs them. Writes and deletes
        # run last and always use synthetic IDs (never a real one).
        probes.sort(key=lambda p: (
            p["method"] != "GET", p["path"].count("/"), p["api"], p["path"]
        ))
        print(f"Probing {len(probes)} endpoints...\n")
        for p in probes:
            # GETs are read-only, so real IDs are safe and harvested along the way;
            # mutating verbs stay synthetic for safety.
            if p["method"] == "GET":
                filled, confidence = fill_get(
                    p["api"], p["path"], items_by_source, field_pool
                )
            else:
                filled, confidence = fill_path(p["path"], {})
            p["url"] = p["base"] + filled
            status, outcome, snippet, data = run_probe(client, token, p)
            if p["method"] == "GET" and data is not None:
                harvest(p["api"], p["path"], data, items_by_source, field_pool, known)
            held = outcome in _HELD
            # Only a real-ID (or param-free) endpoint proves authorization; a
            # fabricated-ID 404 just means the resource doesn't exist.
            if held and confidence == "real":
                roles_held.add(p["api"])
            rows.append({
                "api": p["api"], "method": p["method"], "path": p["path"],
                "kind": p["kind"], "confidence": confidence,
                "expected_role": p["expected_role"],
                "status": status, "outcome": outcome, "role_held": held,
                "response_body": snippet,
            })
            print(f"  {outcome:12} {status:>3} {confidence:13} {p['method']:6} {p['api']}{p['path']}")

    level = guess_level(roles_held)
    held_names = ", ".join(ROLE[a][0] for a in APIS if a in roles_held) or "none detected"
    print(f"\nAccess level guess: {level}  ({held_names})")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_user = re.sub(r"[^A-Za-z0-9_-]", "_", str(user_id))
    out = pathlib.Path(args.out) / f"scan-{safe_user}-{level}-{stamp}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Report: {out}")


def _selftest():
    assert classify_outcome(200, "scim") == "ACCESS"
    assert classify_outcome(404, "scim") == "AUTHORIZED"
    assert classify_outcome(403, "scim") == "ROLE_DENIED"
    assert classify_outcome(401, "scim") == "AUTH_FAIL"
    assert classify_outcome(401, "administration") == "ROLE_DENIED"
    assert classify_outcome(500, "administration") == "ROLE_DENIED"
    assert classify_outcome(452, "cloudworks") == "NOT_ENTITLED"
    assert classify_kind("post", "/events/search") == "search"
    assert classify_kind("post", "/Users") == "write"
    assert classify_kind("delete", "/Users/{id}") == "delete"
    assert guess_level({"audit", "integration"}) == "model+auditor"
    assert guess_level(set()) == "basic"
    assert _singular("lineItems") == "lineItem"
    assert _singular("dimensions") == "dimension"
    assert _singular("categories") == "category"
    # fill_path (mutating verbs): no real IDs -> every param fabricated
    assert fill_path("/models/{modelId}", {}) == (f"/models/{FAKE_ID}", "fabricated-id")
    assert fill_path("/workspaces", {}) == ("/workspaces", "real")
    # _pick tolerates the field-name spread (integrationId / id / taskId)
    assert _pick({"integrationId": "I1"}, "integrationId") == "I1"
    assert _pick({"id": "X"}, "modelId") == "X"
    assert _pick({"taskId": "T"}, "syncTaskId") == "T"  # alm syncTasks item field
    assert _pick({"name": "n"}, "modelId") is None
    # _first_item: list-of-dicts, SCIM Resources, and single nested task object
    assert _first_item({"models": [{"id": "M1"}]}) == {"id": "M1"}
    assert _first_item({"Resources": [{"id": "U1"}]}) == {"id": "U1"}
    assert _first_item({"meta": 1, "task": {"taskId": "T1"}}) == {"taskId": "T1"}
    # _best skips archived / inactive items so the seed model is usable
    assert _best([{"id": "A", "activeState": "ARCHIVED"}, {"id": "B"}]) == {"id": "B"}
    assert _best([{"id": "A", "active": False}, {"id": "B", "active": True}])["id"] == "B"
    assert _best([{"id": "A", "activeState": "ARCHIVED"}])["id"] == "A"  # no choice
    assert _first_item({"models": [{"id": "A", "activeState": "ARCHIVED"},
                                   {"id": "B"}]}) == {"id": "B"}
    # _scrape: embedded IDs land in the pool; task IDs and bare 'id' do not
    known = {"integrationId", "notificationId", "modelId", "runId"}
    fp = {}
    _scrape({"integrations": [{"integrationId": "I1", "notificationId": "N1"}]}, fp, known)
    assert fp == {"integrationId": "I1", "notificationId": "N1"}
    fp = {}
    _scrape({"tasks": [{"taskId": "T"}]}, fp, known)  # task IDs stay source-linked
    assert fp == {}
    fp = {}
    _scrape({"history_of_runs": {"runs": [{"id": "R1"}]}}, fp, known)
    assert fp == {"runId": "R1"}
    # fill_get: source-linked, field pool, alias, chunk default
    src = {
        ("integration", "/models"): {"id": "M1"},
        ("cloudworks", "/integrations"): {"integrationId": "I1"},
        # same param name, two parents -> two sources, never crossed
        ("integration", "/models/M1/actions/A1/tasks"): {"taskId": "AT"},
        ("integration", "/models/M1/imports/N1/tasks"): {"taskId": "IT"},
    }
    assert fill_get("integration", "/models/{modelId}", src, {}) == ("/models/M1", "real")
    assert fill_get("cloudworks", "/integrations/{integrationId}", src, {}) == (
        "/integrations/I1", "real")
    act = fill_get("integration", "/models/M1/actions/A1/tasks/{taskId}", src, {})
    imp = fill_get("integration", "/models/M1/imports/N1/tasks/{taskId}", src, {})
    assert act == ("/models/M1/actions/A1/tasks/AT", "real")
    assert imp == ("/models/M1/imports/N1/tasks/IT", "real")  # not AT
    # field-pool fallback + alias: scim {id} resolves from seeded userId
    assert fill_get("scim", "/Users/{id}", {}, {"userId": "U9"}) == ("/Users/U9", "real")
    # chunkId defaults to 0
    assert fill_get("integration", "/f/{chunkId}", {}, {}) == ("/f/0", "real")
    # no source at all -> fabricated
    assert fill_get("integration", "/x/{fileId}", {}, {}) == (f"/x/{FAKE_ID}", "fabricated-id")
    # _param_names pulls real params from the specs
    assert {"modelId", "taskId", "integrationId", "chunkId"} <= _param_names()
    # default tier: no writes, no deletes
    probes = list(build_probes(False, False))
    assert {p["kind"] for p in probes} == {"read", "search"}
    assert all("base" in p and "url" not in p for p in probes)
    assert "delete" in {p["kind"] for p in build_probes(True, True)}
    print("selftest OK")


if __name__ == "__main__":
    main()
