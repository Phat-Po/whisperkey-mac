"""Regression tests for the main application flow."""

from types import SimpleNamespace
import threading
import unittest.mock
import sys

from whisperkey_mac.config import AppConfig
from whisperkey_mac.main import App, main
from whisperkey_mac.service_controller import ServiceController


class DummyService:
    is_busy = ServiceController.is_busy
    _start_recording = ServiceController._start_recording
    _start_streaming_asr = ServiceController._start_streaming_asr
    _stop_and_transcribe = ServiceController._stop_and_transcribe
    _stop_and_transcribe_worker = ServiceController._stop_and_transcribe_worker
    _transcribe_and_inject = ServiceController._transcribe_and_inject
    _process_and_inject_text = ServiceController._process_and_inject_text
    _hide_overlay_after_cancel = ServiceController._hide_overlay_after_cancel
    _start_disconnect_watchdog = ServiceController._start_disconnect_watchdog
    _stop_disconnect_watchdog = ServiceController._stop_disconnect_watchdog
    _disconnect_watchdog_loop = ServiceController._disconnect_watchdog_loop
    _notify_device_disconnected = ServiceController._notify_device_disconnected
    _frontmost_bundle_id = ServiceController._frontmost_bundle_id
    _should_attempt_direct_paste = ServiceController._should_attempt_direct_paste
    cycle_online_prompt_mode = ServiceController.cycle_online_prompt_mode
    notify_mode_switch = ServiceController.notify_mode_switch
    notify_mode_switch_busy = ServiceController.notify_mode_switch_busy


def _build_service() -> DummyService:
    service = DummyService()
    service._config = AppConfig(ui_language="zh")
    service._overlay = unittest.mock.MagicMock()
    service._output = unittest.mock.MagicMock()
    service._transcriber = unittest.mock.MagicMock()
    service._transcribe_lock = threading.Lock()
    service._activity_lock = threading.Lock()
    service._processing_busy = False
    service._ui_quiet_until = 0.0
    service._record_target_bundle_id = None
    service._disconnect_watchdog_thread = None
    service._disconnect_watchdog_stop = None
    service._disconnect_watchdog_lock = threading.Lock()
    return service


def test_stop_and_transcribe_hides_overlay_when_recording_too_short():
    service = _build_service()
    service._recorder = unittest.mock.MagicMock()
    service._recorder.stop_and_save.return_value = None

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        service._stop_and_transcribe_worker()

    # Cancel returns to idle bubble rather than fully hiding
    mock_dispatch.assert_called_once_with(service._overlay.show_idle)


def test_stop_and_transcribe_returns_before_stopping_audio_stream():
    service = _build_service()
    service._recorder = unittest.mock.MagicMock()
    service._record_target_bundle_id = "com.example.App"

    with unittest.mock.patch("whisperkey_mac.service_controller.threading.Thread") as mock_thread:
        service._stop_and_transcribe()

    service._recorder.stop_and_save.assert_not_called()
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once_with()
    assert service._processing_busy is True
    assert service._record_target_bundle_id is None


def test_transcribe_and_inject_hides_overlay_when_no_speech():
    service = _build_service()
    service._transcriber.transcribe.return_value = ""
    recording = SimpleNamespace(path=unittest.mock.MagicMock())

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        service._transcribe_and_inject(recording)

    # Cancel (no speech) returns to idle bubble
    mock_dispatch.assert_called_once_with(service._overlay.show_idle)
    service._output.inject.assert_not_called()


def test_transcribe_and_inject_hides_overlay_on_transcribe_error():
    service = _build_service()
    service._transcriber.transcribe.side_effect = RuntimeError("boom")
    recording = SimpleNamespace(path=unittest.mock.MagicMock())

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        service._transcribe_and_inject(recording)

    # Cancel (transcribe error) returns to idle bubble
    mock_dispatch.assert_called_once_with(service._overlay.show_idle)
    service._output.inject.assert_not_called()


