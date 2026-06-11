"""Tests for build_spec.py — the generic spec-build CLI (issue #11)."""

import json
from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate

from build_spec import build_spec_from_postman, servers_for_api

REPO_ROOT = Path(__file__).parent.parent
AUTH_POSTMAN = REPO_ROOT / "sources" / "postman-spec.yaml"


# ─── servers_for_api ──────────────────────────────────────────────────────────

# ─── build_spec_from_postman ──────────────────────────────────────────────────

def test_build_from_postman_writes_json_to_correct_path(tmp_path):
    json_path = build_spec_from_postman("authentication", AUTH_POSTMAN, repo_root=tmp_path)
    assert json_path == tmp_path / "authentication" / "authentication-openapi.json"
    assert json_path.exists()


def test_build_from_postman_output_is_valid_openapi(tmp_path):
    json_path = build_spec_from_postman("authentication", AUTH_POSTMAN, repo_root=tmp_path)
    spec = json.loads(json_path.read_text(encoding="utf-8"))
    validate(spec)  # raises on failure


def test_build_from_postman_syncs_yaml(tmp_path):
    json_path = build_spec_from_postman("authentication", AUTH_POSTMAN, repo_root=tmp_path)
    yaml_path = json_path.with_suffix(".yaml")
    assert yaml_path.exists()
    parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert parsed["openapi"].startswith("3.0")


def test_build_from_postman_injects_correct_servers(tmp_path):
    json_path = build_spec_from_postman("authentication", AUTH_POSTMAN, repo_root=tmp_path)
    spec = json.loads(json_path.read_text(encoding="utf-8"))
    urls = [s["url"] for s in spec["servers"]]
    assert any("auth.anaplan.com" in u for u in urls)
    assert not any("api.anaplan.com" in u for u in urls)
    assert not any(u.startswith("https://us1a.app.anaplan.com") for u in urls)


def test_servers_for_unknown_api_raises():
    with pytest.raises(ValueError, match="bogus"):
        servers_for_api("bogus")


def test_servers_for_oauth_use_app_domain():
    servers = servers_for_api("oauth")
    urls = [s["url"] for s in servers]
    assert any("app.anaplan.com" in u for u in urls)
    assert not any("auth.anaplan.com" in u for u in urls)
    assert not any("api.anaplan.com" in u for u in urls)


@pytest.mark.parametrize("api_name", ["integration", "cloudworks", "scim", "alm", "audit", "financial-consolidation", "exception"])
def test_servers_for_api_family_use_api_domain(api_name):
    servers = servers_for_api(api_name)
    urls = [s["url"] for s in servers]
    assert any("api.anaplan.com" in u for u in urls)
    assert not any("auth.anaplan.com" in u for u in urls)
    assert not any("app.anaplan.com" in u for u in urls)


def test_servers_for_authentication_use_auth_domain():
    servers = servers_for_api("authentication")
    assert servers
    urls = [s["url"] for s in servers]
    # Primary domain must appear at least once
    assert any("auth.anaplan.com" in u for u in urls)
    # Must not bleed into the wrong API families
    assert not any("api.anaplan.com" in u for u in urls)
    assert not any(u.startswith("https://us1a.app.anaplan.com") for u in urls)
