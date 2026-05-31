import json
import pathlib
import sys
from openapi_spec_validator import validate
from openapi_spec_validator.exceptions import OpenAPISpecValidatorError


def main():
    """Validate OpenAPI specs. Usage: validate.py [path] or validate.py (for all specs)."""
    if len(sys.argv) > 1:
        spec_files = [pathlib.Path(arg) for arg in sys.argv[1:]]
    else:
        specs_dir = pathlib.Path(".")
        spec_files = list(specs_dir.glob("*/*-openapi.json"))

    if not spec_files:
        print("No OpenAPI specs found.")
        return 1

    print(f"Validating {len(spec_files)} spec(s)...\n")

    all_valid = True
    for spec_file in sorted(spec_files):
        if not _validate_spec(spec_file):
            all_valid = False

    if all_valid:
        print(f"\nAll {len(spec_files)} spec(s) are valid.")
        return 0
    else:
        print(f"\nSome specs failed validation.")
        return 1


def _validate_spec(spec_file):
    """Validate a single OpenAPI spec file."""
    try:
        with open(spec_file, encoding="utf-8") as f:
            spec = json.load(f)

        validate(spec)
        print(f"[OK] {spec_file}")
        return True

    except json.JSONDecodeError as e:
        print(f"[FAIL] {spec_file}: Invalid JSON - {e}")
        return False

    except OpenAPISpecValidatorError as e:
        print(f"[FAIL] {spec_file}: OpenAPI validation failed")
        print(f"       {e}")
        return False

    except Exception as e:
        print(f"[FAIL] {spec_file}: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    sys.exit(main())
