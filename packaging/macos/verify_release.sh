#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="${ROOT_DIR}/dist/WhisperKey.app"
ALLOW_UNSTAPLED=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-unstapled)
      ALLOW_UNSTAPLED=1
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--allow-unstapled] [APP_PATH]"
      echo "  Verifies Developer ID signing, hardened runtime, Gatekeeper, and stapling."
      echo "  --allow-unstapled skips Gatekeeper and stapler checks for local diagnostics only."
      exit 0
      ;;
    -*)
      echo "[whisperkey] Unknown argument: $1" >&2
      exit 2
      ;;
    *)
      APP_PATH="$1"
      shift
      ;;
  esac
done

if [[ ! -d "${APP_PATH}" ]]; then
  echo "[whisperkey] App bundle not found: ${APP_PATH}" >&2
  exit 1
fi

echo "[whisperkey] Verifying release signature..."
CODESIGN_INFO="$(codesign -dvv "${APP_PATH}" 2>&1 || true)"
printf '%s\n' "${CODESIGN_INFO}"

if printf '%s\n' "${CODESIGN_INFO}" | grep -q "Signature=adhoc"; then
  echo "[whisperkey] Release verification failed: app is ad-hoc signed." >&2
  exit 1
fi

if ! printf '%s\n' "${CODESIGN_INFO}" | grep -q "Authority=Developer ID Application:"; then
  echo "[whisperkey] Release verification failed: missing Developer ID Application authority." >&2
  exit 1
fi

if ! printf '%s\n' "${CODESIGN_INFO}" | grep -q "Runtime Version="; then
  echo "[whisperkey] Release verification failed: hardened runtime is missing." >&2
  exit 1
fi

codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

if [[ "${ALLOW_UNSTAPLED}" -eq 1 ]]; then
  echo "[whisperkey] WARNING: skipping Gatekeeper and staple checks; this build is not customer-ready." >&2
  exit 0
fi

echo "[whisperkey] Assessing Gatekeeper policy..."
spctl --assess --type execute --verbose=2 "${APP_PATH}"

echo "[whisperkey] Validating notarization staple..."
xcrun stapler validate "${APP_PATH}"

echo "[whisperkey] Release verification passed."
