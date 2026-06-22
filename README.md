<p align="center">
  <img src="pc_drive_dashboard/static/app-icon.png" alt="Gateway Dashboard logo" width="112" height="112">
</p>

# Gateway Dashboard

<p align="center">
  <a href="https://github.com/gkaragioul/Gateway_Dashboard/releases/latest">
    <img src="https://img.shields.io/badge/Download-Latest%20release-2ea44f?style=for-the-badge" alt="Download latest release">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="MIT License">
  </a>
</p>

Gateway Dashboard is a self-hosted browser dashboard for browsing a Windows storage PC over a private network such as Tailscale. It gives a lightweight web UI for drive overview, folder navigation, file previews, path copying, and audit logs without opening a full remote desktop session.

## Features

- Password setup and trusted-browser login sessions.
- Tailscale/loopback-first bind guard with an explicit public-bind override.
- Windows drive overview cards.
- Fast folder explorer with single-click folder navigation.
- Desktop quick shortcut for browsing and uploading to the Windows Desktop.
- Folder uploads from the browser into the selected Windows folder.
- Dashboard previews for images, video, audio, PDF, and text files.
- Preview-window actions menu for copy/open workflows.
- Right-click file and folder actions.
- Copy Windows, SSH-style, POSIX-style, and item-name path variants.
- JSONL audit log for authentication and filesystem actions.
- App logo, favicon, and dashboard styling included.

## Download

Use the latest packaged source from the releases page:

[Download the latest release](https://github.com/gkaragioul/Gateway_Dashboard/releases/latest)

## Install From Source

Requirements:

- Python 3.11+
- Windows for live filesystem browsing
- Tailscale or another private network if you want remote browser access

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

Local-only development:

```bash
python -m pc_drive_dashboard --host 127.0.0.1 --port 8787
```

Windows private-network run:

```powershell
$env:PCDD_HOME = "G:\Tools\GatewayDashboard"
.\.venv\Scripts\python.exe -m pc_drive_dashboard --host 100.x.y.z --port 8787
```

Then open:

```text
http://127.0.0.1:8787
```

or your private-network host/IP.

## Configuration

Gateway Dashboard stores config, logs, and runtime data under `PCDD_HOME` by default. You can override individual locations:

```text
PCDD_HOME
PCDD_CONFIG_DIR
PCDD_LOG_DIR
PCDD_DATA_DIR
```

Default Windows-style layout:

```text
G:\Tools\GatewayDashboard\config\config.json
G:\Tools\GatewayDashboard\logs\dashboard.jsonl
G:\Tools\GatewayDashboard\data
```

## Security Notes

- Do not expose this app directly to the public internet.
- Prefer binding to `127.0.0.1` or a Tailscale/private-network address.
- Use `--allow-public-bind` only when you intentionally understand the network exposure.
- The app stores salted password hashes, not raw passwords.
- File browsing and preview routes are intended for trusted personal/admin use on systems you own or administer.
- Uploads write files to the selected folder, reject unsafe Windows filenames, and do not silently overwrite existing files.
- Gateway Dashboard is independent software and is not affiliated with, endorsed by, or sponsored by Tailscale.

## Development

Run tests:

```bash
python -m unittest discover -s tests
node --check pc_drive_dashboard/static/app.js
```

Generate/update macOS icon assets:

```bash
python scripts/generate_icon.py
```

## License

Gateway Dashboard is released under the MIT License. See [LICENSE](LICENSE).
