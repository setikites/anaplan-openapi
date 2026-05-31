import pytest


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "live: mark test as requiring live API access (skipped by default)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip live tests by default unless --live flag is passed."""
    if config.getoption("--live"):
        return

    skip_live = pytest.mark.skip(reason="Use --live flag to run live API tests")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


def pytest_addoption(parser):
    """Add --live command line option."""
    parser.addoption(
        "--live", action="store_true", default=False, help="Run live API tests"
    )
