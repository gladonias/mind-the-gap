# Mind the Gap — Install Script (Windows PowerShell)
# Usage: irm https://raw.githubusercontent.com/<repo>/install.ps1 | iex

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  Mind the Gap — Installer" -ForegroundColor White
Write-Host ""

# --- Check Python ---
$python = $null
foreach ($cmd in @("python3", "python", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 9) {
                $python = $cmd
                Write-Host "  ✓  Found $ver" -ForegroundColor Green
                break
            }
        }
    } catch {
        continue
    }
}

if (-not $python) {
    Write-Host "  ✗  Python 3.9+ is required." -ForegroundColor Red
    Write-Host "     Download from: https://python.org" -ForegroundColor Yellow
    exit 1
}

# --- Check pipx ---
$usePipx = $false
try {
    & pipx --version 2>&1 | Out-Null
    $usePipx = $true
    Write-Host "  ✓  Found pipx" -ForegroundColor Green
} catch {
    Write-Host "  ℹ  pipx not found — will use pip" -ForegroundColor Cyan
}

# --- Install ---
Write-Host ""
Write-Host "  Installing Mind the Gap..." -ForegroundColor Cyan
Write-Host ""

if ($usePipx) {
    try {
        & pipx install mind-the-gap
    } catch {
        Write-Host "  ⚠  PyPI install failed, trying local install..." -ForegroundColor Yellow
        & pipx install .
    }
} else {
    try {
        & $python -m pip install --user mind-the-gap
    } catch {
        Write-Host "  ⚠  PyPI install failed, trying local install..." -ForegroundColor Yellow
        & $python -m pip install --user .
    }
}

# --- Verify ---
Write-Host ""
try {
    $mtgVer = & mtg --version 2>&1
    Write-Host "  ✓  Installed $mtgVer" -ForegroundColor Green
} catch {
    Write-Host "  ⚠  mtg may not be on your PATH." -ForegroundColor Yellow
    Write-Host "     Try restarting your terminal, or check:" -ForegroundColor Yellow
    $userScripts = & $python -c "import site; print(site.getusersitepackages().replace('site-packages','Scripts'))" 2>&1
    Write-Host "     $userScripts" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "  Setup" -ForegroundColor White
Write-Host ""
Write-Host "  Run " -NoNewline
Write-Host "mtg init" -ForegroundColor Cyan -NoNewline
Write-Host " to choose where to store your study plans."
Write-Host "  Then " -NoNewline
Write-Host "mtg help" -ForegroundColor Cyan -NoNewline
Write-Host " to see all available commands."
Write-Host ""