def test_transcribe_and_inject_uses_clipboard_path_for_finder():
    service = _build_service()
    service._transcriber.transcribe.return_value = "你好世界"
    service._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.apple.finder")
    recording = SimpleNamespace(path=unittest.mock.MagicMock())

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=True),
        unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch,
        unittest.mock.patch("pyperclip.copy") as mock_copy,
    ):
        service._transcribe_and_inject(recording)

    mock_copy.assert_called_once_with("你好世界")
    service._output.inject.assert_not_called()
    mock_dispatch.assert_called_once_with(
        service._overlay.show_result,
        "你好世界",
        "已复制到剪贴板",
        3.0,
        0.4,
    )


def test_transcribe_and_inject_uses_corrected_text_for_direct_paste():
    service = _build_service()
    service._transcriber.transcribe.return_value = "原始文本"
    service._output.inject.return_value = "inserted"
    service._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.apple.TextEdit")
    recording = SimpleNamespace(path=unittest.mock.MagicMock())

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=True),
        unittest.mock.patch("whisperkey_mac.online_correct.maybe_correct_online", return_value="修正后文本"),
        unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch,
    ):
        service._transcribe_and_inject(recording, "com.apple.TextEdit")

    service._output.inject.assert_called_once_with("修正后文本", target_bundle_id="com.apple.TextEdit")
    mock_dispatch.assert_called_once_with(
        service._overlay.show_result,
        "修正后文本",
        "已输入",
        1.2,
        0.25,
    )


def test_start_recording_captures_frontmost_bundle_id():
    service = _build_service()
    service._recorder = unittest.mock.MagicMock()
    service._recorder.is_recording = False
    service._recorder.active_device_name = ""  # default mic → no disconnect watchdog
    service._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.apple.TextEdit")

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        service._start_recording()

    assert service._record_target_bundle_id == "com.apple.TextEdit"
    service._recorder.start.assert_called_once_with()
    mock_dispatch.assert_called_once_with(service._overlay.show_recording)


def test_start_recording_ignores_when_service_is_processing():
    service = _build_service()
    service._recorder = unittest.mock.MagicMock()
    service._recorder.is_recording = False
    service._hotkey = unittest.mock.MagicMock()
    service._processing_busy = True

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        service._start_recording()

    service._recorder.start.assert_not_called()
    service._hotkey.reset_state.assert_called_once_with()
    mock_dispatch.assert_not_called()


def test_doubao_engine_does_not_fall_back_to_local_recording_when_streaming_unavailable():
    service = _build_service()
    service._config.asr_engine = "doubao"
    service._recorder = unittest.mock.MagicMock()
    service._recorder.is_recording = False
    service._hotkey = unittest.mock.MagicMock()
    service._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.apple.TextEdit")
    service._start_streaming_asr = unittest.mock.MagicMock(return_value=False)

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        service._start_recording()

    service._start_streaming_asr.assert_called_once_with()
    service._recorder.start.assert_not_called()
    service._hotkey.reset_state.assert_called_once_with()
    assert mock_dispatch.call_args_list[-1] == unittest.mock.call(service._overlay.show_idle)


def test_local_engine_does_not_start_streaming_asr():
    service = _build_service()
    service._config.asr_engine = "local"
    service._recorder = unittest.mock.MagicMock()
    service._recorder.is_recording = False
    service._recorder.active_device_name = ""  # default mic → no disconnect watchdog
    service._hotkey = unittest.mock.MagicMock()
    service._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.apple.TextEdit")
    service._start_streaming_asr = unittest.mock.MagicMock(return_value=True)

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main"):
        service._start_recording()

    service._start_streaming_asr.assert_not_called()
    service._recorder.start.assert_called_once_with()


def test_should_attempt_direct_paste_blocks_finder_even_when_ax_matches():
    service = _build_service()
    service._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.apple.finder")

    with unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=True):
        assert service._should_attempt_direct_paste() is False


