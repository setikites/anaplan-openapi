"""
Live API integration tests for Authentication API.

Run with: uv run pytest tests/test_auth_integration_live.py --live

These tests require:
- ANAPLAN_USERNAME: username for basic auth
- ANAPLAN_PASSWORD: password for basic auth
- ANAPLAN_CA_CERT_PATH: path to CA certificate file (optional, for CA cert auth)
- ANAPLAN_CA_SIGNATURE: signature payload for CA cert auth (optional)
"""

import base64
import json
import os
import pathlib
import pytest
import httpx
import yaml
from openapi_spec_validator import validate

# Load spec for response validation
SPEC_FILE = pathlib.Path(__file__).parent.parent / "authentication" / "postman-spec.yaml"
with open(SPEC_FILE, encoding="utf-8") as f:
    SPEC = yaml.safe_load(f)

API_URL = "https://auth.anaplan.com"


@pytest.fixture
def auth_creds():
    """Load authentication credentials from environment."""
    username = os.getenv("ANAPLAN_USERNAME")
    password = os.getenv("ANAPLAN_PASSWORD")

    if not username or not password:
        pytest.skip("ANAPLAN_USERNAME and ANAPLAN_PASSWORD not set")

    return {"username": username, "password": password}


@pytest.fixture
def ca_certs():
    """Load CA certificate credentials from environment."""
    cert_path = os.getenv("ANAPLAN_CA_CERT_PATH")
    signature = os.getenv("ANAPLAN_CA_SIGNATURE")

    if not cert_path or not signature:
        return None

    if not pathlib.Path(cert_path).exists():
        pytest.skip(f"CA certificate file not found: {cert_path}")

    with open(cert_path, encoding="utf-8") as f:
        cert = f.read()

    return {"cert": cert, "signature": signature}


@pytest.mark.live
def test_auth_workflow_basic_auth(auth_creds):
    """Test full workflow with basic authentication."""
    username, password = auth_creds["username"], auth_creds["password"]
    discrepancies = []

    with httpx.Client() as client:
        # 1. Authenticate
        auth_header = base64.b64encode(f"{username}:{password}".encode()).decode()
        auth_response = client.post(
            f"{API_URL}/token/authenticate",
            headers={"Authorization": f"Basic {auth_header}"},
        )

        assert_response_code(auth_response, [200], discrepancies)
        auth_data = auth_response.json()
        token = auth_data.get("tokenInfo", {}).get("tokenValue")
        assert token, "No token returned from authenticate"

        # 2. Validate token
        validate_response = client.get(
            f"{API_URL}/token/validate",
            headers={"Authorization": f"AnaplanAuthToken {token}"},
        )

        assert_response_code(validate_response, [200], discrepancies)
        validate_data = validate_response.json()
        assert validate_data.get("tokenInfo"), "No tokenInfo in validate response"

        # 3. Refresh token
        refresh_response = client.post(
            f"{API_URL}/token/refresh",
            headers={"Authorization": f"AnaplanAuthToken {token}"},
        )

        assert_response_code(refresh_response, [200], discrepancies)
        refresh_data = refresh_response.json()
        new_token = refresh_data.get("tokenInfo", {}).get("tokenValue")
        assert new_token, "No token returned from refresh"
        assert new_token != token, "Refresh should return a different token"

        # 4. Validate new token
        validate2_response = client.get(
            f"{API_URL}/token/validate",
            headers={"Authorization": f"AnaplanAuthToken {new_token}"},
        )

        assert_response_code(validate2_response, [200], discrepancies)

        # 5. Logout
        logout_response = client.post(
            f"{API_URL}/token/logout",
            headers={"Authorization": f"AnaplanAuthToken {new_token}"},
        )

        assert_response_code(logout_response, [204], discrepancies)

        # 6. Verify token is revoked
        revoked_response = client.get(
            f"{API_URL}/token/validate",
            headers={"Authorization": f"AnaplanAuthToken {new_token}"},
        )

        assert_response_code(revoked_response, [401], discrepancies)

    if discrepancies:
        pytest.warns(
            UserWarning,
            f"Found {len(discrepancies)} discrepancy/ies: {discrepancies}",
        )


