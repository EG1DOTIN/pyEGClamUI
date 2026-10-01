<#
================================================================================
pyEGClamUI - ClamAV Daemon Windows Service Installer & Activator
================================================================================
Self-elevates to Administrator to configure clamd.conf, freshclam.conf,
registers the "ClamAV ClamD" Windows Service, and starts it on TCP 3310.
================================================================================
#>

[CmdletBinding()]
param(
    [string]$ClamDir = ""
)

$ErrorActionPreference = "Stop"

if (-not $ClamDir -or -not (Test-Path $ClamDir)) {
    $Candidates = @(
        "C:\Program Files\ClamAV",
        "C:\Program Files (x86)\ClamAV",
        "$env:LOCALAPPDATA\Programs\ClamAV"
    )
    $FoundCmd = Get-Command clamscan.exe -ErrorAction SilentlyContinue
    if ($FoundCmd) {
        $Candidates = @(Split-Path (Split-Path $FoundCmd.Source -Parent) -Parent), (Split-Path $FoundCmd.Source -Parent) + $Candidates
    }

    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path (Join-Path $Candidate "clamd.exe"))) {
            $ClamDir = $Candidate
            break
        }
    }
}

if (-not $ClamDir -or -not (Test-Path (Join-Path $ClamDir "clamd.exe"))) {
    Write-Host "[!] ClamAV clamd.exe not found in candidates or PATH." -ForegroundColor Red
    Write-Host "    Please ensure ClamAV is installed before configuring the service."
    Exit 1
}

$ClamdExe = Join-Path $ClamDir "clamd.exe"

# 1. Self-Elevate to Administrator if running in a standard user session
$CurrentPrincipal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
$IsAdmin = $CurrentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $IsAdmin) {
    Write-Host "[*] Administrator privileges required to configure Windows Services." -ForegroundColor Yellow
    Write-Host "[*] Requesting UAC elevation..." -ForegroundColor Cyan
    try {
        $ArgList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -ClamDir `"$ClamDir`""
        Start-Process powershell -Verb RunAs -Wait -ArgumentList $ArgList
        Write-Host "[+] Elevated configuration process completed." -ForegroundColor Green
        Exit 0
    } catch {
        Write-Host "[X] UAC elevation was declined by user: $_" -ForegroundColor Red
        Exit 1
    }
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "   ClamAV Resident Daemon (clamd) Service Installer   " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

# 2. Configure clamd.conf
$ClamdConf = Join-Path $ClamDir "clamd.conf"
$SampleClamd = Join-Path $ClamDir "conf_examples\clamd.conf.sample"

if (-not (Test-Path $ClamdConf)) {
    if (Test-Path $SampleClamd) {
        Write-Host "[*] Generating clamd.conf from sample..." -ForegroundColor Cyan
        $Content = Get-Content $SampleClamd
        $NewLines = @()
        foreach ($Line in $Content) {
            if ($Line -match "^Example") {
                $NewLines += "#Example"
            } else {
                $NewLines += $Line
            }
        }
        $NewLines += ""
        $NewLines += "# Added by pyEGClamUI for sub-20ms real-time protection"
        $NewLines += "TCPSocket 3310"
        $NewLines += "TCPAddr 127.0.0.1"
        $NewLines | Set-Content -Path $ClamdConf -Encoding UTF8
        Write-Host "[+] Created $ClamdConf with TCPSocket 3310 enabled." -ForegroundColor Green
    } else {
        Write-Host "[!] Sample clamd configuration not found at: $SampleClamd" -ForegroundColor Yellow
    }
} else {
    Write-Host "[+] clamd.conf already exists." -ForegroundColor Green
}

# 3. Configure freshclam.conf
$FcConf = Join-Path $ClamDir "freshclam.conf"
$SampleFc = Join-Path $ClamDir "conf_examples\freshclam.conf.sample"

if (-not (Test-Path $FcConf)) {
    if (Test-Path $SampleFc) {
        Write-Host "[*] Generating freshclam.conf from sample..." -ForegroundColor Cyan
        $ContentFc = Get-Content $SampleFc
        $NewLinesFc = @()
        foreach ($Line in $ContentFc) {
            if ($Line -match "^Example") {
                $NewLinesFc += "#Example"
            } else {
                $NewLinesFc += $Line
            }
        }
        $NewLinesFc | Set-Content -Path $FcConf -Encoding UTF8
        Write-Host "[+] Created $FcConf." -ForegroundColor Green
    }
} else {
    Write-Host "[+] freshclam.conf already exists." -ForegroundColor Green
}

# 4. Install clamd as a Windows Service
Write-Host "[*] Registering clamd as a Windows Service..." -ForegroundColor Cyan
try {
    & $ClamdExe --install-service
    Write-Host "[+] Windows Service registered." -ForegroundColor Green
} catch {
    Write-Host "[!] Service registration message: $_" -ForegroundColor Yellow
}

# 5. Start Service
Write-Host "[*] Starting 'ClamAV ClamD' service..." -ForegroundColor Cyan
try {
    Start-Service -Name "ClamAV ClamD"
    Write-Host "[+] Service start command executed." -ForegroundColor Green
} catch {
    Write-Host "[!] Service start warning: $_" -ForegroundColor Yellow
}

# 6. Verify Service State
Start-Sleep -Seconds 2
$Svc = Get-Service -Name "ClamAV ClamD" -ErrorAction SilentlyContinue
if ($Svc -and $Svc.Status -eq "Running") {
    Write-Host ""
    Write-Host "[+] SUCCESS: 'ClamAV ClamD' is RUNNING on TCP 3310!" -ForegroundColor Green
    Write-Host "    pyEGClamUI will now stream real-time scans in ~20ms." -ForegroundColor Green
} else {
    Write-Host "[!] Service current state: $($Svc.Status)" -ForegroundColor Yellow
}

Write-Host ""
Start-Sleep -Seconds 2
