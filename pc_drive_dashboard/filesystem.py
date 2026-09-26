import os
import mimetypes
import re
import shutil
import stat
import subprocess
import time
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from .path_utils import PathError, format_path_variants, normalize_windows_path


class FilesystemUnavailable(RuntimeError):
    """Raised when a Windows filesystem operation cannot run here."""


class UploadConflictError(FileExistsError):
    """Raised when an upload would overwrite an existing file."""


class UploadNameError(ValueError):
    """Raised when an upload filename is unsafe for Windows."""


class FileOperationConflictError(FileExistsError):
    """Raised when a file operation would overwrite an existing item."""


class FileOperationSafetyError(ValueError):
    """Raised when a file operation targets an unsafe location."""


@dataclass(frozen=True)
class PreparedDownload:
    path: Path
    filename: str
    media_type: str
    cleanup: bool = False


UPLOAD_CHUNK_SIZE = 1024 * 1024

# Folder downloads are zipped on the PC first: keep this much disk free and clear abandoned zips.
DOWNLOAD_FREE_SPACE_RESERVE = 1024 * 1024 * 1024
STALE_DOWNLOAD_ARCHIVE_SECONDS = 6 * 60 * 60
_DOWNLOAD_ARCHIVE_NAME = re.compile(r"-[0-9a-f]{32}\.zip$")

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

WINDOWS_FORBIDDEN_FILENAME_CHARS = set('<>:"/\\|?*')


TEXT_EXTENSIONS = {
    ".bat",
    ".c",
    ".cfg",
    ".cmd",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".env",
    ".go",
    ".h",
    ".hpp",
    ".htm",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".log",
    ".md",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".svg",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

TEXT_FILENAMES = {
    ".gitignore",
    "makefile",
    "readme",
}

MEDIA_TYPES = {
    ".aac": "audio/aac",
    ".avif": "image/avif",
    ".avi": "video/x-msvideo",
    ".bmp": "image/bmp",
    ".flac": "audio/flac",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".m4a": "audio/mp4",
    ".m4v": "video/x-m4v",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".ogg": "audio/ogg",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".wav": "audio/wav",
    ".webm": "video/webm",
    ".webp": "image/webp",
    ".wmv": "video/x-ms-wmv",
}


def list_children(raw_path: str, page: int = 1, page_size: int = 200) -> dict[str, Any]:
    path = normalize_windows_path(raw_path)
    _require_windows()
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(path)
    if not target.is_dir():
        raise NotADirectoryError(path)

    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    children = []
    with os.scandir(target) as iterator:
        for entry in iterator:
            try:
                stat = entry.stat(follow_symlinks=False)
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                stat = None
                is_dir = False
            children.append(
                {
                    "name": entry.name,
                    "path": normalize_windows_path(str(Path(path) / entry.name)),
                    "kind": "folder" if is_dir else "file",
                    "size": stat.st_size if stat and not is_dir else None,
                    "modified": stat.st_mtime if stat else None,
                }
            )

    children.sort(key=lambda item: (item["kind"] != "folder", item["name"].lower()))
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "path": path,
        "page": page,
        "page_size": page_size,
        "total": len(children),
        "children": children[start:end],
    }


def common_locations() -> list[dict[str, str]]:
    if os.name != "nt":
        return []

    locations = []
    desktop = Path.home() / "Desktop"
    if desktop.exists() and desktop.is_dir():
        locations.append(
            {
                "name": "Desktop",
                "path": normalize_windows_path(str(desktop)),
                "kind": "folder",
            }
        )
    return locations


def item_metadata(raw_path: str) -> dict[str, Any]:
    path = normalize_windows_path(raw_path)
    _require_windows()
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(path)
    stat = target.stat()
    return {
        **format_path_variants(path),
        "kind": "folder" if target.is_dir() else "file",
        "size": None if target.is_dir() else stat.st_size,
        "modified": stat.st_mtime,
        "exists": True,
    }


def preview_file_path(raw_path: str) -> Path:
    path = normalize_windows_path(raw_path)
    _require_windows()
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(path)
    if target.is_dir():
        raise IsADirectoryError(path)
    return target


def preview_media_type(raw_path: str) -> str:
    path = normalize_windows_path(raw_path)
    target = Path(path)
    suffix = target.suffix.lower()
    name = target.name.lower()

    if suffix in TEXT_EXTENSIONS or name in TEXT_FILENAMES:
        return "text/plain; charset=utf-8"
    if suffix in MEDIA_TYPES:
        return MEDIA_TYPES[suffix]

    guessed, _ = mimetypes.guess_type(path)
    if guessed and (guessed.startswith("image/") or guessed.startswith("audio/") or guessed.startswith("video/")):
        return guessed
    return "application/octet-stream"


