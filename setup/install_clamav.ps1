<#
================================================================================
pyEGClamUI - ClamAV Auto-Provisioner via Windows Package Manager (winget)
================================================================================
Checks if ClamAV is installed; if not, silently installs Cisco.ClamAV via winget.
Runs 100% hidden with no visible command console windows.
================================================================================
#>

$ErrorActionPreference = "SilentlyContinue"

# Check if clamscan is already installed
$ClamCandidates = @(
    "C:\Program Files\ClamAV\clamscan.exe",
    "C:\Program Files (x86)\ClamAV\clamscan.exe",
    "$env:LOCALAPPDATA\Programs\ClamAV\clamscan.exe"
)
foreach ($Cand in $ClamCandidates) {
    if (Test-Path $Cand) {
        Exit 0
    }
}

if (Get-Command clamscan.exe -ErrorAction SilentlyContinue) {
    Exit 0
}

# Locate winget.exe (check PATH and Microsoft WindowsApps)
$WingetExe = "winget.exe"
$UserWinget = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\winget.exe"
if (Test-Path $UserWinget) {
    $WingetExe = $UserWinget
} else {
    $Resolved = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WindowsApps" -Filter "winget.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
    if ($Resolved) {
        $WingetExe = $Resolved
    }
}

# Execute silent installation of Cisco.ClamAV
& $WingetExe install --id Cisco.ClamAV -e --silent --accept-package-agreements --accept-source-agreements
Start-Sleep -Seconds 2
Exit 0
