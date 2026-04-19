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

**按住按键说话，松开完成转录。**

macOS 本地语音输入工具 — 离线、免费、无订阅。可选本地或云端后处理，把口语稿整理成干净的书面文字。

📖 [View English README](README.md)

---

## 为什么选择 WhisperKey？

大部分 macOS 语音输入工具要么只能联网，要么价格昂贵：

| | WhisperKey | SuperWhisper | Wispr Flow | macOS 听写 |
|---|:---:|:---:|:---:|:---:|
| 免费 & 开源 | ✅ | ❌（$250 买断） | ❌（$15/月） | ✅ |
| 完全离线转录 | ✅ | ✅ | ❌ | ❌ |
| 中英混合 | ✅ | ✅ | ✅ | ⚠️ |
| 语音清理（去赘词、重写） | ✅ | ✅ | ✅ | ❌ |
| 自订替换词典 | ✅ | ⚠️ | ⚠️ | ❌ |
| Token 用量仪表板 | ✅ | ❌ | ❌ | ❌ |
| 自订快捷键 | ✅ | ✅ | ❌ | ❌ |
| 直接下载 `.app` | ✅ | ✅ | ✅ | — |

WhisperKey 以 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 在本机完成转录。核心听写流程完全本地优先，可选 OpenAI 后处理则由你自己的 API Key 驱动。

---

## ✨ 核心功能

### 🎙️ 语音输入
- **按住说话** — 按住 Right Option ⌥ 录音，松开自动转录
- **免持模式** — Right Option ⌥ + Right Command ⌘ 切换持续录音
- **90+ 语言** 支持，中英混合处理
- **完全离线转录**（faster-whisper）— 首次下载模型后无需联网
- **自动粘贴** 到当前应用
- **VoiceInput 胶囊浮层** — 紧凑低干扰的录音/转录/结果视觉回馈

### 🧼 可选 AI 后处理
- **语音清理（Voice Cleanup）** — 去除「嗯」「呃」「就是」「那個」等口头禅、删除重复、把散乱口语重组成通顺文字
- **ASR 纠错** — 修正同音字、标点、明显的识别错误（短文本适用，改写幅度最小）
- **自订 Prompt** — 使用你自己的系统提示词，做领域专属改写
- **输出语言** — 保留原文 / 翻成英文 / 翻成中文
- 使用你自己的 OpenAI API Key，存放在 macOS Keychain（绝不进 git）

### ⚙️ 完整可调
- **Settings GUI**，5 个分页：一般、语音、替换词典、用量、进阶
- **选单列 App** — 实时状态、一键暂停/恢复、快速开启 Settings
- **替换词典** — 自动把 `cloude → Claude`、`gpt → GPT` 等错识修回
- **Token 用量仪表板** — 追踪 OpenAI 消耗（今日/本周/总计）与磁碟占用
- **麦克风选择器** — 支援任何已连接输入装置
- **完全自订快捷键** — hold key 与 handsfree 组合
- **开机自启** 一键切换（由 macOS LaunchAgent 管理）
- **中英双语 UI** 贯穿 setup、Settings、选单列
- **优雅降级** — 云端逾时或错误时自动贴上原始转录

---

## 📋 系统需求

- **macOS** 12 Monterey 或更高（建议 Apple Silicon）
- **Python 3.10+**（仅源码安装需要；使用 `.app` 不需要）
- **麦克风**
- 系统权限：**输入监控** + **辅助使用**
- *（可选）* OpenAI API Key 用于后处理

---

## 📦 安装

### 方式 A — 下载 App（推荐）

