"""Import live Anaplan object schemas and wire them into an OpenAPI spec."""

import json
import re
from pathlib import Path

import jsonschema

# JSON Schema draft-04 extras that have no OpenAPI 3.0 equivalent.
_EXTRAS = frozenset(
    {"$schema", "id", "foreignKeys", "bulk", "primaryKey", "name", "order",
     "hidden", "version", "title"}
)

# Regex to extract object name from any Anaplan objects URL.
# Handles: /2/0/objects/{name}, /2/0/models/{id}/objects/{name}, double-slashes, fragments.
_OBJECT_NAME_RE = re.compile(r"/objects/([^/#?\s]+)")


def _to_pascal(name: str) -> str:
    return name[0].upper() + name[1:] if name else name


def _remap_property(prop: dict) -> dict:
    """Convert a single property dict from JSON Schema draft-04 to OpenAPI 3.0."""
    prop = dict(prop)
    t = prop.get("type")
    if isinstance(t, dict):
        # draft-04 allows type to be a schema object e.g. {"enum": [...]}
        prop.pop("type")
        prop.update(t)
    elif t == "set":
        prop["type"] = "array"
    elif t == "date-time":
        prop["type"] = "string"
        prop["format"] = "date-time"
    if "$ref" in prop:
        prop["$ref"] = _convert_ref(prop["$ref"])
    if "properties" in prop:
        prop["properties"] = {k: _remap_property(v) for k, v in prop["properties"].items()}
    if "items" in prop and isinstance(prop["items"], dict):
        prop["items"] = _remap_property(prop["items"])
    return prop


def _convert_ref(url: str) -> str:
    """Convert an absolute Anaplan objects URL to an internal #/components/schemas/ ref."""
    m = _OBJECT_NAME_RE.search(url)
    if m:
        return f"#/components/schemas/{_to_pascal(m.group(1))}"
    return url


def _clean_schema(raw: dict) -> dict:
    """Strip draft-04 extras and remap types/refs in a single schema object."""
    result = {}
    for k, v in raw.items():
        if k in _EXTRAS:
            continue
        if k == "properties" and isinstance(v, dict):
            result[k] = {pk: _remap_property(pv) for pk, pv in v.items()}
        elif k == "$ref":
            result[k] = _convert_ref(v)
        else:
            result[k] = v
    return result


def _name_from_object_schema(entry: dict) -> str | None:
    """Extract PascalCase name from an objectSchema.json entry (uses 'title')."""
    title = entry.get("title", "")
    return _to_pascal(title) if title else None


def _name_from_model_schema(entry: dict) -> str | None:
    """Extract PascalCase name from a modelObjectschema.json entry (uses 'id' URL)."""
    url = entry.get("id", "")
    m = _OBJECT_NAME_RE.search(url)
    return _to_pascal(m.group(1)) if m else None


def load_object_schemas(
    object_schema_path: Path,
    model_schema_path: Path,
) -> dict[str, dict]:
    """Merge both source files into an OpenAPI 3.0 components/schemas dict.

    modelObjectschema.json wins on overlap. Names are PascalCase.
    """
    obj_entries: list[dict] = json.loads(object_schema_path.read_text(encoding="utf-8"))
    mod_entries: list[dict] = json.loads(model_schema_path.read_text(encoding="utf-8"))

    schemas: dict[str, dict] = {}

    for entry in obj_entries:
        name = _name_from_object_schema(entry)
        if name:
            schemas[name] = _clean_schema(entry)

    for entry in mod_entries:
        name = _name_from_model_schema(entry)
        if name:
            schemas[name] = _clean_schema(entry)

    return schemas


# ─── Response schema wiring ───────────────────────────────────────────────────

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})


def _schema_name_from_url(url: str) -> str | None:
    """Extract PascalCase schema name from a meta.schema URL."""
    m = _OBJECT_NAME_RE.search(url)
    return _to_pascal(m.group(1)) if m else None


def wire_response_schema_refs(spec: dict) -> dict:
    """For responses with example.meta.schema URL, add a schema object with $ref.

    Idempotent. Preserves examples unchanged.
    """
    component_schemas: dict = spec.get("components", {}).get("schemas", {})

    for path_item in spec.get("paths", {}).values():
        for method, operation in path_item.items():
            if not isinstance(operation, dict) or method not in _HTTP_METHODS:
                continue
            for response in operation.get("responses", {}).values():
                if not isinstance(response, dict):
                    continue
                media = response.get("content", {}).get("application/json", {})
                if "schema" in media:
                    continue  # already wired — idempotent
                example = media.get("example")
                if not isinstance(example, dict):
                    continue
                meta = example.get("meta")
                if not isinstance(meta, dict):
                    continue
                schema_url = meta.get("schema", "")
                if not schema_url:
                    continue

                name = _schema_name_from_url(schema_url)
                if not name or name not in component_schemas:
                    continue

                item_keys = [k for k in example if k not in ("meta", "status")]
                if not item_keys:
                    continue

                properties: dict = {
                    "meta":   {"type": "object"},
                    "status": {"type": "object"},
                }
                for key in item_keys:
                    value = example[key]
                    if isinstance(value, list):
                        properties[key] = {
                            "type": "array",
                            "items": {"$ref": f"#/components/schemas/{name}"},
                        }
                    else:
                        properties[key] = {"$ref": f"#/components/schemas/{name}"}

                media["schema"] = {"type": "object", "properties": properties}

    return spec


# ─── Example validation ───────────────────────────────────────────────────────

def validate_response_examples(spec: dict) -> list[str]:
    """Validate each response example that has a sibling schema.

    Resolves $ref against components/schemas. Returns warning strings for mismatches.
    """
    warnings: list[str] = []
    resolver = jsonschema.RefResolver("", spec)

    for path_str, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict) or method not in _HTTP_METHODS:
                continue
            for code, response in operation.get("responses", {}).items():
                if not isinstance(response, dict):
                    continue
                media = response.get("content", {}).get("application/json", {})
                schema = media.get("schema")
                example = media.get("example")
                if schema is None or example is None:
                    continue
                try:
                    jsonschema.validate(example, schema, resolver=resolver)
                except jsonschema.ValidationError as exc:
                    warnings.append(
                        f"{method.upper()} {path_str} ({code}): {exc.message}"
                    )
                except jsonschema.SchemaError as exc:
                    warnings.append(
                        f"{method.upper()} {path_str} ({code}): schema error — {exc.message}"
                    )

    return warnings