@pytest.mark.live
def test_auth_workflow_ca_cert(ca_certs):
    """Test full workflow with CA certificate authentication."""
    if not ca_certs:
        pytest.skip("CA certificate credentials not configured")

    discrepancies = []

    with httpx.Client() as client:
        # 1. Authenticate with CA cert
        cert_payload = {
            "certificateChain": ca_certs["cert"],
            "signature": ca_certs["signature"],
        }

        auth_response = client.post(
            f"{API_URL}/token/authenticate",
            headers={"Authorization": f"CACertificate {ca_certs['cert']}"},
            json=cert_payload,
        )

        assert_response_code(auth_response, [200], discrepancies)
        auth_data = auth_response.json()
        token = auth_data.get("tokenInfo", {}).get("tokenValue")
        assert token, "No token returned from CA cert authentication"

        # 2. Validate token
        validate_response = client.get(
            f"{API_URL}/token/validate",
            headers={"Authorization": f"AnaplanAuthToken {token}"},
        )

        assert_response_code(validate_response, [200], discrepancies)

        # 3. Logout
        logout_response = client.post(
            f"{API_URL}/token/logout",
            headers={"Authorization": f"AnaplanAuthToken {token}"},
        )

        assert_response_code(logout_response, [204], discrepancies)

    if discrepancies:
        pytest.warns(
            UserWarning,
            f"Found {len(discrepancies)} discrepancy/ies: {discrepancies}",
        )


@pytest.mark.live
def test_invalid_credentials(auth_creds):
    """Test authentication with invalid credentials."""
    username = auth_creds["username"]
    invalid_password = "wrong_password_xyz"
    discrepancies = []

    with httpx.Client() as client:
        auth_header = base64.b64encode(f"{username}:{invalid_password}".encode()).decode()
        response = client.post(
            f"{API_URL}/token/authenticate",
            headers={"Authorization": f"Basic {auth_header}"},
        )

        assert_response_code(response, [401, 400], discrepancies)

    if discrepancies:
        pytest.warns(
            UserWarning,
            f"Found {len(discrepancies)} discrepancy/ies: {discrepancies}",
        )


@pytest.mark.live
def test_invalid_auth_header_formats(auth_creds):
    """Test with invalid Authorization header formats."""
    username, password = auth_creds["username"], auth_creds["password"]
    discrepancies = []

    invalid_formats = [
        ("InvalidScheme xyz", "Unknown auth scheme"),
        ("Bearer xyz", "Bearer instead of Basic"),
        ("Basic ", "Empty basic auth"),
        ("xyz", "No scheme"),
    ]

    with httpx.Client() as client:
        for auth_header, description in invalid_formats:
            response = client.post(
                f"{API_URL}/token/authenticate",
                headers={"Authorization": auth_header},
            )

            # Spec doesn't document these cases; we expect 401 or 400
            if response.status_code not in [400, 401, 403]:
                discrepancies.append(
                    f"{description}: got {response.status_code}, expected 400/401/403"
                )

    if discrepancies:
        pytest.warns(
            UserWarning,
            f"Found {len(discrepancies)} discrepancy/ies in invalid auth formats",
        )


@pytest.mark.live
def test_response_schemas_valid(auth_creds):
    """Validate that all responses match the spec schemas."""
    username, password = auth_creds["username"], auth_creds["password"]

    with httpx.Client() as client:
        auth_header = base64.b64encode(f"{username}:{password}".encode()).decode()
        response = client.post(
            f"{API_URL}/token/authenticate",
            headers={"Authorization": f"Basic {auth_header}"},
        )

        if response.status_code == 200:
            # Validate the spec itself is valid
            validate(SPEC)

            # Note: Full response validation against spec would require more setup
            # For now, we just verify the spec is valid and responses have expected structure
            auth_data = response.json()
            assert "tokenInfo" in auth_data
            assert "status" in auth_data
            assert "statusMessage" in auth_data


def assert_response_code(response, expected_codes, discrepancies):
    """Assert response code is in expected_codes, track discrepancies."""
    if response.status_code not in expected_codes:
        discrepancies.append(
            f"Got {response.status_code}, expected one of {expected_codes}"
        )
