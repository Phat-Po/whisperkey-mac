"""Tests for the packaged macOS app entrypoint."""

from pathlib import Path
import unittest.mock

from whisperkey_mac import app_entry


def test_app_entry_routes_cli_commands_to_app_main():
    with (
        unittest.mock.patch.object(app_entry.sys, "argv", ["WhisperKey", "--help"]),
        unittest.mock.patch.object(app_entry, "_prepare_packaged_runtime"),
        unittest.mock.patch("whisperkey_mac.main.main") as mock_app_main,
        unittest.mock.patch("whisperkey_mac.supervisor.Supervisor") as mock_supervisor,
    ):
        app_entry.main()

    mock_app_main.assert_called_once_with()
    mock_supervisor.assert_not_called()


def test_app_entry_routes_child_process_to_app_main():
    with (
        unittest.mock.patch.object(app_entry.sys, "argv", ["WhisperKey"]),
        unittest.mock.patch.dict(app_entry.os.environ, {"WHISPERKEY_APP_CHILD": "1"}),
        unittest.mock.patch.object(app_entry, "_prepare_packaged_runtime"),
        unittest.mock.patch("whisperkey_mac.main.main") as mock_app_main,
        unittest.mock.patch("whisperkey_mac.supervisor.Supervisor") as mock_supervisor,
    ):
        app_entry.main()

    mock_app_main.assert_called_once_with()
    mock_supervisor.assert_not_called()


def test_app_entry_starts_supervisor_for_normal_app_launch():
    supervisor = unittest.mock.MagicMock()
    supervisor.run.return_value = 0

    with (
        unittest.mock.patch.object(app_entry.sys, "argv", ["WhisperKey"]),
        unittest.mock.patch.object(app_entry.sys, "executable", "/tmp/WhisperKey.app/Contents/MacOS/WhisperKey"),
        unittest.mock.patch.dict(app_entry.os.environ, {}, clear=True),
        unittest.mock.patch.object(app_entry, "_prepare_packaged_runtime"),
        unittest.mock.patch("whisperkey_mac.supervisor.Supervisor", return_value=supervisor) as mock_supervisor,
    ):
        try:
            app_entry.main()
        except SystemExit as exc:
            assert exc.code == 0

    mock_supervisor.assert_called_once_with(app_executable="/tmp/WhisperKey.app/Contents/MacOS/WhisperKey")
    supervisor.run.assert_called_once_with()


def test_prepare_packaged_runtime_creates_app_support_and_chdirs(tmp_path: Path):
    app_support = tmp_path / "Application Support" / "WhisperKey"

    with (
        unittest.mock.patch.object(app_entry, "APP_SUPPORT_DIR", app_support),
        unittest.mock.patch.object(app_entry.os, "chdir") as mock_chdir,
        unittest.mock.patch.dict(app_entry.os.environ, {}, clear=True),
    ):
        app_entry._prepare_packaged_runtime()
        assert app_entry.os.environ["PYTHONUNBUFFERED"] == "1"

    assert app_support.exists()
    mock_chdir.assert_called_once_with(app_support)
