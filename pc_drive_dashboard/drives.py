import os
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DRIVE_ROLES = {
    "C": {"label": "System", "role": "Windows system drive"},
    "D": {"label": "Games", "role": "Game installs"},
    "F": {"label": "Games Overflow", "role": "Overflow game storage"},
    "G": {"label": "Project Library", "role": "Canonical project library"},
    "H": {"label": "Backup", "role": "Backup snapshots and safety layer"},
}

CRITICAL_DRIVES = {"G", "H"}


@dataclass(frozen=True)
class DriveInfo:
    letter: str
    path: str
    label: str
    role: str
    available: bool
    total: int | None
    free: int | None
    filesystem: str | None
    warning: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def list_drives() -> list[dict[str, Any]]:
    if os.name != "nt":
        return [_offline_drive(letter, "Service is not running on Windows.").as_dict() for letter in DRIVE_ROLES]

    drives = []
    for letter, info in DRIVE_ROLES.items():
        root = f"{letter}:\\"
        if not Path(root).exists():
            drives.append(_offline_drive(letter, "Drive is not mounted.").as_dict())
            continue

        usage = shutil.disk_usage(root)
        label = _volume_label(root) or info["label"]
        drives.append(
            DriveInfo(
                letter=letter,
                path=root,
                label=label,
                role=info["role"],
                available=True,
                total=usage.total,
                free=usage.free,
                filesystem=_filesystem(root),
            ).as_dict()
        )
    return drives


def storage_health(drives: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    checked_drives = drives if drives is not None else list_drives()
    unavailable = [
        {
            "letter": drive["letter"],
            "label": drive.get("label") or DRIVE_ROLES.get(drive["letter"], {}).get("label", drive["letter"]),
            "role": drive.get("role") or DRIVE_ROLES.get(drive["letter"], {}).get("role", "Expected drive"),
            "warning": drive.get("warning") or "Unavailable",
        }
        for drive in checked_drives
        if not drive.get("available")
    ]
    missing_critical = [drive for drive in unavailable if drive["letter"] in CRITICAL_DRIVES]

    if missing_critical:
        status = "degraded"
        drive_list = ", ".join(f"{drive['letter']}:" for drive in missing_critical)
        message = f"Critical storage missing: {drive_list}. Mounted folders remain browsable."
    elif unavailable:
        status = "warning"
        drive_list = ", ".join(f"{drive['letter']}:" for drive in unavailable)
        message = f"Some expected drives are unavailable: {drive_list}."
    else:
        status = "ok"
        message = "All expected storage drives are mounted."

    return {
        "status": status,
        "message": message,
        "expected_count": len(DRIVE_ROLES),
        "available_count": len(checked_drives) - len(unavailable),
        "unavailable": unavailable,
        "missing_critical": missing_critical,
        "critical_letters": sorted(CRITICAL_DRIVES),
    }


def storage_diagnostics() -> dict[str, Any]:
    if os.name != "nt":
        return {
            "core_storage_present": False,
            "active_work_present": True,
            "summary": "Storage diagnostics are only available on Windows.",
            "suspect_devices": [],
            "pnp_devices": [],
            "volumes": [],
        }

    script = r"""
$pnp = Get-PnpDevice -Class DiskDrive |
  Select-Object Status,FriendlyName,InstanceId
$volumes = Get-Volume |
  Select-Object DriveLetter,FileSystemLabel,FileSystem,DriveType,HealthStatus,OperationalStatus,SizeRemaining,Size
$disks = Get-Disk |
  Select-Object Number,FriendlyName,OperationalStatus,HealthStatus,Size
[PSCustomObject]@{
  core_storage_present = ((Test-Path G:\) -and (Test-Path H:\))
  pnp_devices = $pnp
  volumes = $volumes
  disks = $disks
} | ConvertTo-Json -Depth 5
"""
    try:
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", script],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        raw = json.loads(output)
    except Exception as exc:
        return {
            "core_storage_present": Path("G:/").exists() and Path("H:/").exists(),
            "active_work_present": True,
            "summary": f"Storage diagnostics failed: {exc.__class__.__name__}",
            "suspect_devices": [],
            "pnp_devices": [],
            "volumes": [],
            "disks": [],
        }

    return parse_storage_diagnostics(raw)


def parse_storage_diagnostics(raw: dict[str, Any]) -> dict[str, Any]:
    pnp_devices = [_normalize_keys(item) for item in _as_list(raw.get("pnp_devices"))]
    volumes = [_normalize_keys(item) for item in _as_list(raw.get("volumes"))]
    disks = [_normalize_keys(item) for item in _as_list(raw.get("disks"))]
    mounted_letters = {str(volume.get("drive_letter") or "").upper() for volume in volumes if volume.get("drive_letter")}
    core_storage_present = bool(raw.get("core_storage_present")) or {"G", "H"}.issubset(mounted_letters)

    suspect_devices = []
    for device in pnp_devices:
        friendly_name = str(device.get("friendly_name") or "")
        status = str(device.get("status") or "")
        if status.lower() != "ok":
            suspect_devices.append(
                {
                    "friendly_name": friendly_name,
                    "status": status or "Unknown",
                    "instance_id": device.get("instance_id"),
                    "reason": _diagnostic_reason(status),
                }
            )

    if core_storage_present:
        summary = "Core storage is mounted: G: Project Library and H: Backup are available."
    else:
        missing = ", ".join(f"{letter}:" for letter in ("G", "H") if letter not in mounted_letters)
        summary = f"Core storage missing: {missing or 'G:/H:'}."

    return {
        "core_storage_present": core_storage_present,
        "active_work_present": True,
        "summary": summary,
        "suspect_devices": suspect_devices,
        "pnp_devices": pnp_devices,
        "volumes": volumes,
        "disks": disks,
    }


def _diagnostic_reason(status: str) -> str:
    if status.lower() != "ok":
        return f"Device status is {status or 'Unknown'}."
    return "Storage device."


def _normalize_keys(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    normalized = {}
    for key, value in item.items():
        snake = []
        for index, char in enumerate(str(key)):
            if char.isupper() and index > 0:
                snake.append("_")
            snake.append(char.lower())
        normalized["".join(snake)] = value
    return normalized


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _offline_drive(letter: str, warning: str) -> DriveInfo:
    info = DRIVE_ROLES[letter]
    return DriveInfo(
        letter=letter,
        path=f"{letter}:\\",
        label=info["label"],
        role=info["role"],
        available=False,
        total=None,
        free=None,
        filesystem=None,
        warning=warning,
    )


def _volume_label(root: str) -> str | None:
    if sys.platform != "win32":
        return None

    try:
        import ctypes

        volume_name = ctypes.create_unicode_buffer(261)
        filesystem = ctypes.create_unicode_buffer(261)
        serial = ctypes.c_ulong()
        max_component = ctypes.c_ulong()
        flags = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root),
            volume_name,
            ctypes.sizeof(volume_name),
            ctypes.byref(serial),
            ctypes.byref(max_component),
            ctypes.byref(flags),
            filesystem,
            ctypes.sizeof(filesystem),
        )
        return volume_name.value if ok else None
    except Exception:
        return None


def _filesystem(root: str) -> str | None:
    try:
        output = subprocess.check_output(
            ["fsutil", "fsinfo", "volumeinfo", root], text=True, stderr=subprocess.DEVNULL
        )
    except Exception:
        return None
    for line in output.splitlines():
        if "File System Name" in line:
            return line.split(":", 1)[-1].strip()
    return None
