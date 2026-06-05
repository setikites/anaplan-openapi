"""Pytest configuration for loading .env file."""

import os
from pathlib import Path
import pytest


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
                    os.environ[key.strip()] = value.strip()


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
