<#
================================================================================
pyEGClamUI - Windows PowerShell 1-Liner Bootstrap Installer & Updater
================================================================================
Usage:
    .\setup\install.ps1 [-Install] [-Update] [-Check] [-ShortcutsOnly] [-Uninstall] [-Verbose] [-Start]
================================================================================
#>

[CmdletBinding()]
param (
    [switch]$Install,
    [switch]$Update,
    [switch]$Check,
    [switch]$ShortcutsOnly,
    [switch]$Uninstall,
    [switch]$PurgeAll,
    [switch]$Start
)

$ErrorActionPreference = "Stop"

# 0. Self-Elevate to Administrator if needed (required to register Windows background service)
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin -and (-not $Check)) {
    Write-Host "[*] Administrator privileges required to register ClamAV background service." -ForegroundColor Cyan
    Write-Host "[*] Requesting Windows UAC elevation..." -ForegroundColor Cyan
    $ArgStr = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($PSBoundParameters.Count -gt 0) {
        foreach ($k in $PSBoundParameters.Keys) {
            $ArgStr += " -$k"
        }
    }
    try {
        Start-Process powershell -Verb RunAs -ArgumentList $ArgStr
        Exit 0
    } catch {
        Write-Host "[!] UAC elevation declined. Proceeding in standard user mode..." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "     pyEGClamUI Windows Setup & Bootstrap Launcher    " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Determine Project Directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($ScriptDir -and (Test-Path "$ScriptDir\setup.py")) {
    $ProjectRoot = Split-Path -Parent $ScriptDir
} elseif (Test-Path ".\setup\setup.py") {
    $ProjectRoot = (Get-Item ".").FullName
} else {
    # If invoked directly via remote 1-liner in an empty folder, clone repo
    $TargetDir = "$HOME\pyEGClamUI"
    Write-Host "[*] Setting up pyEGClamUI in: $TargetDir" -ForegroundColor Cyan
    if (-not (Test-Path $TargetDir)) {
        if (Get-Command git -ErrorAction SilentlyContinue) {
            git clone https://github.com/EG1DOTIN/pyEGClamUI.git $TargetDir
            $ProjectRoot = $TargetDir
        } else {
            Write-Host "[!] Git not found. Please install Git or download pyEGClamUI repository." -ForegroundColor Red
            Exit 1
        }
    } else {
        $ProjectRoot = $TargetDir
    }
}

Set-Location $ProjectRoot

# 2. Check for Python 3.9+
$PythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PyVer = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($PyVer -and ([version]$PyVer -ge [version]"3.9")) {
        $PythonCmd = "python"
    }
}

if (-not $PythonCmd -and (Get-Command py -ErrorAction SilentlyContinue)) {
    $PyVer = py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($PyVer -and ([version]$PyVer -ge [version]"3.9")) {
        $PythonCmd = "py -3"
    }
}

if (-not $PythonCmd) {
    Write-Host "[!] Python 3.9+ was not detected on this system." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "[*] Installing Python 3.12 via Windows Package Manager (winget)..." -ForegroundColor Cyan
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $PythonCmd = "python"
    } else {
        Write-Host "[X] winget not available. Please install Python >= 3.9 from https://www.python.org/downloads/" -ForegroundColor Red
        Exit 1
    }
}

Write-Host "[+] Python environment verified ($PythonCmd)." -ForegroundColor Green

# 3. Construct Arguments and Hand Off to setup.py
$SetupScript = Join-Path $ProjectRoot "setup\setup.py"
$ArgsList = @()

if ($Check) {
    $ArgsList += "--check"
} elseif ($Update) {
    $ArgsList += "--update"
} elseif ($ShortcutsOnly) {
    $ArgsList += "--shortcuts-only"
} elseif ($Uninstall) {
    $ArgsList += "--uninstall"
    if ($PurgeAll) {
        $ArgsList += "--purge-all"
    }
} else {
    $ArgsList += "--install"
}

if ($Start) {
    $ArgsList += "--start"
}

# Execute master installer
& $PythonCmd $SetupScript @ArgsList
