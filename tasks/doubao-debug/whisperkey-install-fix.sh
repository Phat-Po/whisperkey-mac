#!/bin/bash
set -u

SRC="/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/dist/WhisperKey.app"
DST="/Applications/WhisperKey.app"
STAGING="/Applications/WhisperKey.app.staging"
TS="$(date +%Y%m%d-%H%M%S)"
TRASH="$HOME/.Trash/WhisperKey-old-${TS}.app"
PROC="WhisperKey.app/Contents/MacOS/WhisperKey"

cd "$HOME" || exit 1

echo "=== 步驟 1/7: 检查修复版来源 (worktree dist) ==="
if [ ! -x "${SRC}/Contents/MacOS/WhisperKey" ]; then
  echo "ERROR: 找不到修复版 app: ${SRC}" >&2
  exit 1
fi
echo "来源 build 时间: $(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "${SRC}/Contents/MacOS/WhisperKey")"
echo ""

echo "=== 步驟 2/7: 暂存复制修复版到 /Applications (旧版暂时不动) ==="
[ -e "${STAGING}" ] && mv "${STAGING}" "$HOME/.Trash/WhisperKey-staging-${TS}.app"
ditto "${SRC}" "${STAGING}"
if [ ! -x "${STAGING}/Contents/MacOS/WhisperKey" ]; then
  echo "ERROR: 暂存复制失败，旧版未受影响，已中止。" >&2
  [ -e "${STAGING}" ] && mv "${STAGING}" "$HOME/.Trash/WhisperKey-staging-failed-${TS}.app"
  exit 1
fi
echo "暂存完成: ${STAGING}"
echo ""

echo "=== 步驟 3/7: 退出正在运行的 WhisperKey (新旧实例全部) ==="
osascript -e 'quit app "WhisperKey"' 2>/dev/null || true
sleep 2
pkill -f "${PROC}" 2>/dev/null || true
sleep 2
if pgrep -f "${PROC}" >/dev/null 2>&1; then
  pkill -9 -f "${PROC}" 2>/dev/null || true
  sleep 1
fi
echo "已退出。剩余进程: $(pgrep -f "${PROC}" | wc -l | tr -d ' ')"
echo ""

echo "=== 步驟 4/7: 把旧版 /Applications app 移到废纸篓 (可恢复，不是删除) ==="
if [ -e "${DST}" ]; then
  mv "${DST}" "${TRASH}"
  echo "旧版已移至: ${TRASH}"
else
  echo "(原本没有 /Applications/WhisperKey.app，跳过)"
fi
echo ""

echo "=== 步驟 5/7: 把修复版就位为 /Applications/WhisperKey.app ==="
mv "${STAGING}" "${DST}"
if [ ! -x "${DST}/Contents/MacOS/WhisperKey" ]; then
  echo "ERROR: 就位失败。可从废纸篓恢复: ${TRASH}" >&2
  exit 1
fi
xattr -cr "${DST}" 2>/dev/null || true
echo "就位完成。"
echo ""

echo "=== 步驟 6/7: 启动新的 /Applications/WhisperKey.app ==="
open "${DST}"
sleep 3
echo ""

echo "=== 步驟 7/7: 验证 ==="
echo "版本:     $(defaults read "${DST}/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null)"
echo "build时间: $(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "${DST}/Contents/MacOS/WhisperKey")  <- 应为今天 06-14"
echo "运行进程: $(pgrep -fl "${PROC}" | grep Applications || echo '(尚未出现，稍等几秒再看菜单栏图标)')"
echo ""
echo "=== 完成。现在菜单栏的 WhisperKey 就是修复版。选 Doubao 模式后按住热键测试。 ==="
