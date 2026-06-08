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
    spec = _promote_response_descriptions(spec)
    spec = _enhance_endpoints(spec)
    spec = _extract_reused_schemas(spec)
    spec = clean_descriptions(spec)
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
    """Add missing descriptions, summaries, and placeholder responses to endpoints."""
    if "paths" not in spec:
        return spec

    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if isinstance(operation, dict) and method in ["get", "post", "put", "delete", "patch", "options", "head"]:
                if "description" not in operation and "summary" not in operation:
                    operation["summary"] = f"{method.upper()} {path}"
                if not operation.get("responses"):
                    operation["responses"] = {"200": {"description": "TODO: document response"}}

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


# ─── Response detail extraction ──────────────────────────────────────────────

import re as _re

_RESP_BODY_HEADING_RE = _re.compile(r"###\s+Response\s+(\d{3})\b", _re.IGNORECASE)
_RESP_HEADERS_HEADING_RE = _re.compile(r"###\s+Response\s+headers\b", _re.IGNORECASE)
_FENCED_BLOCK_RE = _re.compile(r"```[^\n]*\n(.*?)```", _re.DOTALL)
_BACKTICK_HEADER_RE = _re.compile(r"`([A-Za-z][^:`\n]*):\s*([^`\n]+)`")
_PROSE_HTTP_CODE_RE = _re.compile(r"`([2-5]\d{2})`")


def extract_op_response_details(operation: dict) -> dict:
    """Parse ### Response N sections from description; promote to responses, strip from description."""
    description = operation.get("description", "")
    if not description:
        return operation

    responses = {k: dict(v) if isinstance(v, dict) else v for k, v in operation.get("responses", {}).items()}
    kept = []

    for section in _re.split(r"(?=###\s)", description):
        body_m = _RESP_BODY_HEADING_RE.match(section)
        if body_m:
            code = body_m.group(1)
            fence_m = _FENCED_BLOCK_RE.search(section)
            if fence_m:
                raw = fence_m.group(1).strip().replace("\xa0", " ").replace("\\_", " ")
                try:
                    example = json.loads(raw)
                    resp = responses.setdefault(code, {"description": f"Response {code}"})
                    resp.setdefault("content", {}).setdefault("application/json", {}).setdefault("example", example)
                except json.JSONDecodeError:
                    kept.append(section)
                    continue
            continue  # remove section whether or not we extracted a body

        if _RESP_HEADERS_HEADING_RE.match(section):
            resp = responses.setdefault("200", {"description": "Response 200"})
            hdrs = resp.setdefault("headers", {})
            for hm in _BACKTICK_HEADER_RE.finditer(section):
                name, value = hm.group(1).strip(), hm.group(2).strip()
                hdrs.setdefault(name, {"schema": {"type": "string"}, "example": value})
            continue  # remove section

        kept.append(section)

    remaining = "".join(kept)
    for cm in _PROSE_HTTP_CODE_RE.finditer(remaining):
        code = cm.group(1)
        if code not in responses:
            responses[code] = {"description": "more detail in path description"}

    new_op = dict(operation)
    new_description = remaining.strip()
    if new_description:
        new_op["description"] = new_description
    elif "description" in new_op:
        del new_op["description"]
    if responses:
        new_op["responses"] = responses
    return new_op


def _promote_response_descriptions(spec: dict) -> dict:
    """Walk all operations and promote ### Response sections into the responses object."""
    _methods = {"get", "post", "put", "delete", "patch", "options", "head"}
    for path_item in spec.get("paths", {}).values():
        for method, operation in path_item.items():
            if isinstance(operation, dict) and method in _methods:
                path_item[method] = extract_op_response_details(operation)
    return spec


# ─── Description cleaning ────────────────────────────────────────────────────

_BARE_JSON_LINE = _re.compile(r"^\s*[{\[]")


