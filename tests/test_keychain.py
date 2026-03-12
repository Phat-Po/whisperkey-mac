"""Tests for macOS Keychain OpenAI credential helpers."""

import unittest.mock

from whisperkey_mac.keychain import load_openai_api_key, save_openai_api_key


def test_save_openai_api_key_returns_false_for_blank_value():
    assert save_openai_api_key("   ") is False


def test_save_openai_api_key_uses_security_cli():
    with unittest.mock.patch("whisperkey_mac.keychain.subprocess.run") as mock_run:
        mock_run.return_value = unittest.mock.Mock(returncode=0)
        assert save_openai_api_key("sk-test") is True

    args = mock_run.call_args.args[0]
    assert args[:3] == ["security", "add-generic-password", "-a"]


def test_load_openai_api_key_prefers_environment_variable():
    with (
        unittest.mock.patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}, clear=True),
        unittest.mock.patch("whisperkey_mac.keychain.subprocess.run") as mock_run,
    ):
        assert load_openai_api_key() == "env-key"
    mock_run.assert_not_called()


def test_load_openai_api_key_reads_keychain_when_env_missing():
    with (
        unittest.mock.patch.dict("os.environ", {}, clear=True),
        unittest.mock.patch("whisperkey_mac.keychain.subprocess.run") as mock_run,
    ):
        mock_run.return_value = unittest.mock.Mock(returncode=0, stdout="stored-key\n")
        assert load_openai_api_key() == "stored-key"
