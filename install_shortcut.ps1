# Create desktop and Start menu shortcuts for Writing Review (写作复利).
# The shortcut starts the local service with pythonw (no console window) and opens the browser.
# If the service is already running, clicking the icon only opens the page.
# Usage (PowerShell):  powershell -ExecutionPolicy Bypass -File install_shortcut.ps1 [-Vault <Obsidian vault folder>]
param(
    [string]$Vault = ""
)
$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "pythonw.exe not found next to $python" }

# Remember the vault once, so later starts need no arguments.
$data = Join-Path $env:LOCALAPPDATA "WritingReview"
New-Item -ItemType Directory -Force $data | Out-Null
$config = Join-Path $data "config.json"
if ($Vault -ne "") {
    $cfg = @{}
    if (Test-Path $config) {
        $old = Get-Content $config -Raw -Encoding UTF8 | ConvertFrom-Json
        $old.PSObject.Properties | ForEach-Object { $cfg[$_.Name] = $_.Value }
    }
    $cfg["vault"] = (Resolve-Path $Vault).Path
    [System.IO.File]::WriteAllText($config, ($cfg | ConvertTo-Json), (New-Object System.Text.UTF8Encoding $false))
}

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "写作复利.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "写作复利.lnk")
)
foreach ($lnk in $targets) {
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = $pythonw
    $s.Arguments = "-X utf8 -m writing_review"
    $s.WorkingDirectory = $project
    $s.Description = "Writing Review 写作复利：本机批注，AI 出方案"
    $s.IconLocation = "$env:SystemRoot\System32\imageres.dll,109"
    $s.Save()
    Write-Output "Shortcut: $lnk"
}
Write-Output "Log file: $(Join-Path $data 'server.log')"
