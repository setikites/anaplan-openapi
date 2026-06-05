"""Shared assertion helpers for live API tests."""

import json
import pathlib
import warnings

import yaml


def assert_response_code(response, expected_codes, discrepancies):
    """Record a discrepancy if the response code is not among expected_codes."""
    if response.status_code not in expected_codes:
        discrepancies.append(
            f"Got {response.status_code}, expected one of {expected_codes}"
        )


def assert_enum_value(body, field, expected, discrepancies, label):
    """Assert body[field] matches the expected enum value from the spec."""
    actual = body.get(field)
    if actual != expected:
        discrepancies.append(f"{label}: expected {expected!r}, got {actual!r}")


def assert_spec_conformant(response, spec_path, endpoint, method):
    """Check that a response conforms to its spec definition.

    Loads the spec at spec_path, finds the operation for endpoint/method, then checks:
      - response status code is declared in the spec
      - content-type matches a spec-declared media type (when the spec declares content)
      - required body fields are present (for application/json responses)

    Returns a list of discrepancy strings; warns via UserWarning if any are found.
    """
    spec_file = pathlib.Path(spec_path)
    with open(spec_file, encoding="utf-8") as f:
        spec = json.load(f) if spec_file.suffix == ".json" else yaml.safe_load(f)

    operation = spec.get("paths", {}).get(endpoint, {}).get(method.lower(), {})
    responses = operation.get("responses", {})

    status_code = str(response.status_code)
    discrepancies = []

    if responses and status_code not in responses and "default" not in responses:
        discrepancies.append(
            f"{method.upper()} {endpoint}: status {status_code} not in spec "
            f"responses {list(responses.keys())}"
        )

    spec_response = responses.get(status_code) or responses.get("default", {})
    content = spec_response.get("content", {}) if spec_response else {}

    if content:
        actual_ct = response.headers.get("content-type", "")
        if not any(mime.split(";")[0].strip() in actual_ct for mime in content):
            discrepancies.append(
                f"{method.upper()} {endpoint} {status_code}: "
                f"content-type {actual_ct!r} not in spec types {list(content.keys())}"
            )

        try:
            body = response.json()
            for mime, media_obj in content.items():
                if "application/json" in mime:
                    required = (media_obj.get("schema") or {}).get("required", [])
                    for field in required:
                        if field not in body:
                            discrepancies.append(
                                f"{method.upper()} {endpoint} {status_code}: "
                                f"required field '{field}' missing from response body"
                            )
                    break
        except Exception:
            pass

    if discrepancies:
        warnings.warn(
            "Spec conformance discrepancies:\n"
            + "\n".join(f"  - {d}" for d in discrepancies),
            UserWarning,
            stacklevel=2,
        )

    return discrepancies