def test_should_attempt_direct_paste_blocks_terminal_even_when_ax_matches():
    service = _build_service()
    service._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.apple.Terminal")

    with unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=True):
        assert service._should_attempt_direct_paste() is False


def test_should_attempt_direct_paste_blocks_own_python_app_even_when_ax_matches():
    service = _build_service()
    service._frontmost_bundle_id = unittest.mock.MagicMock(return_value="org.python.python")

    with unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=True):
        assert service._should_attempt_direct_paste() is False


def test_should_attempt_direct_paste_allows_non_blocked_app_when_ax_detection_misses():
    service = _build_service()
    service._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.openai.chat")

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=False),
        unittest.mock.patch("builtins.print") as mock_print,
    ):
        assert service._should_attempt_direct_paste() is True

    mock_print.assert_called_once_with(
        "[whisperkey] AX text-field detection missed bundle=com.openai.chat; trying direct inject anyway."
    )


def test_apply_config_reuses_recorder_when_audio_config_is_unchanged():
    service = ServiceController.__new__(ServiceController)
    old_config = AppConfig(online_prompt_mode="disabled")
    new_config = AppConfig(online_prompt_mode="voice_cleanup")
    recorder = unittest.mock.MagicMock()
    transcriber = unittest.mock.MagicMock()

    service._config = old_config
    service._recorder = recorder
    service._transcriber = transcriber
    service._output = unittest.mock.MagicMock()
    service._record_target_bundle_id = "com.example.App"
    service._service_running = True
    service._hotkey = unittest.mock.MagicMock()
    service._status_callbacks = []

    service.apply_config(new_config)

    recorder.cancel.assert_not_called()
    assert service._recorder is recorder
    assert service._recorder._config is new_config


def test_apply_config_updates_mode_cycle_hotkey_binding():
    service = ServiceController.__new__(ServiceController)
    old_config = AppConfig()
    new_config = AppConfig(mode_cycle_keys=["cmd", "char:m"])

    service._config = old_config
    service._recorder = unittest.mock.MagicMock()
    service._transcriber = unittest.mock.MagicMock()
    service._output = unittest.mock.MagicMock()
    service._record_target_bundle_id = None
    service._service_running = True
    service._hotkey = unittest.mock.MagicMock()
    service._status_callbacks = []

    service.apply_config(new_config)

    service._hotkey.update_keys.assert_called_once_with(
        new_config.hold_key,
        new_config.handsfree_keys,
        ["cmd", "char:m"],
    )


def test_cycle_online_prompt_mode_persists_next_target():
    service = ServiceController.__new__(ServiceController)
    service._config = AppConfig(
        online_prompt_mode="asr_correction",
        mode_cycle_targets=["asr_correction", "voice_cleanup"],
    )
    service._recorder = unittest.mock.MagicMock()
    service._recorder.is_recording = False
    service._activity_lock = threading.Lock()
    service._processing_busy = False
    service._status_callbacks = [unittest.mock.MagicMock()]
    service.notify_mode_switch = unittest.mock.MagicMock()
    service.notify_mode_switch_busy = unittest.mock.MagicMock()

    with unittest.mock.patch("whisperkey_mac.service_controller.save_config") as mock_save:
        next_mode = service.cycle_online_prompt_mode()

    assert next_mode == "voice_cleanup"
    assert service._config.online_prompt_mode == "voice_cleanup"
    assert service._config.online_correct_enabled is True
    mock_save.assert_called_once_with(service._config)
    service.notify_mode_switch.assert_called_once_with("voice_cleanup")
    service.notify_mode_switch_busy.assert_not_called()
    service._status_callbacks[0].assert_called_once_with()


