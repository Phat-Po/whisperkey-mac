"""Tests for online correction helpers."""

from types import SimpleNamespace
import unittest.mock

from whisperkey_mac.config import AppConfig
from whisperkey_mac.online_correct import (
    maybe_correct_online,
    maybe_process_online,
    verify_openai_connection,
)


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
    # ASR correction now returns plain text directly (no JSON wrapper)
    cfg = _config()
    fake_client = unittest.mock.MagicMock()
    fake_client.responses.create.return_value = SimpleNamespace(
        output_text="今天下午三点开会"
    )

    with (
        unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.online_correct._build_openai_client", return_value=fake_client),
    ):
        result = maybe_correct_online("今天下午三点开灰", cfg)

    assert result == "今天下午三点开会"


def test_asr_correction_respects_english_output_language():
    cfg = _config(output_language="en")
    fake_client = unittest.mock.MagicMock()
    fake_client.responses.create.return_value = SimpleNamespace(
        output_text="Meeting at three this afternoon."
    )

    with (
        unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.online_correct._build_openai_client", return_value=fake_client),
    ):
        result = maybe_correct_online("今天下午三点开灰", cfg)

    assert result == "Meeting at three this afternoon."
    kwargs = fake_client.responses.create.call_args.kwargs
    assert "output the result in English" in kwargs["instructions"]
    assert "Do not translate" not in kwargs["instructions"]


def test_asr_correction_output_language_bypasses_cjk_ratio_guard():
    cfg = _config(output_language="zh")
    fake_client = unittest.mock.MagicMock()
    fake_client.responses.create.return_value = SimpleNamespace(output_text="你好，世界")

    with (
        unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.online_correct._build_openai_client", return_value=fake_client),
    ):
        result = maybe_correct_online("hello world", cfg)

    assert result == "你好，世界"
    fake_client.responses.create.assert_called_once()


def test_online_correction_returns_plain_text_as_is():
    # Plain text response is returned directly (no JSON parsing)
    cfg = _config()
    fake_client = unittest.mock.MagicMock()
    fake_client.responses.create.return_value = SimpleNamespace(output_text="今天下午三点开会")

    with (
        unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.online_correct._build_openai_client", return_value=fake_client),
    ):
        result = maybe_correct_online("今天下午三点开灰", cfg)

    assert result == "今天下午三点开会"


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


def test_asr_correction_instructions_include_filler_removal():
    # "Remove Fillers" (去除干扰词) mode strips hesitation words but stays plain prose.
    cfg = _config()
    fake_client = unittest.mock.MagicMock()
    fake_client.responses.create.return_value = SimpleNamespace(output_text="帮我检查这个代码")

    with (
        unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.online_correct._build_openai_client", return_value=fake_client),
    ):
        result = maybe_correct_online("嗯然后就是我想让你帮我检查这个代码", cfg)

    assert result == "帮我检查这个代码"
    instructions = fake_client.responses.create.call_args.kwargs["instructions"]
    assert "filler words" in instructions
    # Must NOT borrow Agent mode's structured-template behaviour.
    assert "Topic/Tasks template" in instructions
    assert "transcript-to-instruction editor" not in instructions


def test_summary_mode_returns_plain_summary():
    cfg = _config(online_prompt_mode="summary")
    fake_client = unittest.mock.MagicMock()
    fake_client.responses.create.return_value = SimpleNamespace(
        output_text="用户想先做手机版，重点是控制成本。"
    )

    with (
        unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.online_correct._build_openai_client", return_value=fake_client),
    ):
        result = maybe_process_online(
            "嗯就是我觉得我们应该先做手机版，然后那个成本要控制一下", cfg
        )

    assert result == "用户想先做手机版，重点是控制成本。"
    kwargs = fake_client.responses.create.call_args.kwargs
    assert "summary for a human reader" in kwargs["instructions"]
    assert "NOT a list of instructions for an AI agent" in kwargs["instructions"]
    assert kwargs["max_output_tokens"] == 512


def test_summary_mode_bypasses_cjk_and_max_chars_guards():
    # Same long/mixed-text tolerance as Agent mode: only min_chars applies.
    cfg = _config(online_prompt_mode="summary", online_correct_max_chars=10)
    fake_client = unittest.mock.MagicMock()
    fake_client.responses.create.return_value = SimpleNamespace(output_text="summary text")

    with (
        unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.online_correct._build_openai_client", return_value=fake_client),
    ):
        result = maybe_process_online("hello world this is a long english sentence", cfg)

    assert result == "summary text"
    fake_client.responses.create.assert_called_once()


def test_doubao_asr_engine_keeps_selected_processing_mode():
    cfg = _config(asr_engine="doubao", online_prompt_mode="voice_cleanup")
    fake_client = unittest.mock.MagicMock()
    fake_client.responses.create.return_value = SimpleNamespace(output_text="Topic: 豆包接入")

    with (
        unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.online_correct._build_openai_client", return_value=fake_client),
    ):
        result = maybe_process_online("嗯然后我们接入豆包实时语音识别", cfg)

    assert result == "Topic: 豆包接入"
    kwargs = fake_client.responses.create.call_args.kwargs
    assert "transcript-to-instruction editor" in kwargs["instructions"]


def test_verify_openai_connection_no_key():
    with unittest.mock.patch("whisperkey_mac.online_correct.load_openai_api_key", return_value=None):
        ok, code = verify_openai_connection("")
    assert ok is False
    assert code == "openai_status_no_key"


def test_verify_openai_connection_ok():
    fake_client = unittest.mock.MagicMock()
    fake_client.with_options.return_value = fake_client
    fake_client.models.list.return_value = SimpleNamespace(data=[])

    with unittest.mock.patch(
        "whisperkey_mac.online_correct._build_openai_client", return_value=fake_client
    ):
        ok, code = verify_openai_connection("sk-test")
    assert ok is True
    assert code == "openai_status_ok"
    fake_client.with_options.assert_called_once_with(max_retries=0)


def test_verify_openai_connection_bad_key():
    fake_client = unittest.mock.MagicMock()
    fake_client.with_options.return_value = fake_client

    class AuthenticationError(Exception):
        pass

    fake_client.models.list.side_effect = AuthenticationError("invalid api key")

    with unittest.mock.patch(
        "whisperkey_mac.online_correct._build_openai_client", return_value=fake_client
    ):
        ok, code = verify_openai_connection("sk-bad")
    assert ok is False
    assert code == "openai_status_bad_key"


def test_verify_openai_connection_network_failure():
    fake_client = unittest.mock.MagicMock()
    fake_client.with_options.return_value = fake_client

    class APITimeoutError(Exception):
        pass

    fake_client.models.list.side_effect = APITimeoutError("timed out")

    with unittest.mock.patch(
        "whisperkey_mac.online_correct._build_openai_client", return_value=fake_client
    ):
        ok, code = verify_openai_connection("sk-test")
    assert ok is False
    assert code == "openai_status_failed"


def test_verify_openai_connection_falls_back_to_stored_key():
    fake_client = unittest.mock.MagicMock()
    fake_client.with_options.return_value = fake_client
    fake_client.models.list.return_value = SimpleNamespace(data=[])

    with (
        unittest.mock.patch(
            "whisperkey_mac.online_correct.load_openai_api_key", return_value="sk-stored"
        ),
        unittest.mock.patch(
            "whisperkey_mac.online_correct._build_openai_client", return_value=fake_client
        ) as build,
    ):
        ok, code = verify_openai_connection("")
    assert ok is True
    assert build.call_args.args[0] == "sk-stored"
