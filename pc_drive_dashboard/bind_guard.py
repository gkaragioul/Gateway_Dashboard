import ipaddress


class BindAddressError(ValueError):
    """Raised when a requested bind host is outside the approved boundary."""


def validate_bind_host(host: str, allow_public: bool = False) -> str:
    normalized = host.strip().lower()
    if not normalized:
        raise BindAddressError("Bind host cannot be empty.")

    if allow_public:
        return host

    if normalized in {"localhost", "::1"}:
        return host

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise BindAddressError(
            "Use localhost, a loopback IP, or the PC Tailscale IP. "
            f"Refusing hostname '{host}'."
        ) from exc

    tailscale_v4 = ipaddress.ip_network("100.64.0.0/10")
    tailscale_v6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")

    if address.is_loopback or address in tailscale_v4 or address in tailscale_v6:
        return host

    raise BindAddressError(
        f"Refusing to bind to {host}. Use 127.0.0.1 or a Tailscale address, "
        "or pass --allow-public-bind intentionally."
    )
