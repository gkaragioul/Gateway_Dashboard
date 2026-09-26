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

## Security: read this first

Gateway Dashboard gives whoever logs in a lot of power over the PC it runs on. Please read this before installing it.

- **The password unlocks the whole PC, not one folder.** Anyone who logs in can browse and download every file on every drive that the Windows account running the dashboard can read: documents, photos, browser data, SSH keys, other programs' settings.
- **Uploads can go into any folder that account can write to**, including folders such as Windows Startup. Uploads never overwrite or delete existing files. To make the dashboard read-only, start it with `PCDD_ENABLE_WRITES=0`.
- **"Open on PC" runs files on the PC.** It opens the chosen item with its default Windows program, exactly like double-clicking it there. For programs and scripts (`.exe`, `.bat`, `.cmd`, ...) that means they run. Together with uploads, anyone who has the password can run their own programs on the PC.
- **Treat the dashboard password like the PC's own password**: long, unique, and never shared.
- **Traffic is plain HTTP; the dashboard does not encrypt it.** Use it only on the PC itself, on a trusted home network, or through a VPN such as Tailscale (which encrypts the connection). **Never port-forward it on your router, never put it behind a public tunnel (ngrok, Cloudflare Tunnel, Tailscale Funnel and similar), and never expose it to the internet.** Do not use `--allow-public-bind` on shared or public Wi-Fi.
- **First-run setup is locked to the PC.** Until a password exists, it can only be created from a browser on the PC itself, or with the one-time setup code the dashboard saves on the PC (see [First-run setup](#first-run-setup)). Set the password straight after installing.
- **Wrong passwords are throttled.** After 5 wrong attempts from one device, that device has to wait 30 seconds; each further lockout doubles the wait, up to 15 minutes. The counter is kept in memory and resets when the dashboard restarts.
- **On Windows, settings and logs go to `G:\Tools\GatewayDashboard` unless you set `PCDD_HOME`.** If your PC has no G: drive, or G: is a USB stick or network drive, set `PCDD_HOME` first (see [Configuration](#configuration)).
- Gateway Dashboard is provided **as is, without warranty of any kind**, and you use it at your own risk. See [LICENSE](LICENSE).

## Features

- Password setup and trusted-browser login sessions.
- First-run setup locked to the PC (or a one-time setup code) and lockout after repeated wrong passwords.
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
- Hidden Windows scheduled-task watchdog installer for keeping the dashboard alive without flashing a console window.
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

### First-run setup

While no password exists, the dashboard prints a one-time setup code when it starts and saves it in `setup-code.txt` in its config folder (by default `G:\Tools\GatewayDashboard\config\setup-code.txt`). When it runs through the hidden Windows scheduled task, the printed code goes to `logs\service.out.log`. The code is deleted as soon as the password is set.

- **On the PC itself:** open `http://127.0.0.1:8787` and create the password. No code is needed. This only works when the dashboard listens on `127.0.0.1`.
- **From another device**, for example over Tailscale: open the dashboard, then enter the new password together with the setup code from that file.

### Reset the password or sign out every device

There is no password-change screen yet. Stop the dashboard, delete `config\config.json` (this also signs out every remembered browser), start it again, and set a new password straight away as described in [First-run setup](#first-run-setup).

### Stop or remove the Windows background task

`scripts\install_windows_startup_task.ps1` registers a scheduled task named `GatewayDashboard` that restarts the dashboard every minute if it stops, so closing the Python process alone is not enough:

```powershell
Disable-ScheduledTask -TaskName GatewayDashboard                    # stop automatic restarts
Unregister-ScheduledTask -TaskName GatewayDashboard -Confirm:$false  # remove the task completely
```

Then end the running dashboard `python.exe` process in Task Manager.

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
G:\Tools\GatewayDashboard\config\setup-code.txt   (only until the first password is set)
G:\Tools\GatewayDashboard\logs\dashboard.jsonl
G:\Tools\GatewayDashboard\data
```

Without `PCDD_HOME`, Windows always uses `G:\Tools\GatewayDashboard`; other systems use `~/.gateway-dashboard`.

Uploads are on by default. Set `PCDD_ENABLE_WRITES=0` (or `false`, `no`, `off`) to make the dashboard read-only: uploads are then refused.

## Security Notes

See [Security: read this first](#security-read-this-first). In addition:

- The app refuses to listen on anything other than `127.0.0.1`/`localhost` or a Tailscale address unless you pass `--allow-public-bind`. Use that flag only when you understand the network exposure.
- The app stores salted PBKDF2 password hashes, not raw passwords, and only hashes of browser session tokens.
- File browsing and preview routes are intended for trusted personal/admin use on systems you own or administer.
- Uploads write files to the selected folder, reject unsafe Windows filenames, and do not overwrite existing files.
- Gateway Dashboard is independent software and is not affiliated with, endorsed by, or sponsored by Tailscale.

## Development

Run tests:

```bash
python -m unittest discover -s tests
node --check pc_drive_dashboard/static/app.js
```

The API tests use FastAPI's `TestClient`, which needs `httpx` (`python -m pip install httpx`). Without it they are skipped.

Generate/update macOS icon assets:

```bash
python scripts/generate_icon.py
```

## License

Gateway Dashboard is released under the MIT License and is provided as is, without warranty of any kind. See [LICENSE](LICENSE).
