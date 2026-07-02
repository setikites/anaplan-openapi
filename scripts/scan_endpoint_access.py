"""Scan live Anaplan API endpoints to map a user's access level, emit a CSV report.

Authenticates with the OAuth Authorization Code flow on the command line (token
kept in memory only — never stored), fetches the caller's Anaplan user id,
discovers a workspace + model the user can actually reach, then probes every
operation across seven APIs (integration, cloudworks, scim, alm, audit,
exception, administration) and records the status / outcome / response body for
each. From the role-gated APIs it guesses the user's access level.

Path parameters are filled with the discovered real workspace/model IDs where
possible; anything left (fileId, viewId, revisionId, ...) falls back to a
fabricated non-existent ID. Each row carries a `confidence`:

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

# OAuth access tokens ride as Bearer everywhere except exception/administration,
# which reject Bearer and require the AnaplanAuthToken scheme (see CONTEXT.md).
AUTH_SCHEME = {"exception": "AnaplanAuthToken", "administration": "AnaplanAuthToken"}

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


def build_probes(include_writes, include_deletes, real_ids):
    """Yield probe dicts for every in-scope operation across the seven specs."""
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
                elif kind in ("write",):
                    body = {}
                else:
                    body = None
                filled, confidence = fill_path(path, real_ids)
                yield {
                    "api": api,
                    "method": method.upper(),
                    "path": path,
                    "kind": kind,
                    "expected_role": ROLE[api][0],
                    "url": base + filled,
                    "scheme": scheme,
                    "body": body,
                    "confidence": confidence,
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


def discover_context(client, token):
    """Find a workspace + model the user can reach, to fill {workspaceId}/{modelId}.

    Returns a real-ID map for fill_path. Endpoints scoped to a real model return a
    genuine role gate (403) instead of a fabricated-ID 404, so the scan reflects the
    user's authorization rather than resource existence. Returns {} if the user has
    no accessible model (falls back to fabricated IDs for every scoped path).
    """
    base = json.loads(
        (REPO / "integration" / "integration-openapi.json").read_text(encoding="utf-8")
    )["servers"][0]["url"]
    hdr = {"Authorization": f"Bearer {token}"}
    ids = {}
    try:
        ws = client.get(f"{base}/workspaces", headers=hdr).json().get("workspaces", [])
        if ws:
            ids["workspaceId"] = ws[0]["id"]
        models = client.get(f"{base}/models", headers=hdr).json().get("models", [])
        if models:
            ids["modelId"] = models[0]["id"]
            # Prefer the model's own workspace so the paired {workspaceId}/{modelId}
            # endpoints resolve to a consistent, reachable pair.
            if models[0].get("currentWorkspaceId"):
                ids["workspaceId"] = models[0]["currentWorkspaceId"]
    except (httpx.HTTPError, KeyError, ValueError):
        pass
    return ids


def run_probe(client, token, probe):
    headers = {"Authorization": f"{probe['scheme']} {token}"}
    try:
        r = client.request(
            probe["method"], probe["url"], headers=headers, json=probe["body"]
        )
        status, text = r.status_code, r.text
    except httpx.HTTPError as e:
        status, text = 0, f"REQUEST_ERROR: {e}"
    outcome = classify_outcome(status, probe["api"]) if status else "REQUEST_ERROR"
    snippet = " ".join(text.split())[:300]
    return status, outcome, snippet


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
    with httpx.Client(timeout=30) as client:
        user_id = fetch_user_id(client, token)
        real_ids = discover_context(client, token)
        print(f"\nUser id: {user_id}")
        print("Real IDs: " + (", ".join(f"{k}={v}" for k, v in real_ids.items()) or "none — all scoped paths fabricated"))
        probes = list(build_probes(args.include_writes, args.include_deletes, real_ids))
        print(f"Probing {len(probes)} endpoints...\n")
        for p in probes:
            status, outcome, snippet = run_probe(client, token, p)
            held = outcome in _HELD
            # Only a real-ID (or param-free) endpoint proves authorization; a
            # fabricated-ID 404 just means the resource doesn't exist.
            if held and p["confidence"] == "real":
                roles_held.add(p["api"])
            rows.append({
                "api": p["api"], "method": p["method"], "path": p["path"],
                "kind": p["kind"], "confidence": p["confidence"],
                "expected_role": p["expected_role"],
                "status": status, "outcome": outcome, "role_held": held,
                "response_body": snippet,
            })
            print(f"  {outcome:12} {status:>3} {p['confidence']:13} {p['method']:6} {p['api']}{p['path']}")

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
    # fill_path: real IDs -> "real"; any leftover param -> "fabricated-id"
    ids = {"workspaceId": "W1", "modelId": "M1"}
    assert fill_path("/models/{modelId}", ids) == ("/models/M1", "real")
    assert fill_path("/workspaces", ids) == ("/workspaces", "real")
    assert fill_path("/models/{modelId}/files/{fileId}", ids) == (
        f"/models/M1/files/{FAKE_ID}", "fabricated-id")
    # default tier: no writes, no deletes; scoped paths marked
    probes = list(build_probes(False, False, ids))
    assert {p["kind"] for p in probes} == {"read", "search"}
    assert {p["confidence"] for p in probes} == {"real", "fabricated-id"}
    assert "delete" in {p["kind"] for p in build_probes(True, True, ids)}
    print("selftest OK")


if __name__ == "__main__":
    main()
