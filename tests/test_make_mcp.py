"""Guards for scripts/make_mcp.py — chiefly that its output is deterministic.

make_mcp once emitted component schemas in `set`-iteration order, so regenerating a
*-mcp.json produced a spurious reordering diff on every run (and defeated the
scripts/check_generated.py drift check). Emission now follows the source spec's order.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from make_mcp import render_mcp, transform  # noqa: E402


def _spec():
    # Schemas declared in source order (Zeta, Alpha, Mid) that differs from ref-discovery
    # order (requestBody -> Alpha, then its props -> Mid, Zeta), so source-order emission
    # is distinguishable from BFS / set-iteration order. transform() strips response bodies,
    # so the reachability seed must come through requestBody.
    return {
        "openapi": "3.0.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/x": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Alpha"}
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
        "components": {
            "schemas": {
                "Zeta": {"type": "string"},
                "Alpha": {
                    "type": "object",
                    "properties": {
                        "m": {"$ref": "#/components/schemas/Mid"},
                        "z": {"$ref": "#/components/schemas/Zeta"},
                    },
                },
                "Mid": {"type": "integer"},
            }
        },
    }


def test_schema_emission_follows_source_order():
    out = transform(_spec())
    # All three are reachable via requestBody (Alpha -> Mid, Zeta); emitted in SOURCE order.
    assert list(out["components"]["schemas"]) == ["Zeta", "Alpha", "Mid"]


def test_render_is_deterministic():
    spec = _spec()
    assert render_mcp(spec) == render_mcp(spec)
