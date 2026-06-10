"""
Live integration tests for the Financial Consolidation API.

These tests are skipped unconditionally because live testing requires credentials
from a Financial Consolidation (Fluence) environment that are not available in CI:
  - X_API_TOKEN: a token created in the Fluence Security module
  - TENANT: the target tenant identifier

When credentials become available, remove the skip and implement tests following
the pattern in tests/test_audit_live.py.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Live testing requires X_API_TOKEN and TENANT from a Financial Consolidation "
        "environment — credentials not available in CI"
    )
)
