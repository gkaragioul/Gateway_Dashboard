"""First-run protection: only the PC itself, or someone holding the one-time setup code, may set the password."""

import hmac
import ipaddress
import re
import secrets
from pathlib import Path

SETUP_CODE_FILENAME = "setup-code.txt"

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_RE = re.compile(r"\b([A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4})\b")


def setup_code_path(config_dir: Path) -> Path:
    return Path(config_dir) / SETUP_CODE_FILENAME


def load_or_create_setup_code(config_dir: Path) -> str:
    """Return the pending setup code, creating it (and its file) when none exists yet.

    The code lives in a file so every dashboard process started by the watchdog agrees on it.
    """
    path = setup_code_path(config_dir)
    try:
        match = _CODE_RE.search(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        match = None
    if match:
        return match.group(1)

    code = "-".join("".join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(3))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"Gateway Dashboard one-time setup code: {code}\n"
        "Enter it on the 'Create dashboard password' screen when you set the password from another device.\n"
        "This file is deleted automatically once the password is set.\n",
        encoding="utf-8",
    )
    return code


def clear_setup_code(config_dir: Path) -> None:
    try:
        setup_code_path(config_dir).unlink(missing_ok=True)
    except OSError:
        pass


def setup_code_matches(expected: str, supplied: str | None) -> bool:
    expected_normalized = _normalize_code(expected)
    supplied_normalized = _normalize_code(supplied)
    if not expected_normalized or not supplied_normalized:
        return False
    return hmac.compare_digest(expected_normalized.encode("utf-8"), supplied_normalized.encode("utf-8"))


def is_local_request(client_host: str | None, host_header: str | None) -> bool:
    """True only when the TCP peer is loopback AND the browser addressed the dashboard by a loopback name.

    Checking the Host header as well stops DNS-rebinding pages and localhost tunnels/proxies
    (which forward with their own public hostname) from counting as "on the PC".
    """
    return _is_loopback_ip(client_host) and (
        (host_header or "").strip().lower() == "localhost" or _is_loopback_ip(host_header)
    )


def _is_loopback_ip(value: str | None) -> bool:
    if not value:
        return False
    try:
        address = ipaddress.ip_address(value.strip().strip("[]"))
    except ValueError:
        return False
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback


def _normalize_code(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(char for char in value.upper() if char.isalnum())
