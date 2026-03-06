#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN=".venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[whisperkey] Missing or broken local virtual environment: $PYTHON_BIN"
  echo "[whisperkey] Recreate .venv with Python 3.10+ and reinstall dependencies."
  echo "[whisperkey] Example:"
  echo "  python3.12 -m venv .venv"
  echo "  .venv/bin/python -m pip install -e ."
  exit 1
fi

exec env WHISPERKEY_MODEL="${WHISPERKEY_MODEL:-small}" \
  "$PYTHON_BIN" -m whisperkey_mac.main "$@"
