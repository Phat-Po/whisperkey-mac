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

**按住按键说话，松开即转文字。**

适用于 macOS 的本地语音输入工具 — 离线运行，完全免费，无订阅费用。

📖 [English Documentation](README.md)

---

## 为什么选择 WhisperKey？

大多数 macOS 语音输入工具要么需要联网，要么价格不菲：

| | WhisperKey | SuperWhisper | Wispr Flow | macOS 听写 |
|---|:---:|:---:|:---:|:---:|
| 免费开源 | ✅ | ❌（$250 买断）| ❌（$15/月）| ✅ |
| 完全离线 | ✅ | ✅ | ❌ | ❌ |
| 中英混合识别 | ✅ | ✅ | ✅ | ⚠️ |
| 自定义快捷键 | ✅ | ✅ | ❌ | ❌ |
| 无需安装 .app | ✅ | ❌ | ❌ | — |

WhisperKey 的核心转录基于 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 在本机运行，主链路保持 local-first；如果你需要更强的语义修正，也可以稍后用自己的 OpenAI API key 开启可选的在线纠错。

---

## ✨ 功能特点

| | |
|---|---|
| 🎤 | 按住右 Option ⌥ 录音，松手自动转录并粘贴 |
| 🔁 | 免提模式：同时按 Option + Command 开关持续录音 |
| 🌍 | 支持中文、英文及 90+ 种语言 |
| 💾 | 完全本地运行，首次下载模型后无需联网 |
| 📋 | 转录结果自动复制到剪贴板并粘贴至当前应用 |
| 🪟 | 长文本结果 HUD 最多支持 3 行显示与自适应高度 |
| ✨ | 可选 OpenAI 在线纠错，使用你自己的 API key |
| 🔧 | 交互式安装向导，中英双语 |
| 🚀 | 支持开机自启（macOS LaunchAgent） |
| ⌨️ | 可自定义快捷键 |

---

## 📋 系统要求

- **macOS** 12 Monterey 或更高版本
- **Python 3.10+**（推荐通过 Homebrew 安装）
- **麦克风**
- 系统权限：**辅助功能** + **输入监控**

---

## 📦 安装

```bash
pip install git+https://github.com/Phat-Po/whisperkey-mac.git
```

或克隆仓库进行开发安装：

