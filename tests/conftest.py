"""Pytest configuration for loading .env file."""

import base64
import os
import secrets
from pathlib import Path

import httpx
import pytest

AUTH_URL = "https://auth.anaplan.com"


@pytest.fixture(scope="session", autouse=True)
def load_env():
    """Load .env file before running tests."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    value = value.strip()
                    # Strip one layer of surrounding quotes, as dotenv does — a
                    # quoted path (e.g. one containing spaces) must not keep its
                    # literal quotes, or file lookups fail.
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                        value = value[1:-1]
                    os.environ[key.strip()] = value


# ---------------------------------------------------------------------------
# Credential fixtures (shared across all live-test files)
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_creds():
    """Load basic authentication credentials from environment."""
    username = os.getenv("ANAPLAN_USERNAME")
    password = os.getenv("ANAPLAN_PASSWORD")
    if not username or not password:
        pytest.skip("ANAPLAN_USERNAME and ANAPLAN_PASSWORD not set")
    return {"username": username, "password": password}


@pytest.fixture
def ca_certs():
    """Load CA certificate paths from environment. Returns None when not configured."""
    cert_path = os.getenv("ANAPLAN_CA_CERT_PATH")
    key_path = os.getenv("ANAPLAN_CA_KEY_PATH")
    if not cert_path or not key_path:
        return None
    cert_file = Path(cert_path)
    key_file = Path(key_path)
    if not cert_file.exists():
        pytest.skip(f"CA certificate file not found: {cert_path}")
    if not key_file.exists():
        pytest.skip(f"Private key file not found: {key_path}")
    return {
        "cert_path": str(cert_file),
        "key_path": str(key_file),
        "key_password": os.getenv("ANAPLAN_CA_KEY_PASSWORD"),
    }


@pytest.fixture
def cert_token(ca_certs):
    """AnaplanAuthToken obtained via CACertificate auth (the cert-auth user).

    Skips when cert env vars are unset. Logs out on teardown. Used where a test
    needs the specific cert-auth principal rather than the basic-auth account.
    """
    if not ca_certs:
        pytest.skip("ANAPLAN_CA_CERT_PATH / ANAPLAN_CA_KEY_PATH not set")

    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    with open(ca_certs["key_path"], "rb") as f:
        pwd = ca_certs["key_password"]
        key = serialization.load_pem_private_key(
            f.read(), password=pwd.encode() if pwd else None, backend=default_backend()
        )
    with open(ca_certs["cert_path"], "rb") as f:
        cert_b64 = base64.b64encode(f.read()).decode()

    random_data = secrets.token_bytes(150)
    signature = base64.b64encode(
        key.sign(random_data, padding.PKCS1v15(), hashes.SHA512())
    ).decode()

    with httpx.Client() as client:
        resp = client.post(
            f"{AUTH_URL}/token/authenticate",
            headers={"Authorization": f"CACertificate {cert_b64}"},
            json={
                "encodedData": base64.b64encode(random_data).decode(),
                "encodedSignedData": signature,
            },
        )
        if resp.status_code != 201:
            pytest.skip(f"CACertificate auth failed ({resp.status_code})")
        token = resp.json().get("tokenInfo", {}).get("tokenValue")

        yield token

        client.post(
            f"{AUTH_URL}/token/logout",
            headers={"Authorization": f"AnaplanAuthToken {token}"},
        )


@pytest.fixture
def oauth_client_id():
    """Load Authorization Code Grant client ID from environment."""
    client_id = os.getenv("ANAPLAN_OAUTH_CLIENT_ID")
    if not client_id:
        pytest.skip("ANAPLAN_OAUTH_CLIENT_ID not set")
    return client_id


@pytest.fixture
def oauth_device_client_id():
    """Load Device Authorization Grant client ID from environment."""
    client_id = os.getenv("ANAPLAN_OAUTH_DEVICE_CLIENT_ID")
    if not client_id:
        pytest.skip("ANAPLAN_OAUTH_DEVICE_CLIENT_ID not set")
    return client_id
