# 设计说明：处理模式重命名 + 新增 Summarize 模式

> **状态：已实现（2026-06-20，`批准执行`）。** 307 测试全绿。本节以下为设计记录。
> 关联代码：`whisperkey_mac/online_correct.py`、`config.py`、`i18n.py`、`settings_window.py`、`menu_bar.py`

---

## 0. 关键澄清（必读）

操作者口中的「ASR 口语纠正」在现有代码里其实对应 **两个不同的模式**，需要先消歧：

| 操作者用语 | 真实存在的模式 | 行为 |
|---|---|---|
| 「ASR 纠错 / 口语纠正」 | `asr_correction`（UI：ASR 纠错） | 只修同音字、标点、明显 ASR 错误，不改写、不扩写 |
| 「处理成发给 agent 的指令」 | `voice_cleanup`（UI：口语清理） | 把整段口述转成可执行的 AI agent 指令（`online_correct.py:37` 那段大 prompt） |

操作者描述的「agent 模式」行为——**「把用户的话处理成发给 agent 的指令」**——逐字对应**现有的 `voice_cleanup`**，而**不是** `asr_correction`。

因此本设计的实质是：
1. 把 `voice_cleanup`（口语清理）**重命名**为「Agent 模式」——行为不变，它本来就在做这件事。
2. `asr_correction`（ASR 纠错）**保留不动**——这满足「保留口语纠正功能场景的关联」与「保留 ASR 语境背景」。
3. **新增** `summary` 模式——把整段话 summarize 成简单易读的形式，明确区别于「发指令给 agent」。

---

## 1. 模式总览（改造后 · 操作者命名定稿 2026-06-20）

`online_prompt_mode` 的合法值（`config.py:12` `VALID_PROMPT_MODES`）：

| internal id | 旧 UI 名 | 新 UI 名（中文） | 定位 | 输出形态 |
|---|---|---|---|---|
| `disabled` | 关闭 | 关闭 | 直通，不调用 LLM | 原文 |
| `asr_correction` | ASR 纠错 | **去除干扰词** | **轻度清理**：修错字 + 删填充词（行为扩展，见 §1.1） | 自然顺句，**无模板** |
| `voice_cleanup`（id 不变） | 口语清理 | **Agent 模式** | 转成发给 agent 的长指令 | 结构化可执行指令块 |
| `summary` **（新增）** | — | **总结发言** | 转成简短易读的总结 | 1–4 句口语化白话 |
| `custom` | 自定义 | 自定义 | 用户自定义 prompt | 不限 |

三个核心模式构成递进：**去除干扰词（轻）→ Agent 模式（重组成指令）→ 总结发言（压缩成摘要）**。

### 1.1 命名定稿：`asr_correction` → 「去除干扰词」（含行为扩展）

操作者定名「去除干扰词」。为使名实相符，`asr_correction` 的 prompt **新增 filler 移除能力**：

- **原行为（保留）**：修同音字 / 标点 / 明显识别错误，不翻译、不改写语义、不扩写。
- **新增行为**：删除纯填充词与语气词（嗯/呃/啊/就是/那个/然后/对对对、um/uh/you know/like）——仅当它们不承载语义时才删；若某词标记顺序/转折/因果/强调，则保留。
- **硬边界**：输出仍是**那段话本身的自然顺句**，**绝不**套用 Agent 模式的 `Topic/Tasks` 结构化模板。这是「去除干扰词」与「Agent 模式」的根本区别。

> 该 filler 判定规则可直接借鉴 Agent 模式 prompt（`online_correct.py:47-55`）里已写好的「只删无意义填充词」逻辑，但**不要**带入它的结构化输出段。

> **实现取舍**：`voice_cleanup` 的 internal id **保留不改**（只改 UI 显示文案），避免破坏已存配置文件、cycle 目标、迁移逻辑（`config.py:101` 已有一次 `streaming→voice_cleanup` 迁移的先例）。仅在 i18n / 下拉选项 / 菜单标签层把可见文案换成「Agent 模式」。

---

## 2. 模式详细设计

### 2.0 去除干扰词模式（= `asr_correction`，改名 + 行为扩展）

- **意图**：把语音转写里的错字修对、把无意义的填充词删掉，但**保持原话的自然句子**，不重组、不结构化。
- **行为**：在现有 `_CORRECTION_INSTRUCTIONS`（`online_correct.py:13`）基础上**追加**一条 filler 移除规则。
- **建议追加到 prompt 的内容（草案，待评审）**：

  ```text
  Also remove pure filler words and hesitation sounds when they carry no meaning:
  um, uh, you know, like, 嗯, 呃, 啊, 就是, 那个, 然后, 对对对.
  Only remove them when meaningless. If a word marks sequence, contrast, cause,
  emphasis, or a real transition, keep it.
  Output the cleaned sentences as natural prose. Do NOT use any heading, bullet,
  or Topic/Tasks template. Keep the original meaning, order, and tone.
  ```

- **守卫**：保持现有 `asr_correction` 的守卫（min/max chars + CJK 比例），不放宽。
- **与 Agent 模式的硬边界**：输出**自然散文**，**禁止**出现 `Topic/Objective/Tasks` 模板——那是 Agent 模式专属。

### 2.1 Agent 模式（= 现 `voice_cleanup`，仅改名）

- **意图**：用户对着麦克风口述一段需求，输出可直接粘贴给 AI agent 执行的指令。
- **行为**：完全沿用现有 `_VOICE_CLEANUP_PROMPT`（`online_correct.py:37-95`），不改 prompt 内容。
- **输出格式**：现有的 `Topic / Objective / Tasks / Requirements / Constraints / Preferences / Inputs / Output / Notes` 结构化块。
- **守卫**：沿用现有 `_should_process_online` 中 `voice_cleanup` 分支——跳过 max_chars / CJK 比例检查，只看 `min_chars`（`online_correct.py:194-196`）。
- **改动面**：仅 UI 文案（见 §3）。逻辑零改动。

