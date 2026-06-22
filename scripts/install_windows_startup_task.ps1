param(
    [string]$TaskName = "GatewayDashboard",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8787,
    [string]$BaseDir = "G:\Tools\GatewayDashboard"
)

$ErrorActionPreference = "Stop"

$AppDir = Join-Path $BaseDir "app"
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"

if (!(Test-Path -LiteralPath $PythonExe)) {
    throw "Dashboard Python executable not found: $PythonExe"
}

$arguments = "-m pc_drive_dashboard --host $HostAddress --port $Port"
$action = New-ScheduledTaskAction -Execute $PythonExe -Argument $arguments -WorkingDirectory $AppDir
$triggerAtLogon = New-ScheduledTaskTrigger -AtLogOn
$triggerAtStartup = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

try {
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType InteractiveOrPassword -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($triggerAtStartup, $triggerAtLogon) -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null
} catch {
    # Fallback for non-elevated installs: at-logon is enough for the user's normal desktop session.
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggerAtLogon -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null
}

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State, TaskPath
Get-NetTCPConnection -LocalAddress $HostAddress -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, State, OwningProcess
