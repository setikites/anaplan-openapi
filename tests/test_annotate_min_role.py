"""
Tests the one-shot minimum-role annotator (ADR 0006).
See docs/adr/0006-minimum-role-annotations.md
"""

from annotate_min_role import annotate, _parse_except, _norm
from check_min_role import check_spec_min_roles


def _spec(*ops):
    """Build a spec from (method, path, op) tuples."""
    paths = {}
    for method, path, op in ops:
        paths.setdefault(path, {})[method] = op
    return {"paths": paths}


def test_uniform_default_annotates_every_op_and_passes_lint():
    spec = _spec(
        ("get", "/a", {"summary": "A", "description": "Do A.", "operationId": "a"}),
        ("post", "/b", {"summary": "B", "description": "Do B.", "operationId": "b"}),
    )
    changed, notes = annotate(spec, "Workspace Administrator", {}, set())
    assert changed == 2 and notes == []
    for m, p in (("get", "/a"), ("post", "/b")):
        op = spec["paths"][p][m]
        assert op["x-anaplan-min-role"] == "Workspace Administrator"
        assert op["description"].startswith("Minimum role: Workspace Administrator.\n\n")
    assert check_spec_min_roles(spec, "t") == []


def test_extension_lands_immediately_after_operationId():
    spec = _spec(("get", "/a", {"summary": "A", "description": "Do A.", "operationId": "a"}))
    annotate(spec, "Tenant Auditor", {}, set())
    keys = list(spec["paths"]["/a"]["get"])
    assert keys[keys.index("operationId") + 1] == "x-anaplan-min-role"


def test_exception_overrides_default():
    spec = _spec(
        ("get", "/a", {"description": "Do A.", "operationId": "a"}),
        ("get", "/pub", {"description": "Public.", "operationId": "pub"}),
    )
    annotate(spec, "Tenant Administrator", {"GET /pub": "Standard User"}, set())
    assert spec["paths"]["/pub"]["get"]["x-anaplan-min-role"] == "Standard User"
    assert spec["paths"]["/a"]["get"]["x-anaplan-min-role"] == "Tenant Administrator"


def test_needs_info_flag_set():
    spec = _spec(("get", "/a", {"description": "Do A.", "operationId": "a"}))
    annotate(spec, "Workspace Administrator", {}, {"GET /a"})
    assert spec["paths"]["/a"]["get"]["x-anaplan-min-role-needs-info"] is True
    assert check_spec_min_roles(spec, "t") == []


def test_redundant_requires_prose_is_stripped():
    spec = _spec(("post", "/a", {
        "description": "Set online. Requires Workspace Administrator role. Returns 400 on error.",
        "operationId": "a",
    }))
    annotate(spec, "Workspace Administrator", {}, set())
    desc = spec["paths"]["/a"]["post"]["description"]
    assert "Requires Workspace Administrator role" not in desc
    assert desc.startswith("Minimum role: Workspace Administrator.\n\n")
    assert "Returns 400 on error." in desc


def test_requires_prose_with_trailing_qualifier_stripped_cleanly():
    # "Requires X role on both models." must be removed whole — no orphan fragment.
    spec = _spec(("get", "/a", {
        "description": "Returns revisions, ordered by date. Requires Workspace Administrator role on both models.",
        "operationId": "a",
    }))
    annotate(spec, "Workspace Administrator", {}, set())
    desc = spec["paths"]["/a"]["get"]["description"]
    assert "on both models" not in desc
    assert "Requires" not in desc
    assert desc == "Minimum role: Workspace Administrator.\n\nReturns revisions, ordered by date."


def test_idempotent_rerun_does_not_stack():
    spec = _spec(("get", "/a", {"description": "Do A.", "operationId": "a"}))
    annotate(spec, "Workspace Administrator", {}, set())
    first = spec["paths"]["/a"]["get"]["description"]
    annotate(spec, "Workspace Administrator", {}, set())
    assert spec["paths"]["/a"]["get"]["description"] == first
    assert first.count("Minimum role:") == 1


def test_rerun_with_new_role_replaces():
    spec = _spec(("get", "/a", {"description": "Do A.", "operationId": "a"}))
    annotate(spec, "Standard User", {}, set())
    annotate(spec, "Tenant Auditor", {}, set(), force=True)
    op = spec["paths"]["/a"]["get"]
    assert op["x-anaplan-min-role"] == "Tenant Auditor"
    assert op["description"].count("Minimum role:") == 1
    assert "Standard User" not in op["description"]


def test_conflicting_annotation_skipped_without_force():
    spec = _spec(("get", "/a", {
        "description": "Minimum role: Standard User.\n\nDo A.",
        "operationId": "a",
        "x-anaplan-min-role": "Standard User",
    }))
    changed, notes = annotate(spec, "Tenant Administrator", {}, set(), force=False)
    assert changed == 0 and any("left as-is" in n for n in notes)
    assert spec["paths"]["/a"]["get"]["x-anaplan-min-role"] == "Standard User"


def test_force_overwrites_conflict():
    spec = _spec(("get", "/a", {
        "description": "Minimum role: Standard User.\n\nDo A.",
        "operationId": "a",
        "x-anaplan-min-role": "Standard User",
    }))
    changed, _ = annotate(spec, "Tenant Administrator", {}, set(), force=True)
    assert changed == 1
    assert spec["paths"]["/a"]["get"]["x-anaplan-min-role"] == "Tenant Administrator"


def test_needs_info_without_role_is_reported_not_applied():
    spec = _spec(("get", "/a", {"description": "Do A.", "operationId": "a"}))
    changed, notes = annotate(spec, None, {}, {"GET /a"})
    assert changed == 0 and any("no role" in n for n in notes)


def test_unmatched_flag_key_warns():
    spec = _spec(("get", "/a", {"description": "Do A.", "operationId": "a"}))
    _, notes = annotate(spec, "Standard User", {"GET /typo": "Standard User"}, set())
    assert any("matched no operation" in n for n in notes)


def test_parse_except_and_norm():
    assert _parse_except(["Standard User=get /a,POST /b"]) == {
        "GET /a": "Standard User", "POST /b": "Standard User",
    }
    assert _norm("get /x/{id}") == "GET /x/{id}"
