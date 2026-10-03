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
    [string]$ClamDir = "",
    [string]$DatabaseDir = ""
)

$ErrorActionPreference = "Stop"

# Log file for debugging and transparency
$LogPath = Join-Path $env:TEMP "pyegclamui_service_setup.log"
function Log-Msg {
    param([string]$Msg)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$Timestamp] $Msg" | Out-File $LogPath -Append -Encoding UTF8
    Write-Host $Msg
}

# Helper to write clean UTF-8 WITHOUT Byte Order Mark (BOM)
function Set-ContentNoBom {
    param(
        [string]$Path,
        $Lines
    )
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($Path, [string[]]$Lines, $Utf8NoBom)
}

# Helper to resolve winget executable
function Get-WingetPath {
    $Cmd = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($Cmd) { return $Cmd.Source }
    $Cand1 = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\winget.exe"
    if (Test-Path $Cand1) { return $Cand1 }
    $Cand2 = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WindowsApps" -Filter "winget.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
    if ($Cand2) { return $Cand2 }
    return "winget.exe"
}

Log-Msg "======================================================"
Log-Msg "   ClamAV Resident Daemon (clamd) Service Installer   "
Log-Msg "======================================================"
Log-Msg "Parameters: ClamDir='$ClamDir', DatabaseDir='$DatabaseDir'"

