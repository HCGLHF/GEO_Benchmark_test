#requires -version 5.1

[CmdletBinding()]
param(
    [switch]$NoDev,
    [switch]$SkipPlaywright
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message"
}

function Test-PythonVersion {
    param([string]$Version)

    $parts = $Version.Trim().Split(".")
    if ($parts.Count -lt 2) {
        return $false
    }

    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    return ($major -gt 3) -or (($major -eq 3) -and ($minor -ge 11))
}

function Resolve-ProjectPython {
    $candidates = @(
        @{ Exe = "py"; Args = @("-3.11") },
        @{ Exe = "python"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) {
            continue
        }

        $versionArgs = @($candidate.Args) + @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        $version = & $candidate.Exe @versionArgs 2>$null
        if ($LASTEXITCODE -ne 0) {
            continue
        }

        if (Test-PythonVersion -Version $version) {
            return [pscustomobject]@{
                Exe = $candidate.Exe
                Args = @($candidate.Args)
                Version = $version.Trim()
            }
        }
    }

    throw "Python 3.11 or newer was not found. Install Python 3.11+, then rerun .\setup.ps1."
}

$RepoRoot = $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

Write-Step "Resolve Python 3.11+"
Write-Host "Trying py -3.11 first, then python."
$Python = Resolve-ProjectPython
Write-Host "Using $($Python.Exe) $($Python.Args -join ' ') ($($Python.Version))"

$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvDir)) {
    Write-Step "Create .venv with python -m venv"
    $venvArgs = @($Python.Args) + @("-m", "venv", $VenvDir)
    & $Python.Exe @venvArgs
}
else {
    Write-Step "Reuse existing .venv"
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment Python was not found at $VenvPython."
}

Write-Step "Upgrade installer: python -m pip install -U pip"
& $VenvPython -m pip install -U pip

$InstallTarget = if ($NoDev) { "." } else { ".[dev]" }
Write-Step "Install project dependencies: python -m pip install -e $InstallTarget"
& $VenvPython -m pip install -e $InstallTarget

if ($SkipPlaywright) {
    Write-Step "Skip browser install because -SkipPlaywright was provided"
}
else {
    Write-Step "Install Playwright Chromium: python -m playwright install chromium"
    & $VenvPython -m playwright install chromium
}

$EnvExamplePath = Join-Path $RepoRoot ".env.example"
$EnvPath = Join-Path $RepoRoot ".env"

Write-Step "Prepare local .env"
if (-not (Test-Path -LiteralPath $EnvExamplePath)) {
    throw ".env.example was not found."
}

if (Test-Path -LiteralPath $EnvPath) {
    Write-Host ".env already exists; leaving it unchanged."
}
else {
    Copy-Item -LiteralPath $EnvExamplePath -Destination $EnvPath
    Write-Host "Created .env from .env.example. Fill in AWS, RDS, crawler, and LLM credentials before cloud/API runs."
}

Write-Step "Done"
Write-Host "Activate the environment:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Verify shared cloud corpus access after filling .env:"
Write-Host "  python scripts\cloud\verify_cloud_import.py --industry geo-agency --corpus-version 2026-05-22-initial"
Write-Host ""
Write-Host "Start the local UI console:"
Write-Host "  python -m scripts.ui_app.server --host 127.0.0.1 --port 8765"
