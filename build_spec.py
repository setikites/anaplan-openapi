"""Generic spec-build CLI for Anaplan OpenAPI specifications.

Usage:
    uv run build_spec.py <api-name> --source apiary --identifier <id>
    uv run build_spec.py <api-name> --source postman --file <path>
"""

import argparse
import json
from pathlib import Path

import yaml
from openapi_spec_validator import validate

from converter import apiary_to_openapi_skeleton, convert_openapi_spec, fetch_apiary
from sync_yaml import sync_yaml

_REPO_ROOT = Path(__file__).parent

# Servers arrays sourced from existing validated specs (authentication, oauth)
# and CONTEXT.md regional URL table for the api.anaplan.com family.
_SERVERS_AUTH = [
    {"url": "https://auth.anaplan.com", "description": "US1, US2, US5, US7, EU1, EU2, EU4, AP1"},
    {"url": "https://us9.auth.anaplan.com", "description": "US9"},
    {"url": "https://eu3.auth.anaplan.com", "description": "EU3"},
    {"url": "https://eu5.auth.anaplan.com", "description": "EU5"},
    {"url": "https://gb1.auth.anaplan.com", "description": "GB1"},
    {"url": "https://ca1a.auth.anaplan.com", "description": "CA1"},
    {"url": "https://sg1.auth.anaplan.com", "description": "SG1"},
    {"url": "https://ae1.auth.anaplan.com", "description": "AE1"},
    {"url": "https://in1.auth.anaplan.com", "description": "IN1"},
    {"url": "https://id1.auth.anaplan.com", "description": "ID1"},
    {"url": "https://me1.auth.anaplan.com", "description": "ME1"},
    {"url": "https://au1a.app2.anaplan.com", "description": "AU1"},
]

_SERVERS_APP = [
    {"url": "https://us1a.app.anaplan.com", "description": "US1, US2, US5, US7, AP1, EU1, EU2, EU4"},
    {"url": "https://us9.app.anaplan.com", "description": "US9"},
    {"url": "https://eu3.app.anaplan.com", "description": "EU3"},
    {"url": "https://eu5.app.anaplan.com", "description": "EU5"},
    {"url": "https://gb1.app.anaplan.com", "description": "GB1"},
    {"url": "https://ca1a.app.anaplan.com", "description": "CA1"},
    {"url": "https://sg1.app.anaplan.com", "description": "SG1"},
    {"url": "https://ae1.app.anaplan.com", "description": "AE1"},
    {"url": "https://me1.app.anaplan.com", "description": "ME1"},
    {"url": "https://in1.app.anaplan.com", "description": "IN1"},
    {"url": "https://id1.app.anaplan.com", "description": "ID1"},
    {"url": "https://au1a.app2.anaplan.com", "description": "AU1"},
]

_SERVERS_API = [
    {"url": "https://api.anaplan.com", "description": "US1, US2, US5, US7, EU1, EU2, EU4, AP1"},
    {"url": "https://us9.api.anaplan.com", "description": "US9"},
    {"url": "https://eu3.api.anaplan.com", "description": "EU3"},
    {"url": "https://eu5.api.anaplan.com", "description": "EU5"},
    {"url": "https://gb1.api.anaplan.com", "description": "GB1"},
    {"url": "https://ca1a.api.anaplan.com", "description": "CA1"},
    {"url": "https://sg1.api.anaplan.com", "description": "SG1"},
    {"url": "https://ae1.api.anaplan.com", "description": "AE1"},
    {"url": "https://in1.api.anaplan.com", "description": "IN1"},
    {"url": "https://id1.api.anaplan.com", "description": "ID1"},
    {"url": "https://me1.api.anaplan.com", "description": "ME1"},
    {"url": "https://au1a.api2.anaplan.com", "description": "AU1"},
]

_API_FAMILY: dict[str, list[dict]] = {
    "authentication": _SERVERS_AUTH,
    "oauth": _SERVERS_APP,
    "integration": _SERVERS_API,
    "cloudworks": _SERVERS_API,
    "scim": _SERVERS_API,
    "alm": _SERVERS_API,
    "audit": _SERVERS_API,
    "financial-consolidation": _SERVERS_API,
    "exception": _SERVERS_API,
}


def servers_for_api(api_name: str) -> list[dict]:
    """Return the servers[] list for the given API name."""
    if api_name not in _API_FAMILY:
        known = ", ".join(sorted(_API_FAMILY))
        raise ValueError(f"Unknown API {api_name!r}. Known APIs: {known}")
    return _API_FAMILY[api_name]


def build_spec_from_postman(
    api_name: str,
    file: Path,
    *,
    repo_root: Path = _REPO_ROOT,
) -> Path:
    """Load a Postman-derived YAML, convert, validate, and write JSON + YAML."""
    with file.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    spec = convert_openapi_spec(raw)
    spec["servers"] = servers_for_api(api_name)

    validate(spec)

    out_dir = repo_root / api_name
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{api_name}-openapi.json"

    with json_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(spec, f, indent=2)

    sync_yaml(json_path)
    return json_path


def build_spec_from_apiary(
    api_name: str,
    identifier: str,
    *,
    repo_root: Path = _REPO_ROOT,
) -> Path:
    """Fetch Apiary docs, build an OpenAPI skeleton, convert, validate, and write."""
    apiary_json = fetch_apiary(identifier)
    skeleton = apiary_to_openapi_skeleton(apiary_json, servers=servers_for_api(api_name))
    spec = convert_openapi_spec(skeleton)

    validate(spec)

    out_dir = repo_root / api_name
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{api_name}-openapi.json"

    with json_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(spec, f, indent=2)

    sync_yaml(json_path)
    return json_path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an Anaplan OpenAPI spec from available source material.",
    )
    parser.add_argument("api_name", metavar="api-name", help="API directory name (e.g. integration)")
    sub = parser.add_subparsers(dest="source", required=True)

    ap = sub.add_parser("apiary", help="Fetch from Apiary")
    ap.add_argument("--identifier", required=True, help="Apiary API identifier")

    pm = sub.add_parser("postman", help="Load from a Postman-derived YAML file")
    pm.add_argument("--file", required=True, type=Path, help="Path to postman-spec.yaml")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    if args.source == "apiary":
        path = build_spec_from_apiary(args.api_name, args.identifier)
    else:
        path = build_spec_from_postman(args.api_name, args.file)

    yaml_path = path.with_suffix(".yaml")
    print(f"Written: {path}")
    print(f"Written: {yaml_path}")


if __name__ == "__main__":
    main()
