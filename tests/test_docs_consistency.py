"""Guards against documentation drift for per-API confidence and spec lifecycle.

Single source of truth:
  - Confidence  -> the confidence table in CONTEXT.md
  - Lifecycle   -> derived from the filesystem (an API is hand-maintained iff a
                   tests/test_<api>_live.py file exists)

The README APIs table mirrors the Confidence column for an audience that should
not have to open CONTEXT.md; this test keeps that intentional copy in sync, and
checks that the CONTEXT lifecycle column matches the live-test files on disk.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
CONTEXT = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

# API (keyed by first word, lowercased) -> its live-test file.
# Adding a new API here forces a decision about its live test + lifecycle.
LIVE_TEST = {
    "authentication": "test_auth_integration_live.py",
    "oauth": "test_oauth_integration_live.py",
    "integration": "test_integration_live.py",
    "cloudworks": "test_cloudworks_live.py",
    "scim": "test_scim_live.py",
    "alm": "test_alm_live.py",
    "audit": "test_audit_live.py",
    "financial": "test_financial_consolidation_live.py",
    "exception": "test_exception_live.py",
    "administration": "test_administration_live.py",
}


def _api_key(name: str) -> str:
    """Normalize an API display name to a stable key (e.g. 'OAuth 2.0' -> 'oauth')."""
    return name.strip().split()[0].lower()


def _level(cell: str) -> str:
    """Extract the confidence level, ignoring annotations ('High — live-tested' -> 'High')."""
    m = re.match(r"\s*(High|Medium|Low)", cell)
    return m.group(1) if m else cell.strip()


def _parse_table(markdown: str, *required_headers: str) -> list[dict]:
    """Return the rows (as header->cell dicts) of the first table containing all required headers."""
    lines = markdown.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|") and all(h in line for h in required_headers):
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            rows = []
            for row in lines[i + 2:]:  # +2 skips the |---|---| separator
                if not row.lstrip().startswith("|"):
                    break
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                rows.append(dict(zip(headers, cells)))
            return rows
    raise AssertionError(f"No table found with headers {required_headers}")


_context_rows = _parse_table(CONTEXT, "Confidence", "Spec lifecycle")
_readme_rows = _parse_table(README, "API", "Directory", "Confidence")

CONTEXT_BY_API = {_api_key(r["API"]): r for r in _context_rows}
README_BY_API = {_api_key(r["API"]): r for r in _readme_rows}


def test_both_tables_cover_the_same_apis():
    assert set(CONTEXT_BY_API) == set(LIVE_TEST), "CONTEXT confidence table APIs drifted from LIVE_TEST map"
    assert set(README_BY_API) == set(LIVE_TEST), "README APIs table drifted from LIVE_TEST map"


@pytest.mark.parametrize("api", sorted(LIVE_TEST))
def test_readme_confidence_mirrors_context(api):
    """The README Confidence column must match the canonical CONTEXT table."""
    assert _level(README_BY_API[api]["Confidence"]) == _level(CONTEXT_BY_API[api]["Confidence"])


@pytest.mark.parametrize("api", sorted(LIVE_TEST))
def test_lifecycle_matches_live_test_presence(api):
    """CONTEXT lifecycle says 'hand-maintained' iff a live-test file exists for the API."""
    hand_maintained = "hand-maintained" in CONTEXT_BY_API[api]["Spec lifecycle"].lower()
    live_test_exists = (REPO_ROOT / "tests" / LIVE_TEST[api]).exists()
    assert hand_maintained == live_test_exists
