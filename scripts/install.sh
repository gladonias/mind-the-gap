#!/usr/bin/env bash
set -euo pipefail

# Mind the Gap — Install Script (Linux / macOS)
# Usage: curl -fsSL https://raw.githubusercontent.com/<repo>/install.sh | bash

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

info()  { echo -e "  ${CYAN}ℹ${NC}  $1"; }
ok()    { echo -e "  ${GREEN}✓${NC}  $1"; }
warn()  { echo -e "  ${YELLOW}⚠${NC}  $1"; }
fail()  { echo -e "  ${RED}✗${NC}  $1"; exit 1; }

echo ""
echo -e "  ${BOLD}Mind the Gap${NC} — Installer"
echo ""

# --- Check Python ---
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python 3.9+ is required. Please install Python first: https://python.org"
fi

ok "Found $($PYTHON --version)"

# --- Check pipx or pip ---
USE_PIPX=false
if command -v pipx &>/dev/null; then
    USE_PIPX=true
    ok "Found pipx"
else
    info "pipx not found — will use pip instead"
    info "For a cleaner install, consider: ${CYAN}$PYTHON -m pip install pipx${NC}"
fi

# --- Install ---
echo ""
info "Installing Mind the Gap..."
echo ""

if [ "$USE_PIPX" = true ]; then
    pipx install mind-the-gap 2>&1 || pipx install . 2>&1 || {
        warn "pipx install from PyPI failed, trying local install..."
        pipx install . 2>&1
    }
else
    $PYTHON -m pip install --user mind-the-gap 2>&1 || $PYTHON -m pip install --user . 2>&1 || {
        warn "PyPI install failed, trying local install..."
        $PYTHON -m pip install --user . 2>&1
    }
fi

# --- Verify ---
echo ""
if command -v mtg &>/dev/null; then
    ok "Installed $(mtg --version)"
else
    # Check common user bin paths
    for bindir in "$HOME/.local/bin" "$HOME/.local/pipx/venvs/mind-the-gap/bin"; do
        if [ -f "$bindir/mtg" ]; then
            warn "mtg was installed to ${CYAN}$bindir${NC}"
            warn "Add it to your PATH:"
            echo ""
            echo -e "    export PATH=\"$bindir:\$PATH\""
            echo ""
            warn "Then add that line to your shell config (~/.bashrc, ~/.zshrc, etc.)"
            break
        fi
    done
fi

echo ""
echo -e "  ${BOLD}Setup${NC}"
echo ""
echo -e "  Run ${CYAN}mtg init${NC} to choose where to store your study plans."
echo -e "  Then ${CYAN}mtg help${NC} to see all available commands."
echo ""
