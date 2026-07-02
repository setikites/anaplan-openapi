"""
Tests minimum-role annotation consistency per ADR 0006.
See docs/adr/0006-minimum-role-annotations.md
"""

import json
import re
import pytest
from pathlib import Path
from check_min_role import check_spec_min_roles

REPO_ROOT = Path(__file__).parent.parent
SPEC_FILES = sorted(REPO_ROOT.glob("*/*-openapi.json"))

_ADR = "docs/adr/0006-minimum-role-annotations.md"


def _spec(op: dict) -> dict:
    return {"paths": {"/x": {"post": op}}}


# ─── Un-annotated is legal (migration in progress) ────────────────────────

def test_operation_without_any_role_annotation_passes():
    assert check_spec_min_roles(_spec({"summary": "S", "description": "Do a thing."}), "t") == []


# ─── Well-formed annotation passes ────────────────────────────────────────

def test_matching_extension_and_sentence_passes():
    op = {
        "summary": "S",
        "description": "Minimum role: Workspace Administrator.\n\nSet a model online.",
        "x-anaplan-min-role": "Workspace Administrator",
    }
    assert check_spec_min_roles(_spec(op), "t") == []


# ─── Inconsistency is caught ──────────────────────────────────────────────

def test_extension_without_sentence_fails():
    op = {"description": "Set a model online.", "x-anaplan-min-role": "Workspace Administrator"}
    v = check_spec_min_roles(_spec(op), "t")
    assert v and any("no leading" in x for x in v)


def test_sentence_without_extension_fails():
    op = {"description": "Minimum role: Tenant Auditor.\n\nRead the log."}
    v = check_spec_min_roles(_spec(op), "t")
    assert v and any("no x-anaplan-min-role" in x for x in v)


def test_extension_sentence_mismatch_fails():
    op = {
        "description": "Minimum role: Standard User.\n\nRead.",
        "x-anaplan-min-role": "Tenant Administrator",
    }
    v = check_spec_min_roles(_spec(op), "t")
    assert v and any("disagrees" in x for x in v)


def test_role_outside_vocabulary_fails():
    op = {
        "description": "Minimum role: Superuser.\n\nDo.",
        "x-anaplan-min-role": "Superuser",
    }
    v = check_spec_min_roles(_spec(op), "t")
    assert v and any("not in role vocabulary" in x for x in v)


# ─── needs-info flag ──────────────────────────────────────────────────────

def test_needs_info_with_best_known_role_passes():
    op = {
        "description": "Minimum role: Tenant Administrator.\n\nDo.",
        "x-anaplan-min-role": "Tenant Administrator",
        "x-anaplan-min-role-needs-info": True,
    }
    assert check_spec_min_roles(_spec(op), "t") == []


def test_needs_info_without_role_fails():
    op = {"description": "Do.", "x-anaplan-min-role-needs-info": True}
    v = check_spec_min_roles(_spec(op), "t")
    assert v and any("no best-known" in x for x in v)


def test_needs_info_non_boolean_fails():
    op = {
        "description": "Minimum role: None.\n\nDo.",
        "x-anaplan-min-role": "None",
        "x-anaplan-min-role-needs-info": "yes",
    }
    v = check_spec_min_roles(_spec(op), "t")
    assert v and any("must be boolean true" in x for x in v)


# ─── Integration: every shipped spec is consistent ────────────────────────

@pytest.mark.parametrize("spec_path", SPEC_FILES, ids=lambda p: p.parent.name)
def test_spec_conforms_to_min_role_standard(spec_path):
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    violations = check_spec_min_roles(spec, spec_path.parent.name)
    assert not violations, (
        f"{spec_path.parent.name}: {len(violations)} min-role violation(s):\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ─── ALM is fully annotated (issue #179) ──────────────────────────────────

_HTTP = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def _alm_ops():
    spec = json.loads((REPO_ROOT / "alm" / "alm-openapi.json").read_text(encoding="utf-8"))
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method in _HTTP:
                yield f"{method.upper()} {path}", op


def test_every_alm_operation_has_a_min_role():
    missing = [k for k, op in _alm_ops() if "x-anaplan-min-role" not in op]
    assert not missing, f"ALM operations without a minimum role: {missing}"


def test_alm_has_no_leftover_requires_role_prose():
    leftover = [k for k, op in _alm_ops()
                if re.search(r"Requires .+? role", op.get("description", ""), re.IGNORECASE)]
    assert not leftover, f"ALM operations with ad-hoc 'Requires ... role' prose: {leftover}"


def test_alm_report_endpoints_flagged_needs_info():
    flagged = {k for k, op in _alm_ops() if op.get("x-anaplan-min-role-needs-info") is True}
    expected = {
        "GET /models/{modelId}/alm/comparisonReportTasks/{taskId}",
        "GET /models/{modelId}/alm/comparisonReports/{targetRevisionId}/{sourceRevisionId}",
        "POST /models/{modelId}/alm/summaryReportTasks",
        "GET /models/{modelId}/alm/summaryReportTasks/{taskId}",
        "GET /models/{modelId}/alm/summaryReports/{targetRevisionId}/{sourceRevisionId}",
    }
    assert flagged == expected
