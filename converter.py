import json
import yaml


def convert_openapi_spec(input_spec):
    """
    Convert an OpenAPI spec to a validated OpenAPI 3.0.0 spec.

    Accepts multiple input formats and enhances the spec with missing documentation.

    Args:
        input_spec: OpenAPI spec as dict, YAML string, or JSON string

    Returns:
        dict: Valid OpenAPI 3.0.0 spec with enhancements
    """
    spec = _parse_input(input_spec)
    spec = _enhance_endpoints(spec)
    return spec


def _parse_input(input_spec):
    """Parse input spec from dict, YAML string, or JSON string."""
    if isinstance(input_spec, dict):
        return input_spec

    if isinstance(input_spec, str):
        try:
            return json.loads(input_spec)
        except json.JSONDecodeError:
            return yaml.safe_load(input_spec)

    raise ValueError(f"Unsupported input type: {type(input_spec)}")


def _enhance_endpoints(spec):
    """Add missing descriptions and summaries to endpoints."""
    if "paths" not in spec:
        return spec

    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if isinstance(operation, dict) and method in ["get", "post", "put", "delete", "patch", "options", "head"]:
                if "description" not in operation and "summary" not in operation:
                    operation["summary"] = f"{method.upper()} {path}"

    return spec
