#!/usr/bin/env bash
# PWD Estimator — macOS / Linux launcher. First run installs everything; later runs just start the app.
set -e
cd "$(dirname "$0")"
echo
echo "  ====================================================="
echo "    PWD Estimator  -  Drawings to PWD cost estimate"
echo "  ====================================================="
echo

# ---- 1. Python 3.10-3.12 ----
PY=""
for c in python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "[setup] Python 3.12 not found - installing with Homebrew (one time)..."
    brew install python@3.12 && PY="$(brew --prefix)/bin/python3.12"
  elif command -v apt-get >/dev/null 2>&1; then
    echo "[setup] Python 3.12 not found - installing with apt (may ask for your password)..."
    sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip && PY=python3
  fi
fi
if [ -z "$PY" ]; then
  echo "[ERROR] Python 3.12 is needed. Install it from https://www.python.org/downloads/ and run ./start.sh again."
  exit 1
fi

# ---- 2. Private environment for the app ----
if [ ! -x ".venv/bin/python" ]; then
  echo "[setup] Creating the app environment..."
  "$PY" -m venv .venv
fi

# ---- 3. One-time setup: libraries, Llama engine, model files, SearXNG ----
if [ ! -f ".setup_done" ]; then
  .venv/bin/python tools/setup_local.py
fi

# ---- 4. Run ----
exec .venv/bin/python tools/run_local.py
