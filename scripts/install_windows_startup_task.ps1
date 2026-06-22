param(
    [string]$TaskName = "GatewayDashboard",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8787,
    [string]$BaseDir = "G:\Tools\GatewayDashboard"
)

$ErrorActionPreference = "Stop"

$AppDir = Join-Path $BaseDir "app"
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"
$RunnerScript = Join-Path $AppDir "scripts\run_windows_dashboard.ps1"
$LauncherScript = Join-Path $AppDir "scripts\run_windows_dashboard_hidden.vbs"

if (!(Test-Path -LiteralPath $PythonExe)) {
    throw "Dashboard Python executable not found: $PythonExe"
}

if (!(Test-Path -LiteralPath $RunnerScript)) {
    throw "Dashboard runner script not found: $RunnerScript"
}

$escapedRunnerScript = $RunnerScript.Replace('"', '""')
$escapedBaseDir = $BaseDir.Replace('"', '""')
$launcherBody = @"
Set shell = CreateObject("WScript.Shell")
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$escapedRunnerScript"" -HostAddress $HostAddress -Port $Port -BaseDir ""$escapedBaseDir""", 0, False
"@
Set-Content -LiteralPath $LauncherScript -Value $launcherBody -Encoding ASCII

$arguments = "//B //NoLogo `"$LauncherScript`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $arguments -WorkingDirectory $AppDir
$triggerAtLogon = New-ScheduledTaskTrigger -AtLogOn
$triggerAtStartup = New-ScheduledTaskTrigger -AtStartup
$triggerWatchdog = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 1) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger @($triggerAtStartup, $triggerAtLogon, $triggerWatchdog) `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State, TaskPath
Get-NetTCPConnection -LocalAddress $HostAddress -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, State, OwningProcess
