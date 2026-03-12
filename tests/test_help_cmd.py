"""Tests for help command config summary."""

import unittest.mock

from whisperkey_mac.config import AppConfig
from whisperkey_mac.help_cmd import run_help


def test_help_command_prints_online_correction_summary(capsys):
    cfg = AppConfig(
        online_correct_enabled=True,
        online_correct_provider="openai",
        online_correct_model="gpt-5-mini",
        result_max_lines=3,
    )

    with (
        unittest.mock.patch("whisperkey_mac.help_cmd._rich", False),
        unittest.mock.patch("whisperkey_mac.help_cmd.load_config", return_value=cfg),
        unittest.mock.patch("whisperkey_mac.help_cmd._check_process", return_value=(False, "")),
        unittest.mock.patch("whisperkey_mac.help_cmd._check_accessibility", return_value=True),
        unittest.mock.patch("whisperkey_mac.help_cmd._check_input_monitoring", return_value=True),
        unittest.mock.patch("whisperkey_mac.help_cmd._check_audio", return_value=["Mic"]),
        unittest.mock.patch("whisperkey_mac.help_cmd._check_model", return_value=True),
        unittest.mock.patch("whisperkey_mac.help_cmd.load_openai_api_key", return_value="sk-test"),
        unittest.mock.patch("pathlib.Path.exists", return_value=True),
    ):
        run_help()

    output = capsys.readouterr().out
    assert "provider=openai" in output
    assert "model=gpt-5-mini" in output
    assert "result_max_lines=3" in output
