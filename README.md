# WhisperKey 🎙️

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform: macOS](https://img.shields.io/badge/Platform-macOS-lightgrey?logo=apple)](https://www.apple.com/macos/)
[![Powered by faster-whisper](https://img.shields.io/badge/STT-faster--whisper-orange)](https://github.com/SYSTRAN/faster-whisper)

<pre>
█░░░█ █░░░█ ░███░ ░████ ████░ █████ ████░ █░░░█ █████ █░░░█
█░░░█ █░░░█ ░░█░░ █░░░░ █░░░█ █░░░░ █░░░█ █░█░░ █░░░░ █░░░█
█░█░█ █████ ░░█░░ ░███░ ████░ ████░ ████░ ███░░ ████░ ░███░
█░█░█ █░░░█ ░░█░░ ░░░░█ █░░░░ █░░░░ █░█░░ █░█░░ █░░░░ ░░█░░
░███░ █░░░█ ░███░ ████░ █░░░░ █████ █░░█░ █░░░█ █████ ░░█░░
</pre>

**Hold a key to speak. Release to transcribe.**

Local voice input for macOS — offline, free, no subscriptions.

📖 [查看简体中文文档](README.zh.md)

---

## Why WhisperKey?

Most macOS dictation tools are either online-only or expensive:

| | WhisperKey | SuperWhisper | Wispr Flow | macOS Dictation |
|---|:---:|:---:|:---:|:---:|
| Free & open source | ✅ | ❌ ($250 lifetime) | ❌ ($15/mo) | ✅ |
| Fully offline | ✅ | ✅ | ❌ | ❌ |
| Chinese/English mixed | ✅ | ✅ | ✅ | ⚠️ |
| Customizable hotkeys | ✅ | ✅ | ❌ | ❌ |
| No app install needed | ✅ | ❌ | ❌ | — |

WhisperKey runs entirely on your Mac using [faster-whisper](https://github.com/SYSTRAN/faster-whisper). No cloud, no API keys, no recurring cost.

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

```bash
pip install git+https://github.com/Phat-Po/whisperkey-mac.git
```

Or clone and install for development:

```bash
git clone https://github.com/Phat-Po/whisperkey-mac.git
cd whisperkey-mac
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

> **Tip for macOS**: if `python3 -V` is below 3.10, use a Homebrew Python explicitly instead of the system interpreter. For example: `python3.12 -m venv .venv` and `python3.12 -m pip install -e .`.

> **Note**: The selected Whisper model is auto-downloaded from HuggingFace on first transcription (internet required). All subsequent runs are fully offline.

> **Cache behavior**: reinstalling WhisperKey or rebuilding a local `venv` does **not** re-download an already cached model. Existing model files under `~/.cache/huggingface/hub` are reused unless you delete them manually.

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

```bash
whisperkey setup   # re-run setup wizard
whisperkey help    # troubleshoot permissions, model, audio
```

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

**1. Input Monitoring** — to detect your hotkeys
→ System Settings → Privacy & Security → Input Monitoring

**2. Accessibility** — to paste transcribed text into the active app
→ System Settings → Privacy & Security → Accessibility

Add **Python.app** to both lists and enable the toggle. Python.app is typically at:
```
/opt/homebrew/Cellar/python@3.xx/x.x.x/Frameworks/Python.framework/Versions/3.xx/Resources/Python.app
```

---

## 🛠️ Troubleshooting

```bash
whisperkey help
```

Automatically checks: process status · Accessibility · Input Monitoring · audio devices · model files · config

**No response to hotkeys** → check Input Monitoring permission
**Transcription not pasting** → check Accessibility permission

```bash
tail -f /tmp/whisperkey.log                            # live logs
launchctl kickstart -k gui/$(id -u)/com.whisperkey    # restart service
```

---

<details>
<summary>🚀 Auto-start on Login (LaunchAgent setup)</summary>

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
        <string>/Users/YOUR_USERNAME/Library/Application Support/whisperkey/venv/bin/python</string>
        <string>-m</string>
        <string>whisperkey_mac.main</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>WHISPERKEY_MODEL</key>
        <string>small</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>LimitLoadToSessionType</key>
    <string>Aqua</string>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USERNAME/Library/Application Support/whisperkey</string>
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

This LaunchAgent pattern is more resilient than calling the console script directly, and it continues to reuse any model already cached on disk.

</details>

<details>
<summary>🛠️ Development</summary>

```bash
git clone https://github.com/Phat-Po/whisperkey-mac.git
cd whisperkey-mac
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

whisperkey        # run
whisperkey setup  # reconfigure
whisperkey help   # troubleshoot
```

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

</details>

---

## 📄 License

MIT © 2026 [Phat-Po](https://github.com/Phat-Po)

---

<div align="center">

Built with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [pynput](https://github.com/moses-palmer/pynput) · [sounddevice](https://python-sounddevice.readthedocs.io/)

If this project helps you, consider giving it a ⭐ Star!

</div>