def _fence_bare_json(text: str) -> str:
    """Wrap bare JSON lines outside fenced blocks in ```json fences. Idempotent."""
    lines = text.splitlines()
    result = []
    in_fence = False
    for line in lines:
        if line.startswith("```"):
            in_fence = not in_fence
            result.append(line)
        elif not in_fence and _BARE_JSON_LINE.match(line):
            result.append("```json")
            result.append(line)
            result.append("```")
        else:
            result.append(line)
    return "\n".join(result)


def clean_descriptions(spec: dict) -> dict:
    """Clean all 'description' strings: strip NBSP and fence bare JSON. Idempotent."""
    def _clean(text: str) -> str:
        text = text.replace("\xa0", " ")
        text = _fence_bare_json(text)
        return text

    def _walk(obj):
        if isinstance(obj, dict):
            return {
                k: _clean(v) if k == "description" and isinstance(v, str) else _walk(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_walk(item) for item in obj]
        return obj

    return _walk(spec)

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
    Build an OpenAPI 3.0.0 skeleton from Apiary JSON (jsapi.apiary.io format).

    Extracts paths, HTTP methods, summaries, and response status codes from
    the resourceGroups → resources → actions → examples hierarchy. Response
    schemas are left as TODO placeholders — refine manually or via live testing.
    Pipe the result through convert_openapi_spec() for standard enhancements.
    """
    title = str(apiary_json.get("name", "")) or "Untitled API"
    paths = _extract_apiary_paths(apiary_json)
    return {
        "openapi": "3.0.0",
        "info": {"title": title, "version": version},
        "servers": servers or [],
        "paths": paths,
    }


def _extract_apiary_paths(apiary_json: dict) -> dict:
    """
    Walk resourceGroups → resources → actions → examples to build OpenAPI paths.

    Only the first action per (uri, method) pair is kept — Apiary sometimes
    lists the same action multiple times with different example bodies.
    """
    paths: dict = {}

    for group in apiary_json.get("resourceGroups", []):
        for resource in group.get("resources", []):
            uri = resource.get("uriTemplate", "/")
            for action in resource.get("actions", []):
                method = action.get("method", "GET").lower()
                if uri not in paths:
                    paths[uri] = {}
                if method in paths[uri]:
                    continue  # first action wins

                responses: dict = {}
                for example in action.get("examples", []):
                    for resp in example.get("responses", []):
                        code = str(resp.get("status", "200"))
                        if code not in responses:
                            desc = resp.get("description") or "TODO: document response"
                            responses[code] = {"description": desc}

                if not responses:
                    responses["200"] = {"description": "TODO: document response"}

                operation: dict = {"responses": responses}
                if action.get("name"):
                    operation["summary"] = action["name"]
                if action.get("description"):
                    operation["description"] = action["description"]

                paths[uri][method] = operation

    return paths


# ─── Version prefix hoisting ─────────────────────────────────────────────────

_VERSION_SEGMENT = _re.compile(r"^v?\d+$")


def _is_version_segment(segment: str) -> bool:
    return bool(_VERSION_SEGMENT.match(segment))


def hoist_version_prefix(spec: dict) -> dict:
    """Move a version prefix common to all paths into every server URL.

    If every path begins with the same leading sequence of version-like
    segments (e.g. /2/0 or /v1), strip that prefix from each path and
    append it to each server URL. Returns the spec unchanged when no
    qualifying common prefix exists.
    """
    paths = list(spec.get("paths", {}).keys())
    if not paths:
        return spec

    # Split each path into non-empty segments.
    segmented = [p.split("/")[1:] for p in paths]  # drop leading empty string

    # Find how many leading segments are common to all paths.
    min_len = min(len(s) for s in segmented)
    common_len = 0
    for i in range(min_len):
        seg = segmented[0][i]
        if all(s[i] == seg for s in segmented) and _is_version_segment(seg):
            common_len += 1
        else:
            break

    if common_len == 0:
        return spec

    prefix = "/" + "/".join(segmented[0][:common_len])

    new_paths = {p[len(prefix):] or "/": item for p, item in spec["paths"].items()}
    new_servers = [
        {**s, "url": s["url"].rstrip("/") + prefix}
        for s in spec.get("servers", [])
    ]

    return {**spec, "paths": new_paths, "servers": new_servers}

