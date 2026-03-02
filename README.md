# VibeMouse 🎙️

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform: macOS](https://img.shields.io/badge/Platform-macOS-lightgrey?logo=apple)](https://www.apple.com/macos/)
[![Powered by faster-whisper](https://img.shields.io/badge/STT-faster--whisper-orange)](https://github.com/SYSTRAN/faster-whisper)

**按住按键说话，松开即转文字** — 适用于 macOS 的本地语音输入工具

**Hold a key to speak, release to transcribe** — Local voice input for macOS

> 由 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 驱动，完全离线运行，无 API 费用，支持中英混合输入。
>
> Powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — runs fully offline, no API costs, supports Chinese/English mixed input.

---

## ✨ 功能 / Features

| | 中文 | English |
|---|---|---|
| 🎤 | 按住右 Option ⌥ 录音，松手自动转录 | Hold Right Option ⌥ to record, release to transcribe |
| 🔁 | 免提模式：Option + Command 持续录音 | Hands-free: Option + Command to toggle recording |
| 🌍 | 支持中文、英文及 90+ 种语言 | Supports Chinese, English and 90+ languages |
| 💾 | 完全本地运行，无网络需求 | Runs fully offline, no internet required |
| 📋 | 转录结果自动复制到剪贴板并粘贴 | Auto-copies and pastes transcription result |
| 🔧 | 交互式安装向导，中英双语 | Interactive setup wizard, bilingual zh/en |
| 🚀 | 开机自启（macOS LaunchAgent） | Auto-start on login via macOS LaunchAgent |
| ⌨️ | 可自定义快捷键 | Customizable hotkeys |

---

## 📋 系统要求 / Requirements

- **macOS** 12 Monterey 或更高版本 / macOS 12 Monterey or later
- **Python 3.10+**（推荐 Homebrew 安装 / recommended via Homebrew）
- **麦克风** / Microphone
- 系统权限：**辅助功能** + **输入监控** / System permissions: **Accessibility** + **Input Monitoring**

---

## 📦 安装 / Installation

### 方式一：从 GitHub 安装（推荐）/ Install from GitHub (recommended)

```bash
# 克隆仓库 / Clone the repo
git clone https://github.com/Phat-Po/vibemouse-mac.git
cd vibemouse-mac

# 创建虚拟环境 / Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 安装 / Install
pip install -e .
```

### 方式二：直接安装 / Direct install

```bash
pip install git+https://github.com/Phat-Po/vibemouse-mac.git
```

> **注意**：首次转录时会自动从 HuggingFace 下载所选的 Whisper 模型（需要网络）。后续完全离线运行。
>
> **Note**: The selected Whisper model will be auto-downloaded from HuggingFace on first use (internet required). All subsequent runs are fully offline.

---

## 🚀 快速开始 / Quick Start

### 首次运行 / First Run

```bash
vibemouse
```

首次运行会自动启动安装向导，引导你完成：

The first run automatically launches the setup wizard, guiding you through:

1. **界面语言** / UI language (中文 / English)
2. **转录语言** / Transcription language (中文 / English / 混合 / Other)
3. **Whisper 模型** / Whisper model (base / small / large-v3-turbo)
4. **快捷键** / Hotkeys (default or custom)
5. **系统权限** / System permissions (guided setup)

### 之后每次使用 / Subsequent Use

VibeMouse 在后台运行，不需要打开任何窗口。

VibeMouse runs in the background — no window needed.

| 操作 / Action | 快捷键 / Hotkey |
|---|---|
| 开始录音 / Start recording | 按住 Right Option ⌥ / Hold Right Option ⌥ |
| 停止并转录 / Stop and transcribe | 松开 Right Option ⌥ / Release Right Option ⌥ |
| 免提模式开/关 / Toggle hands-free | Right Option ⌥ + Right Command ⌘ |

---

## ⌨️ 快捷键 / Hotkeys

默认快捷键 / Default hotkeys:

```
右 Option ⌥  (按住)          →  开始录音
右 Option ⌥  (松开)          →  停止录音 + 自动转录 + 粘贴
右 Option ⌥ + 右 Command ⌘   →  免提模式开/关

Right Option ⌥  (hold)       →  Start recording
Right Option ⌥  (release)    →  Stop + transcribe + paste
Right Option ⌥ + Right ⌘     →  Toggle hands-free mode
```

可通过 `vibemouse setup` 自定义快捷键。

Run `vibemouse setup` to customize hotkeys.

---

## 🔧 配置 / Configuration

### 重新配置 / Reconfigure

```bash
vibemouse setup
```

### 配置文件 / Config file

配置保存在 `~/.config/vibemouse/config.json`，可手动编辑：

Config is saved at `~/.config/vibemouse/config.json`, editable manually:

```json
{
  "ui_language": "zh",
  "transcribe_language": "auto",
  "model_size": "small",
  "hold_key": "alt_r",
  "handsfree_keys": ["alt_r", "cmd_r"]
}
```

### 模型选项 / Model Options

| 模型 / Model | 大小 / Size | 适用场景 / Best for |
|---|---|---|
| `base` | ~141 MB | 低配设备，速度优先 / Low-end devices, speed priority |
| `small` | ~464 MB | **推荐 ⭐** 速度与准确度平衡 / **Recommended** balanced |
| `large-v3-turbo` | ~1.5 GB | 最高准确度 / Highest accuracy |

---

## 🔒 系统权限 / System Permissions

VibeMouse 需要两个 macOS 系统权限：

VibeMouse requires two macOS system permissions:

### 1. 输入监控 / Input Monitoring
用于监听快捷键 / Required to detect your hotkeys

**系统设置 → 隐私与安全性 → 输入监控**

**System Settings → Privacy & Security → Input Monitoring**

### 2. 辅助功能 / Accessibility
用于将转录文字粘贴到当前应用 / Required to paste transcribed text

**系统设置 → 隐私与安全性 → 辅助功能**

**System Settings → Privacy & Security → Accessibility**

在两处均将 **Python.app** 添加到列表并开启开关。

Add **Python.app** to both lists and enable the toggle.

Python.app 的路径通常为 / Python.app is typically located at:
```
/opt/homebrew/Cellar/python@3.xx/x.x.x/Frameworks/Python.framework/Versions/3.xx/Resources/Python.app
```

---

## 🚀 开机自启 / Auto-start on Login

将 VibeMouse 设置为开机自启（macOS LaunchAgent）：

Set up VibeMouse to auto-start on login via macOS LaunchAgent:

```bash
# 1. 在本地安装（不依赖外置磁盘）
# Install locally (not on external drive)
mkdir -p ~/Library/Application\ Support/vibemouse
python3 -m venv ~/Library/Application\ Support/vibemouse/venv
~/Library/Application\ Support/vibemouse/venv/bin/pip install git+https://github.com/Phat-Po/vibemouse-mac.git

# 2. 创建 LaunchAgent / Create LaunchAgent
cat > ~/Library/LaunchAgents/com.vibemouse.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.vibemouse</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/Library/Application Support/vibemouse/venv/bin/vibemouse</string>
    </array>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/vibemouse.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/vibemouse.log</string>
</dict>
</plist>
EOF

# 将 YOUR_USERNAME 替换为你的用户名 / Replace YOUR_USERNAME with your username

# 3. 注册服务 / Register service
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vibemouse.plist
```

---

## 🛠️ 故障排查 / Troubleshooting

```bash
vibemouse help
```

自动检查以下项目 / Automatically checks:

- ✅ 后台进程状态 / Background process status
- ✅ 辅助功能权限 / Accessibility permission
- ✅ 输入监控权限 / Input Monitoring permission
- ✅ 音频输入设备 / Audio input devices
- ✅ Whisper 模型文件 / Whisper model files
- ✅ 配置文件 / Config file

### 常见问题 / Common Issues

**没有任何反应 / No response to hotkeys**
→ 检查输入监控权限 / Check Input Monitoring permission
→ 运行 `vibemouse help` 查看详情 / Run `vibemouse help` for details

**转录结果没有粘贴 / Transcription not pasting**
→ 检查辅助功能权限 / Check Accessibility permission

**服务未启动 / Service not running**
```bash
launchctl list | grep vibemouse
cat /tmp/vibemouse.log
```

**查看实时日志 / View live logs**
```bash
tail -f /tmp/vibemouse.log
```

**重启服务 / Restart service**
```bash
launchctl kickstart -k gui/$(id -u)/com.vibemouse
```

---

## 🛠️ 开发 / Development

```bash
git clone https://github.com/Phat-Po/vibemouse-mac.git
cd vibemouse-mac
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 直接运行 / Run directly
vibemouse

# 重新配置 / Reconfigure
vibemouse setup

# 故障排查 / Troubleshoot
vibemouse help
```

项目结构 / Project structure:

```
vibemouse_mac/
├── main.py           # Entry point, CLI routing
├── config.py         # Config loading/saving (JSON + env vars)
├── i18n.py           # zh/en string dictionary
├── keyboard_listener.py  # Hold-key + hands-free hotkey logic
├── audio.py          # Audio recording (sounddevice)
├── transcriber.py    # Whisper STT (faster-whisper)
├── output.py         # Text injection (clipboard + AppleScript)
├── setup_wizard.py   # Interactive terminal setup
└── help_cmd.py       # Troubleshooter
```

---

## 📄 License

MIT © 2026 [Phat-Po](https://github.com/Phat-Po)

---

<div align="center">

Built with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [pynput](https://github.com/moses-palmer/pynput) · [sounddevice](https://python-sounddevice.readthedocs.io/)

如果这个项目对你有帮助，欢迎点个 ⭐ Star！

If this project helps you, consider giving it a ⭐ Star!

</div>
