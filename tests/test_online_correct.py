"""Tests for online correction helpers."""

from types import SimpleNamespace
import unittest.mock

from whisperkey_mac.config import AppConfig
from whisperkey_mac.online_correct import maybe_correct_online, maybe_process_online


def _config(**kwargs):
    defaults = {
        "online_correct_enabled": True,
        "online_correct_provider": "openai",
        "online_correct_model": "gpt-5-mini",
        "online_prompt_mode": "asr_correction",
        "online_correct_timeout_s": 2.0,
        "online_correct_min_chars": 6,
        "online_correct_max_chars": 120,
        "online_correct_min_cjk_ratio": 0.35,
    }
    defaults.update(kwargs)
    return AppConfig(**defaults)


def test_online_correction_returns_raw_text_when_disabled():
    cfg = _config(online_correct_enabled=False)
    assert maybe_correct_online("这是一个测试文本", cfg) == "这是一个测试文本"


def test_online_correction_returns_raw_text_when_key_missing():
    cfg = _config()

    with unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value=None):
        assert maybe_correct_online("这是一个测试文本", cfg) == "这是一个测试文本"


def test_online_correction_skips_low_cjk_ratio_text():
    cfg = _config()

    with unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"):
        assert maybe_correct_online("hello world 12345", cfg) == "hello world 12345"


def test_online_correction_returns_corrected_text_from_response():
    cfg = _config()
    fake_client = unittest.mock.MagicMock()
    fake_client.responses.create.return_value = SimpleNamespace(
        output_text='{"corrected_text":"今天下午三点开会"}'
    )

    with (
        unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.online_correct._build_openai_client", return_value=fake_client),
    ):
        result = maybe_correct_online("今天下午三点开灰", cfg)

    assert result == "今天下午三点开会"


def test_online_correction_falls_back_on_invalid_json():
    cfg = _config()
    fake_client = unittest.mock.MagicMock()
    fake_client.responses.create.return_value = SimpleNamespace(output_text="not-json")

    with (
        unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.online_correct._build_openai_client", return_value=fake_client),
    ):
        result = maybe_correct_online("今天下午三点开灰", cfg)

    assert result == "今天下午三点开灰"


def test_custom_prompt_mode_returns_plain_text_output():
    cfg = _config(
        online_prompt_mode="custom",
        online_prompt_custom_text="Translate to English.",
    )
    fake_client = unittest.mock.MagicMock()
    fake_client.responses.create.return_value = SimpleNamespace(output_text="hello world")

    with (
        unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.online_correct._build_openai_client", return_value=fake_client),
    ):
        result = maybe_process_online("你好世界", cfg)

    assert result == "hello world"