def open_in_explorer(raw_path: str) -> None:
    path = normalize_windows_path(raw_path)
    _require_windows()
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(path)
    subprocess.Popen(["explorer.exe", path])


def paste_item(
    raw_source_path: str,
    raw_destination_folder_path: str,
    operation: str,
    protected_paths: Iterable[Path] = (),
) -> dict[str, Any]:
    source_path = normalize_windows_path(raw_source_path)
    destination_folder_path = normalize_windows_path(raw_destination_folder_path)
    normalized_operation = str(operation or "").strip().lower()
    if normalized_operation not in {"copy", "cut"}:
        raise FileOperationSafetyError("Paste operation must be copy or cut.")

    _require_windows()
    source = Path(source_path)
    destination_folder = Path(destination_folder_path)
    if _is_drive_root(source_path):
        raise FileOperationSafetyError("Drive roots cannot be copied or moved.")
    if not source.exists():
        raise FileNotFoundError(source_path)
    if normalized_operation == "cut":
        _reject_protected(source, protected_paths, "moved")
    if not destination_folder.exists():
        raise FileNotFoundError(destination_folder_path)
    if not destination_folder.is_dir():
        raise NotADirectoryError(destination_folder_path)

    if source.is_dir():
        _reject_folder_into_itself(source, destination_folder)

    destination = destination_folder / source.name
    if destination.exists():
        raise FileOperationConflictError(str(destination))

    if normalized_operation == "copy":
        if source.is_dir():
            shutil.copytree(source, destination, symlinks=True)
        else:
            shutil.copy2(source, destination)
    else:
        shutil.move(str(source), str(destination))

    return {
        "operation": normalized_operation,
        "path": normalize_windows_path(str(destination)),
        "name": destination.name,
        "kind": "folder" if destination.is_dir() else "file",
    }


