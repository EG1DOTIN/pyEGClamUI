#!/usr/bin/env bash
# ==============================================================================
# pyEGClamUI - Linux & macOS Application Launcher
# ==============================================================================
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
cd "$PROJECT_ROOT"

# 1. Check for local virtual environment Python
if [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    exec "$PROJECT_ROOT/.venv/bin/python" -m pyegclamui "$@"
fi

# 2. Check for standalone compiled binary in dist/
if [ -f "$PROJECT_ROOT/dist/pyegclamui" ]; then
    exec "$PROJECT_ROOT/dist/pyegclamui" "$@"
elif [ -f "$PROJECT_ROOT/dist/pyEGClamUI" ]; then
    exec "$PROJECT_ROOT/dist/pyEGClamUI" "$@"
fi

# 3. If environment is not yet initialized, invoke bootstrap installer
echo "======================================================"
echo "   pyEGClamUI - Initializing Environment Setup        "
echo "======================================================"
echo "Local virtual environment (.venv) not found."
echo "Running automated setup engine..."
echo ""

if [ -f "$PROJECT_ROOT/setup/install.sh" ]; then
    bash "$PROJECT_ROOT/setup/install.sh" --start "$@"
else
    python3 "$PROJECT_ROOT/setup/setup.py" --start "$@"
fi