def test_cycle_online_prompt_mode_is_ignored_while_recording():
    service = ServiceController.__new__(ServiceController)
    service._config = AppConfig(
        online_prompt_mode="asr_correction",
        mode_cycle_targets=["asr_correction", "voice_cleanup"],
    )
    service._recorder = unittest.mock.MagicMock()
    service._recorder.is_recording = True
    service._activity_lock = threading.Lock()
    service._processing_busy = False
    service._status_callbacks = [unittest.mock.MagicMock()]
    service.notify_mode_switch = unittest.mock.MagicMock()
    service.notify_mode_switch_busy = unittest.mock.MagicMock()

    with unittest.mock.patch("whisperkey_mac.service_controller.save_config") as mock_save:
        next_mode = service.cycle_online_prompt_mode()

    assert next_mode == "asr_correction"
    assert service._config.online_prompt_mode == "asr_correction"
    mock_save.assert_not_called()
    service.notify_mode_switch.assert_not_called()
    service.notify_mode_switch_busy.assert_called_once_with()
    service._status_callbacks[0].assert_not_called()


def test_cycle_online_prompt_mode_is_ignored_while_processing():
    service = ServiceController.__new__(ServiceController)
    service._config = AppConfig(
        online_prompt_mode="voice_cleanup",
        mode_cycle_targets=["asr_correction", "voice_cleanup"],
    )
    service._recorder = unittest.mock.MagicMock()
    service._recorder.is_recording = False
    service._activity_lock = threading.Lock()
    service._processing_busy = True
    service._status_callbacks = [unittest.mock.MagicMock()]
    service.notify_mode_switch = unittest.mock.MagicMock()
    service.notify_mode_switch_busy = unittest.mock.MagicMock()

    with unittest.mock.patch("whisperkey_mac.service_controller.save_config") as mock_save:
        next_mode = service.cycle_online_prompt_mode()

    assert next_mode == "voice_cleanup"
    assert service._config.online_prompt_mode == "voice_cleanup"
    mock_save.assert_not_called()
    service.notify_mode_switch.assert_not_called()
    service.notify_mode_switch_busy.assert_called_once_with()
    service._status_callbacks[0].assert_not_called()


def test_notify_mode_switch_dispatches_overlay_feedback_when_idle():
    service = _build_service()
    service._service_running = True
    service._recorder = unittest.mock.MagicMock()
    service._recorder.is_recording = False

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        service.notify_mode_switch("voice_cleanup")

    mock_dispatch.assert_called_once_with(
        service._overlay.show_mode_switch,
        "voice_cleanup",
        "zh",
    )


def test_notify_mode_switch_skips_overlay_feedback_while_busy():
    service = _build_service()
    service._service_running = True
    service._processing_busy = True
    service._recorder = unittest.mock.MagicMock()
    service._recorder.is_recording = False

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        service.notify_mode_switch("asr_correction")

    mock_dispatch.assert_not_called()


def test_notify_mode_switch_busy_dispatches_overlay_hint():
    service = _build_service()
    service._service_running = True

    with unittest.mock.patch("whisperkey_mac.overlay.dispatch_to_main") as mock_dispatch:
        service.notify_mode_switch_busy()

    mock_dispatch.assert_called_once_with(
        service._overlay.show_busy_mode_switch_hint,
        "zh",
    )


def test_should_attempt_direct_paste_allowlists_codex_without_noise():
    service = _build_service()
    service._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.openai.codex")

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=False),
        unittest.mock.patch("builtins.print") as mock_print,
    ):
        assert service._should_attempt_direct_paste() is True

    mock_print.assert_not_called()


def test_should_attempt_direct_paste_allowlists_wechat_without_noise():
    service = _build_service()
    service._frontmost_bundle_id = unittest.mock.MagicMock(return_value="com.tencent.xinWeChat")

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.is_cursor_in_text_field", return_value=False),
        unittest.mock.patch("builtins.print") as mock_print,
    ):
        assert service._should_attempt_direct_paste() is True

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


