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
rm -f "${ZIP_PATH}"

echo "[whisperkey] Creating release zip..."
ditto -c -k --sequesterRsrc --keepParent "${APP_PATH}" "${ZIP_PATH}"

echo "[whisperkey] Release artifact:"
ls -lh "${ZIP_PATH}"
