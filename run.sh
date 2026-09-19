#!/usr/bin/env sh
# =====================================================================
#  Sudoku launcher (macOS / Linux)
#  1) locate a Python 3 interpreter  2) make sure pygame is there
#  3) run the game, passing through any extra arguments
# =====================================================================
set -e
cd "$(dirname "$0")"

PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "[ERROR] Python 3 was not found in PATH." >&2
    echo "        Install it from https://www.python.org/downloads/" >&2
    exit 1
fi

if ! "$PY" -c "import pygame" >/dev/null 2>&1; then
    echo "pygame is not installed, installing it now..."
    if ! "$PY" -m pip install -r requirements.txt; then
        echo "No official pygame wheel for this Python, trying pygame-ce..."
        "$PY" -m pip install pygame-ce
    fi
fi

exec "$PY" sudoku.py "$@"
