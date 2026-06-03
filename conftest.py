import httpx
import pytest

_WRITE_METHODS = frozenset({"PUT", "POST", "PATCH", "DELETE"})


def _is_data_plane_host(url: str) -> bool:
    """Return True if the URL targets an Anaplan data-plane host (api.anaplan.com).

    Auth (auth.anaplan.com) and OAuth (app.anaplan.com) hosts are excluded —
    those POST/PUT calls are authentication infrastructure, not data mutations.
    """
    try:
        host = httpx.URL(url).host
    except Exception:
        return False
    return host == "api.anaplan.com" or host.endswith(".api.anaplan.com")


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
    """Add --live and --allow-writes command line options."""
    parser.addoption(
        "--live", action="store_true", default=False, help="Run live API tests"
    )
    parser.addoption(
        "--allow-writes",
        action="store_true",
        default=False,
        help=(
            "Permit write methods (PUT/POST/PATCH/DELETE) to api.anaplan.com "
            "in live tests. Requires explicit human confirmation — omit this "
            "flag to keep live test runs read-only."
        ),
    )


@pytest.fixture(autouse=True)
def _guard_write_methods(request, pytestconfig):
    """Block write methods to the data-plane API unless --allow-writes is set.

    Only active for tests marked @pytest.mark.live. Auth-plane calls
    (auth.anaplan.com, app.anaplan.com) are never blocked.
    """
    if not request.node.get_closest_marker("live"):
        yield
        return

    if pytestconfig.getoption("--allow-writes"):
        yield
        return

    original_send = httpx.Client.send

    def _guarded_send(self, req, **kwargs):
        if req.method in _WRITE_METHODS and _is_data_plane_host(str(req.url)):
            pytest.skip(
                f"{req.method} {req.url} requires --allow-writes flag. "
                "Pass it only after explicit human approval."
            )
        return original_send(self, req, **kwargs)

    httpx.Client.send = _guarded_send
    try:
        yield
    finally:
        httpx.Client.send = original_send
