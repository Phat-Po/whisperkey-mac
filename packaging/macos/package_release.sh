#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
APP_PATH="${ROOT_DIR}/dist/WhisperKey.app"
RELEASE_DIR="${ROOT_DIR}/dist/release"

cd "${ROOT_DIR}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[whisperkey] Missing local venv Python: ${PYTHON_BIN}" >&2
  exit 1
fi

"${ROOT_DIR}/packaging/macos/build_app.sh"

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
   如果系统提示「无法验证开发者」，去 系统设置 → 隐私与安全性，
   点「仍要打开」。
   First launch: right-click WhisperKey in Applications → Open.
   If macOS says the developer cannot be verified, go to
   System Settings → Privacy & Security and click "Open Anyway".

3. 跟随安装向导授予 辅助功能 / 输入监控 / 麦克风 权限，
   然后点「重启 WhisperKey」完成安装。
   Follow the setup window to grant Accessibility / Input Monitoring /
   Microphone, then click "Restart WhisperKey" to finish.
NOTE

hdiutil create -volname "WhisperKey ${VERSION}" \
  -srcfolder "${STAGING_DIR}" -ov -format UDZO "${DMG_PATH}" >/dev/null

echo "[whisperkey] Release artifacts:"
ls -lh "${ZIP_PATH}" "${DMG_PATH}"
