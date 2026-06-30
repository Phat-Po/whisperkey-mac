#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
SPEC_FILE="${ROOT_DIR}/packaging/macos/WhisperKey.spec"
APP_PATH="${ROOT_DIR}/dist/WhisperKey.app"
ENTITLEMENTS="${ROOT_DIR}/packaging/macos/entitlements.plist"
ICON_GENERATOR="${ROOT_DIR}/packaging/macos/generate_icon.py"
BUILD_MODE="${WHISPERKEY_BUILD_MODE:-development}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release)
      BUILD_MODE="release"
      shift
      ;;
    --free-release)
      BUILD_MODE="free-release"
      shift
      ;;
    --development|--dev)
      BUILD_MODE="development"
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--development|--release]"
      echo "  --development  Allow Apple Development or ad-hoc signing for local builds."
      echo "  --release      Require Developer ID Application signing for customer builds."
      echo "  --free-release Create an intentionally ad-hoc signed public free build."
      exit 0
      ;;
    *)
      echo "[whisperkey] Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "${BUILD_MODE}" != "development" && "${BUILD_MODE}" != "release" && "${BUILD_MODE}" != "free-release" ]]; then
  echo "[whisperkey] Invalid WHISPERKEY_BUILD_MODE: ${BUILD_MODE}" >&2
  echo "[whisperkey] Expected: development, release, or free-release" >&2
  exit 2
fi

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

echo "[whisperkey] Generating app icon..."
"${PYTHON_BIN}" "${ICON_GENERATOR}"

echo "[whisperkey] Building WhisperKey.app..."
"${PYTHON_BIN}" -m PyInstaller --clean --noconfirm "${SPEC_FILE}"

if [[ ! -x "${APP_PATH}/Contents/MacOS/WhisperKey" ]]; then
  echo "[whisperkey] Build failed: executable missing at ${APP_PATH}/Contents/MacOS/WhisperKey" >&2
  exit 1
fi

echo "[whisperkey] Stripping extended attributes..."
xattr -cr "${APP_PATH}"

SIGN_IDENTITY="${WHISPERKEY_SIGN_IDENTITY:-}"

if [[ "${BUILD_MODE}" == "release" ]]; then
  if [[ -z "${SIGN_IDENTITY}" ]]; then
    SIGN_IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | awk -F'"' '/Developer ID Application/{print $2; exit}')"
  fi

  if [[ -z "${SIGN_IDENTITY}" ]]; then
    echo "[whisperkey] Release signing failed: no Developer ID Application identity found." >&2
    echo "[whisperkey] Install a Developer ID Application certificate, or set WHISPERKEY_SIGN_IDENTITY explicitly." >&2
    exit 1
  fi

  if [[ "${SIGN_IDENTITY}" != Developer\ ID\ Application:* ]]; then
    echo "[whisperkey] Release signing refused: identity is not Developer ID Application." >&2
    echo "[whisperkey] Current identity: ${SIGN_IDENTITY}" >&2
    exit 1
  fi

  echo "[whisperkey] Signing release with Developer ID identity: ${SIGN_IDENTITY}"
  codesign --force --deep --options runtime --timestamp --sign "${SIGN_IDENTITY}" --entitlements "${ENTITLEMENTS}" "${APP_PATH}"
elif [[ "${BUILD_MODE}" == "free-release" ]]; then
  echo "[whisperkey] Signing free public build with ad-hoc identity."
  echo "[whisperkey] This build is not notarized and will require Gatekeeper manual approval after download."
  codesign --force --deep --options runtime --sign - --entitlements "${ENTITLEMENTS}" "${APP_PATH}"
else
  if [[ -z "${SIGN_IDENTITY}" ]]; then
    SIGN_IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | awk -F'"' '/Apple Development|Developer ID Application/{print $2; exit}')"
  fi

  if [[ -n "${SIGN_IDENTITY}" ]]; then
    echo "[whisperkey] Signing development build with stable identity: ${SIGN_IDENTITY}"
    echo "[whisperkey] (stable identity keeps TCC permission grants across rebuilds on this Mac)"
    codesign --force --deep --timestamp=none --sign "${SIGN_IDENTITY}" --entitlements "${ENTITLEMENTS}" "${APP_PATH}"
  else
    echo "[whisperkey] WARNING: no signing identity found — falling back to ad-hoc." >&2
    echo "[whisperkey] WARNING: ad-hoc CDHash changes every build; TCC grants will reset." >&2
    codesign --force --deep --sign - --entitlements "${ENTITLEMENTS}" "${APP_PATH}"
  fi
fi

echo "[whisperkey] Inspecting Info.plist..."
plutil -p "${APP_PATH}/Contents/Info.plist"

echo "[whisperkey] Verifying code signature..."
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

echo "[whisperkey] App build complete:"
echo "  ${APP_PATH}"