def delete_item(raw_path: str, protected_paths: Iterable[Path] = ()) -> dict[str, Any]:
    """Permanently delete a file or folder (nothing goes to the Recycle Bin).

    A symbolic link or junction is removed as a link only: what it points to is never touched.
    Folder contents are removed with shutil.rmtree, which does not follow links or junctions inside.
    """
    path = normalize_windows_path(raw_path)
    _require_windows()
    if _is_drive_root(path):
        raise FileOperationSafetyError("Drive roots cannot be deleted.")

    target = Path(path)
    if not os.path.lexists(target):
        raise FileNotFoundError(path)
    _reject_protected(target, protected_paths, "deleted")

    if _is_link_or_junction(target):
        if getattr(os.lstat(target), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_DIRECTORY:
            os.rmdir(target)  # Removes a directory link/junction itself, never its target.
        else:
            os.unlink(target)
        kind = "link"
    elif target.is_dir():
        shutil.rmtree(target)
        kind = "folder"
    else:
        target.unlink()
        kind = "file"

    return {
        "operation": "delete",
        "path": path,
        "name": target.name,
        "kind": kind,
    }


def prepare_download(raw_path: str, archive_dir: Path) -> PreparedDownload:
    path = normalize_windows_path(raw_path)
    _require_windows()
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(path)

    if target.is_file():
        return PreparedDownload(
            path=target,
            filename=target.name,
            media_type=preview_media_type(path),
            cleanup=False,
        )

    if not target.is_dir():
        raise FileNotFoundError(path)
    if _is_drive_root(path):
        raise FileOperationSafetyError("A whole drive cannot be downloaded. Download a folder inside it instead.")

    archive_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_download_archives(archive_dir)
    files, total_size = _collect_download_files(target, skip_dir=archive_dir)
    free_space = shutil.disk_usage(archive_dir).free
    if total_size + DOWNLOAD_FREE_SPACE_RESERVE > free_space:
        raise FileOperationSafetyError(
            "Not enough free space on the PC to prepare this folder download "
            f"({total_size // (1024 * 1024)} MB of files, {free_space // (1024 * 1024)} MB free)."
        )

    basename = _download_basename(target)
    archive_path = archive_dir / f"{basename}-{uuid4().hex}.zip"
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for child in files:
                archive.write(child, child.relative_to(target).as_posix())
    except BaseException:
        archive_path.unlink(missing_ok=True)
        raise

    return PreparedDownload(
        path=archive_path,
        filename=f"{basename}.zip",
        media_type="application/zip",
        cleanup=True,
    )


def _collect_download_files(target: Path, skip_dir: Path) -> tuple[list[Path], int]:
    """Files to zip, without following links/junctions and without the dashboard's own zip folder."""
    skip = _canonical(skip_dir)
    files: list[Path] = []
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(target, followlinks=False):
        folder = Path(dirpath)
        dirnames[:] = [
            name
            for name in dirnames
            if not _is_link_or_junction(folder / name) and not _is_same_or_inside(_canonical(folder / name), skip)
        ]
        for name in filenames:
            child = folder / name
            if _is_link_or_junction(child):
                continue
            try:
                total_size += child.stat().st_size
            except OSError:
                continue
            files.append(child)
    return files, total_size


def _remove_stale_download_archives(archive_dir: Path) -> None:
    """Remove the dashboard's own leftover folder-download zips (e.g. after an interrupted download)."""
    cutoff = time.time() - STALE_DOWNLOAD_ARCHIVE_SECONDS
    for archive in archive_dir.glob("*.zip"):
        try:
            if _DOWNLOAD_ARCHIVE_NAME.search(archive.name) and archive.stat().st_mtime < cutoff:
                archive.unlink()
        except OSError:
            continue


def _is_link_or_junction(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT) and (
        getattr(info, "st_reparse_tag", None) == stat.IO_REPARSE_TAG_MOUNT_POINT
    )


def _reject_protected(target: Path, protected_paths: Iterable[Path], verb: str) -> None:
    candidate = _canonical(target)
    for protected in protected_paths:
        guarded = _canonical(protected)
        if _is_same_or_inside(candidate, guarded) or _is_same_or_inside(guarded, candidate):
            raise FileOperationSafetyError(
                f"The dashboard's own folders (and folders containing them) cannot be {verb} from the dashboard."
            )


def _canonical(path: Path) -> str:
    return os.path.normcase(os.path.realpath(path))


def _is_same_or_inside(child: str, parent: str) -> bool:
    parent = parent.rstrip("\\/")
    return child == parent or child.startswith(parent + os.sep)


def _download_basename(target: Path) -> str:
    name = target.name or target.anchor.replace(":\\", "-drive").replace(":", "-drive")
    cleaned = "".join("-" if char in WINDOWS_FORBIDDEN_FILENAME_CHARS or ord(char) < 32 else char for char in name).strip(" .")
    return cleaned or "download"


def _is_drive_root(path: str) -> bool:
    return len(path) == 3 and path[1:] == ":\\"


def _reject_folder_into_itself(source: Path, destination_folder: Path) -> None:
    try:
        destination_folder.resolve().relative_to(source.resolve())
    except ValueError:
        return
    raise FileOperationSafetyError("Folders cannot be pasted into themselves or their descendants.")


def upload_file_to_folder(raw_folder_path: str, raw_filename: str, source: BinaryIO) -> dict[str, Any]:
    folder_path = normalize_windows_path(raw_folder_path)
    filename = sanitize_upload_filename(raw_filename)
    _require_windows()
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(folder_path)
    if not folder.is_dir():
        raise NotADirectoryError(folder_path)

    target = folder / filename
    if target.exists():
        raise UploadConflictError(str(target))

    temp_target = folder / f".{filename}.upload-{uuid4().hex}.tmp"
    bytes_written = 0
    try:
        with temp_target.open("xb") as handle:
            while True:
                chunk = source.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                bytes_written += len(chunk)
        if target.exists():
            raise UploadConflictError(str(target))
        try:
            temp_target.rename(target)
        except FileExistsError as exc:
            raise UploadConflictError(str(target)) from exc
    except Exception:
        try:
            temp_target.unlink(missing_ok=True)
        finally:
            raise

    return {
        "name": filename,
        "path": normalize_windows_path(str(target)),
        "size": bytes_written,
    }


def sanitize_upload_filename(raw_filename: str) -> str:
    if not isinstance(raw_filename, str) or not raw_filename.strip():
        raise UploadNameError("Upload filename is required.")

    filename = raw_filename.strip()
    if "/" in filename or "\\" in filename:
        raise UploadNameError("Upload filename cannot contain path separators.")
    if filename in {".", ".."}:
        raise UploadNameError("Upload filename is not allowed.")
    if filename.endswith((" ", ".")):
        raise UploadNameError("Upload filename cannot end with a space or period.")
    if any(char in WINDOWS_FORBIDDEN_FILENAME_CHARS or ord(char) < 32 for char in filename):
        raise UploadNameError("Upload filename contains characters Windows cannot store.")

    stem = filename.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        raise UploadNameError("Upload filename is reserved on Windows.")
    return filename


def _require_windows() -> None:
    if os.name != "nt":
        raise FilesystemUnavailable("Windows filesystem access is only available on the PC.")


def path_variants(raw_path: str) -> dict[str, str]:
    try:
        return format_path_variants(raw_path)
    except PathError:
        raise
