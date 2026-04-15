from __future__ import annotations

import json
import re

from whisperkey_mac.config import AppConfig
from whisperkey_mac.keychain import load_openai_api_key


_CJK_RE = re.compile(r"[\u3400-\u9fff]")

_CORRECTION_INSTRUCTIONS = (
    "You correct Chinese ASR transcripts. "
    "Return a JSON object with exactly one key: corrected_text. "
    "Keep the original meaning. Fix only obvious ASR mistakes, homophone substitutions, "
    "punctuation, and short context errors. Do not add explanations. "
    "Do not translate. Do not rewrite style. Do not expand the content."
)

_VOICE_CLEANUP_PROMPT_ZH = """你是一位語音輸入文字清理專家。用戶會貼入語音轉文字的原始逐字稿，你的任務是輸出乾淨、完整、邏輯連貫的版本。

## 處理規則

**第一層：去噪**
- 刪除純填充語氣詞：就是、然後、那個、嗯、啊、齁、對對對、欸、你知道嗎、怎麼說、我跟你說
- 修正語音辨識錯字（根據上下文判斷同音字：在/再、的/得/地、做/作、那/哪 等）
- 修正被打散的專有名詞和術語

**第二層：去重合併**
- 同一個意思用不同方式說了多次 → 合併為表達最清楚的那一版
- 反覆猶豫後有明確結論的 → 只保留最終結論，刪除中間的猶豫過程
- 但如果猶豫本身是重要資訊（例如用戶確實在兩個選項間權衡），則保留為「A 或 B，尚未決定」

**第三層：重組輸出**
- 按語義邏輯重新排列，不必遵循口述的時間順序
- 如果內容包含多個主題，用分段或編號區隔
- 保留所有具體細節：數字、名稱、條件、限制、偏好
- 保留語氣中的不確定度（「應該」「可能」「大概」→ 保留，不要擅自變成肯定句）

## 輸出格式

依照內容性質選擇結構：

**操作指令 / 功能需求**（含步驟、條件、規則、限制）：
- 第一行：主題標題，格式為「主題：」
- 後續：條列式，每條一行，一個完整意思
- 例外或限制條件單獨成條，可標明「例外：」「限制：」

**個人想法 / 筆記 / 腦力激盪**：
- 第一行：一句話說明在思考什麼（不加標籤）
- 後續：標籤開頭的條列，如「動機：」「顧慮：」「初步想法：」
- 若用戶開頭說「筆記模式」，強制使用此風格

**格式規則：**
- 不要加任何說明、前言或「以下是清理後的版本」——直接輸出結果
- 不要用 Markdown 語法（不用 **粗體**，不用 # 標題符號）
- 每行一個完整意思，不要硬換行切斷句子

## 關鍵原則

- 寧可多保留一句，也不要丟失任何原始意圖或細節
- 不要添加原文沒有的內容
- 不要改變用戶的立場或語氣強度
- 如果某段話實在無法確定意思，用 [語意不明：原文片段] 標記

## 輸出語言
輸出為中文。若原文為其他語言，請先翻譯為中文再進行清理。"""

_VOICE_CLEANUP_PROMPT_EN = """You are an expert at cleaning up voice-to-text transcripts. The user will paste a raw voice transcript. Your task is to output a clean, complete, logically coherent version.

## Layer 1: Denoise
- Remove pure filler words: um, uh, you know, like, so, basically, I mean, right, okay so, kind of, sort of
- Fix speech recognition errors based on context
- Fix broken proper nouns and technical terms

## Layer 2: Dedup and Merge
- Same idea stated multiple ways → keep the clearest version
- Repeated hesitation before a clear conclusion → keep only the final conclusion, remove the hesitation
- If the hesitation itself is meaningful (weighing two options) → keep as "A or B, undecided"

## Layer 3: Restructure Output
- Reorder by semantic logic, not necessarily the order spoken
- If content covers multiple topics, use paragraphs or numbering
- Preserve all specifics: numbers, names, conditions, constraints, preferences
- Preserve uncertainty markers (should, might, probably → keep as-is, do not convert to certainties)

## Output Format

Choose structure based on content type:

**Action instructions / Feature requirements** (steps, conditions, rules, constraints):
- First line: topic title in format "Topic:"
- Subsequent lines: one bullet per point, one complete idea per line
- Exceptions and constraints get their own bullet, labeled "Exception:" or "Constraint:"

**Personal thoughts / Notes / Brainstorm**:
- First line: one sentence stating what is being considered (no label)
- Subsequent lines: labeled bullets like "Motivation:", "Concerns:", "Initial idea:"
- If user starts with "note mode", force this style

**Format rules:**
- No preamble, explanation, or "here is the cleaned version" — output the result directly
- No Markdown syntax (no **bold**, no # heading markers)
- One complete idea per line, never break a sentence with a hard line break

## Key Principles
- Keep one extra sentence rather than lose any original intent or detail
- Do not add content not present in the original
- Do not change the user's stance or tone intensity
- If a segment is truly unclear, mark it as [unclear: original fragment]

Output in English. If the input is not in English, translate it to English first, then clean up."""

