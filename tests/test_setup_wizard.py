"""Tests for setup wizard online correction, permission path, and launch behavior."""

import unittest.mock
from pathlib import Path

from whisperkey_mac.setup_wizard import (
    _resolve_python_app_path,
    _step_online_correction,
    run_permissions,
    run_setup,
)


def test_step_online_correction_can_skip():
    with unittest.mock.patch("whisperkey_mac.setup_wizard._ask", return_value=2):
        assert _step_online_correction("zh") is False


def test_step_online_correction_saves_key_when_requested():
    with (
        unittest.mock.patch("whisperkey_mac.setup_wizard._ask", side_effect=[1, 1]),
        unittest.mock.patch("whisperkey_mac.setup_wizard.getpass.getpass", return_value="sk-test"),
        unittest.mock.patch("whisperkey_mac.setup_wizard.save_openai_api_key", return_value=True) as mock_save,
    ):
        assert _step_online_correction("zh") is True

    mock_save.assert_called_once_with("sk-test")


def test_run_setup_starts_app_when_requested():
    with (
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_language", return_value="zh"),
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_transcribe_language", return_value=("zh", "zh")),
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_model", return_value="small"),
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_hotkeys", return_value=("alt_r", ["alt_r", "cmd_r"])),
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_permissions"),
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_online_correction", return_value=False),
        unittest.mock.patch("whisperkey_mac.setup_wizard.save_config") as mock_save,
        unittest.mock.patch("whisperkey_mac.launch_agent.LaunchAgentManager.is_loaded", return_value=False),
        unittest.mock.patch("whisperkey_mac.main.App") as mock_app,
    ):
        cfg = run_setup(start_after=True)

    assert cfg.ui_language == "zh"
    assert cfg.model_size == "small"
    mock_save.assert_called_once()
    mock_app.return_value.run.assert_called_once_with()


def test_run_setup_restarts_launch_agent_instead_of_starting_duplicate_app():
    with (
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_language", return_value="zh"),
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_transcribe_language", return_value=("zh", "zh")),
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_model", return_value="small"),
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_hotkeys", return_value=("alt_r", ["cmd", "char:\\"])),
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_permissions"),
        unittest.mock.patch("whisperkey_mac.setup_wizard._step_online_correction", return_value=False),
        unittest.mock.patch("whisperkey_mac.setup_wizard.save_config"),
        unittest.mock.patch("whisperkey_mac.launch_agent.LaunchAgentManager.is_loaded", return_value=True),
        unittest.mock.patch("whisperkey_mac.launch_agent.LaunchAgentManager.restart") as mock_restart,
        unittest.mock.patch("whisperkey_mac.main.App") as mock_app,
    ):
        run_setup(start_after=True)

    mock_restart.assert_called_once_with()
    mock_app.assert_not_called()


def test_resolve_python_app_path_prefers_real_python_app():
    python_app = "/opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/Resources/Python.app"

    with unittest.mock.patch.object(
        Path,
        "exists",
        autospec=True,
        side_effect=lambda path: str(path) == python_app,
    ):
        resolved = _resolve_python_app_path(
            "/tmp/project/.venv/bin/python",
            base_executable="/opt/homebrew/Cellar/python@3.12/3.12.10_1/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
            base_prefix="/opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12",
        )

    assert resolved == python_app


def test_run_permissions_prints_real_python_app_and_opens_settings(capsys):
    with (
        unittest.mock.patch("whisperkey_mac.setup_wizard.load_config", return_value=unittest.mock.MagicMock(ui_language="en")),
        unittest.mock.patch("whisperkey_mac.help_cmd._check_accessibility", return_value=False),
        unittest.mock.patch("whisperkey_mac.help_cmd._check_input_monitoring", return_value=False),
        unittest.mock.patch("whisperkey_mac.setup_wizard._python_app_path", return_value="/opt/homebrew/.../Python.app"),
        unittest.mock.patch("whisperkey_mac.setup_wizard._open_permission_settings") as mock_open,
    ):
        run_permissions(open_settings=True)

    output = capsys.readouterr().out
    assert "Permission Setup" in output
    assert "/opt/homebrew/.../Python.app" in output
    mock_open.assert_called_once_with()
