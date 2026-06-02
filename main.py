"""Thin wrapper — use build_spec.py for all spec generation."""

from pathlib import Path
from build_spec import build_spec_from_postman


def main():
    path = build_spec_from_postman(
        "authentication",
        Path("authentication/postman-spec.yaml"),
    )
    print(f"Generated {path}")


if __name__ == "__main__":
    main()
