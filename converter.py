import json
import yaml
import httpx


_APIARY_BASE_URL = "https://jsapi.apiary.io/apis"


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


# ─── Apiary fetch and skeleton builder ───────────────────────────────────────


def fetch_apiary(api_identifier: str, timeout: float = 30.0) -> dict:
    """
    Fetch API documentation from Apiary's JSON endpoint.

    Returns the raw Drafter Refract JSON. Pass to apiary_to_openapi_skeleton()
    to produce an OpenAPI skeleton ready for refinement.

    See CONTEXT.md §"Accessing Apiary documentation" for known Anaplan identifiers.
    """
    url = f"{_APIARY_BASE_URL}/{api_identifier}.json"
    response = httpx.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def apiary_to_openapi_skeleton(
    apiary_json: dict,
    *,
    servers: list[dict] | None = None,
    version: str = "1.0.0",
) -> dict:
    """
    Build an OpenAPI 3.0.0 skeleton from Apiary Refract JSON.

    Extracts paths, HTTP methods, summaries, and response status codes.
    Response schemas are left as TODO placeholders — refine manually or via
    live testing. Pipe the result through convert_openapi_spec() for standard
    enhancements (summary injection, schema extraction).
    """
    title = _refract_api_title(apiary_json)
    paths = _refract_extract_paths(apiary_json)
    return {
        "openapi": "3.0.0",
        "info": {"title": title or "Untitled API", "version": version},
        "servers": servers or [],
        "paths": paths,
    }


def _refract_string_value(element) -> str:
    """Extract a plain string from a Refract element or bare value."""
    if element is None:
        return ""
    if isinstance(element, str):
        return element
    if isinstance(element, dict):
        content = element.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list) and content:
            return _refract_string_value(content[0])
    return ""


def _refract_walk(node, element_type: str):
    """Recursively yield all Refract elements with the given element name."""
    if isinstance(node, dict):
        if node.get("element") == element_type:
            yield node
        for child in node.get("content", []) or []:
            yield from _refract_walk(child, element_type)
    elif isinstance(node, list):
        for item in node:
            yield from _refract_walk(item, element_type)


def _refract_api_title(apiary_json: dict) -> str:
    """Return the API title from a Refract document."""
    if "name" in apiary_json:
        return str(apiary_json["name"])
    for category in _refract_walk(apiary_json, "category"):
        title = _refract_string_value(category.get("meta", {}).get("title"))
        if title:
            return title
    return ""


def _refract_extract_paths(apiary_json: dict) -> dict:
    """
    Extract OpenAPI-style paths from a Refract document.

    Each resource → path; each transition → operation. Only the first
    httpTransaction per (path, method) pair is used — duplicates in Apiary
    typically represent request/response examples, not distinct operations.
    """
    paths: dict = {}

    for resource in _refract_walk(apiary_json, "resource"):
        href = _refract_string_value(
            resource.get("attributes", {}).get("href")
        ) or "/"

        for transition in _refract_walk(resource, "transition"):
            meta = transition.get("meta", {})
            summary = _refract_string_value(meta.get("title"))
            description = _refract_string_value(meta.get("description"))

            for transaction in _refract_walk(transition, "httpTransaction"):
                content = transaction.get("content") or []

                request = next(
                    (c for c in content if isinstance(c, dict) and c.get("element") == "httpRequest"),
                    None,
                )
                if request is None:
                    continue

                method = _refract_string_value(
                    request.get("attributes", {}).get("method")
                ).lower() or "get"

                if href not in paths:
                    paths[href] = {}
                if method in paths[href]:
                    continue  # first transaction wins

                responses_raw = [
                    c for c in content
                    if isinstance(c, dict) and c.get("element") == "httpResponse"
                ]
                responses: dict = {}
                for resp in responses_raw:
                    code = _refract_string_value(
                        resp.get("attributes", {}).get("statusCode")
                    ) or "200"
                    if code not in responses:
                        responses[code] = {"description": "TODO: document response"}

                if not responses:
                    responses["200"] = {"description": "TODO: document response"}

                operation: dict = {"responses": responses}
                if summary:
                    operation["summary"] = summary
                if description:
                    operation["description"] = description

                paths[href][method] = operation

    return paths