```bash
git clone https://github.com/Phat-Po/whisperkey-mac.git
cd whisperkey-mac
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

> **提示（macOS）**：如果 `python3 -V` 低于 3.10，请不要直接使用系统自带 Python，改用 Homebrew 安装的 Python。示例：`python3.12 -m venv .venv`，然后 `python3.12 -m pip install -e .`。

> **注意**：首次转录时会自动从 HuggingFace 下载所选的 Whisper 模型（需要网络）。后续完全离线运行。

> **缓存说明**：重新安装 WhisperKey 或重建本地 `venv` **不会**重复下载已经缓存的模型。只要你没有手动删除 `~/.cache/huggingface/hub` 里的模型文件，就会直接复用。

---

## 🚀 快速开始

### 首次运行

```bash
whisperkey
```

首次运行会自动启动安装向导，引导你完成：

1. **界面语言** — 中文 / English
2. **转录语言** — 中文 / 英文 / 混合 / 其他
3. **Whisper 模型** — base / small / large-v3-turbo
4. **快捷键** — 使用默认或自定义
5. **系统权限** — 逐步引导开启
6. **在线纠错（可选）** — 可启用 OpenAI 在线纠错并把 API key 保存到 macOS Keychain

### 之后每次使用

WhisperKey 在后台运行，不需要打开任何窗口。

| 操作 | 快捷键 |
|---|---|
| 开始录音 | 按住右 Option ⌥ |
| 停止并转录 | 松开右 Option ⌥ |
| 免提模式开/关 | 右 Option ⌥ + 右 Command ⌘ |

---

## ⌨️ 快捷键

默认快捷键：

```
右 Option ⌥  （按住）         →  开始录音
右 Option ⌥  （松开）         →  停止录音 + 自动转录 + 粘贴
右 Option ⌥  + 右 Command ⌘  →  免提模式开/关
```

可通过 `whisperkey setup` 自定义快捷键。

---

## 🔧 配置

```bash
whisperkey setup   # 重新运行安装向导
whisperkey permissions  # 打开正确的 macOS 权限页并显示 Python.app 路径
whisperkey help    # 检查权限、模型、音频
```

配置保存在 `~/.config/whisperkey/config.json`，可手动编辑：

```json
{
  "ui_language": "zh",
  "transcribe_language": "auto",
  "model_size": "small",
  "hold_key": "alt_r",
  "handsfree_keys": ["alt_r", "cmd_r"],
  "result_max_lines": 3,
  "online_correct_enabled": false,
  "online_correct_provider": "openai",
  "online_correct_model": "gpt-5-mini"
}
```

### 可选在线纠错

- 默认关闭，可通过 `whisperkey setup` 启用。
- 使用你自己的 OpenAI API key。安装向导会把 key 保存到 macOS Keychain。
- 如果设置了 `OPENAI_API_KEY`，它会覆盖 Keychain 中保存的值。
- 若没有 key、请求超时、或 OpenAI 返回错误，WhisperKey 会自动回退到原始转录文本，不会阻断输入。

### 模型选项

| 模型 | 大小 | 适用场景 |
|---|---|---|
| `base` | ~141 MB | 低配设备，速度优先 |
| `small` | ~464 MB | **推荐 ⭐** 速度与准确度平衡 |
| `large-v3-turbo` | ~1.5 GB | 最高准确度 |

---

## 🔒 系统权限

WhisperKey 需要两个 macOS 系统权限：

**1. 输入监控** — 用于监听快捷键
→ 系统设置 → 隐私与安全性 → 输入监控

**2. 辅助功能** — 用于将文字粘贴到当前应用
→ 系统设置 → 隐私与安全性 → 辅助功能

在两处均将 **Python.app** 添加到列表并开启开关。Python.app 的路径通常为：
```
/opt/homebrew/Cellar/python@3.xx/x.x.x/Frameworks/Python.framework/Versions/3.xx/Resources/Python.app
```

---

## 🛠️ 故障排查

```bash
whisperkey help
```

自动检查：进程状态 · 辅助功能 · 输入监控 · 音频设备 · 模型文件 · 配置文件

**按快捷键没有反应** → 检查输入监控权限
**转录结果没有粘贴** → 检查辅助功能权限
**在线纠错没有生效** → 重新运行 `whisperkey setup` 或设置 `OPENAI_API_KEY`
**Electron / Web 聊天输入框显示 `inject_path=applescript`** → 这是预期兼容路径；这类输入框常常不会完整暴露 AX 文本角色

```bash
tail -f /tmp/whisperkey.log                            # 实时日志
launchctl kickstart -k gui/$(id -u)/com.whisperkey    # 重启服务
```

---

<details>
<summary>🚀 开机自启（LaunchAgent 设置）</summary>

```bash
# 1. 在本地安装（不依赖外置磁盘）
mkdir -p ~/Library/Application\ Support/whisperkey
python3 -m venv ~/Library/Application\ Support/whisperkey/venv
~/Library/Application\ Support/whisperkey/venv/bin/pip install git+https://github.com/Phat-Po/whisperkey-mac.git

# 2. 创建 LaunchAgent
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

# 将 YOUR_USERNAME 替换为你的用户名

# 3. 注册服务
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.whisperkey.plist
```

这种 LaunchAgent 写法比直接调用 console script 更稳，也会继续复用磁盘上已缓存的模型。

</details>

<details>
<summary>🛠️ 开发</summary>

```bash
git clone https://github.com/Phat-Po/whisperkey-mac.git
cd whisperkey-mac
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

whisperkey        # 直接运行
whisperkey setup  # 重新配置
whisperkey help   # 故障排查
```

```
whisperkey_mac/
├── main.py               # 入口，CLI 路由
├── config.py             # 配置读写（JSON + 环境变量）
├── i18n.py               # 中英文字符串字典
├── keyboard_listener.py  # 按住模式 + 免提模式逻辑
├── audio.py              # 音频录制（sounddevice）
├── transcriber.py        # Whisper 语音转文字（faster-whisper）
├── online_correct.py     # 可选 OpenAI 在线纠错管线
├── keychain.py           # OpenAI API key 的 macOS Keychain 辅助
├── output.py             # 文字注入（剪贴板 + 聚焦目标粘贴）
├── setup_wizard.py       # 交互式终端安装向导
└── help_cmd.py           # 故障排查工具
```

</details>

---

## 📄 License

MIT © 2026 [Phat-Po](https://github.com/Phat-Po)

---

<div align="center">

Built with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [pynput](https://github.com/moses-palmer/pynput) · [sounddevice](https://python-sounddevice.readthedocs.io/)

如果这个项目对你有帮助，欢迎点个 ⭐ Star！

</div>