def test_app_run_shuts_down_service_after_nsapp_returns():
    app = App.__new__(App)
    app._config = AppConfig(ui_language="en")
    app._service = unittest.mock.MagicMock()
    app._launch_agent = unittest.mock.MagicMock()

    nsapp = unittest.mock.MagicMock()
    nsapplication = unittest.mock.MagicMock()
    nsapplication.sharedApplication.return_value = nsapp

    with (
        unittest.mock.patch("AppKit.NSApplication", new=nsapplication),
        unittest.mock.patch("PyObjCTools.AppHelper.callLater"),
        unittest.mock.patch("whisperkey_mac.menu_bar.build_menu_bar_controller", return_value=unittest.mock.sentinel.menu_bar),
        unittest.mock.patch("signal.signal"),
        unittest.mock.patch.object(app, "_acquire_single_instance_lock", return_value=True),
    ):
        app.run()

    app._service.ensure_overlay.assert_called_once_with()
    app._service.start_service.assert_called_once_with()
    app._service.shutdown.assert_called_once_with()
    nsapp.run.assert_called_once_with()


def test_app_open_settings_defers_while_service_busy():
    app = App.__new__(App)
    app._service = SimpleNamespace(is_busy=True)
    app._settings_retry_pending = False

    with (
        unittest.mock.patch("PyObjCTools.AppHelper.callLater") as mock_call_later,
        unittest.mock.patch("whisperkey_mac.settings_window.build_settings_window_controller") as mock_build,
    ):
        app.open_settings()

    mock_call_later.assert_called_once_with(1.0, app._retry_open_settings)
    mock_build.assert_not_called()
    assert app._settings_retry_pending is True


def test_app_open_settings_passes_hotkey_capture_callback():
    app = App.__new__(App)
    app._service = unittest.mock.MagicMock()
    app._service.is_busy = False
    app._service.config = AppConfig()
    app._launch_agent = unittest.mock.MagicMock()
    app._launch_agent.is_enabled.return_value = False
    app._settings_retry_pending = False
    app._settings_window = None
    settings_window = unittest.mock.MagicMock()

    with unittest.mock.patch(
        "whisperkey_mac.settings_window.build_settings_window_controller",
        return_value=settings_window,
    ) as mock_build:
        app.open_settings()

    callback = mock_build.call_args.kwargs["on_hotkey_capture_active"]
    assert callback == app._set_settings_hotkey_capture_active
    settings_window.show.assert_called_once_with()


def test_app_settings_hotkey_capture_callback_suspends_and_resumes_service():
    app = App.__new__(App)
    app._service = unittest.mock.MagicMock()

    app._set_settings_hotkey_capture_active(True)
    app._set_settings_hotkey_capture_active(False)

    app._service.suspend_hotkeys_for_settings.assert_called_once_with()
    app._service.resume_hotkeys_after_settings.assert_called_once_with()


def test_app_save_settings_defers_while_service_busy():
    app = App.__new__(App)
    app._service = unittest.mock.MagicMock()
    app._service.is_busy = True
    app._launch_agent = unittest.mock.MagicMock()
    app._pending_settings_save = None
    app._settings_save_retry_pending = False
    config = AppConfig()

    with (
        unittest.mock.patch("PyObjCTools.AppHelper.callLater") as mock_call_later,
        unittest.mock.patch("whisperkey_mac.main.save_config") as mock_save_config,
    ):
        app._save_settings(config, "secret", True)

    mock_call_later.assert_called_once_with(1.0, app._retry_save_settings)
    mock_save_config.assert_not_called()
    assert app._pending_settings_save == (config, "secret", True)
    assert app._settings_save_retry_pending is True