到 [Releases 页面](https://github.com/Phat-Po/whisperkey-mac/releases) 下载 `WhisperKey-macOS-arm64-v0.2.2.zip`，解压后把 `WhisperKey.app` 拖到 `/应用程式`。

首次启动时授权两个 macOS 权限：
- **输入监控** — 让 WhisperKey 监听快捷键
- **辅助使用** — 让 WhisperKey 把文字贴进当前应用

此版本为本机签名但未经过 Apple 公证。若 macOS 挡下首次启动，请右键 `WhisperKey.app` → **打开** → 确认。

首次转录会从 HuggingFace 下载所选 Whisper 模型（需联网一次）。之后转录完全离线运行。

### 方式 B — 从源码安装

```bash
pip install git+https://github.com/Phat-Po/whisperkey-mac.git
```

或 clone 下来开发：

```bash
git clone https://github.com/Phat-Po/whisperkey-mac.git
cd whisperkey-mac
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

> **macOS 提示**：若 `python3 -V` 低于 3.10，请明确指定 Homebrew 版本：`python3.12 -m venv .venv`。

> **模型快取**：重装或重建 venv **不会** 重新下载已快取的模型。`~/.cache/huggingface/hub` 下的模型会自动复用，除非手动删除。

---

## 🚀 快速开始

### 首次运行

```bash
whisperkey
```

交互式设置精灵会引导你：

1. **界面语言** — English 或 中文
2. **转录语言** — 英文 / 中文 / 混合 / 其它
3. **Whisper 模型** — base / small / large-v3-turbo
4. **快捷键** — 使用默认或自订
5. **系统权限** — 引导授权
6. **AI 后处理（可选）** — 选择模式并把 OpenAI API Key 存入 Keychain

### 日常使用

WhisperKey 常驻于选单列，无需开窗。

| 操作 | 快捷键 |
|---|---|
| 开始录音 | 按住 Right Option ⌥ |
| 停止并转录 | 松开 Right Option ⌥ |
| 切换免持模式 | Right Option ⌥ + Right Command ⌘ |

---

## 🎛️ 后处理模式

本机转录完成后，WhisperKey 可选择把结果送到 OpenAI 做清理。**Settings → 语音 → Processing Mode** 提供 3 种模式：

| 模式 | 用途 | 适合场景 | 建议逾时 |
|---|---|---|---|
| **Disabled** | 直接贴上 Whisper 原文 | 最快；不调用云端 | — |
| **ASR Correction** | 修正同音字、缺漏标点、明显识别错误，几乎不改写 | 短语、指令输入、技术词 | 3 秒 |
| **Voice Cleanup** ⭐ | 去除「嗯/呃/就是/那個」等赘词、删除重复犹豫、把散乱口语重组成通顺文字。保留所有具体细节（数字、名称、限制条件）。 | 较长的说话内容、笔记、起草邮件/文档 | 8 秒 |
| **Custom** | 使用你自己的 system prompt | 领域专属改写（正式语气、代码、翻译风格等） | 8 秒 |

所有模式在逾时或 API 错误时都会自动降级为原始转录。

---

## 🍎 选单列控制

WhisperKey 常驻 macOS 选单列。点击图标可：

- **状态列** — running / paused / 等待权限
- **暂停 / 恢复** — 不退出程序的临时停止监听（玩游戏或录屏时好用）
- **Settings…** — 开启完整 Settings GUI
- **Quit WhisperKey**

选单列标题会根据服务状态实时变化。

---

## ⚙️ Settings GUI

**选单列 → Settings…** 开启。5 个分页涵盖所有配置：

### 一般（General）
- 界面语言（zh / en）
- 转录语言（Auto / zh / en / 其它 ISO code）
- **输出语言**（保留原文 / 翻成英文 / 翻成中文）
- Whisper 模型（`base` / `small` / `large-v3-turbo`）
- **麦克风** — 挑选任一已连接的输入装置（或系统默认）
- **开机自启** 切换

### 语音（Voice）
- **Processing Mode**（Disabled / ASR Correction / Voice Cleanup / Custom）
- **Online Model**（如 `gpt-5.4` — 可自订）
- **逾时**秒数（建议：Voice Cleanup 8 秒，ASR Correction 3 秒）

### 替换词典（Word Fix）
个人化词典，会对每次转录结果做替换。适合 STT 模型老是听错的品牌名或专有名词。

```
cloude → Claude
cloud ai → Claude AI
open ei eye → OpenAI
```

- 一行一条替换
- 使用 `→` 或 `->`
- 不分大小写，最长匹配优先
- 完全本地执行，不调用云端

### 用量（Usage）
实时仪表板，显示：
- OpenAI token 消耗（输入/输出，今日/本周/总计）
- 磁碟占用 — 音频暂存 + Whisper 模型快取路径

### 进阶（Advanced）
- **Hold Key** — 任意 pynput 按键名（如 `alt_r`、`cmd_r`、`f13`）
- **Handsfree Keys** — 逗号分隔组合（如 `alt_r, cmd_r`）
- **API Key** — 贴上新的 OpenAI key；自动存入 macOS Keychain

---

## 📊 用量追踪

**Usage** 分页透明呈现你的 OpenAI 消耗：

- 每日 / 每周 / 总计的 输入/输出 token 数
- 音频暂存磁碟占用（`/tmp/whisperkey_mac/`）
- Whisper 模型快取占用（`~/.cache/huggingface/hub/`）
- 一键刷新

所有数据仅本地读取，不上传任何遥测。

---

## 🔧 配置文件

进阶或脚本化场景可直接编辑 `~/.config/whisperkey/config.json`：

```json
{
  "ui_language": "zh",
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

### 环境变量覆写

适合 LaunchAgent 与 CI 场景：

| 变量 | 覆写项 |
|---|---|
| `OPENAI_API_KEY` | Keychain 内的 API key |
| `WHISPERKEY_MODEL` | `model_size` |
| `WHISPERKEY_COMPUTE_TYPE` | `compute_type`（默认 `int8`） |
| `WHISPERKEY_DEVICE` | `device`（默认 `cpu`） |
| `WHISPERKEY_LANGUAGE` | Whisper 语言提示 |
| `WHISPERKEY_SAMPLE_RATE` | 录音采样率 |
| `WHISPERKEY_AUTO_PASTE` | `1` / `0` |
| `WHISPERKEY_RESULT_MAX_LINES` | HUD 行数上限 |
| `WHISPERKEY_ONLINE_CORRECT` | `1` / `0` |
| `WHISPERKEY_ONLINE_CORRECT_MODEL` | OpenAI 模型名 |
| `WHISPERKEY_ONLINE_PROMPT_MODE` | `disabled` / `asr_correction` / `voice_cleanup` / `custom` |

### 模型选项

| 模型 | 大小 | 适合 |
|---|---|---|
| `base` | ~141 MB | 低配设备、速度优先 |
| `small` | ~464 MB | **推荐 ⭐** 速度与准确度平衡 |
| `large-v3-turbo` | ~1.5 GB | 最高准确度 |

---

## 🔒 系统权限

WhisperKey 需要两个 macOS 系统权限：

**1. 输入监控**（Input Monitoring）— 监听快捷键
→ 系统设置 → 隐私与安全性 → 输入监控

**2. 辅助使用**（Accessibility）— 把转录文字贴进当前应用
→ 系统设置 → 隐私与安全性 → 辅助使用

把 `whisperkey permissions` 或 `whisperkey help` 列出的应用加到两个列表并启用开关。
源码安装通常是 Python.app：
```
/opt/homebrew/Cellar/python@3.xx/x.x.x/Frameworks/Python.framework/Versions/3.xx/Resources/Python.app
```
打包版本则授权 `WhisperKey.app`。

> **注意**：每次打包 CDHash 都会变，所以升级 `.app` 后需重新授权两个权限。

---

## 🛠️ 故障排查

```bash
whisperkey help
```

自动检查：进程状态 · 辅助使用 · 输入监控 · 音频设备 · 模型文件 · 配置

| 症状 | 解决 |
|---|---|
| 快捷键无响应 | 检查**输入监控**权限 |
| 转录没粘贴 | 检查**辅助使用**权限 |
| 后处理没生效 | 重跑 `whisperkey setup` 或设 `OPENAI_API_KEY`；确认 Settings → 语音 → Processing Mode |
| 日志出现 `inject_path=applescript` | Electron/网页类应用的兼容路径，属预期 |
| 升级 `.app` 后失效 | 重新授权输入监控 + 辅助使用（CDHash 变了） |

```bash
tail -f /tmp/whisperkey.log                           # 实时日志
launchctl kickstart -k gui/$(id -u)/com.whisperkey    # 重启服务
```

---

<details>
<summary>🚀 开机自启（LaunchAgent 手动设置）</summary>

Settings GUI 的 **Launch at Login** 开关会自动管理这个。源码安装的手动方案：

```bash
# 1. 本地安装（不要放外接磁碟）
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

# 把 YOUR_USERNAME 改成实际用户名

# 3. 注册服务
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.whisperkey.plist
```

LaunchAgent 会启动 crash supervisor，由它拉起主程序；若意外退出会把细节写入 `/tmp/whisperkey-last-crash.log` 并弹出 macOS 通知。

</details>

<details>
<summary>🛠️ 开发</summary>

```bash
git clone https://github.com/Phat-Po/whisperkey-mac.git
cd whisperkey-mac
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

whisperkey        # 运行
whisperkey setup  # 重新配置
whisperkey help   # 故障排查
```

```
whisperkey_mac/
├── main.py               # 入口，CLI 路由
├── app_entry.py          # 选单列 App 启动
├── menu_bar.py           # 选单列图标 + 状态同步
├── settings_window.py    # Settings GUI（5 分页）
├── config.py             # 配置读写（JSON + 环境变量）
├── i18n.py               # zh/en 字串字典
├── keyboard_listener.py  # Hold-key + 免持快捷键逻辑
├── audio.py              # 录音（sounddevice）
├── transcriber.py        # Whisper STT（faster-whisper）
├── online_correct.py     # 可选 OpenAI 后处理管线
├── keychain.py           # macOS Keychain 助手（OpenAI API key）
├── output.py             # 文字注入（剪贴板 + 当前应用粘贴）
├── overlay.py            # VoiceInput 胶囊浮层
├── usage_log.py          # Token 消耗追踪
├── launch_agent.py       # LaunchAgent 安装/卸载
├── setup_wizard.py       # 交互式终端设置
└── help_cmd.py           # 故障排查工具
```

打包：`packaging/macos/build_app.sh`（PyInstaller + codesign）→ `packaging/macos/package_release.sh`（打 zip 上传 Release）。

</details>

---

## 📄 License

MIT © 2026 [Phat-Po](https://github.com/Phat-Po)

---

<div align="center">

基于 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [pynput](https://github.com/moses-palmer/pynput) · [sounddevice](https://python-sounddevice.readthedocs.io/) · [PyObjC](https://pyobjc.readthedocs.io/)

如果这个项目对你有帮助，请给个 ⭐ Star！

</div>
