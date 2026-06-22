import re
from pathlib import PureWindowsPath


class PathError(ValueError):
    """Raised for paths that are unsafe or unsupported by the v1 dashboard."""


_DRIVE_PATH_RE = re.compile(r"^[a-zA-Z]:(?:[\\/].*)?$")


def normalize_windows_path(raw_path: str) -> str:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise PathError("Path is required.")

    candidate = raw_path.strip()
    if candidate.startswith("\\\\") or candidate.startswith("//"):
        raise PathError("UNC paths are disabled in version 1.")

    if not _DRIVE_PATH_RE.match(candidate):
        raise PathError("Only absolute Windows drive paths are supported.")

    drive = candidate[0].upper()
    rest = candidate[2:].replace("/", "\\")
    parts = [part for part in rest.split("\\") if part and part != "."]

    if any(part == ".." for part in parts):
        raise PathError("Parent traversal is not allowed.")

    if not parts:
        return f"{drive}:\\"

    return str(PureWindowsPath(f"{drive}:\\", *parts))


def format_path_variants(raw_path: str) -> dict[str, str]:
    windows_path = normalize_windows_path(raw_path)
    drive = windows_path[0].lower()
    path_without_drive = windows_path[2:].replace("\\", "/")
    ssh_path = f"{windows_path[0].upper()}:{path_without_drive}"
    posix_path = f"/{drive}{path_without_drive}"
    name = PureWindowsPath(windows_path).name or f"{windows_path[0].upper()}:"

    return {
        "windows": windows_path,
        "ssh": ssh_path,
        "posix": posix_path,
        "name": name,
    }
