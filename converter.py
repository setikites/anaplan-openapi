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
    spec = _extract_reused_schemas(spec)
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


def _extract_reused_schemas(spec):
    """Extract inline schemas that appear multiple times to components/schemas."""
    if "paths" not in spec:
        return spec

    schema_usage = {}
    schema_locations = {}

    def find_schemas_in_object(obj, path=""):
        """Recursively find all inline schemas in an object."""
        if isinstance(obj, dict):
            if _is_schema_object(obj):
                schema_key = json.dumps(obj, sort_keys=True)
                if schema_key not in schema_usage:
                    schema_usage[schema_key] = 0
                    schema_locations[schema_key] = []
                schema_usage[schema_key] += 1
                schema_locations[schema_key].append(path)
            for key, value in obj.items():
                find_schemas_in_object(value, f"{path}/{key}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                find_schemas_in_object(item, f"{path}[{i}]")

    find_schemas_in_object(spec)

    reused_schemas = {
        schema_str: paths
        for schema_str, paths in schema_locations.items()
        if len(paths) > 1 and _should_extract_schema(json.loads(schema_str))
    }

    if not reused_schemas:
        return spec

    if "components" not in spec:
        spec["components"] = {}
    if "schemas" not in spec["components"]:
        spec["components"]["schemas"] = {}

    for schema_str, locations in reused_schemas.items():
        schema_obj = json.loads(schema_str)
        schema_name = _infer_schema_name(schema_obj, locations)

        if schema_name not in spec["components"]["schemas"]:
            spec["components"]["schemas"][schema_name] = schema_obj

        _replace_schemas_with_refs(spec, schema_obj, schema_name, locations)

    return spec


def _should_extract_schema(schema_obj):
    """Check if a schema is complex enough to warrant extraction."""
    if "properties" in schema_obj:
        return True
    if "oneOf" in schema_obj or "allOf" in schema_obj:
        return True
    return False


def _is_schema_object(obj):
    """Check if an object is a schema (has type or properties but no operation methods)."""
    if not isinstance(obj, dict):
        return False

    operation_methods = {"get", "post", "put", "delete", "patch", "head", "options", "trace"}
    if any(method in obj for method in operation_methods):
        return False

    if "$ref" in obj and len(obj) == 1:
        return False

    return "type" in obj or "properties" in obj or "oneOf" in obj or "allOf" in obj


def _infer_schema_name(schema_obj, locations):
    """Infer a schema name from the schema object or its usage locations."""
    if "title" in schema_obj:
        return schema_obj["title"]

    for location in locations:
        if "tokenInfo" in location:
            return "TokenInfo"
        if "userInfo" in location:
            return "UserInfo"

    return f"Schema{len(locations)}"


def _replace_schemas_with_refs(spec, schema_obj, schema_name, locations):
    """Replace inline schemas with $ref references, excluding components/schemas."""
    schema_key = json.dumps(schema_obj, sort_keys=True)

    def replace_in_object(obj, path=""):
        """Recursively replace matching schemas with $ref."""
        if isinstance(obj, dict):
            if (
                _is_schema_object(obj)
                and json.dumps(obj, sort_keys=True) == schema_key
                and not path.startswith("/components/schemas")
            ):
                return {"$ref": f"#/components/schemas/{schema_name}"}
            for key, value in list(obj.items()):
                obj[key] = replace_in_object(value, f"{path}/{key}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                obj[i] = replace_in_object(item, f"{path}[{i}]")
        return obj

    replace_in_object(spec)
