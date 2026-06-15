from __future__ import annotations

import json
import re

from whisperkey_mac.config import AppConfig
from whisperkey_mac.keychain import load_openai_api_key
from whisperkey_mac.usage_log import log_usage


_CJK_RE = re.compile(r"[\u3400-\u9fff]")

_CORRECTION_INSTRUCTIONS = (
    "You correct Chinese ASR transcripts. "
    "Output only the corrected text, no explanation. "
    "Keep the original meaning. Fix only obvious ASR mistakes, homophone substitutions, "
    "punctuation, and short context errors. "
    "Do not translate. Do not rewrite style. Do not expand the content."
)

_CORRECTION_INSTRUCTIONS_TO_EN = (
    "You correct ASR transcripts, then output the result in English. "
    "Output only the final text, no explanation. "
    "Keep the original meaning. Fix only obvious ASR mistakes, homophone substitutions, "
    "punctuation, and short context errors before translating. "
    "Do not expand the content or add details."
)

_CORRECTION_INSTRUCTIONS_TO_ZH = (
    "You correct ASR transcripts, then output the result in Simplified Chinese. "
    "Output only the final text, no explanation. "
    "Keep the original meaning. Fix only obvious ASR mistakes, homophone substitutions, "
    "punctuation, and short context errors before translating. "
    "Do not expand the content or add details."
)

_VOICE_CLEANUP_PROMPT = """You are a transcript-to-instruction editor. The user will paste a raw voice-to-text transcript. Convert it into clean, faithful, executable instructions for an AI agent.

Before writing the final output, internally do this:

1. Identify the user's final intent, especially later corrections or revisions.
2. Extract tasks, requirements, constraints, preferences, inputs, and expected output.
3. Remove noise, merge duplicates, resolve self-corrections, and organize the result by topic.

Rules:

* Remove pure filler words and hesitation sounds, such as: um, uh, you know, like, 嗯, 呃, 啊, 就是, 那个, 然后, 对对对, 这样子.
* Only remove these words when they add no meaning. If a word marks sequence, contrast, cause, emphasis, or a real transition, keep or rewrite it.
* Examples:

  * "嗯然后就是我想让你帮我检查这个代码" → "帮我检查这个代码"
  * "然后第二步要把结果整理成表格" → "第二步，把结果整理成表格"
  * "不是不是，我的意思是先做手机版" → "先做手机版"
  * "这个可能就是成本太高" → "这个可能成本太高"
  * "就是因为预算不够，所以先不上广告" → "因为预算不够，所以先不上广告"
* If the user corrects or revises themselves, the later version overrides the earlier version.
* If the user explores multiple options without deciding, preserve the options and mark them as undecided.
* Do not add information not present in the transcript.
* Do not change the user's stance, urgency, certainty, or tone intensity.
* Preserve uncertainty words such as should, might, probably, 应该, 可能, 大概.
* Preserve all specific details: numbers, names, tools, platforms, conditions, constraints, preferences, examples, and output requirements.
* Fix obvious speech-to-text errors only when context is clear.
* If a fragment is unclear, keep it inline as [unclear: original fragment]. Do not create questions for the user.
* Reorder by execution logic, not spoken order.
* If there are multiple topics, create one separate Topic block for each topic.
* Skip any section that has no relevant content. Do not output empty sections.

Output:

* Use the same language mix as the input.
* No preamble or explanation.
* No Markdown heading symbols or bold text.
* One complete idea per line.
* Write the result as instructions that an AI agent can directly execute.

Format:

Topic: [short task title]
Objective:

* [what the agent should accomplish]
  Tasks:
* [specific task]
  Requirements:
* [must-follow requirement]
  Constraints:
* [limitation, condition, or boundary]
  Preferences:
* [style, direction, priority, or user preference]
  Inputs:
* [materials, files, links, text, data, or context mentioned by the user]
  Output:
* [expected deliverable, format, structure, or language]
  Notes:
* [undecided options, unclear fragments, or important context that should not be lost]"""


def _voice_cleanup_prompt(config: AppConfig) -> str:
    return _VOICE_CLEANUP_PROMPT


def _asr_correction_instructions(config: AppConfig) -> str:
    output_lang = getattr(config, "output_language", "auto")
    if output_lang == "en":
        return _CORRECTION_INSTRUCTIONS_TO_EN
    if output_lang == "zh":
        return _CORRECTION_INSTRUCTIONS_TO_ZH
    return _CORRECTION_INSTRUCTIONS


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
                max_output_tokens=1024,
            )
            try:
                u = response.usage
                log_usage("custom", config.online_correct_model, u.input_tokens, u.output_tokens)
            except Exception:
                pass
            return _extract_plain_text(getattr(response, "output_text", "")) or normalized

        if mode == "voice_cleanup":
            response = client.responses.create(
                model=config.online_correct_model,
                instructions=_voice_cleanup_prompt(config),
                input=normalized,
                max_output_tokens=1024,
            )
            try:
                u = response.usage
                log_usage("voice_cleanup", config.online_correct_model, u.input_tokens, u.output_tokens)
            except Exception:
                pass
            return _extract_plain_text(getattr(response, "output_text", "")) or normalized

        # asr_correction (default)
        response = client.responses.create(
            model=config.online_correct_model,
            instructions=_asr_correction_instructions(config),
            input=f"Transcript:\n{normalized}",
            max_output_tokens=256,
        )
        try:
            u = response.usage
            log_usage("asr_correction", config.online_correct_model, u.input_tokens, u.output_tokens)
        except Exception:
            pass
        return _extract_plain_text(getattr(response, "output_text", "")) or normalized

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
    if getattr(config, "output_language", "auto") in {"en", "zh"}:
        return True
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
