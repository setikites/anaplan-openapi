# Anaplan domain allowlist reference

Reference for `scripts/check_server_domains.py`, which checks every `servers[].url`
host in the specs against the patterns below. This file is the thing to update
after re-checking Anaplan's official sources — the script only diffs against it.

## Official sources (re-check these, they are not scrapable)

- [URL, IP, and allowlist requirements](https://support.anaplan.com/url-ip-and-allowlist-requirements-c8235c7d-8af2-413b-a9ff-d465978806b9) — Anaplan Support. Regional entries (us1a, us2a, us5a, us6a, us7a, us8a, us9, eu1a-eu5, gb1, ca1a, ca2a, sg1, ae1, me1, in1, id1, au1a, ap1a, ap2a) are behind expandable sections and a region picker, so a script cannot pull this page directly. Expand each region by hand and compare.
- [IP allowlist](https://help.anaplan.com/ip-allowlist-90adad3e-aa57-44c1-8ec4-71ca1a25a563) — Anapedia.
- [Domain and IP ranges](https://support.anaplan.com/domain-and-ip-ranges-c8235c7d-8af2-413b-a9ff-d465978806b9) — Anaplan Support.

## Allowed patterns

Every spec server host must end in `.anaplan.com` or be `anaplan.com` itself,
**except** the documented exceptions below.

## Documented exceptions

| Host suffix | API | Why |
|---|---|---|
| `fluence.app` | `financial-consolidation` | Financial Consolidation runs on the Fluence platform (Anaplan acquisition); it was never migrated to an `anaplan.com` host. |

## Last verified

2026-09-04 — official allowlist sources still use `anaplan.com` domains (plus the existing `fluence.app` exception for Financial Consolidation). The Support region picker now shows additional app-plane region codes (`us6a`, `us8a`, `ca2a`, `ap2a`) and uses `a` suffixes (`us1a`, `eu1a`, `au1a`, etc.). Current API/Auth spec hosts remain unchanged (`api.anaplan.com` and `auth.anaplan.com` regional sets).
