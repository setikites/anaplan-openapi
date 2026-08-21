"""
Tests that every spec's servers are on the Anaplan domain allowlist.
See docs/anaplan-domain-allowlist.md.
"""
import json
from pathlib import Path

import pytest

from check_server_domains import check_server_domains

REPO_ROOT = Path(__file__).parent.parent
SPEC_FILES = sorted(REPO_ROOT.glob("*/*-openapi.json"))


def test_checker_passes_an_anaplan_com_host():
    spec = {"servers": [{"url": "https://api.anaplan.com/2/0"}]}
    assert check_server_domains(spec, "integration") == []


def test_checker_flags_an_unlisted_host():
    spec = {"servers": [{"url": "https://api.anaplan.io/2/0"}]}
    violations = check_server_domains(spec, "integration")
    assert violations
    assert "api.anaplan.io" in violations[0]


def test_checker_allows_the_fluence_exception_only_for_financial_consolidation():
    spec = {"servers": [{"url": "https://fluenceapi-prod.fluence.app/api/v1"}]}
    assert check_server_domains(spec, "financial-consolidation") == []
    assert check_server_domains(spec, "integration") != []


@pytest.mark.parametrize("path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_committed_spec_servers_are_on_the_allowlist(path):
    spec = json.loads(path.read_text(encoding="utf-8"))
    assert check_server_domains(spec, path.parent.name) == []
