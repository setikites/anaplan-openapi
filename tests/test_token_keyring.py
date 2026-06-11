"""
Unit tests for the chunked OS-keyring token store (scripts/oauth/token_keyring.py).

These run without live API access or a real keyring backend: an in-memory fake
keyring stands in for the OS credential store. The fake enforces a per-secret
size cap, mirroring the Windows Credential Manager limit that forces a long JWT
token blob to be split across multiple entries.

Run with:
    uv run pytest tests/test_token_keyring.py
"""

import keyring
import pytest
from keyring.backend import KeyringBackend

from oauth.token_keyring import clear_token, load_token, store_token

# Windows Credential Manager caps a credential blob at ~2560 bytes. The fake
# enforces a cap in this range so a token longer than it must be chunked.
_BACKEND_LIMIT = 1280


class _SizeLimitedMemoryKeyring(KeyringBackend):
    """In-memory keyring that rejects any single secret over the size cap.

    Storing a value longer than _BACKEND_LIMIT raises, exactly as the Windows
    backend does. A store that round-trips a long token through this backend
    has therefore proven it chunks rather than writing one oversized secret.
    """

    priority = 1

    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        if len(password) > _BACKEND_LIMIT:
            raise ValueError(
                f"secret of {len(password)} chars exceeds backend limit "
                f"{_BACKEND_LIMIT}"
            )
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        self._store.pop((service, username), None)


@pytest.fixture
def fake_keyring():
    """Install the in-memory keyring for the duration of a test."""
    backend = _SizeLimitedMemoryKeyring()
    previous = keyring.get_keyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


# ── Tracer bullet ─────────────────────────────────────────────────────────────

def test_store_then_load_round_trips_a_token(fake_keyring):
    """A token stored under a service name can be read back identically."""
    store_token("anaplan-oauth-test", '{"access_token": "abc123"}')

    assert load_token("anaplan-oauth-test") == '{"access_token": "abc123"}'


# ── Chunking ──────────────────────────────────────────────────────────────────

def test_store_then_load_round_trips_a_token_longer_than_backend_limit(fake_keyring):
    """A token blob larger than a single secret survives a store/load round-trip.

    The fake backend raises if any one secret exceeds its size cap, so a clean
    round-trip here proves the value was split into multiple chunks rather than
    written as one oversized secret.
    """
    long_token = "x" * (_BACKEND_LIMIT * 3 + 7)

    store_token("anaplan-oauth-test", long_token)

    assert load_token("anaplan-oauth-test") == long_token


def test_overwriting_with_shorter_token_leaves_no_orphaned_chunks(fake_keyring):
    """Replacing a long token with a short one must not leave stale chunks behind.

    Orphaned high-index chunks would leave fragments of an old token lingering in
    the OS credential store. After overwriting, only the new token's chunks (plus
    the count) should remain.
    """
    store_token("anaplan-oauth-test", "y" * (_BACKEND_LIMIT * 3))
    store_token("anaplan-oauth-test", '{"access_token": "short"}')

    assert load_token("anaplan-oauth-test") == '{"access_token": "short"}'
    stored_usernames = {
        username for (_, username) in fake_keyring._store
    }
    assert stored_usernames == {"chunk_count", "chunk_0"}


# ── Absence and clearing ──────────────────────────────────────────────────────

def test_load_returns_none_when_nothing_stored(fake_keyring):
    """Loading a service that was never stored returns None, not an error."""
    assert load_token("never-stored") is None


def test_clear_removes_a_stored_token(fake_keyring):
    """After clearing, the token can no longer be loaded."""
    store_token("anaplan-oauth-test", "y" * (_BACKEND_LIMIT * 2))

    clear_token("anaplan-oauth-test")

    assert load_token("anaplan-oauth-test") is None
    assert fake_keyring._store == {}
