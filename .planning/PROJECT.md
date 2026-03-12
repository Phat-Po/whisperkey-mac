# WhisperKey

## What This Is

WhisperKey 是一个 macOS 本地离线语音输入工具。按住热键录音，松开后自动转录并注入文字到当前应用。基于 faster-whisper，无需联网、无订阅费用，支持中英文混合识别。目标用户是自己（solo 使用场景）。

## Core Value

按住热键说话，松开就出现文字——零延迟感、零打断工作流。

## Requirements

### Validated

- ✓ 按住 Right Option 录音，松开触发转录并注入文字 — MVP
- ✓ Hands-free 模式（Option + Command 切换持续录音）— MVP
- ✓ 支持中文、英文及 90+ 语言 — MVP
- ✓ 完全离线运行（首次联网下载模型后） — MVP
- ✓ 转录结果自动复制到剪贴板并注入当前 app — MVP
- ✓ 交互式双语设置向导（zh/en） — MVP
- ✓ macOS LaunchAgent 开机自启动 — MVP
- ✓ 自定义热键配置 — MVP
- ✓ `whisperkey help` 诊断命令 — MVP
- ✓ 底部居中 HUD 浮层已上线：录音 bars、转录 dots、深灰玻璃结果条 — MVP
- ✓ 转录完成后始终显示结果文字：输入框分支显示“已输入”，非输入框分支显示“已复制到剪贴板” — MVP
- ✓ Finder / 桌面安全走剪贴板分支，不再误触系统提示音 — MVP
- ✓ 快速连续按压 5 次以上不会残留 bars/dots 或卡住转录状态 — MVP
- ✓ 结果 HUD 支持最多 3 行显示与自适应高度，长文本不再只剩单行截断 — Post-MVP
- ✓ 可选 OpenAI 在线纠错已接入：用户自带 API key，Keychain 保存，失败自动回退原始转录 — Post-MVP

### Active

- [ ] Plan 5: 用真实 OpenAI API key 做一次手动验证，确认 setup / Keychain / correction 回退链路正常
- [ ] Plan 6: 评估是否引入边说边出字的 streaming / incremental ASR 架构

### Queued Post-MVP Optimizations

- [ ] 实时/准实时转录研究：评估是否值得引入边说边出字的 streaming 架构；这项先做 research spike，不直接进入主流程

### Out of Scope

- 菜单栏图标变化 — 有浮层已够，避免重复
- 转录历史记录 — 当前阶段不需要
- 多语言 UI 切换（浮层固定中文即可）— 简化实现

## Context

- 现有 MVP 已在本地 macOS 稳定运行，后台 LaunchAgent 已配置
- 包名：`whisperkey-mac`，CLI 入口：`whisperkey`
- 代码结构：`whisperkey_mac/`（main.py、keyboard_listener.py、audio.py、transcriber.py、output.py 等）
- 目前误触 hands-free 模式的问题是核心痛点，浮层 UI 可提供视觉反馈，降低误操作
- 技术栈：Python 3.10+，macOS AppKit/PyObjC 可用于浮层 UI
- GitHub：https://github.com/Phat-Po/whisperkey-mac

## Constraints

- **Platform**: macOS only — 浮层 UI 使用 macOS 原生框架
- **Language**: Python — 保持和现有代码库一致，不引入新语言
- **No bundling**: 不打包成 .app，仍以 pip install / python -m 方式运行

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 浮层使用 PyObjC/AppKit 实现 | Python 原生 tkinter 难以做透明浮层，AppKit 是 macOS 标准 | Implemented |
| 底部居中，深灰玻璃 HUD | 类 Apple HUD 设计，不遮挡主要工作内容且提升白字可读性 | Implemented |
| 在线纠错采用用户自带 OpenAI API key | 不新增 WhisperKey 自有后端，不要求 OAuth；把成本和凭证控制权留给用户 | Implemented |
| 实时转录先研究后实现 | 流式 ASR 是架构级改造，必须先验证延迟/准确率/CPU 成本 | Queued |

---
*Last updated: 2026-03-12 after implementing Plan 5 multiline HUD + optional OpenAI correction*
