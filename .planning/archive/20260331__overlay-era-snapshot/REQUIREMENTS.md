# Requirements: WhisperKey — Recording Overlay UI

**Defined:** 2026-03-09
**Core Value:** 按住热键说话，松开就出现文字——零延迟感、零打断工作流。

## v1 Requirements

### Overlay Foundation

- [x] **OVL-01**: 录音中，屏幕底部居中显示半透明圆角浮层（NSPanel，常驻最顶层，点击穿透）
- [x] **OVL-02**: 浮层出现时不抢夺焦点，不打断用户当前文字输入
- [x] **OVL-03**: 浮层在所有 Space 可见（Mission Control 切换不消失）

### Recording State

- [x] **REC-01**: 录音期间浮层显示动态波形动画（4-6 bars，~30fps，idle sine-wave）
- [x] **REC-02**: 浮层出现动效：150ms fade-in + 8pt 上滑，ease-out

### Transcribing State

- [x] **TRN-01**: 松开热键后，浮层切换到"转录中"状态，显示 3 dots 脉冲动画（300ms/dot，900ms 全循环）
- [x] **TRN-02**: 录音状态平滑切换到转录中状态（无闪烁）

### Result State — Text Input Branch

- [x] **RST-01**: 转录完成，若光标在文字输入框，静默注入文字，并短暂显示转录结果与"已输入"提示

### Result State — Clipboard Branch

- [x] **RST-02**: 转录完成，若光标不在文字输入框，浮层显示转录文字内容
- [x] **RST-03**: 浮层根据输出分支显示"已输入"或"已复制到剪贴板"提示文字
- [x] **RST-04**: 输入框分支约 1.2 秒后 250ms fade-out；剪贴板分支 3 秒后 400ms fade-out；取消/空录音分支快速收尾

### Text Input Detection

- [x] **DET-01**: 使用 macOS Accessibility API 判断当前焦点是否在文字输入框（AXRole 匹配 AXTextField / AXTextArea / AXComboBox / AXSearchField）
- [x] **DET-02**: Accessibility API 失败或返回 None 时，默认走剪贴板路径（安全降级）

## v2 Requirements

### Visual Enhancement

- **VIS-01**: 波形改为 RMS 驱动（实时音频振幅），替代 idle sine-wave
- **VIS-02**: 多显示器支持——浮层跟随当前活跃窗口所在的屏幕

### Result Readability

- [x] **RES-01**: 结果浮层支持最多 2-3 行显示，长文本先换行再截断
- [x] **RES-02**: 结果浮层根据文本行数自适应高度，不影响录音/转录状态的固定布局

### Online Correction

- [x] **COR-01**: 转录完成后可选执行 OpenAI 在线纠错，用于修正常见同音字、近音词、上下文小错误
- [x] **COR-02**: 在线纠错必须可开关；请求失败、缺 key、超时或解析失败时回退原始转录结果，不阻断输出

## v3 Research Backlog

### Streaming / Incremental ASR

- **STR-01**: 评估本地实时或准实时转录方案，支持边说边显示增量文本
- **STR-02**: 在实现前对延迟、准确率、CPU/内存成本、Apple Silicon 适配难度做研究对比

## Out of Scope

| Feature | Reason |
|---------|--------|
| 菜单栏图标变化 | 有浮层已足够，避免冗余 |
| 可拖动浮层 | solo 用户不需要，增加状态复杂度 |
| 转录历史记录 | 超出本次功能范围 |
| 流式局部转录（streaming） | faster-whisper 返回完整结果；伪造 streaming 有误导性 |
| 声音效果 | 未请求 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| OVL-01 | Phase 1 | Complete |
| OVL-02 | Phase 1 | Complete |
| OVL-03 | Phase 1 | Complete |
| REC-01 | Phase 3 | Complete |
| REC-02 | Phase 3 | Complete |
| TRN-01 | Phase 3 | Complete |
| TRN-02 | Phase 3 | Complete |
| RST-01 | Phase 2 | Complete |
| RST-02 | Phase 3 | Complete |
| RST-03 | Phase 3 | Complete |
| RST-04 | Phase 4 | Complete |
| DET-01 | Phase 2 | Complete |
| DET-02 | Phase 2 | Complete |
| RES-01 | Plan 5 | Complete |
| RES-02 | Plan 5 | Complete |
| COR-01 | Plan 5 | Complete |
| COR-02 | Plan 5 | Complete |
| STR-01 | Plan 6 | Pending |
| STR-02 | Plan 6 | Pending |

**Coverage:**
- v1 requirements: 11 total
- Mapped to phases: 11
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-09*
*Last updated: 2026-03-12 — Plan 5 multiline HUD and optional OpenAI correction implemented*
