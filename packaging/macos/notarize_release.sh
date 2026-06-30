#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RELEASE_DIR="${ROOT_DIR}/dist/release"
NOTARY_PROFILE="${WHISPERKEY_NOTARY_PROFILE:-whisperkey-notary}"
TARGET_PATH="${1:-${ROOT_DIR}/dist/WhisperKey.app}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      echo "Usage: $0 [APP_OR_DMG_PATH]"
      echo "  Submits an app bundle or DMG to Apple notarization and staples the ticket."
      echo "  Uses WHISPERKEY_NOTARY_PROFILE or the default keychain profile: whisperkey-notary."
      exit 0
      ;;
    -*)
      echo "[whisperkey] Unknown argument: $1" >&2
      exit 2
      ;;
    *)
      TARGET_PATH="$1"
      shift
      ;;
  esac
done

if [[ ! -e "${TARGET_PATH}" ]]; then
  echo "[whisperkey] Notarization target not found: ${TARGET_PATH}" >&2
  exit 1
fi

if ! command -v xcrun >/dev/null 2>&1; then
  echo "[whisperkey] xcrun is required for notarization." >&2
  exit 1
fi

mkdir -p "${RELEASE_DIR}"

UPLOAD_PATH="${TARGET_PATH}"
if [[ -d "${TARGET_PATH}" ]]; then
  NOTARY_ZIP="${RELEASE_DIR}/WhisperKey-notary-upload.zip"
  rm -f "${NOTARY_ZIP}"
  echo "[whisperkey] Creating notarization upload zip..."
  ditto -c -k --sequesterRsrc --keepParent "${TARGET_PATH}" "${NOTARY_ZIP}"
  UPLOAD_PATH="${NOTARY_ZIP}"
fi

echo "[whisperkey] Submitting to Apple notarization with keychain profile: ${NOTARY_PROFILE}"
xcrun notarytool submit "${UPLOAD_PATH}" \
  --keychain-profile "${NOTARY_PROFILE}" \
  --wait

echo "[whisperkey] Stapling notarization ticket..."
xcrun stapler staple "${TARGET_PATH}"
xcrun stapler validate "${TARGET_PATH}"

echo "[whisperkey] Notarization complete."
