"""Guards for scripts/make_ptc.py.

The load-bearing behaviors are the ones a downstream agent cannot recover from on its own:
a response `$ref` cycle that never terminates, a truncated shape that reads as complete, an
absent response schema that reads as "returns no fields", and a build-time API exclusion
that a config mistake could otherwise walk around.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from make_ptc import EXCLUDED, NO_RESPONSE, TRUNC, main, render_ptc, transform  # noqa: E402

REPO = pathlib.Path(__file__).parent.parent


def _spec():
    """Covers, in one document: a workspace-scoped duplicate path, a synthesized
    operationId, an opaque-ID parameter, a recursive response schema, a $ref'd response
    object, and an operation with no 2xx JSON response at all."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/models/{modelId}/exports": {
                "parameters": [
                    {
                        "name": "modelId",
                        "in": "path",
                        "required": True,
                        "example": "A1B2",
                        "schema": {"type": "string", "pattern": "^[0-9A-F]{32}$", "format": "hex"},
                    }
                ],
                "get": {
                    "summary": "List exports",
                    "description": "Long prose.",
                    "responses": {"204": {"description": "no content"}},
                },
            },
            "/workspaces/{workspaceId}/models/{modelId}/exports": {
                "get": {"operationId": "wsTwin", "responses": {"200": {"description": "dup"}}}
            },
            "/tree": {
                "post": {
                    "operationId": "postTree",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Req"}}
                        },
                    },
                    "responses": {"200": {"$ref": "#/components/responses/Tree"}},
                }
            },
        },
        "components": {
            "schemas": {
                "Req": {"type": "object", "properties": {"name": {"type": "string"}}},
                "Node": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "children": {"type": "array", "items": {"$ref": "#/components/schemas/Node"}},
                    },
                },
            },
            "responses": {
                "Tree": {
                    "description": "ok",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Node"}}},
                }
            },
            "securitySchemes": {"B": {"type": "http", "scheme": "bearer"}},
        },
    }


def test_render_is_deterministic():
    spec = _spec()
    assert render_ptc(spec) == render_ptc(spec)


def test_workspace_scoped_twin_is_dropped():
    out = transform(_spec())
    paths = [e["path"] for e in out["catalog"]]
    assert "/workspaces/{workspaceId}/models/{modelId}/exports" not in paths
    assert "/models/{modelId}/exports" in paths
    assert "wsTwin" not in out["detail"]


def test_operation_id_is_synthesized_when_absent():
    out = transform(_spec())
    assert out["catalog"][0]["op_id"] == "getModelsByModelidExports"


def test_catalog_and_detail_are_in_bijection():
    out = transform(_spec())
    assert {e["op_id"] for e in out["catalog"]} == set(out["detail"])


def test_summary_in_catalog_description_in_detail():
    out = transform(_spec())
    entry = out["catalog"][0]
    assert entry["summary"] == "List exports"
    assert "description" not in entry
    assert out["detail"]["getModelsByModelidExports"]["description"] == "Long prose."


def test_recursive_response_schema_terminates_and_is_marked():
    out = transform(_spec())
    detail = out["detail"]["postTree"]
    assert detail["response_truncated"] is True
    node = detail["response"]["schema"]["properties"]["children"]["items"]
    assert node[TRUNC].startswith("recursive schema")


def test_missing_response_schema_is_marked_not_emptied():
    detail = transform(_spec())["detail"]["getModelsByModelidExports"]
    assert detail["response"] is None
    assert detail["response_note"] == NO_RESPONSE
    assert "response_truncated" not in detail


def test_request_body_fields_reach_the_catalog():
    out = transform(_spec())
    entry = next(e for e in out["catalog"] if e["op_id"] == "postTree")
    assert entry["body_fields"] == ["name"]
    assert out["detail"]["postTree"]["request_body"]["required"] is True


def test_no_refs_or_security_survive():
    text = render_ptc(_spec())
    assert '"$ref"' not in text
    assert "security" not in text
    assert "securitySchemes" not in text


def test_opaque_id_constraints_are_stripped():
    param = transform(_spec())["detail"]["getModelsByModelidExports"]["parameters"][0]
    assert "example" not in param
    assert not {"example", "pattern", "format"} & set(param["schema"])


def test_excluded_apis_produce_no_artifact(tmp_path):
    assert EXCLUDED == {"authentication", "oauth", "financial-consolidation"}
    api_dir = tmp_path / "oauth"
    api_dir.mkdir()
    src = api_dir / "oauth-openapi.json"
    src.write_text(json.dumps(_spec()), encoding="utf-8")
    with pytest.raises(SystemExit):
        main(str(src))
    assert not (api_dir / "oauth-ptc.json").exists()


@pytest.mark.parametrize("api", sorted(EXCLUDED))
def test_no_committed_artifact_for_excluded_apis(api):
    assert not (REPO / api / f"{api}-ptc.json").exists()


def test_committed_artifacts_hold_134_unique_operations():
    files = sorted(REPO.glob("*/*-ptc.json"))
    assert len(files) == 7
    op_ids = [
        e["op_id"]
        for f in files
        for e in json.loads(f.read_text(encoding="utf-8"))["catalog"]
    ]
    assert len(op_ids) == 134
    assert len(set(op_ids)) == 134
