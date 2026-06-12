"""
Unit tests for the Authorization Code grant helper (scripts/oauth/oauth_authcode.py).

These cover the pure logic that used to live inline across the former step1/step2
scripts: building the authorize URL and extracting the code from the browser
redirect. The token exchange itself needs a live browser flow and is not unit
tested here.

Run with:
    uv run pytest tests/test_oauth_authcode.py
"""

import urllib.parse

import pytest

from oauth.oauth_authcode import build_auth_url, extract_code


# ── Tracer bullet ─────────────────────────────────────────────────────────────

def test_extract_code_returns_code_when_state_matches():
    """A redirect URL with the expected state yields its authorization code."""
    redirect = "https://www.anaplan.com/?code=abc123&state=xyz"

    assert extract_code(redirect, expected_state="xyz") == "abc123"


# ── State (CSRF) guard and error cases ────────────────────────────────────────

def test_extract_code_rejects_state_mismatch():
    """A redirect whose state differs from the one we sent is rejected (CSRF guard)."""
    redirect = "https://www.anaplan.com/?code=abc123&state=tampered"

    with pytest.raises(ValueError, match="state mismatch"):
        extract_code(redirect, expected_state="xyz")


def test_extract_code_raises_when_code_absent():
    """A redirect with a matching state but no code parameter is an error."""
    redirect = "https://www.anaplan.com/?state=xyz"

    with pytest.raises(ValueError, match="no 'code'"):
        extract_code(redirect, expected_state="xyz")


# ── Authorize URL ─────────────────────────────────────────────────────────────

def test_build_auth_url_carries_grant_parameters():
    """The authorize URL targets prelogin and carries the auth-code grant params."""
    url = build_auth_url("client-123", state="st-456")

    assert url.startswith("https://us1a.app.anaplan.com/auth/prelogin?")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client-123"]
    assert query["state"] == ["st-456"]
    assert query["redirect_uri"] == ["https://www.anaplan.com"]
