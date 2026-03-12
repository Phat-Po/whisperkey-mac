"""Regression tests for the main application flow."""

from types import SimpleNamespace
import threading
import unittest.mock
import sys

from whisperkey_mac.config import AppConfig
from whisperkey_mac.main import App, main


class DummyApp:
    _start_recording = App._start_recording
    _stop_and_transcribe = App._stop_and_transcribe
    _transcribe_and_inject = App._transcribe_and_inject
    _hide_overlay_after_cancel = App._hide_overlay_after_cancel
    _frontmost_bundle_id = App._frontmost_bundle_id
    _should_attempt_direct_paste = App._should_attempt_direct_paste


def _build_app() -> DummyApp:
    app = DummyApp()
    app._config = AppConfig(ui_language="zh")
    app._overlay = unittest.mock.MagicMock()
    app._output = unittest.mock.MagicMock()
    app._transcriber = unittest.mock.MagicMock()
    app._transcribe_lock = threading.Lock()
    app._record_target_bundle_id = None
    return app


def test_stop_and_transcribe_hides_overlay_when_recording_too_short():
    app = _build_app()
    app._recorder = unittest.mock.MagicMock()
    app._recorder.stop_and_save.return_value = None

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        app._stop_and_transcribe()

    mock_dispatch.assert_called_once_with(app._overlay.hide_after_paste, 0.15)


def test_transcribe_and_inject_hides_overlay_when_no_speech():
    app = _build_app()
    app._transcriber.transcribe.return_value = ""
    recording = SimpleNamespace(path=unittest.mock.MagicMock())

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        app._transcribe_and_inject(recording)

    mock_dispatch.assert_called_once_with(app._overlay.hide_after_paste, 0.15)
    app._output.inject.assert_not_called()


def test_transcribe_and_inject_hides_overlay_on_transcribe_error():
    app = _build_app()
    app._transcriber.transcribe.side_effect = RuntimeError("boom")
    recording = SimpleNamespace(path=unittest.mock.MagicMock())

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        app._transcribe_and_inject(recording)

    mock_dispatch.assert_called_once_with(app._overlay.hide_after_paste, 0.15)
    app._output.inject.assert_not_called()


def test_transcribe_and_inject_uses_clipboard_path_for_finder():
    app = _build_app()
    app._transcriber.transcribe.return_value = "你好世界"
    app._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.apple.finder")
    recording = SimpleNamespace(path=unittest.mock.MagicMock())

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=True),
        unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch,
        unittest.mock.patch("pyperclip.copy") as mock_copy,
    ):
        app._transcribe_and_inject(recording)

    mock_copy.assert_called_once_with("你好世界")
    app._output.inject.assert_not_called()
    mock_dispatch.assert_called_once_with(
        app._overlay.show_result,
        "你好世界",
        "已复制到剪贴板",
        3.0,
        0.4,
    )


def test_transcribe_and_inject_uses_corrected_text_for_direct_paste():
    app = _build_app()
    app._transcriber.transcribe.return_value = "原始文本"
    app._output.inject.return_value = "inserted"
    recording = SimpleNamespace(path=unittest.mock.MagicMock())

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=True),
        unittest.mock.patch("whisperkey_mac.online_correct.maybe_correct_online", return_value="修正后文本"),
        unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch,
    ):
        app._transcribe_and_inject(recording, "com.apple.TextEdit")

    app._output.inject.assert_called_once_with("修正后文本", target_bundle_id="com.apple.TextEdit")
    mock_dispatch.assert_called_once_with(
        app._overlay.show_result,
        "修正后文本",
        "已输入",
        1.2,
        0.25,
    )


def test_start_recording_captures_frontmost_bundle_id():
    app = _build_app()
    app._recorder = unittest.mock.MagicMock()
    app._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.apple.TextEdit")

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        app._start_recording()

    assert app._record_target_bundle_id == "com.apple.TextEdit"
    app._recorder.start.assert_called_once_with()
    mock_dispatch.assert_called_once_with(app._overlay.show_recording)


def test_should_attempt_direct_paste_blocks_finder_even_when_ax_matches():
    app = _build_app()
    app._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.apple.finder")

    with unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=True):
        assert app._should_attempt_direct_paste() is False


def test_should_attempt_direct_paste_allows_non_blocked_app_when_ax_detection_misses():
    app = _build_app()
    app._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.openai.chat")

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=False),
        unittest.mock.patch("builtins.print") as mock_print,
    ):
        assert app._should_attempt_direct_paste() is True

    mock_print.assert_called_once_with(
        "[whisperkey] AX text-field detection missed bundle=com.openai.chat; trying direct inject anyway."
    )


def test_should_attempt_direct_paste_allowlists_codex_without_noise():
    app = _build_app()
    app._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.openai.codex")

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=False),
        unittest.mock.patch("builtins.print") as mock_print,
    ):
        assert app._should_attempt_direct_paste() is True

    mock_print.assert_not_called()


def test_main_setup_command_starts_after_setup():
    with (
        unittest.mock.patch.object(sys, "argv", ["whisperkey", "setup"]),
        unittest.mock.patch("whisperkey_mac.setup_wizard.run_setup") as mock_run_setup,
    ):
        main()

    mock_run_setup.assert_called_once_with(start_after=True)


def test_main_permissions_command_opens_permission_helper():
    with (
        unittest.mock.patch.object(sys, "argv", ["whisperkey", "permissions"]),
        unittest.mock.patch("whisperkey_mac.setup_wizard.run_permissions") as mock_run_permissions,
    ):
        main()

    mock_run_permissions.assert_called_once_with(open_settings=True)


def test_main_settings_alias_opens_permission_helper():
    with (
        unittest.mock.patch.object(sys, "argv", ["whisperkey", "settings"]),
        unittest.mock.patch("whisperkey_mac.setup_wizard.run_permissions") as mock_run_permissions,
    ):
        main()

    mock_run_permissions.assert_called_once_with(open_settings=True)


def test_main_first_run_uses_setup_auto_start_without_duplicate_app():
    with (
        unittest.mock.patch.object(sys, "argv", ["whisperkey"]),
        unittest.mock.patch("whisperkey_mac.main.config_exists", return_value=False),
        unittest.mock.patch("sys.stdin.isatty", return_value=True),
        unittest.mock.patch("whisperkey_mac.setup_wizard.run_setup") as mock_run_setup,
        unittest.mock.patch("whisperkey_mac.main.App") as mock_app,
    ):
        main()

    mock_run_setup.assert_called_once_with(start_after=True)
    mock_app.assert_not_called()
