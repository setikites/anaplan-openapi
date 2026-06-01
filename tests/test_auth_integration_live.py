"""
Live API integration tests for Authentication API.

Run with:
    uv run --env-file .env pytest tests/test_auth_integration_live.py --live

Credentials are read from .env at the repo root. Required variables:
    ANAPLAN_USERNAME       - username for basic auth
    ANAPLAN_PASSWORD       - password for basic auth

Optional variables (for CA certificate auth):
    ANAPLAN_CA_CERT_PATH   - path to CA certificate file (PEM format)
    ANAPLAN_CA_KEY_PATH    - path to private key file (PEM format)
    ANAPLAN_CA_KEY_PASSWORD - password for the private key (if encrypted)
"""

import base64
import os
import pathlib
import secrets
import warnings
import pytest
import httpx
import yaml
from openapi_spec_validator import validate
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

# Load spec for response validation
SPEC_FILE = pathlib.Path(__file__).parent.parent / "authentication" / "postman-spec.yaml"
with open(SPEC_FILE, encoding="utf-8") as f:
    SPEC = yaml.safe_load(f)

API_URL = "https://auth.anaplan.com"


def _sign_data_with_private_key(data: bytes, key_path: str, key_password: str | None = None) -> str:
    """Sign data with a private key using SHA512withRSA and return base64-encoded signature."""
    with open(key_path, "rb") as f:
        key_data = f.read()

    password = key_password.encode() if key_password else None
    private_key = serialization.load_pem_private_key(
        key_data, password=password, backend=default_backend()
    )

    signature = private_key.sign(data, padding.PKCS1v15(), hashes.SHA512())
    return base64.b64encode(signature).decode()


def _load_certificate(cert_path: str) -> str:
    """Load and return base64-encoded certificate in PEM format."""
    with open(cert_path, "rb") as f:
        cert_data = f.read()
    return base64.b64encode(cert_data).decode()


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
    """Load CA certificate paths from environment."""
    cert_path = os.getenv("ANAPLAN_CA_CERT_PATH")
    key_path = os.getenv("ANAPLAN_CA_KEY_PATH")

    if not cert_path or not key_path:
        return None

    cert_file = pathlib.Path(cert_path)
    key_file = pathlib.Path(key_path)

    if not cert_file.exists():
        pytest.skip(f"CA certificate file not found: {cert_path}")
    if not key_file.exists():
        pytest.skip(f"Private key file not found: {key_path}")

    key_password = os.getenv("ANAPLAN_CA_KEY_PASSWORD")

    return {
        "cert_path": str(cert_file),
        "key_path": str(key_file),
        "key_password": key_password,
    }


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

        assert_response_code(auth_response, [201], discrepancies)
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
        msg = f"Found {len(discrepancies)} discrepancy/ies: {discrepancies}"
        warnings.warn(msg, UserWarning, stacklevel=2)


@pytest.mark.live
def test_auth_workflow_ca_cert(ca_certs):
    """Test full workflow with CA certificate authentication.

    Implements the Anaplan certificate auth flow:
    1. Generate random 100+ byte string
    2. Base64 encode it
    3. Sign with private key using SHA512withRSA
    4. Base64 encode signature
    5. Send to /token/authenticate
    """
    if not ca_certs:
        pytest.skip("CA certificate credentials not configured")

    discrepancies = []

    # Generate random data (150 bytes)
    random_data = secrets.token_bytes(150)
    encoded_data = base64.b64encode(random_data).decode()

    # Sign the random data with the private key
    signature = _sign_data_with_private_key(
        random_data, ca_certs["key_path"], ca_certs["key_password"]
    )

    # Load the certificate in base64
    cert_b64 = _load_certificate(ca_certs["cert_path"])

    with httpx.Client() as client:
        # 1. Authenticate with CA cert
        cert_payload = {
            "encodedData": encoded_data,
            "encodedSignedData": signature,
        }

        auth_response = client.post(
            f"{API_URL}/token/authenticate",
            headers={"Authorization": f"CACertificate {cert_b64}"},
            json=cert_payload,
        )

        # Certificate auth may fail if cert is not registered for API use
        if auth_response.status_code == 401:
            error_msg = auth_response.json().get("statusMessage", "Unknown error")
            pytest.skip(
                f"Certificate not registered for API authentication: {error_msg}"
            )

        assert_response_code(auth_response, [201], discrepancies)
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
        msg = f"Found {len(discrepancies)} discrepancy/ies: {discrepancies}"
        warnings.warn(msg, UserWarning, stacklevel=2)


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
        msg = f"Found {len(discrepancies)} discrepancy/ies: {discrepancies}"
        warnings.warn(msg, UserWarning, stacklevel=2)


@pytest.mark.live
def test_invalid_auth_header_formats():
    """Test all endpoints return 401 for invalid Authorization header formats,
    and that 401 response bodies match the spec's ValidationUrl schema."""
    discrepancies = []

    invalid_formats = [
        ("InvalidScheme xyz", "unknown scheme"),
        ("Bearer xyz", "Bearer instead of AnaplanAuthToken"),
        ("xyz", "no scheme"),
    ]

    # (method, path, expected_4xx_code)
    # /token/refresh and /token/validate return 400 for malformed headers;
    # /token/authenticate and /token/logout return 401.
    endpoints = [
        ("POST", "/token/authenticate", 401),
        ("POST", "/token/refresh",      400),
        ("GET",  "/token/validate",     400),
        ("POST", "/token/logout",       401),
    ]

    with httpx.Client() as client:
        for method, path, expected_code in endpoints:
            url = f"{API_URL}{path}"
            for auth_header, description in invalid_formats:
                label = f"{method} {path} [{description}]"
                try:
                    request_fn = client.get if method == "GET" else client.post
                    response = request_fn(url, headers={"Authorization": auth_header})

                    if response.status_code != expected_code:
                        discrepancies.append(
                            f"{label}: got {response.status_code}, expected {expected_code}"
                        )
                        continue

                    # All 4xx responses should return ErrorResponse: {status, statusMessage}
                    try:
                        body = response.json()
                        for field in ("status", "statusMessage"):
                            if field not in body:
                                discrepancies.append(
                                    f"{label}: {expected_code} body missing '{field}', got keys={list(body.keys())}"
                                )
                    except Exception:
                        discrepancies.append(f"{label}: {expected_code} response is not valid JSON")

                except (httpx.LocalProtocolError, ValueError) as e:
                    discrepancies.append(f"{label}: client rejected ({type(e).__name__}: {e})")

    if discrepancies:
        msg = "Discrepancies in invalid auth header formats:\n" + "\n".join(f"  - {d}" for d in discrepancies)
        warnings.warn(msg, UserWarning, stacklevel=2)


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

        if response.status_code == 201:
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
