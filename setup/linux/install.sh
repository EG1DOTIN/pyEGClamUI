#!/usr/bin/env bash
# ==============================================================================
# pyEGClamUI - Linux & macOS 1-Liner Bootstrap Installer & Updater
# ==============================================================================
# Usage:
#   curl -sSL https://raw.githubusercontent.com/EG1DOTIN/pyEGClamUI/main/setup/install.sh | bash
#   or from cloned folder:
#   bash setup/install.sh [--install] [--update] [--check] [--uninstall] [--purge-all]
# ==============================================================================

set -e

# Terminal formatting
BOLD="\033[1m"
GREEN="\033[92m"
CYAN="\033[96m"
YELLOW="\033[93m"
RED="\033[91m"
RESET="\033[0m"

echo -e "\n${CYAN}${BOLD}======================================================${RESET}"
echo -e "${CYAN}${BOLD}   pyEGClamUI Linux / macOS Bootstrap Installer       ${RESET}"
echo -e "${CYAN}${BOLD}======================================================${RESET}\n"

# 1. Determine Project Directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/setup.py" ]; then
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
elif [ -f "./setup/setup.py" ]; then
    PROJECT_ROOT="$(pwd)"
else
    TARGET_DIR="$HOME/pyEGClamUI"
    echo -e "${CYAN}[*] Bootstrapping pyEGClamUI in: $TARGET_DIR${RESET}"
    if [ ! -d "$TARGET_DIR" ]; then
        if command -v git &>/dev/null; then
            git clone https://github.com/EG1DOTIN/pyEGClamUI.git "$TARGET_DIR"
            PROJECT_ROOT="$TARGET_DIR"
        else
            echo -e "${RED}[!] Git is required to download the repository. Please install git.${RESET}"
            exit 1
        fi
    else
        PROJECT_ROOT="$TARGET_DIR"
    fi
fi

cd "$PROJECT_ROOT"

# 2. Verify Python 3.9+
PYTHON_BIN=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 9 ]; then
            PYTHON_BIN="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${YELLOW}[!] Python 3.9+ was not detected.${RESET}"
    if command -v apt-get &>/dev/null; then
        echo -e "${CYAN}[*] Installing Python3 and venv via apt (requires sudo)...${RESET}"
        sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
        PYTHON_BIN="python3"
    elif command -v brew &>/dev/null; then
        echo -e "${CYAN}[*] Installing Python3 via Homebrew...${RESET}"
        brew install python
        PYTHON_BIN="python3"
    else
        echo -e "${RED}[X] Please install Python 3.9 or higher before running setup.${RESET}"
        exit 1
    fi
fi

echo -e "${GREEN}[+] Python environment verified: $($PYTHON_BIN --version)${RESET}"

# 3. Hand off to setup.py
"$PYTHON_BIN" "$PROJECT_ROOT/setup/setup.py" "$@"
