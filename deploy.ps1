#Requires -Version 5.1
<#
.SYNOPSIS
    Deploy script for Screen Time Monitor.

.DESCRIPTION
    Automates the full deployment pipeline:
      1. Verify Python 3.11+ is available
      2. Install pip dependencies from requirements.txt
      3. Generate the tray icon (assets/icon.png)
      4. Build the single-file exe with PyInstaller
      5. Install the exe to %LOCALAPPDATA%\ScreenTimeMonitor\
      6. Run first-time setup  (--setup) to create admin credentials
         and register the HKCU auto-start registry key
      7. Print a verification summary

.NOTES
    Run from the project root:
        powershell -ExecutionPolicy Bypass -File deploy.ps1

    To redeploy without re-running setup (you already have auth.json):
        powershell -ExecutionPolicy Bypass -File deploy.ps1 -SkipSetup
#>

[CmdletBinding()]
param(
    [switch]$SkipSetup,         # Pass to skip the --setup dialog (auth.json already exists)
    [switch]$SkipBuild,         # Pass to skip PyInstaller (use existing dist\ScreenTimeMonitor.exe)
    [string]$InstallDir = "$env:LOCALAPPDATA\ScreenTimeMonitor"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Helpers ───────────────────────────────────────────────────────────────────

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "  ► $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg) {
    Write-Host "    ✓ $msg" -ForegroundColor Green
}

function Write-Warn([string]$msg) {
    Write-Host "    ⚠ $msg" -ForegroundColor Yellow
}

function Write-Fail([string]$msg) {
    Write-Host ""
    Write-Host "  ✖ $msg" -ForegroundColor Red
    Write-Host ""
    exit 1
}

# ── Banner ────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "  ║   Screen Time Monitor — Deploy Script    ║" -ForegroundColor Blue
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""

# ── Locate project root (script's own directory) ──────────────────────────────

$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) {
    $ProjectRoot = (Get-Location).Path
}
Set-Location $ProjectRoot
Write-Ok "Project root: $ProjectRoot"

# ── Step 1: Check Python ──────────────────────────────────────────────────────

Write-Step "Checking Python version..."

$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 11) {
                $pythonCmd = $candidate
                Write-Ok "Found: $ver  ($candidate)"
                break
            } else {
                Write-Warn "Found $ver but need 3.11+; trying next..."
            }
        }
    } catch { }
}

if (-not $pythonCmd) {
    Write-Fail "Python 3.11 or later not found. Install from https://python.org and re-run."
}

# ── Step 2: Install dependencies ─────────────────────────────────────────────

Write-Step "Installing pip dependencies..."

& $pythonCmd -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { Write-Fail "pip upgrade failed." }

& $pythonCmd -m pip install -r "$ProjectRoot\requirements.txt"
if ($LASTEXITCODE -ne 0) { Write-Fail "pip install failed. Check requirements.txt." }

Write-Ok "Dependencies installed."

# ── Step 3: Generate tray icon ────────────────────────────────────────────────

Write-Step "Generating tray icon..."

$iconPath = "$ProjectRoot\assets\icon.png"
if (Test-Path $iconPath) {
    Write-Ok "Icon already exists — skipping generation."
} else {
    & $pythonCmd "$ProjectRoot\create_icon.py"
    if ($LASTEXITCODE -ne 0) { Write-Fail "Icon generation failed." }
    Write-Ok "Icon created: $iconPath"
}

# ── Step 4: PyInstaller build ─────────────────────────────────────────────────

$exeSource = "$ProjectRoot\dist\ScreenTimeMonitor.exe"

if ($SkipBuild) {
    Write-Step "Skipping PyInstaller build (-SkipBuild flag set)."
    if (-not (Test-Path $exeSource)) {
        Write-Fail "No existing exe found at: $exeSource"
    }
    Write-Ok "Using existing exe: $exeSource"
} else {
    Write-Step "Building exe with PyInstaller..."
    Write-Warn "This can take 1-3 minutes..."

    & $pythonCmd -m PyInstaller "$ProjectRoot\build.spec" --noconfirm
    if ($LASTEXITCODE -ne 0) { Write-Fail "PyInstaller build failed." }

    if (-not (Test-Path $exeSource)) {
        Write-Fail "Build completed but exe not found at: $exeSource"
    }
    Write-Ok "Build succeeded: $exeSource"
}

# ── Step 5: Install exe ───────────────────────────────────────────────────────

Write-Step "Installing to: $InstallDir"

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Write-Ok "Created install directory."
}

$exeDest = "$InstallDir\ScreenTimeMonitor.exe"
Copy-Item -Path $exeSource -Destination $exeDest -Force
Write-Ok "Copied exe to: $exeDest"

# ── Step 6: First-time setup ──────────────────────────────────────────────────

$authFile = "C:\ProgramData\ScreenTimeMonitor\auth.json"

if ($SkipSetup) {
    Write-Step "Skipping setup (-SkipSetup flag set)."
    if (Test-Path $authFile) {
        Write-Ok "auth.json already exists."
    } else {
        Write-Warn "auth.json not found — you may need to run setup manually:"
        Write-Warn "    $exeDest --setup"
    }
} else {
    Write-Step "Running first-time setup (credential dialog will open)..."

    if (Test-Path $authFile) {
        Write-Warn "auth.json already exists. The setup dialog will overwrite it."
        $confirm = Read-Host "    Continue? [y/N]"
        if ($confirm -notmatch "^[Yy]$") {
            Write-Ok "Skipped setup. Existing credentials kept."
            goto VerifyStep
        }
    }

    & $exeDest --setup
    if ($LASTEXITCODE -ne 0) { Write-Fail "Setup exited with an error." }
    Write-Ok "Setup complete."
}

# ── Step 7: Verify ────────────────────────────────────────────────────────────

:VerifyStep
Write-Step "Verifying deployment..."

# Check exe exists.
if (Test-Path $exeDest) {
    Write-Ok "Executable present: $exeDest"
} else {
    Write-Warn "Executable not found at expected path."
}

# Check auth.json.
if (Test-Path $authFile) {
    Write-Ok "auth.json present: $authFile"
} else {
    Write-Warn "auth.json not found — run: $exeDest --setup"
}

# Check HKCU auto-start registry.
$runKey  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$regVal  = (Get-ItemProperty -Path $runKey -ErrorAction SilentlyContinue).ScreenTimeMonitor
if ($regVal) {
    Write-Ok "Auto-start registered: $regVal"
} else {
    Write-Warn "Auto-start key not found. It is registered during --setup."
}

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "  ══════════════════════════════════════════════" -ForegroundColor Blue
Write-Host "  Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Exe  : $exeDest"
Write-Host "  Data : C:\ProgramData\ScreenTimeMonitor\"
Write-Host "  Dashboard: http://127.0.0.1:5055  (after launch)"
Write-Host ""
Write-Host "  To start now:" -ForegroundColor Cyan
Write-Host "    Start-Process '$exeDest'"
Write-Host ""
Write-Host "  To deploy to another user account, log into that" -ForegroundColor Cyan
Write-Host "  account and re-run this script with -SkipBuild:" -ForegroundColor Cyan
Write-Host "    powershell -ExecutionPolicy Bypass -File deploy.ps1 -SkipBuild"
Write-Host "  ══════════════════════════════════════════════" -ForegroundColor Blue
Write-Host ""