_VOICE_CLEANUP_PROMPT_AUTO = """You are an expert at cleaning up voice-to-text transcripts. The user will paste a raw voice transcript. Your task is to output a clean, complete, logically coherent version.

## Layer 1: Denoise
- Remove pure filler words (e.g. um, uh, you know, 就是, 那個, 嗯, 啊, 然後, 對對對)
- Fix speech recognition errors based on context
- Fix broken proper nouns and technical terms

## Layer 2: Dedup and Merge
- Same idea stated multiple ways → keep the clearest version
- Repeated hesitation before a clear conclusion → keep only the final conclusion
- If the hesitation itself is meaningful (weighing options) → keep as "A or B, undecided"

## Layer 3: Restructure Output
- Reorder by semantic logic, not necessarily the order spoken
- If content covers multiple topics, use paragraphs or numbering
- Preserve all specifics: numbers, names, conditions, constraints, preferences
- Preserve uncertainty markers (should, might, probably, 應該, 可能, 大概 → keep as-is)

## Output Format

Choose structure based on content type:

**Action instructions / Feature requirements** (steps, conditions, rules, constraints):
- First line: topic title in format "Topic:"
- Subsequent lines: one bullet per point, one complete idea per line
- Exceptions and constraints get their own bullet, labeled "Exception:" or "Constraint:"

**Personal thoughts / Notes / Brainstorm**:
- First line: one sentence stating what is being considered (no label)
- Subsequent lines: labeled bullets like "Motivation:", "Concerns:", "Initial idea:"

**Format rules:**
- No preamble or explanation — output the result directly
- No Markdown syntax (no **bold**, no # heading markers)
- One complete idea per line, never break a sentence with a hard line break

## Key Principles
- Keep one extra sentence rather than lose any original intent or detail
- Do not add content not present in the original
- Do not change the user's stance or tone intensity
- If a segment is truly unclear, mark it as [unclear: original fragment]

Output in the same language(s) as the input. If the input mixes Chinese and English, preserve the mix naturally."""


def _voice_cleanup_prompt(config: AppConfig) -> str:
    output_lang = getattr(config, "output_language", "auto")
    if output_lang == "en":
        return _VOICE_CLEANUP_PROMPT_EN
    if output_lang == "zh":
        return _VOICE_CLEANUP_PROMPT_ZH
    return _VOICE_CLEANUP_PROMPT_AUTO


def maybe_process_online(text: str, config: AppConfig) -> str:
    normalized = text.strip()
    if not normalized:
        return normalized

    mode = _prompt_mode(config)
    if not _should_process_online(normalized, config, mode):
        return normalized

    api_key = load_openai_api_key()
    if not api_key:
        return normalized

    client = _build_openai_client(api_key, config.online_correct_timeout_s)
    if client is None:
        return normalized

    try:
        if mode == "custom":
            response = client.responses.create(
                model=config.online_correct_model,
                instructions=config.online_prompt_custom_text.strip(),
                input=normalized,
                max_output_tokens=256,
            )
            return _extract_plain_text(getattr(response, "output_text", "")) or normalized

        if mode == "voice_cleanup":
            response = client.responses.create(
                model=config.online_correct_model,
                instructions=_voice_cleanup_prompt(config),
                input=normalized,
                max_output_tokens=1024,
            )
            return _extract_plain_text(getattr(response, "output_text", "")) or normalized

        # asr_correction (default)
        response = client.responses.create(
            model=config.online_correct_model,
            instructions=_CORRECTION_INSTRUCTIONS,
            input=f"Transcript:\n{normalized}",
            text={"format": {"type": "json_object"}},
            max_output_tokens=256,
        )
        corrected = _extract_corrected_text(getattr(response, "output_text", ""))
        return corrected or normalized

    except Exception as exc:
        print(f"[whisperkey] online_correct error: {exc}")
        return normalized


def maybe_correct_online(text: str, config: AppConfig) -> str:
    return maybe_process_online(text, config)


def _prompt_mode(config: AppConfig) -> str:
    mode = getattr(config, "online_prompt_mode", "")
    if mode in {"disabled", "asr_correction", "custom", "voice_cleanup"}:
        return mode
    return "asr_correction" if config.online_correct_enabled else "disabled"


def _should_process_online(text: str, config: AppConfig, mode: str) -> bool:
    if mode == "disabled":
        return False
    if config.online_correct_provider != "openai":
        return False
    if mode == "custom":
        return bool(config.online_prompt_custom_text.strip())
    if mode == "voice_cleanup":
        # Skip max_chars and CJK ratio checks — voice cleanup handles long/mixed text
        return len(text) >= config.online_correct_min_chars
    # asr_correction: apply all guards
    if len(text) < config.online_correct_min_chars:
        return False
    if len(text) > config.online_correct_max_chars:
        return False
    if _cjk_ratio(text) < config.online_correct_min_cjk_ratio:
        return False
    return True


def _cjk_ratio(text: str) -> float:
    non_space_chars = [char for char in text if not char.isspace()]
    if not non_space_chars:
        return 0.0
    cjk_chars = sum(1 for char in non_space_chars if _CJK_RE.match(char))
    return cjk_chars / len(non_space_chars)


def _build_openai_client(api_key: str, timeout_s: float):
    try:
        from openai import OpenAI
    except Exception:
        return None

    try:
        return OpenAI(api_key=api_key, timeout=timeout_s)
    except Exception:
        return None


def _extract_corrected_text(output_text: str) -> str | None:
    normalized = output_text.strip()
    if not normalized:
        return None

    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return None

    corrected = payload.get("corrected_text")
    if not isinstance(corrected, str):
        return None

    corrected = corrected.strip()
    return corrected or None


def _extract_plain_text(output_text: str) -> str | None:
    normalized = output_text.strip()
    return normalized or None
