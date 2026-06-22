import os
import mimetypes
import subprocess
from pathlib import Path
from typing import Any

from .path_utils import PathError, format_path_variants, normalize_windows_path


class FilesystemUnavailable(RuntimeError):
    """Raised when a Windows filesystem operation cannot run here."""


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


def _require_windows() -> None:
    if os.name != "nt":
        raise FilesystemUnavailable("Windows filesystem access is only available on the PC.")


def path_variants(raw_path: str) -> dict[str, str]:
    try:
        return format_path_variants(raw_path)
    except PathError:
        raise
