# WhisperKey 🎙️

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform: macOS](https://img.shields.io/badge/Platform-macOS-lightgrey?logo=apple)](https://www.apple.com/macos/)
[![Powered by faster-whisper](https://img.shields.io/badge/STT-faster--whisper-orange)](https://github.com/SYSTRAN/faster-whisper)

**Hold a key to speak, release to transcribe** — Local voice input for macOS

> Powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — runs fully offline, no API costs, supports Chinese/English mixed input.

📖 [查看简体中文文档](README.zh.md)

---

## ✨ Features

| | |
|---|---|
| 🎤 | Hold Right Option ⌥ to record, release to transcribe |
| 🔁 | Hands-free mode: Option + Command to toggle continuous recording |
| 🌍 | Supports Chinese, English and 90+ languages |
| 💾 | Runs fully offline — no internet required after first run |
| 📋 | Auto-copies and pastes transcription result into the active app |
| 🔧 | Interactive bilingual setup wizard (zh/en) |
| 🚀 | Auto-start on login via macOS LaunchAgent |
| ⌨️ | Fully customizable hotkeys |

---

## 📋 Requirements

- **macOS** 12 Monterey or later
- **Python 3.10+** (recommended via Homebrew)
- **Microphone**
- System permissions: **Accessibility** + **Input Monitoring**

---

## 📦 Installation

### Option A: Clone and install (recommended)

```bash
git clone https://github.com/Phat-Po/whisperkey-mac.git
cd whisperkey-mac

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

### Option B: Install directly from GitHub

```bash
pip install git+https://github.com/Phat-Po/whisperkey-mac.git
```

> **Note**: The selected Whisper model is auto-downloaded from HuggingFace on first transcription (internet required). All subsequent runs are fully offline.

---

## 🚀 Quick Start

### First Run

```bash
whisperkey
```

The first run automatically launches an interactive setup wizard, guiding you through:

1. **UI language** — English or 中文
2. **Transcription language** — English / Chinese / Mixed / Other
3. **Whisper model** — base / small / large-v3-turbo
4. **Hotkeys** — use defaults or define your own
5. **System permissions** — guided walkthrough

### Subsequent Use

WhisperKey runs in the background — no window needed.

| Action | Hotkey |
|---|---|
| Start recording | Hold Right Option ⌥ |
| Stop and transcribe | Release Right Option ⌥ |
| Toggle hands-free mode | Right Option ⌥ + Right Command ⌘ |

---

## ⌨️ Hotkeys

Default hotkeys:

```
Right Option ⌥  (hold)      →  Start recording
Right Option ⌥  (release)   →  Stop + transcribe + paste
Right Option ⌥ + Right ⌘    →  Toggle hands-free mode
```

Run `whisperkey setup` to customize hotkeys.

---

## 🔧 Configuration

### Reconfigure

```bash
whisperkey setup
```

### Config file

Config is saved at `~/.config/whisperkey/config.json`, editable manually:

```json
{
  "ui_language": "en",
  "transcribe_language": "auto",
  "model_size": "small",
  "hold_key": "alt_r",
  "handsfree_keys": ["alt_r", "cmd_r"]
}
```

### Model Options

| Model | Size | Best for |
|---|---|---|
| `base` | ~141 MB | Low-end devices, speed priority |
| `small` | ~464 MB | **Recommended ⭐** Balanced speed and accuracy |
| `large-v3-turbo` | ~1.5 GB | Highest accuracy |

---

## 🔒 System Permissions

WhisperKey requires two macOS system permissions:

### 1. Input Monitoring
Required to detect your hotkeys.

**System Settings → Privacy & Security → Input Monitoring**

### 2. Accessibility
Required to paste transcribed text into the active app.

**System Settings → Privacy & Security → Accessibility**

Add **Python.app** to both lists and enable the toggle.

Python.app is typically located at:
```
/opt/homebrew/Cellar/python@3.xx/x.x.x/Frameworks/Python.framework/Versions/3.xx/Resources/Python.app
```

---

## 🚀 Auto-start on Login

Set up WhisperKey to run automatically on login via macOS LaunchAgent:

```bash
# 1. Install locally (not on an external drive)
mkdir -p ~/Library/Application\ Support/whisperkey
python3 -m venv ~/Library/Application\ Support/whisperkey/venv
~/Library/Application\ Support/whisperkey/venv/bin/pip install git+https://github.com/Phat-Po/whisperkey-mac.git

# 2. Create LaunchAgent
cat > ~/Library/LaunchAgents/com.whisperkey.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.whisperkey</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/Library/Application Support/whisperkey/venv/bin/whisperkey</string>
    </array>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/whisperkey.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/whisperkey.log</string>
</dict>
</plist>
EOF

# Replace YOUR_USERNAME with your actual username

# 3. Register the service
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.whisperkey.plist
```

---

## 🛠️ Troubleshooting

```bash
whisperkey help
```

Automatically checks:

- ✅ Background process status
- ✅ Accessibility permission
- ✅ Input Monitoring permission
- ✅ Audio input devices
- ✅ Whisper model files
- ✅ Config file

### Common Issues

**No response to hotkeys**
→ Check Input Monitoring permission
→ Run `whisperkey help` for details

**Transcription not pasting**
→ Check Accessibility permission

**Service not running**
```bash
launchctl list | grep whisperkey
cat /tmp/whisperkey.log
```

**View live logs**
```bash
tail -f /tmp/whisperkey.log
```

**Restart service**
```bash
launchctl kickstart -k gui/$(id -u)/com.whisperkey
```

---

## 🛠️ Development

```bash
git clone https://github.com/Phat-Po/whisperkey-mac.git
cd whisperkey-mac
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

whisperkey        # run
whisperkey setup  # reconfigure
whisperkey help   # troubleshoot
```

Project structure:

```
whisperkey_mac/
├── main.py               # Entry point, CLI routing
├── config.py             # Config loading/saving (JSON + env vars)
├── i18n.py               # zh/en string dictionary
├── keyboard_listener.py  # Hold-key + hands-free hotkey logic
├── audio.py              # Audio recording (sounddevice)
├── transcriber.py        # Whisper STT (faster-whisper)
├── output.py             # Text injection (clipboard + AppleScript)
├── setup_wizard.py       # Interactive terminal setup
└── help_cmd.py           # Troubleshooter
```

---

## 📄 License

MIT © 2026 [Phat-Po](https://github.com/Phat-Po)

---

<div align="center">

Built with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [pynput](https://github.com/moses-palmer/pynput) · [sounddevice](https://python-sounddevice.readthedocs.io/)

If this project helps you, consider giving it a ⭐ Star!

</div>
