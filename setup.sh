#!/usr/bin/env bash
# One-command setup for Linux / macOS / WSL: checks Python, creates .venv, installs the tool.
set -euo pipefail
cd "$(dirname "$0")"

MIN="3.9"
PY=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && \
       "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
        PY="$cand"; break
    fi
done
if [ -z "$PY" ]; then
    echo "ERROR: Python $MIN or newer was not found." >&2
    echo "  Debian/Ubuntu/WSL:  sudo apt install python3 python3-venv python3-pip" >&2
    echo "  macOS (Homebrew):   brew install python" >&2
    echo "  Any system:         https://www.python.org/downloads/" >&2
    exit 1
fi
echo "Using $($PY --version) ($(command -v $PY))"

if ! "$PY" -m venv .venv 2>/dev/null; then
    echo "ERROR: could not create a virtual environment." >&2
    echo "  On Debian/Ubuntu/WSL install it with:  sudo apt install python3-venv" >&2
    exit 1
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet .
.venv/bin/fm-multi-drop --self-test

cat <<'MSG'

Setup complete. Patch a disc image (your own copy) with:

    .venv/bin/fm-multi-drop "path/to/YFM MOD KURIBOH.iso" --drops 10

or activate the environment once and use the short command:

    source .venv/bin/activate
    fm-multi-drop "path/to/YFM MOD KURIBOH.iso" --drops 10
MSG
