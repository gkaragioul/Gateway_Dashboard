#!/usr/bin/env python3
"""Add the dashboard launcher to the macOS Dock without requiring dockutil."""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path


APP_PATH = Path.home() / "Applications" / "Gateway Dashboard.app"
DOCK_PLIST = Path.home() / "Library" / "Preferences" / "com.apple.dock.plist"
LEGACY_LABELS = {"PC Drive Dashboard"}
LEGACY_APP_NAMES = {"PC Drive Dashboard.app"}


def main() -> None:
    if not APP_PATH.exists():
        raise SystemExit(f"Missing app: {APP_PATH}")

    if DOCK_PLIST.exists():
        with DOCK_PLIST.open("rb") as handle:
            dock = plistlib.load(handle)
    else:
        dock = {}

    apps = dock.setdefault("persistent-apps", [])
    app_url = APP_PATH.resolve().as_uri() + "/"
    label = APP_PATH.stem

    filtered = []
    for item in apps:
        tile_data = item.get("tile-data", {})
        file_data = tile_data.get("file-data", {})
        file_url = file_data.get("_CFURLString", "")
        file_label = tile_data.get("file-label")
        file_name = file_url.rstrip("/").split("/")[-1].replace("%20", " ")
        if file_url == app_url or file_label == label:
            continue
        if file_label in LEGACY_LABELS or file_name in LEGACY_APP_NAMES:
            continue
        filtered.append(item)

    filtered.append(
        {
            "tile-data": {
                "file-data": {
                    "_CFURLString": app_url,
                    "_CFURLStringType": 15,
                },
                "file-label": label,
                "file-mod-date": 0,
                "file-type": 41,
                "parent-mod-date": 0,
            },
            "tile-type": "file-tile",
        }
    )
    dock["persistent-apps"] = filtered

    with DOCK_PLIST.open("wb") as handle:
        plistlib.dump(dock, handle)

    subprocess.run(["killall", "Dock"], check=False)
    print(app_url)


if __name__ == "__main__":
    main()
