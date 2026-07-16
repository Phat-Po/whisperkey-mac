#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
APP_PATH="${ROOT_DIR}/dist/WhisperKey.app"
RELEASE_DIR="${ROOT_DIR}/dist/release"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      echo "Usage: $0"
      echo "  Creates a self-signed (or ad-hoc fallback), not-notarized free public release."
      echo "  Artifacts are labeled free-selfsigned and require manual Gatekeeper approval."
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

"${ROOT_DIR}/packaging/macos/build_app.sh" --free-release

VERSION="$("${PYTHON_BIN}" - <<'PY'
from pathlib import Path
import tomllib

data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["version"])
PY
)"

mkdir -p "${RELEASE_DIR}"
ZIP_PATH="${RELEASE_DIR}/WhisperKey-macOS-arm64-v${VERSION}-free-selfsigned.zip"
DMG_PATH="${RELEASE_DIR}/WhisperKey-macOS-arm64-v${VERSION}-free-selfsigned.dmg"
CHECKSUM_PATH="${RELEASE_DIR}/WhisperKey-macOS-arm64-v${VERSION}-free-selfsigned-SHA256SUMS.txt"
rm -f "${ZIP_PATH}" "${DMG_PATH}" "${CHECKSUM_PATH}"

echo "[whisperkey] Verifying free build signature..."
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"
CODESIGN_INFO="$(codesign -dvv "${APP_PATH}" 2>&1 || true)"
printf '%s\n' "${CODESIGN_INFO}"
if printf '%s\n' "${CODESIGN_INFO}" | grep -q "Signature=adhoc"; then
  echo "[whisperkey] NOTE: signed ad-hoc (no stable local identity found) — end users will need to re-grant TCC permissions on every update."
elif ! printf '%s\n' "${CODESIGN_INFO}" | grep -q "Authority=WhisperKey Dev"; then
  echo "[whisperkey] Free release verification failed: expected ad-hoc or 'WhisperKey Dev' signature, got something else." >&2
  exit 1
fi

echo "[whisperkey] Creating free release zip..."
ditto -c -k --sequesterRsrc --keepParent "${APP_PATH}" "${ZIP_PATH}"

echo "[whisperkey] Creating free drag-install DMG..."
STAGING_DIR="$(mktemp -d /tmp/whisperkey-free-dmg.XXXXXX)"
trap 'rm -rf "${STAGING_DIR}"' EXIT
ditto "${APP_PATH}" "${STAGING_DIR}/WhisperKey.app"
ln -s /Applications "${STAGING_DIR}/Applications"
cat > "${STAGING_DIR}/安装说明 Install.txt" <<'NOTE'
WhisperKey 免费版安装 / Free Build Install

这是免费自签名版本：没有 Apple Developer ID 公证，用的是本地自签名证书签名
（不是 Apple 颁发的证书），首次启动仍需手动放行 Gatekeeper。
This is a free, self-signed build without Apple Developer ID notarization.
It is signed with a local self-signed certificate (not an Apple-issued one),
so you'll still need to manually approve it through Gatekeeper on first launch.

1. 把 WhisperKey.app 拖到 Applications 文件夹。
   Drag WhisperKey.app into the Applications folder.

2. 首次启动请右键点击 WhisperKey.app，然后选择「打开」。
   First launch: right-click WhisperKey.app, then choose Open.

3. 如果 macOS 阻止打开，请到 系统设置 -> 隐私与安全性，
   找到 WhisperKey 的提示并点「仍要打开」。
   If macOS blocks the app, open System Settings -> Privacy & Security,
   then choose Open Anyway for WhisperKey.

4. 跟随安装向导授予 辅助功能 / 输入监控 / 麦克风 权限，
   然后点「重启 WhisperKey」完成安装。
   Follow the setup window to grant Accessibility / Input Monitoring /
   Microphone, then click Restart WhisperKey to finish.
NOTE

hdiutil create -volname "WhisperKey ${VERSION} Free" \
  -srcfolder "${STAGING_DIR}" -ov -format UDZO "${DMG_PATH}" >/dev/null

echo "[whisperkey] Writing checksums..."
(
  cd "${RELEASE_DIR}"
  shasum -a 256 "$(basename "${ZIP_PATH}")" "$(basename "${DMG_PATH}")" > "${CHECKSUM_PATH}"
)

echo "[whisperkey] Free release artifacts:"
ls -lh "${ZIP_PATH}" "${DMG_PATH}" "${CHECKSUM_PATH}"
