import argparse
import os
import subprocess

from .bind_guard import BindAddressError, validate_bind_host


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Gateway Dashboard service.")
    parser.add_argument("--host", default=os.environ.get("PCDD_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PCDD_PORT", "8787")))
    parser.add_argument("--allow-public-bind", action="store_true")
    args = parser.parse_args()

    try:
        host = validate_bind_host(args.host, allow_public=args.allow_public_bind)
    except BindAddressError as exc:
        parser.error(str(exc))

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'uvicorn'. Install with: python -m pip install -r requirements.txt"
        ) from exc

    uvicorn.run("pc_drive_dashboard.app:create_app", factory=True, host=host, port=args.port)


def tailscale_ipv4() -> str | None:
    try:
        output = subprocess.check_output(["tailscale", "ip", "-4"], text=True).strip()
    except Exception:
        return None
    return output.splitlines()[0] if output else None