def test_service_settings_hotkey_suspend_resume_is_nested():
    service = ServiceController.__new__(ServiceController)
    service._settings_hotkey_suspend_count = 0
    service._settings_hotkey_suspend_lock = threading.Lock()
    service._service_running = True
    service._hotkey = unittest.mock.MagicMock()

    service.suspend_hotkeys_for_settings()
    service.suspend_hotkeys_for_settings()
    service.resume_hotkeys_after_settings()
    service.resume_hotkeys_after_settings()

    service._hotkey.full_stop.assert_called_once_with()
    service._hotkey.start.assert_called_once_with()
    assert service._service_running is True


def test_service_settings_hotkey_resume_does_not_start_stopped_service():
    service = ServiceController.__new__(ServiceController)
    service._settings_hotkey_suspend_count = 0
    service._settings_hotkey_suspend_lock = threading.Lock()
    service._service_running = True
    service._hotkey = unittest.mock.MagicMock()

    service.suspend_hotkeys_for_settings()
    service._service_running = False
    service.resume_hotkeys_after_settings()

    service._hotkey.full_stop.assert_called_once_with()
    service._hotkey.start.assert_not_called()


def _bare_mode_service(**config_kwargs):
    service = ServiceController.__new__(ServiceController)
    service._config = AppConfig(**config_kwargs)
    service._recorder = unittest.mock.MagicMock()
    service._recorder.is_recording = False
    service._activity_lock = threading.Lock()
    service._processing_busy = False
    service._status_callbacks = [unittest.mock.MagicMock()]
    service.notify_mode_switch = unittest.mock.MagicMock()
    service.notify_mode_switch_busy = unittest.mock.MagicMock()
    return service


def test_set_online_prompt_mode_persists_selection():
    service = _bare_mode_service(online_prompt_mode="disabled")

    with unittest.mock.patch("whisperkey_mac.service_controller.save_config") as mock_save:
        result = service.set_online_prompt_mode("voice_cleanup")

    assert result == "voice_cleanup"
    assert service._config.online_prompt_mode == "voice_cleanup"
    assert service._config.online_correct_enabled is True
    mock_save.assert_called_once_with(service._config)
    service.notify_mode_switch.assert_called_once_with("voice_cleanup")


def test_set_online_prompt_mode_rejects_unknown_mode():
    service = _bare_mode_service(online_prompt_mode="asr_correction")

    with unittest.mock.patch("whisperkey_mac.service_controller.save_config") as mock_save:
        result = service.set_online_prompt_mode("nonsense")

    assert result == "asr_correction"
    mock_save.assert_not_called()


def test_set_online_prompt_mode_rejects_custom_without_prompt_text():
    service = _bare_mode_service(online_prompt_mode="asr_correction", online_prompt_custom_text="  ")

    with unittest.mock.patch("whisperkey_mac.service_controller.save_config") as mock_save:
        result = service.set_online_prompt_mode("custom")

    assert result == "asr_correction"
    mock_save.assert_not_called()


def test_set_online_prompt_mode_ignored_while_recording():
    service = _bare_mode_service(online_prompt_mode="disabled")
    service._recorder.is_recording = True

    with unittest.mock.patch("whisperkey_mac.service_controller.save_config") as mock_save:
        result = service.set_online_prompt_mode("asr_correction")

    assert result == "disabled"
    mock_save.assert_not_called()
    service.notify_mode_switch_busy.assert_called_once_with()


def test_set_asr_engine_persists_selection():
    service = _bare_mode_service(asr_engine="local")

    with unittest.mock.patch("whisperkey_mac.service_controller.save_config") as mock_save:
        result = service.set_asr_engine("doubao")

    assert result == "doubao"
    assert service._config.asr_engine == "doubao"
    mock_save.assert_called_once_with(service._config)
    service._status_callbacks[0].assert_called_once_with()


def test_set_asr_engine_rejects_unknown_engine():
    service = _bare_mode_service(asr_engine="local")

    with unittest.mock.patch("whisperkey_mac.service_controller.save_config") as mock_save:
        result = service.set_asr_engine("nonsense")

    assert result == "local"
    mock_save.assert_not_called()