# 1. Resolve ClamAV installation directory
if (-not $ClamDir -or -not (Test-Path (Join-Path $ClamDir "clamd.exe"))) {
    $AppRoot = Split-Path $PSScriptRoot -Parent
    $Candidates = @(
        "C:\Program Files\ClamAV",
        "C:\Program Files (x86)\ClamAV",
        (Join-Path $AppRoot "engine"),
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

# If still not found, attempt silent installation via winget
if (-not $ClamDir -or -not (Test-Path (Join-Path $ClamDir "clamd.exe"))) {
    Log-Msg "[*] ClamAV not found on system. Installing via winget..."
    $WingetPath = Get-WingetPath
    try {
        & $WingetPath install --id Cisco.ClamAV -e --silent --accept-package-agreements --accept-source-agreements
        Start-Sleep -Seconds 3
        if (Test-Path "C:\Program Files\ClamAV\clamd.exe") {
            $ClamDir = "C:\Program Files\ClamAV"
            Log-Msg "[+] ClamAV successfully installed via winget to $ClamDir"
        }
    } catch {
        Log-Msg "[!] winget installation encountered an error: $_"
    }
}

if (-not $ClamDir -or -not (Test-Path (Join-Path $ClamDir "clamd.exe"))) {
    Log-Msg "[!] ClamAV clamd.exe not found in candidates or PATH."
    Exit 1
}
Log-Msg "[+] ClamAV directory verified: $ClamDir"
$ClamdExe = Join-Path $ClamDir "clamd.exe"

# 2. Shared ProgramData directories (accessible to both LocalSystem and standard users)
$SharedDir = Join-Path $env:ProgramData "ClamAV"
$SharedDb = Join-Path $SharedDir "database"
$SharedLog = Join-Path $SharedDir "clamd.log"

if (-not (Test-Path $SharedDir)) {
    New-Item -ItemType Directory -Path $SharedDir -Force | Out-Null
}
if (-not (Test-Path $SharedDb)) {
    New-Item -ItemType Directory -Path $SharedDb -Force | Out-Null
}

# Copy existing database files if available
$DbSources = @(
    $DatabaseDir,
    (Join-Path $env:LOCALAPPDATA "pyEGClamUI\database"),
    (Join-Path $ClamDir "database")
)
foreach ($Src in $DbSources) {
    if ($Src -and (Test-Path $Src)) {
        $CvdFiles = Get-ChildItem -Path $Src -Filter "*.c*d" -ErrorAction SilentlyContinue
        if ($CvdFiles) {
            Log-Msg "[*] Copying virus signatures from $Src to $SharedDb..."
            Copy-Item -Path "$Src\*.c*d*" -Destination $SharedDb -Force -ErrorAction SilentlyContinue
            Copy-Item -Path "$Src\freshclam.dat" -Destination $SharedDb -Force -ErrorAction SilentlyContinue
            break
        }
    }
}

# If shared database has no definitions, run freshclam once to initialize
$HasDbs = Get-ChildItem -Path $SharedDb -Filter "*.c*d" -ErrorAction SilentlyContinue
if (-not $HasDbs) {
    $FreshclamExe = Join-Path $ClamDir "freshclam.exe"
    if (Test-Path $FreshclamExe) {
        Log-Msg "[*] Downloading initial virus definitions via freshclam..."
        & $FreshclamExe --datadir="$SharedDb" --stdout --quiet 2>$null
    }
}

# Grant Modify permissions on ProgramData\ClamAV so both standard users and SYSTEM have full access
& icacls.exe $SharedDir /grant "*S-1-5-32-545:(OI)(CI)M" "*S-1-5-18:(OI)(CI)F" /Q 2>$null
Log-Msg "[+] Configured shared directory permissions on $SharedDir"

# 3. Self-Elevate to Administrator if running in a standard user session
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
$IsAdmin = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Log-Msg "[*] Elevation status: IsAdmin=$IsAdmin"

if (-not $IsAdmin) {
    Log-Msg "[*] Requesting Windows Administrator elevation..."
    try {
        $ArgList = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden",
            "-File", "`"$PSCommandPath`"",
            "-ClamDir", "`"$ClamDir`"",
            "-DatabaseDir", "`"$SharedDb`""
        )
        $Proc = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList $ArgList
        if ($Proc.ExitCode -eq 0) {
            Log-Msg "[+] Elevated configuration process completed successfully."
            Exit 0
        } else {
            Log-Msg "[!] Elevated configuration process returned exit code $($Proc.ExitCode)."
            Exit $Proc.ExitCode
        }
    } catch {
        Log-Msg "[X] UAC elevation was declined by user: $_"
        Exit 1
    }
}

try {
    # 4. Configure clamd.conf (UTF-8 without BOM, Port 3310, Shared ProgramData)
    $ClamdConf = Join-Path $ClamDir "clamd.conf"
    $SampleClamd = Join-Path $ClamDir "conf_examples\clamd.conf.sample"

    $BaseLines = @()
    if (Test-Path $ClamdConf) {
        Log-Msg "[*] Reading existing clamd.conf..."
        $BaseLines = [System.IO.File]::ReadAllLines($ClamdConf)
    } elseif (Test-Path $SampleClamd) {
        Log-Msg "[*] Generating clamd.conf from sample..."
        $BaseLines = [System.IO.File]::ReadAllLines($SampleClamd)
    }

    $CleanLines = @()
    foreach ($Line in $BaseLines) {
        $Trimmed = $Line.Trim()
        if ($Trimmed -match "^Example\b") {
            $CleanLines += "#Example"
        } elseif ($Trimmed -match "^(TCPSocket|TCPAddr|DatabaseDirectory|LogFile|LogTime|LogClean|LogFileUnlock)\b") {
            continue
        } else {
            $CleanLines += $Line
        }
    }

    $CleanLines += ""
    $CleanLines += "# Added by pyEGClamUI for high-speed local socket daemon"
    $CleanLines += "TCPSocket 3310"
    $CleanLines += "TCPAddr 127.0.0.1"
    $CleanLines += "DatabaseDirectory `"$SharedDb`""
    $CleanLines += "LogFile `"$SharedLog`""
    $CleanLines += "LogClean yes"
    $CleanLines += "LogTime yes"
    $CleanLines += "LogFileUnlock yes"

    Set-ContentNoBom -Path $ClamdConf -Lines $CleanLines
    Log-Msg "[+] Configured $ClamdConf (UTF-8 without BOM, Port 3310, DB: $SharedDb)"

    # Set official ClamAV ConfDir registry key so engine binaries always locate configs
    $ClamReg = "HKLM:\SOFTWARE\ClamAV"
    if (-not (Test-Path $ClamReg)) {
        New-Item -Path $ClamReg -Force | Out-Null
    }
    Set-ItemProperty -Path $ClamReg -Name "ConfDir" -Value $ClamDir -Force
    Log-Msg "[+] Configured official HKLM:\SOFTWARE\ClamAV\ConfDir = $ClamDir"

    # 5. Configure freshclam.conf (UTF-8 without BOM)
    $FcConf = Join-Path $ClamDir "freshclam.conf"
    $SampleFc = Join-Path $ClamDir "conf_examples\freshclam.conf.sample"

    $BaseFcLines = @()
    if (Test-Path $FcConf) {
        $BaseFcLines = [System.IO.File]::ReadAllLines($FcConf)
    } elseif (Test-Path $SampleFc) {
        Log-Msg "[*] Generating freshclam.conf from sample..."
        $BaseFcLines = [System.IO.File]::ReadAllLines($SampleFc)
    }

    $CleanFcLines = @()
    foreach ($Line in $BaseFcLines) {
        $Trimmed = $Line.Trim()
        if ($Trimmed -match "^Example\b") {
            $CleanFcLines += "#Example"
        } elseif ($Trimmed -match "^(DatabaseDirectory|DatabaseMirror|NotifyClamd)\b") {
            continue
        } else {
            $CleanFcLines += $Line
        }
    }

    $CleanFcLines += ""
    $CleanFcLines += "# Added by pyEGClamUI"
    $CleanFcLines += "DatabaseMirror database.clamav.net"
    $CleanFcLines += "DatabaseDirectory `"$SharedDb`""
    $CleanFcLines += "NotifyClamd `"$ClamdConf`""

    Set-ContentNoBom -Path $FcConf -Lines $CleanFcLines
    Log-Msg "[+] Configured $FcConf (UTF-8 without BOM)"

    # 6. Service Management: Register and ensure correct binary path
    $Svc = Get-Service -Name "clamd" -ErrorAction SilentlyContinue
    if (-not $Svc) {
        Log-Msg "[*] Registering clamd as a Windows Service via --install-service..."
        & $ClamdExe --install-service
        Start-Sleep -Seconds 1
        $Svc = Get-Service -Name "clamd" -ErrorAction SilentlyContinue
    }

    # Explicitly configure SCM registry key directly to eliminate CLI quoting errors
    $RegKey = "HKLM:\SYSTEM\CurrentControlSet\Services\clamd"
    if (Test-Path $RegKey) {
        $BinPathValue = "`"$ClamdExe`" --daemon --service-mode"
        Set-ItemProperty -Path $RegKey -Name "ImagePath" -Value $BinPathValue -Force
        Set-ItemProperty -Path $RegKey -Name "Start" -Value 2 -Force   # 2 = Automatic
        Set-ItemProperty -Path $RegKey -Name "ObjectName" -Value "LocalSystem" -Force
        Log-Msg "[+] Configured SCM ImagePath to: $BinPathValue"
    } else {
        Log-Msg "[!] Registry service key $RegKey not found!"
    }

    # Also run sc.exe config to ensure SCM cache is synchronized
    & sc.exe config clamd start= auto 2>$null

    # 7. Start / Restart Service
    Log-Msg "[*] Stopping existing clamd service if running..."
    Stop-Service -Name "clamd" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800

    Log-Msg "[*] Starting clamd service..."
    try {
        Start-Service -Name "clamd" -ErrorAction Stop
        Log-Msg "[+] Start-Service succeeded. Current status: $((Get-Service -Name 'clamd').Status)"
    } catch {
        Log-Msg "[!] Start-Service encountered an error: $_"
        Log-Msg "[*] Attempting fallback startup via net start clamd..."
        & net.exe start clamd 2>&1 | Out-String | ForEach-Object { Log-Msg "  net: $_" }
    }

    # 8. Verify TCP Socket 3310 Connectivity (wait up to 45 seconds for signature database to load)
    Log-Msg "[*] Waiting for ClamD resident daemon to initialize on TCP 3310 (up to 45s)..."
    $Ready = $false
    for ($i = 1; $i -le 45; $i++) {
        try {
            $Tcp = New-Object System.Net.Sockets.TcpClient
            $ConnectTask = $Tcp.ConnectAsync("127.0.0.1", 3310)
            if ($ConnectTask.Wait(1000) -and $Tcp.Connected) {
                $Stream = $Tcp.GetStream()
                $Stream.ReadTimeout = 2000
                $Stream.WriteTimeout = 2000
                $Writer = New-Object System.IO.StreamWriter($Stream)
                $Reader = New-Object System.IO.StreamReader($Stream)
                $Writer.WriteLine("PING")
                $Writer.Flush()
                $Resp = $Reader.ReadLine()
                $Tcp.Close()
                if ($Resp -match "PONG") {
                    $Ready = $true
                    Log-Msg "[+] SUCCESS: ClamD daemon is ONLINE and responding with PONG on TCP 3310 (at ${i}s)!"
                    break
                }
            } else {
                $Tcp.Close()
            }
        } catch {
            # Socket still not ready or definitions loading
        }
        if ($i % 5 -eq 0) {
            $CurrStatus = (Get-Service -Name "clamd" -ErrorAction SilentlyContinue).Status
            Log-Msg "[*] ClamD service is $CurrStatus. Loading signature database into memory (${i}s / 45s)..."
        }
        Start-Sleep -Seconds 1
    }

    if (-not $Ready) {
        $Svc = Get-Service -Name "clamd" -ErrorAction SilentlyContinue
        Log-Msg "[!] ClamD service is $($Svc.Status). Timed out waiting for TCP 3310 response."
        if (Test-Path $SharedLog) {
            $LogTail = Get-Content $SharedLog -Tail 10 -ErrorAction SilentlyContinue
            Log-Msg "[*] Recent clamd.log output:"
            foreach ($Line in $LogTail) {
                Log-Msg "    $Line"
            }
        }
        Exit 1
    }

    Start-Sleep -Milliseconds 500
} catch {
    Log-Msg "[!] Unexpected error during service setup: $_"
    Log-Msg $_.ScriptStackTrace
    Exit 1
}
