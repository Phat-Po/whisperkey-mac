#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
SPEC_FILE="${ROOT_DIR}/packaging/macos/WhisperKey.spec"
APP_PATH="${ROOT_DIR}/dist/WhisperKey.app"
ENTITLEMENTS="${ROOT_DIR}/packaging/macos/entitlements.plist"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[whisperkey] Missing local venv Python: ${PYTHON_BIN}" >&2
  echo "[whisperkey] Recreate it with Python 3.10+ before building." >&2
  exit 1
fi

if ! "${PYTHON_BIN}" -m PyInstaller --version >/dev/null 2>&1; then
  echo "[whisperkey] Installing PyInstaller into local .venv..."
  "${PYTHON_BIN}" -m pip install "pyinstaller>=6.0,<7"
fi

echo "[whisperkey] Cleaning previous app build..."
rm -rf "${ROOT_DIR}/dist/WhisperKey" "${APP_PATH}" "${ROOT_DIR}/build/WhisperKey"

echo "[whisperkey] Building WhisperKey.app..."
"${PYTHON_BIN}" -m PyInstaller --clean --noconfirm "${SPEC_FILE}"

if [[ ! -x "${APP_PATH}/Contents/MacOS/WhisperKey" ]]; then
  echo "[whisperkey] Build failed: executable missing at ${APP_PATH}/Contents/MacOS/WhisperKey" >&2
  exit 1
fi

echo "[whisperkey] Applying ad-hoc signature..."
codesign --force --deep --sign - --entitlements "${ENTITLEMENTS}" "${APP_PATH}"

echo "[whisperkey] Inspecting Info.plist..."
plutil -p "${APP_PATH}/Contents/Info.plist"

echo "[whisperkey] Verifying code signature..."
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

echo "[whisperkey] App build complete:"
echo "  ${APP_PATH}"
