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
