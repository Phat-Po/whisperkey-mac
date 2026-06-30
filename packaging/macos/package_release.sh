#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
APP_PATH="${ROOT_DIR}/dist/WhisperKey.app"
RELEASE_DIR="${ROOT_DIR}/dist/release"
SKIP_NOTARIZATION=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-notarization)
      SKIP_NOTARIZATION=1
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--skip-notarization]"
      echo "  Creates a Developer ID signed, notarized release by default."
      echo "  --skip-notarization is only for local packaging diagnostics."
      exit 0
      ;;
    *)
      echo "[whisperkey] Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cd "${ROOT_DIR}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[whisperkey] Missing local venv Python: ${PYTHON_BIN}" >&2
  exit 1
fi

"${ROOT_DIR}/packaging/macos/build_app.sh" --release

if [[ "${SKIP_NOTARIZATION}" -eq 0 ]]; then
  "${ROOT_DIR}/packaging/macos/notarize_release.sh" "${APP_PATH}"
else
  echo "[whisperkey] WARNING: skipping notarization; artifacts are not customer-ready." >&2
fi

VERSION="$("${PYTHON_BIN}" - <<'PY'
from pathlib import Path
import tomllib

data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["version"])
PY
)"

mkdir -p "${RELEASE_DIR}"
ZIP_PATH="${RELEASE_DIR}/WhisperKey-macOS-arm64-v${VERSION}.zip"
DMG_PATH="${RELEASE_DIR}/WhisperKey-macOS-arm64-v${VERSION}.dmg"
rm -f "${ZIP_PATH}" "${DMG_PATH}"

echo "[whisperkey] Creating release zip..."
ditto -c -k --sequesterRsrc --keepParent "${APP_PATH}" "${ZIP_PATH}"

echo "[whisperkey] Creating drag-install DMG..."
STAGING_DIR="$(mktemp -d /tmp/whisperkey-dmg.XXXXXX)"
trap 'rm -rf "${STAGING_DIR}"' EXIT
ditto "${APP_PATH}" "${STAGING_DIR}/WhisperKey.app"
ln -s /Applications "${STAGING_DIR}/Applications"
cat > "${STAGING_DIR}/安装说明 Install.txt" <<'NOTE'
WhisperKey 安装 / Install

1. 把 WhisperKey.app 拖到 Applications 文件夹
   Drag WhisperKey.app into the Applications folder.

2. 首次打开：在「应用程序」里右键点击 WhisperKey → 打开。
   First launch: right-click WhisperKey in Applications → Open.

3. 跟随安装向导授予 辅助功能 / 输入监控 / 麦克风 权限，
   然后点「重启 WhisperKey」完成安装。
   Follow the setup window to grant Accessibility / Input Monitoring /
   Microphone, then click "Restart WhisperKey" to finish.
NOTE

hdiutil create -volname "WhisperKey ${VERSION}" \
  -srcfolder "${STAGING_DIR}" -ov -format UDZO "${DMG_PATH}" >/dev/null

if [[ "${SKIP_NOTARIZATION}" -eq 0 ]]; then
  "${ROOT_DIR}/packaging/macos/notarize_release.sh" "${DMG_PATH}"
  "${ROOT_DIR}/packaging/macos/verify_release.sh" "${APP_PATH}"
else
  "${ROOT_DIR}/packaging/macos/verify_release.sh" --allow-unstapled "${APP_PATH}"
fi

echo "[whisperkey] Release artifacts:"
ls -lh "${ZIP_PATH}" "${DMG_PATH}"
