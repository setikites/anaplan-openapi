"""Chunked OS-keyring token store for the OAuth helper scripts.

Stores a token blob (typically the full JSON token response) in the operating
system credential store via ``keyring``. Backends such as the Windows Credential
Manager cap a single secret at roughly 2560 bytes, which a JWT-bearing token
response can exceed, so the value is split across numbered chunk entries under
the same service name.
"""

import keyring

_CHUNK_SIZE = 1000


_COUNT_KEY = "chunk_count"


def store_token(service: str, value: str) -> None:
    """Store ``value`` under ``service`` in the OS keyring, split into chunks."""
    clear_token(service)
    chunks = [
        value[i : i + _CHUNK_SIZE] for i in range(0, len(value), _CHUNK_SIZE)
    ] or [""]
    for index, chunk in enumerate(chunks):
        keyring.set_password(service, f"chunk_{index}", chunk)
    keyring.set_password(service, _COUNT_KEY, str(len(chunks)))


def load_token(service: str) -> str | None:
    """Reassemble and return the token stored under ``service``, or None."""
    count = keyring.get_password(service, _COUNT_KEY)
    if count is None:
        return None
    parts = [keyring.get_password(service, f"chunk_{i}") for i in range(int(count))]
    return "".join(part or "" for part in parts)


def clear_token(service: str) -> None:
    """Delete all chunks stored under ``service``."""
    count = keyring.get_password(service, _COUNT_KEY)
    if count is None:
        return
    for i in range(int(count)):
        keyring.delete_password(service, f"chunk_{i}")
    keyring.delete_password(service, _COUNT_KEY)
