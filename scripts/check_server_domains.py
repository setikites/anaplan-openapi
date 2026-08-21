"""
Checks that every spec's `servers[].url` host is on the Anaplan domain
allowlist. See docs/anaplan-domain-allowlist.md for the reference and the
official sources it was derived from.
"""
from urllib.parse import urlparse

_ALLOWED_SUFFIXES = ("anaplan.com",)

# host suffix -> APIs allowed to use it (see docs/anaplan-domain-allowlist.md)
_EXCEPTIONS = {
    "fluence.app": {"financial-consolidation"},
}


def _host_allowed(host: str, api: str) -> bool:
    if any(host == s or host.endswith("." + s) for s in _ALLOWED_SUFFIXES):
        return True
    for suffix, apis in _EXCEPTIONS.items():
        if (host == suffix or host.endswith("." + suffix)) and api in apis:
            return True
    return False


def check_server_domains(spec: dict, name: str) -> list[str]:
    """Return a list of servers whose host isn't on the allowlist (empty = OK)."""
    violations = []
    for server in spec.get("servers", []):
        url = server.get("url", "")
        host = urlparse(url).netloc
        if not host:
            violations.append(f"{name}: server entry has no host: {url!r}")
        elif not _host_allowed(host, name):
            violations.append(
                f"{name}: server host {host!r} is not on the allowlist "
                f"({url!r}) — see docs/anaplan-domain-allowlist.md"
            )
    return violations


def main() -> int:
    import json
    import pathlib
    import sys

    spec_files = sorted(pathlib.Path(".").glob("*/*-openapi.json"))
    if not spec_files:
        print("No spec files found.")
        return 1

    all_ok = True
    for path in spec_files:
        spec = json.loads(path.read_text(encoding="utf-8"))
        violations = check_server_domains(spec, path.parent.name)
        if violations:
            all_ok = False
            for v in violations:
                print(f"[FAIL] {v}")
        else:
            print(f"[OK] {path.parent.name}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
