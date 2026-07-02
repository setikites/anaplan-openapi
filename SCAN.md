# Running the Anaplan endpoint access scan

This guide walks you through running `scripts/scan_endpoint_access.py` end to end:
authenticate as an Anaplan user via OAuth, probe every endpoint across seven APIs
(integration, cloudworks, scim, alm, audit, exception, administration), and produce
a CSV documenting the success/failure code and response body for each — including
the **write** (POST/PUT/PATCH) and **delete** tiers.

The token is held in memory for the duration of the run only. It is never written
to disk or the OS keyring.

## What the write/delete tiers actually do

The scan tests **access**, not function. Mutating calls are deliberately shaped to
fail before they change anything:

- Every path ID is replaced with a fabricated, non-existent value
  (`00000000000000000000000000000000`).
- Write bodies are empty (`{}`).

Anaplan checks authentication (401) and role authorization (403) *before* resolving
the resource or acting on the body, so a fabricated request still reveals whether
you have access — without creating, updating, or deleting any real data. A DELETE
against a non-existent ID returns 404 before any delete occurs.

That said, you are hitting the **live** API with a real account. Run it against a
tenant where that is acceptable.

## Prerequisites

- [`git`](https://git-scm.com/)
- [`uv`](https://docs.astral.sh/uv/) — Python package/runner. Install:
  ```
  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Windows (PowerShell)
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- An Anaplan OAuth client (client ID + secret) configured for the Authorization
  Code grant. The `.env` file with these values is provided separately.

## 1. Clone the repository

```
git clone https://github.com/setikites/anaplan-openapi.git
cd anaplan-openapi
```

The scanner is on `master`, so a default clone has it — no branch switch needed.

## 2. Add the `.env` file

Place the `.env` file provided to you in the repository root (same directory as
`README.md`). It must contain at least:

```
ANAPLAN_OAUTH_AUTHCODE_CLIENT_ID=<your client id>
ANAPLAN_OAUTH_AUTHCODE_CLIENT_SECRET=<your client secret>
```

`.env` is git-ignored — do not commit it.

## 3. Install dependencies

`uv` reads `pyproject.toml` and installs everything on first run. To do it
explicitly up front:

```
uv sync
```

## 4. Run the scan with writes and deletes

```
uv run --env-file .env python scripts/scan_endpoint_access.py --include-writes --include-deletes
```

You will be prompted to:

1. Open a printed URL in your browser and approve access.
2. After approving, your browser redirects to `https://www.anaplan.com`. Copy the
   **full** URL from the address bar (it carries the authorization code) and paste
   it back at the `Redirect URL:` prompt.

The script then fetches your Anaplan user id, discovers a workspace + model you
can reach, and probes ~159 endpoints, printing each result as it goes. GET
requests run first and harvest real IDs from list responses to fill deeper GET
path parameters (e.g. a `lineItemId` from `.../lineItems` feeds
`.../lineItems/{lineItemId}/dimensions`), so more read endpoints get a trustworthy
`real` confidence. The full parameter→source map is
[docs/scan-path-parameter-sources.md](docs/scan-path-parameter-sources.md).
Mutating requests (POST/PUT/PATCH/DELETE) always use synthetic non-existent IDs,
so they can never change real data.

## 5. Output

A CSV is written to the current directory, named:

```
scan-<userId>-<accessLevel>-<timestamp>.csv
```

where `<accessLevel>` is the guessed level (e.g. `model+auditor+admin`, or `basic`
if no role gate was passed). Columns:

| Column | Meaning |
|--------|---------|
| `api` | which of the seven APIs |
| `method` | HTTP verb |
| `path` | endpoint path |
| `kind` | `read` / `search` / `write` / `delete` |
| `confidence` | `real` = trust this row; `fabricated-id` = a path param used a non-existent ID, so `role_held` is not meaningful (a 404 just means "resource not found") |
| `expected_role` | the role that API is gated on |
| `status` | HTTP status code (`0` = request error) |
| `outcome` | `ACCESS` / `AUTHORIZED` / `ROLE_DENIED` / `AUTH_FAIL` / `NOT_ENTITLED` / `SERVER_ERROR` |
| `role_held` | `True` if the access gate was passed (only trustworthy when `confidence` is `real`) |
| `response_body` | first 300 chars of the response |

**Read `confidence` first.** Only `real`-confidence rows tell you whether *you*
are authorized to an endpoint; `fabricated-id` rows (deep-nested resources like
files, views, revisions) only tell you the endpoint exists. The guessed access
level in the filename is computed from `real` rows only.

Send the CSV back for review.

## Notes

- Defaults to the **us1** region. If your tenant is in another region, tell the
  maintainer — a `--region` flag needs adding.
- Offline sanity check (no network, no credentials):
  ```
  uv run python scripts/scan_endpoint_access.py --selftest
  ```
