#!/usr/bin/env python3
"""Add the dashboard launcher to the macOS Dock without requiring dockutil."""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path


APP_PATH = Path.home() / "Applications" / "Gateway Dashboard.app"
DOCK_PLIST = Path.home() / "Library" / "Preferences" / "com.apple.dock.plist"


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
        file_data = item.get("tile-data", {}).get("file-data", {})
        if file_data.get("_CFURLString") != app_url and item.get("tile-data", {}).get("file-label") != label:
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
