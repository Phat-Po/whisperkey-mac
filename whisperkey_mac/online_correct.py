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

_VOICE_CLEANUP_PROMPT = """你是一位語音輸入文字清理專家。用戶會貼入語音轉文字的原始逐字稿，你的任務是輸出乾淨、完整、邏輯連貫的版本。

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

- 預設輸出精簡段落，適合直接作為 AI prompt 使用
- 如果原文明顯是個人想法記錄而非指令（例如日記、反思、腦力激盪），改用筆記風格輸出
- 如果用戶在開頭寫「筆記模式」，強制使用筆記風格
- 不要加任何說明、前言或「以下是清理後的版本」——直接輸出結果

## 關鍵原則

- 寧可多保留一句，也不要丟失任何原始意圖或細節
- 不要添加原文沒有的內容
- 不要改變用戶的立場或語氣強度
- 如果某段話實在無法確定意思，用 [語意不明：原文片段] 標記"""


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
                instructions=_VOICE_CLEANUP_PROMPT,
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

    except Exception:
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
