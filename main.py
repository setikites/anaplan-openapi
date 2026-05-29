import json
import pathlib
import yaml
from converter import convert_openapi_spec


def main():
    """Convert Postman specs to OpenAPI JSON files."""
    # Convert authentication API
    auth_postman = pathlib.Path("authentication/postman-spec.yaml")
    with open(auth_postman, encoding="utf-8") as f:
        auth_spec = yaml.safe_load(f)

    auth_openapi = convert_openapi_spec(auth_spec)

    # Write authentication-openapi.json
    output_file = pathlib.Path("authentication/authentication-openapi.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(auth_openapi, f, indent=2)

    print(f"Generated {output_file}")


if __name__ == "__main__":
    main()