### 2.2 总结发言模式（新增 `summary`）· 风格定稿：简短口语化

- **意图**：用户口述一长段话（会议想法、灵感、复述），输出**人类直接可读的简短白话总结**，不是给机器执行的指令。
- **风格定稿（操作者 2026-06-20）**：**简短口语化** —— 1–4 句白话陈述，像随手记的要点，不要书面腔、不要模板字段。
- **与 Agent 模式的硬性区别**：

  | 维度 | Agent 模式 | Summarize 模式 |
  |---|---|---|
  | 受众 | AI agent（机器执行） | 人（直接阅读） |
  | 输出 | 指令/任务块，含 Tasks/Constraints | 顺畅的摘要句子，无任务清单语气 |
  | 结构 | 强结构化 Topic 模板 | 自然段或极简要点，无模板字段 |
  | 语气 | 祈使句「帮我…」「第二步…」 | 陈述句「用户想…，重点是…」 |
  | 取舍 | 保留全部细节、约束、参数 | 抓主旨、压缩冗余，允许丢弃次要细节 |

- **建议 prompt（草案，待评审）**：

  ```text
  You summarize raw voice-to-text transcripts into a short, plain, easy-to-read summary
  for a human reader. This is NOT a list of instructions for an AI agent.

  Do this internally:
  1. Find the main point(s) and the speaker's intent.
  2. Drop filler, hesitation, repetition, and self-corrections (keep only the final intent).
  3. Compress secondary detail; keep only what a reader needs to understand the gist.

  Rules:
  * Output in the same language as the input.
  * Write 1–4 short sentences, or at most a few plain bullet points if there are
    clearly separate topics. No headings, no bold, no template fields.
  * Use plain declarative statements ("The user wants…", "Key point is…"),
    NOT imperative commands ("do X", "step 2…").
  * Do NOT turn this into executable tasks or an agent instruction block.
  * Do NOT add information not present in the transcript.
  * Keep important specifics (names, numbers, decisions) only if central to the gist.
  * No preamble, no explanation. Output only the summary.
  ```

- **守卫**：与 `voice_cleanup` 一致——长文本/中英混合友好，跳过 max_chars 与 CJK 比例检查，只看 `min_chars`。
- **token 上限**：建议 `max_output_tokens=512`（介于 `asr_correction` 的 256 与 `voice_cleanup` 的 1024 之间，因摘要应短）。

---

## 3. 落地改动清单（实现阶段参考，本文档不执行）

| 文件 | 改动 |
|---|---|
| `online_correct.py` | ① `_CORRECTION_INSTRUCTIONS`（及 `_TO_EN`/`_TO_ZH` 三个变体）追加 filler 移除规则（§2.0）；② 新增 `_SUMMARY_PROMPT` + `_summary_prompt()`，`maybe_process_online` 加 `mode == "summary"` 分支（仿 `voice_cleanup`，`max_output_tokens=512`，`log_usage("summary", …)`）；③ `_should_process_online` 加 `summary` 分支（同 `voice_cleanup` 守卫） |
| `config.py:12` | `VALID_PROMPT_MODES` 加入 `"summary"` |
| `config.py` | 可选：`DEFAULT_MODE_CYCLE_TARGETS` 是否纳入 `summary`（默认先不加，避免快捷键 cycle 变长） |
| `i18n.py:221-222 / 472-473` | `menu_mode_asr`：`ASR 纠错→去除干扰词` / `ASR Correction→Remove Fillers`；`menu_mode_cleanup`：`口语清理→Agent 模式` / `Voice Cleanup→Agent Mode`；新增 `menu_mode_summary`：`总结发言 / Summarize` |
| `settings_window.py:46-47` | `PROMPT_MODE_OPTIONS`：`("asr_correction","Remove Fillers")`、`("voice_cleanup","Agent Mode")`，新增 `("summary","Summarize")` |
| `menu_bar.py` | 处理模式子菜单：纠错项改名「去除干扰词」，加入「总结发言」项 |
| `tests/` | ① asr_correction 新增 filler 移除断言（且断言**无**模板字段）；② 加 `summary` 分支的处理/守卫单测 |

> **不改**：`voice_cleanup` 的 internal id 与 prompt 内容、现有迁移逻辑。
> **行为变更**：`asr_correction` 的 prompt（追加 filler 移除）—— 已经操作者要求确认。

---

## 4. 决策记录 / 待确认

**已定稿（操作者 2026-06-20）：**
- `asr_correction` → **去除干扰词**，并**扩展行为**：在原有纠错基础上追加 filler 移除，输出仍为自然散文、无模板（§2.0）✅
- `voice_cleanup` → **Agent 模式**（行为不变，专给 agent 发长指令，结构化模板）✅
- 新增 `summary` → **总结发言**，风格 = **简短口语化**（1–4 句白话）✅
- 三模式递进：去除干扰词（轻）→ Agent 模式（重组指令）→ 总结发言（压缩摘要）✅
- 交付范围 = **仅本设计说明**，不进入实现 ✅

**实现前需复核：**
- §2.0 / §2.2 两段 prompt 草案的措辞（filler 清单、摘要长度）。
- 「去除干扰词」与「Agent 模式」的硬边界——前者**绝不**输出 `Topic/Tasks` 模板，需在单测里断言。

> 实现阶段在 `批准执行` 后再启动。
