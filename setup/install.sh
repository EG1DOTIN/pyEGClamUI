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
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/setup.py" ] && [ -d "$SCRIPT_DIR/../src/pyegclamui" ]; then
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
elif [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/../setup.py" ] && [ -d "$SCRIPT_DIR/../../src/pyegclamui" ]; then
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd || echo "")"
elif [ -f "./setup/setup.py" ] && [ -d "./src/pyegclamui" ]; then
    PROJECT_ROOT="$(pwd)"
elif [ -f "../setup/setup.py" ] && [ -d "../src/pyegclamui" ]; then
    PROJECT_ROOT="$(cd .. 2>/dev/null && pwd || echo "")"
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
        echo -e "${CYAN}[*] Installing Python3, venv, and build tools via apt (requires sudo)...${RESET}"
        sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip python3-dev build-essential
        PYTHON_BIN="python3"
    elif command -v dnf &>/dev/null; then
        echo -e "${CYAN}[*] Installing Python3 via dnf...${RESET}"
        sudo dnf install -y python3 python3-pip python3-devel gcc
        PYTHON_BIN="python3"
    elif command -v pacman &>/dev/null; then
        echo -e "${CYAN}[*] Installing Python3 via pacman...${RESET}"
        sudo pacman -S --noconfirm python python-pip base-devel
        PYTHON_BIN="python3"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            echo -e "${CYAN}[*] Installing Python3 via Homebrew...${RESET}"
            brew install python
            PYTHON_BIN="python3"
        else
            echo -e "${RED}[X] Python 3.9+ or Homebrew is required on macOS.${RESET}"
            echo -e "${CYAN}[*] Please install Python from https://www.python.org or install Homebrew via https://brew.sh${RESET}"
            exit 1
        fi
    elif command -v brew &>/dev/null; then
        echo -e "${CYAN}[*] Installing Python3 via Homebrew...${RESET}"
        brew install python
        PYTHON_BIN="python3"
    else
        echo -e "${RED}[X] Please install Python 3.9 or higher before running setup.${RESET}"
        exit 1
    fi
fi

# Linux-Specific Verification: ensure python3-venv, build tools, and Qt6 GUI libraries are present
if [[ "$OSTYPE" == "linux"* ]]; then
    if command -v apt-get &>/dev/null; then
        # Check if venv and ensurepip work
        if ! "$PYTHON_BIN" -c "import venv, ensurepip" &>/dev/null; then
            echo -e "${YELLOW}[!] Installing required python3-venv and build tools via apt (requires sudo)...${RESET}"
            sudo apt-get update && sudo apt-get install -y python3-venv python3-pip python3-dev build-essential
        fi

        # Check Qt6 runtime shared libraries
        MISSING_QT_LIBS=""
        for pkg in libgl1 libegl1 libxkbcommon-x11-0 libdbus-1-3 libxcb-cursor0; do
            if ! dpkg -s "$pkg" &>/dev/null; then
                MISSING_QT_LIBS="$MISSING_QT_LIBS $pkg"
            fi
        done
        if [ -n "$MISSING_QT_LIBS" ]; then
            echo -e "${CYAN}[*] Installing Qt6/PySide6 system GUI libraries via apt...${RESET}"
            sudo apt-get install -y $MISSING_QT_LIBS || echo -e "${YELLOW}[!] Warning: Some Qt libraries could not be auto-installed. PySide6 will rely on system defaults.${RESET}"
        fi

        # Check Tkinter availability for pyEGClamUI Lite GUI (especially on 32-bit or low-RAM systems)
        if ! "$PYTHON_BIN" -c "import tkinter" &>/dev/null; then
            echo -e "${CYAN}[*] Installing python3-tk for pyEGClamUI Lite GUI...${RESET}"
            sudo apt-get install -y python3-tk || echo -e "${YELLOW}[!] Warning: python3-tk could not be auto-installed.${RESET}"
        fi

        # Check for 32-bit architecture (antiX / Debian i386/i686)
        ARCH=$(dpkg --print-architecture 2>/dev/null || uname -m)
        if [[ "$ARCH" == *"i386"* || "$ARCH" == *"i686"* ]]; then
            echo -e "${YELLOW}[!] 32-bit architecture detected ($ARCH).${RESET}"
            echo -e "${GREEN}[+] pyEGClamUI Lite (Tkinter GUI) is qualified and ready for this machine.${RESET}"
        fi
    elif command -v dnf &>/dev/null; then
        if ! "$PYTHON_BIN" -c "import venv, ensurepip" &>/dev/null; then
            sudo dnf install -y python3-devel gcc mesa-libGL libxkbcommon-x11 xcb-util-cursor python3-tkinter || true
        fi
        if ! "$PYTHON_BIN" -c "import tkinter" &>/dev/null; then
            sudo dnf install -y python3-tkinter || true
        fi
    elif command -v pacman &>/dev/null; then
        if ! "$PYTHON_BIN" -c "import venv, ensurepip" &>/dev/null; then
            sudo pacman -S --noconfirm --needed base-devel libxkbcommon-x11 xcb-util-cursor tk || true
        fi
        if ! "$PYTHON_BIN" -c "import tkinter" &>/dev/null; then
            sudo pacman -S --noconfirm --needed tk || true
        fi
    fi
fi

echo -e "${GREEN}[+] Python environment verified: $($PYTHON_BIN --version)${RESET}"

# 3. Hand off to setup.py
"$PYTHON_BIN" "$PROJECT_ROOT/setup/setup.py" "$@"
