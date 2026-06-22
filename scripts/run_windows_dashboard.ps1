param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8787,
    [string]$BaseDir = "G:\Tools\GatewayDashboard"
)

$ErrorActionPreference = "Stop"

$AppDir = Join-Path $BaseDir "app"
$LogDir = Join-Path $BaseDir "logs"
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"
$OutLog = Join-Path $LogDir "service.out.log"
$ErrLog = Join-Path $LogDir "service.err.log"
$StatusLog = Join-Path $LogDir "service.status.log"

New-Item -ItemType Directory -Force $LogDir | Out-Null

$existing = Get-NetTCPConnection -LocalAddress $HostAddress -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $timestamp = Get-Date -Format o
    Add-Content -LiteralPath $StatusLog -Value "$timestamp already listening on $HostAddress`:$Port pid=$($existing.OwningProcess)"
    exit 0
}

if (!(Test-Path -LiteralPath $PythonExe)) {
    throw "Dashboard Python executable not found: $PythonExe"
}

$env:PCDD_HOME = $BaseDir
Set-Location $AppDir
$process = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList @("-m", "pc_drive_dashboard", "--host", $HostAddress, "--port", "$Port") `
    -WorkingDirectory $AppDir `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -WindowStyle Hidden `
    -PassThru

$timestamp = Get-Date -Format o
Add-Content -LiteralPath $StatusLog -Value "$timestamp started dashboard pid=$($process.Id) on $HostAddress`:$Port"
exit 0
