"""Regenerate an OpenAPI YAML spec from its canonical JSON source.

Usage:
    uv run sync_yaml.py <path/to/spec.json>

Writes the corresponding .yaml file in the same directory.
"""

import json
import sys
from pathlib import Path

import yaml


def _literal_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    if "\n" in data:
        normalized = "\n".join(line.rstrip() for line in data.split("\n"))
        return dumper.represent_scalar("tag:yaml.org,2002:str", normalized, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class _LiteralDumper(yaml.Dumper):
    pass


_LiteralDumper.add_representer(str, _literal_representer)


def sync_yaml(json_path: Path) -> Path:
    yaml_path = json_path.with_suffix(".yaml")

    with json_path.open(encoding="utf-8") as f:
        spec = json.load(f)

    with yaml_path.open("w", encoding="utf-8", newline="\n") as f:
        yaml.dump(
            spec,
            f,
            Dumper=_LiteralDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=120,
        )

    return yaml_path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: uv run {Path(sys.argv[0]).name} <path/to/spec.json>")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"Error: {json_path} not found", file=sys.stderr)
        sys.exit(1)
    if json_path.suffix != ".json":
        print(f"Error: expected a .json file, got {json_path.suffix}", file=sys.stderr)
        sys.exit(1)

    yaml_path = sync_yaml(json_path)
    print(f"Written: {yaml_path}")
