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

Local voice input for macOS — offline, free, no subscriptions. Optional on-device or cloud post-processing to clean up your speech into polished writing.

📖 [查看简体中文文档](README.zh.md)

---

## Why WhisperKey?

Most macOS dictation tools are either online-only or expensive:

| | WhisperKey | SuperWhisper | Wispr Flow | macOS Dictation |
|---|:---:|:---:|:---:|:---:|
| Free & open source | ✅ | ❌ ($250 lifetime) | ❌ ($15/mo) | ✅ |
| Fully offline STT | ✅ | ✅ | ❌ | ❌ |
| Chinese/English mixed | ✅ | ✅ | ✅ | ⚠️ |
| Voice cleanup (filler removal, re-writing) | ✅ | ✅ | ✅ | ❌ |
| Custom word replacements | ✅ | ⚠️ | ⚠️ | ❌ |
| Token usage dashboard | ✅ | ❌ | ❌ | ❌ |
| Customizable hotkeys | ✅ | ✅ | ❌ | ❌ |
| Direct `.app` download | ✅ | ✅ | ✅ | — |

WhisperKey keeps transcription on your Mac using [faster-whisper](https://github.com/SYSTRAN/faster-whisper). The core dictation flow stays local-first; optional OpenAI-powered cleanup and correction can be enabled with your own API key.

---

## ✨ Features

### 🎙️ Core dictation
- **Hold-to-talk** — hold Right Option ⌥ to record, release to transcribe
- **Hands-free mode** — Right Option ⌥ + Right Command ⌘ toggles continuous recording
- **90+ languages** with Chinese/English mixed handling
- **Fully offline STT** via faster-whisper — no internet after the first model download
- **Auto-paste** directly into the active app
- **VoiceInput pill overlay** — compact, unobtrusive visual feedback for recording, transcribing, and result states

### 🧼 Optional AI post-processing
- **Voice Cleanup** — removes "um", "uh", fillers, repetition, and rewrites rambling speech into clean prose
- **ASR Correction** — fixes homophones, punctuation, and obvious transcription errors on short texts
- **Custom prompt** — bring your own instruction for domain-specific processing
- **Output Language** — keep original, translate to English, or translate to Chinese after processing
- Uses your own OpenAI API key, stored in macOS Keychain (never committed)

### ⚙️ Full-featured control
- **Settings GUI** with 5 tabs: General, Voice, Word Fix, Usage, Advanced
- **Menu bar app** — at-a-glance status, pause/resume service, quick Settings access
- **Word Replacements dictionary** — map `cloude → Claude`, `gpt → GPT`, and similar corrections automatically
- **Token usage dashboard** — track OpenAI consumption (today / this week / all time) and disk footprint
- **Microphone picker** — select any connected input device
- **Fully customizable hotkeys** — hold key and hands-free combo
- **Launch at Login** toggle (managed via macOS LaunchAgent)
- **Bilingual UI** (zh / en) throughout setup, Settings, and menu bar
- **Graceful fallback** — if the cloud request fails or times out, raw transcript is pasted instead

---

## 📋 Requirements

- **macOS** 12 Monterey or later (Apple Silicon recommended)
- **Python 3.10+** (if installing from source; not needed for the packaged `.app`)
- **Microphone**
- System permissions: **Input Monitoring** + **Accessibility**
- *(Optional)* OpenAI API key for post-processing

---

## 📦 Installation

### Option A — Download the App (recommended)

Grab `WhisperKey-macOS-arm64-v0.2.2.zip` from the [Releases page](https://github.com/Phat-Po/whisperkey-mac/releases), unzip, and move `WhisperKey.app` to `/Applications`.

On first launch, grant the two macOS permissions:
- **Input Monitoring** — lets WhisperKey detect the hotkey
- **Accessibility** — lets WhisperKey paste text into the active app

This build is locally signed but not notarized by Apple. If macOS blocks the first launch, right-click `WhisperKey.app` → **Open** → confirm.

The first transcription downloads the selected Whisper model from HuggingFace (internet required once). After that, transcription runs fully offline.

### Option B — Install from source

```bash
pip install git+https://github.com/Phat-Po/whisperkey-mac.git
```

Or clone for development:

```bash
git clone https://github.com/Phat-Po/whisperkey-mac.git
cd whisperkey-mac
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

> **macOS tip**: if `python3 -V` is below 3.10, use a Homebrew Python explicitly: `python3.12 -m venv .venv`.

> **Cache behavior**: reinstalling or rebuilding a venv does **not** re-download an already cached model. Model files under `~/.cache/huggingface/hub` are reused unless deleted manually.

---

## 🚀 Quick Start

### First run

```bash
whisperkey
```

An interactive setup wizard guides you through:

1. **UI language** — English or 中文
2. **Transcription language** — English / Chinese / Mixed / Other
3. **Whisper model** — base / small / large-v3-turbo
4. **Hotkeys** — defaults or your own
5. **System permissions** — guided walkthrough
6. **AI post-processing (optional)** — pick a mode and save your OpenAI API key to Keychain

### Daily use

WhisperKey runs in the background as a menu bar app — no window needed.

| Action | Hotkey |
|---|---|
| Start recording | Hold Right Option ⌥ |
| Stop and transcribe | Release Right Option ⌥ |
| Toggle hands-free mode | Right Option ⌥ + Right Command ⌘ |

---

## 🎛️ Post-Processing Modes

After local transcription, WhisperKey can optionally pipe the result through OpenAI for cleanup. Three modes are available in **Settings → Voice → Processing Mode**:

| Mode | What it does | Best for | Recommended timeout |
|---|---|---|---|
| **Disabled** | Pastes raw Whisper output | Fastest; no cloud calls | — |
| **ASR Correction** | Fixes homophones, missing punctuation, obvious transcription errors. Minimal rewriting. | Short phrases, command-style input, technical terms | 3 sec |
| **Voice Cleanup** ⭐ | Removes filler words (*um / uh / 就是 / 那個*), deduplicates hesitation, reorganizes rambling thoughts into clean prose. Preserves all specifics (numbers, names, constraints). | Longer messages, notes, drafting emails / docs | 8 sec |
| **Custom** | Runs your own system prompt | Domain-specific rewriting (formal, code, translation styles) | 8 sec |

All modes gracefully fall back to the raw transcript on timeout or API error.

---

## 🍎 Menu Bar Controls

WhisperKey lives in the macOS menu bar. Click the icon to access:

- **Status line** — running / paused / waiting for permissions
- **Pause / Resume** — temporarily stop hotkey listening without quitting (handy for games or screen recording)
- **Settings…** — opens the full Settings GUI
- **Quit WhisperKey**

The menu bar title updates live based on service state.

---

## ⚙️ Settings GUI

Open via **Menu bar → Settings…** — five tabs cover everything:

### General
- Interface Language (zh / en)
- Transcription Language (Auto / zh / en / other ISO code)
- **Output Language** (match input / translate to English / translate to Chinese)
- Whisper Model (`base` / `small` / `large-v3-turbo`)
- **Microphone** — pick any connected input device (or system default)
- **Launch at Login** toggle

### Voice
- **Processing Mode** (Disabled / ASR Correction / Voice Cleanup / Custom)
- **Online Model** (e.g. `gpt-5.4` — customizable)
- **Timeout** in seconds (recommended: 8 for Voice Cleanup, 3 for ASR Correction)

### Word Fix
A personal dictionary that post-processes every transcript. Useful for brand names the STT model consistently mishears.

```
cloude → Claude
cloud ai → Claude AI
open ei eye → OpenAI
```

- One replacement per line
- Use `→` or `->`
- Case-insensitive, longest match wins
- Runs locally; no cloud call needed

### Usage
Live dashboard showing:
- OpenAI token consumption (input / output, today / this week / all time)
- Disk footprint — audio temp files + Whisper model cache paths

### Advanced
- **Hold Key** — any pynput key name (e.g. `alt_r`, `cmd_r`, `f13`)
- **Handsfree Keys** — comma-separated combo (e.g. `alt_r, cmd_r`)
- **API Key** — paste a new OpenAI key; stored in macOS Keychain

---

## 📊 Usage Tracking

The **Usage** tab gives you transparent visibility into your OpenAI spend:

- Per-day, per-week, and lifetime input/output token counts
- Disk usage for audio temp files (`/tmp/whisperkey_mac/`)
- Disk usage for the Whisper model cache (`~/.cache/huggingface/hub/`)
- Refresh button for live updates

No analytics are sent anywhere — everything is read from local logs.

---

## 🔧 Configuration

For advanced or scripted setups, config is stored at `~/.config/whisperkey/config.json`:

```json
{
  "ui_language": "en",
  "transcribe_language": "auto",
  "output_language": "auto",
  "model_size": "small",
  "input_device": "",
  "hold_key": "alt_r",
  "handsfree_keys": ["alt_r", "cmd_r"],
  "auto_paste": true,
  "result_max_lines": 3,
  "online_prompt_mode": "disabled",
  "online_correct_enabled": false,
  "online_correct_provider": "openai",
  "online_correct_model": "gpt-5.4",
  "online_correct_timeout_s": 8.0,
  "online_prompt_custom_text": "",
  "word_replacements": {},
  "launch_at_login": false
}
```

### Environment variable overrides

Useful for LaunchAgents and CI:

| Variable | Overrides |
|---|---|
| `OPENAI_API_KEY` | Keychain-stored API key |
| `WHISPERKEY_MODEL` | `model_size` |
| `WHISPERKEY_COMPUTE_TYPE` | `compute_type` (default `int8`) |
| `WHISPERKEY_DEVICE` | `device` (default `cpu`) |
| `WHISPERKEY_LANGUAGE` | Whisper language hint |
| `WHISPERKEY_SAMPLE_RATE` | Recording sample rate |
| `WHISPERKEY_AUTO_PASTE` | `1` / `0` |
| `WHISPERKEY_RESULT_MAX_LINES` | HUD line cap |
| `WHISPERKEY_ONLINE_CORRECT` | `1` / `0` |
| `WHISPERKEY_ONLINE_CORRECT_MODEL` | OpenAI model name |
| `WHISPERKEY_ONLINE_PROMPT_MODE` | `disabled` / `asr_correction` / `voice_cleanup` / `custom` |

### Model options

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

Add the app printed by `whisperkey permissions` or `whisperkey help` to both lists and enable the toggle.
For source installs this is usually Python.app:
```
/opt/homebrew/Cellar/python@3.xx/x.x.x/Frameworks/Python.framework/Versions/3.xx/Resources/Python.app
```
For the packaged build, authorize `WhisperKey.app`.

> **Note**: each packaged build has a different CDHash, so after upgrading the `.app` you must re-authorize both permissions.

---

## 🛠️ Troubleshooting

```bash
whisperkey help
```

Automatically checks: process status · Accessibility · Input Monitoring · audio devices · model files · config

| Symptom | Fix |
|---|---|
| No response to hotkeys | Check **Input Monitoring** permission |
| Transcription not pasting | Check **Accessibility** permission |
| Post-processing not applying | Re-run `whisperkey setup` or set `OPENAI_API_KEY`; check Settings → Voice → Processing Mode |
| `inject_path=applescript` in logs | Expected for Electron/web chat apps; it's the compatibility paste path |
| Upgraded `.app` stopped working | Re-authorize Input Monitoring + Accessibility (CDHash changed) |

```bash
tail -f /tmp/whisperkey.log                           # live logs
launchctl kickstart -k gui/$(id -u)/com.whisperkey    # restart service
```

---

<details>
<summary>🚀 Auto-start on Login (LaunchAgent setup)</summary>

The Settings GUI **Launch at Login** toggle manages this automatically. Manual setup (for source installs) is below:

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
        <string>whisperkey_mac.supervisor</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>WHISPERKEY_MODEL</key>
        <string>small</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <key>KeepAlive</key>
    <false/>
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

The LaunchAgent starts a crash supervisor, which launches the app, writes crash details to `/tmp/whisperkey-last-crash.log`, and sends a macOS notification on unexpected exit.

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
├── app_entry.py          # Menu bar app bootstrap
├── menu_bar.py           # Menu bar item + state sync
├── settings_window.py    # Settings GUI (5 tabs)
├── config.py             # Config loading/saving (JSON + env vars)
├── i18n.py               # zh/en string dictionary
├── keyboard_listener.py  # Hold-key + hands-free hotkey logic
├── audio.py              # Audio recording (sounddevice)
├── transcriber.py        # Whisper STT (faster-whisper)
├── online_correct.py     # Optional OpenAI post-processing pipeline
├── keychain.py           # macOS Keychain helpers for OpenAI API key
├── output.py             # Text injection (clipboard + focused-app paste)
├── overlay.py            # VoiceInput pill overlay
├── usage_log.py          # Token consumption tracking
├── launch_agent.py       # LaunchAgent install/uninstall helpers
├── setup_wizard.py       # Interactive terminal setup
└── help_cmd.py           # Troubleshooter
```

Packaging: `packaging/macos/build_app.sh` (PyInstaller + codesign) → `packaging/macos/package_release.sh` (zip for Releases).

</details>

---

## 📄 License

MIT © 2026 [Phat-Po](https://github.com/Phat-Po)

---

<div align="center">

Built with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [pynput](https://github.com/moses-palmer/pynput) · [sounddevice](https://python-sounddevice.readthedocs.io/) · [PyObjC](https://pyobjc.readthedocs.io/)

If this project helps you, consider giving it a ⭐ Star!

</div>
