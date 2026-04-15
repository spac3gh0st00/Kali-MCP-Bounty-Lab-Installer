#!/usr/bin/env bash
# =============================================================================
# Kali MCP Bounty Lab — Linux Launcher
# Checks / installs python3-tk and customtkinter, then opens the GUI.
# Usage: bash run.sh
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER="${SCRIPT_DIR}/kali_lab_installer.py"

echo ""
echo "  ⚡  Kali MCP Bounty Lab"
echo "  ─────────────────────────────────────"

# ── Python 3 ──────────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "  ✗  python3 not found"
  echo "     sudo apt-get install python3"
  exit 1
fi
echo "  ✓  python3: $(python3 --version 2>&1)"

# ── python3-tk ────────────────────────────────────────────────────────────────
if ! python3 -c "import tkinter" &>/dev/null 2>&1; then
  echo "  ⚠  python3-tk not found — installing..."
  sudo apt-get install -y python3-tk 2>&1
  if python3 -c "import tkinter" &>/dev/null 2>&1; then
    echo "  ✓  python3-tk installed"
  else
    echo "  ✗  python3-tk install failed"
    echo "     Try manually: sudo apt-get install python3-tk"
    exit 1
  fi
else
  echo "  ✓  python3-tk: OK"
fi

# ── customtkinter ─────────────────────────────────────────────────────────────
if ! python3 -c "import customtkinter" &>/dev/null 2>&1; then
  echo "  ⚠  customtkinter not found — installing..."

  # Ensure pip is available at all (some Ubuntu installs don't have it)
  if ! python3 -m pip --version &>/dev/null 2>&1; then
    echo "  ⚠  pip not found — installing python3-pip..."
    sudo apt-get install -y python3-pip 2>&1
  fi

  # Ubuntu 24.04+ blocks system-wide pip installs by default.
  # Try each method in order until one works:
  python3 -m pip install customtkinter --break-system-packages -q 2>&1 \
    || python3 -m pip install customtkinter --user -q 2>&1 \
    || python3 -m pip install customtkinter -q 2>&1 \
    || sudo apt-get install -y python3-customtkinter 2>&1 \
    || true

  if python3 -c "import customtkinter" &>/dev/null 2>&1; then
    echo "  ✓  customtkinter installed"
  else
    echo "  ✗  customtkinter install failed"
    echo "     Run this manually then try again:"
    echo "     python3 -m pip install customtkinter --break-system-packages"
    exit 1
  fi
else
  echo "  ✓  customtkinter: $(python3 -c 'import customtkinter; print(customtkinter.__version__)' 2>/dev/null || echo 'OK')"
fi

# ── Installer script present ──────────────────────────────────────────────────
if [[ ! -f "$INSTALLER" ]]; then
  echo "  ✗  kali_lab_installer.py not found in ${SCRIPT_DIR}"
  exit 1
fi
if [[ ! -f "${SCRIPT_DIR}/install_linux.sh" ]]; then
  echo "  ✗  install_linux.sh not found in ${SCRIPT_DIR}"
  exit 1
fi

# Make install_linux.sh executable
chmod +x "${SCRIPT_DIR}/install_linux.sh" 2>/dev/null || true

echo "  ─────────────────────────────────────"
echo "  Launching installer..."
echo ""

python3 "$INSTALLER"
