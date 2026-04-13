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

        response = client.responses.create(
            model=config.online_correct_model,
            instructions=_CORRECTION_INSTRUCTIONS,
            input=f"Transcript:\n{normalized}",
            text={"format": {"type": "json_object"}},
            max_output_tokens=256,
        )
    except Exception:
        return normalized

    corrected = _extract_corrected_text(getattr(response, "output_text", ""))
    return corrected or normalized


def maybe_correct_online(text: str, config: AppConfig) -> str:
    return maybe_process_online(text, config)


def _prompt_mode(config: AppConfig) -> str:
    mode = getattr(config, "online_prompt_mode", "")
    if mode in {"disabled", "asr_correction", "custom"}:
        return mode
    return "asr_correction" if config.online_correct_enabled else "disabled"


def _should_process_online(text: str, config: AppConfig, mode: str) -> bool:
    if mode == "disabled":
        return False
    if config.online_correct_provider != "openai":
        return False
    if mode == "custom":
        return bool(config.online_prompt_custom_text.strip())
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
