import unittest.mock

from AppKit import NSEventModifierFlagCommand, NSEventModifierFlagOption

from whisperkey_mac.config import AppConfig
from whisperkey_mac.settings_window import (
    HotkeyRecorderView,
    PROMPT_MODE_OPTIONS,
    SettingsWindowDelegate,
    build_settings_window_controller,
    hotkey_names_from_event_parts,
    hotkey_value_to_display,
    is_valid_hotkey_values,
    parse_shortcut_list,
    shortcut_list_to_text,
)


class _FakeHotkeyEvent:
    def __init__(self, key_code: int, characters: str = "", modifier_flags: int = 0, event_type: int = 10) -> None:
        self._key_code = key_code
        self._characters = characters
        self._modifier_flags = modifier_flags
        self._event_type = event_type

    def keyCode(self) -> int:
        return self._key_code

    def charactersIgnoringModifiers(self) -> str:
        return self._characters

    def modifierFlags(self) -> int:
        return self._modifier_flags

    def type(self) -> int:
        return self._event_type


def test_parse_shortcut_list_trims_and_filters_empty_entries():
    assert parse_shortcut_list(" alt_r, cmd_r , , shift ") == ["alt_r", "cmd_r", "shift"]


def test_shortcut_list_to_text_formats_for_field_display():
    assert shortcut_list_to_text(["alt_r", "cmd_r"]) == "alt_r, cmd_r"


def test_hotkey_display_uses_symbols_for_recorded_combo():
    assert hotkey_value_to_display(["cmd", "char:l"]) == "⌘  L"


def test_single_key_capture_accepts_right_option_flags_event():
    assert hotkey_names_from_event_parts(
        61,
        "",
        int(NSEventModifierFlagOption),
        single_key=True,
        flags_changed=True,
    ) == ["alt_r"]


def test_combo_capture_records_modifier_plus_character():
    assert hotkey_names_from_event_parts(
        37,
        "l",
        int(NSEventModifierFlagCommand),
        single_key=False,
    ) == ["cmd", "char:l"]


def test_combo_capture_requires_a_modifier():
    assert not is_valid_hotkey_values(["char:l", "char:k"], single_key=False)


def test_settings_window_builds_hotkey_recorders(nsapp):
    controller = build_settings_window_controller(
        AppConfig(), launch_at_login_enabled=False, on_save=lambda *args: None
    )

    assert controller._hold_key_recorder.value() == "alt_r"
    assert controller._handsfree_recorder.value() == ["alt_r", "cmd_r"]
    assert controller._mode_cycle_recorder.value() == []


def test_empty_hotkey_recorder_keeps_manual_entry_visible(nsapp):
    recorder = HotkeyRecorderView.alloc().initWithFrame_value_singleKey_(
        ((0.0, 0.0), (230.0, 28.0)),
        [],
        False,
    )

    assert recorder._pill_view.isHidden() is False
    assert recorder._pill_label.stringValue() == "Not set"
    assert recorder._clear_button.isHidden() is True

    recorder.editManually_(None)

    assert recorder._manual_field.isHidden() is False
    assert recorder._pill_view.isHidden() is True


def test_hotkey_recorder_capture_and_manual_edit_callbacks(nsapp):
    events = []
    monitor = object()
    removed = []

    class _FakeNSEvent:
        @staticmethod
        def addLocalMonitorForEventsMatchingMask_handler_(_mask, _handler):
            return monitor

        @staticmethod
        def removeMonitor_(removed_monitor):
            removed.append(removed_monitor)

    recorder = HotkeyRecorderView.alloc().initWithFrame_value_singleKey_(
        ((0.0, 0.0), (230.0, 28.0)),
        ["cmd", "char:k"],
        False,
    )
    recorder.set_capture_callbacks(lambda: events.append("begin"), lambda: events.append("end"))

    with unittest.mock.patch("whisperkey_mac.settings_window.NSEvent", _FakeNSEvent):
        recorder.startCapture_(None)
        recorder._handle_event(_FakeHotkeyEvent(53))

    assert events == ["begin", "end"]
    assert recorder.value() == ["cmd", "char:k"]
    assert removed == [monitor]

    recorder.editManually_(None)
    recorder._manual_field.setStringValue_("cmd, shift, char:m")
    recorder.finishManualEdit_(None)

    assert events == ["begin", "end", "begin", "end"]
    assert recorder.value() == ["cmd", "shift", "char:m"]


def test_settings_controller_aggregates_hotkey_capture_callback(nsapp):
    events = []
    controller = build_settings_window_controller(
        AppConfig(),
        launch_at_login_enabled=False,
        on_save=lambda *args: None,
        on_hotkey_capture_active=lambda active: events.append(active),
    )

    controller._mode_cycle_recorder.editManually_(None)
    controller._hold_key_recorder.editManually_(None)

    assert events == [True]

    controller._mode_cycle_recorder.finishManualEdit_(None)
    assert events == [True]

    controller._hold_key_recorder.finishManualEdit_(None)
    assert events == [True, False]


def test_prompt_mode_options_include_custom():
    assert ("custom", "Custom") in PROMPT_MODE_OPTIONS


def test_custom_prompt_visibility_follows_selected_mode(nsapp):
    controller = build_settings_window_controller(
        AppConfig(online_prompt_mode="disabled"),
        launch_at_login_enabled=False,
        on_save=lambda *args: None,
    )

    assert controller._custom_prompt_scroll.isHidden() is True

    controller._mode_popup.selectItemWithTitle_("Custom")
    controller.promptModeChanged_(None)

    assert controller._custom_prompt_scroll.isHidden() is False


def test_settings_window_uses_separate_close_delegate(nsapp):
    controller = build_settings_window_controller(
        AppConfig(), launch_at_login_enabled=False, on_save=lambda *args: None
    )

    delegate = controller._window_delegate
    assert isinstance(delegate, SettingsWindowDelegate)
    assert controller._window.delegate() is delegate
    # Controller itself must no longer respond to windowWillClose_ selector,
    # otherwise AppKit could still route the callback into the mixed-selector
    # controller object during window teardown.
    assert not controller.respondsToSelector_("windowWillClose:")


def test_settings_window_close_delegate_ends_capture_sessions(nsapp):
    events = []
    controller = build_settings_window_controller(
        AppConfig(),
        launch_at_login_enabled=False,
        on_save=lambda *args: None,
        on_hotkey_capture_active=lambda active: events.append(active),
    )

    controller._hold_key_recorder.editManually_(None)
    assert events == [True]

    controller._window_delegate.windowWillClose_(None)

    assert events == [True, False]
    assert controller._hotkey_capture_count == 0
    # Idempotent: calling again must not underflow or re-toggle.
    controller._window_delegate.windowWillClose_(None)
    assert events == [True, False]


def test_end_active_session_is_idempotent(nsapp):
    recorder = HotkeyRecorderView.alloc().initWithFrame_value_singleKey_(
        ((0.0, 0.0), (230.0, 28.0)),
        ["cmd", "char:k"],
        False,
    )
    events = []
    recorder.set_capture_callbacks(lambda: events.append("begin"), lambda: events.append("end"))

    # No active session — must be a no-op.
    recorder.end_active_session()
    recorder.end_active_session()
    assert events == []


def test_settings_save_collects_custom_prompt_and_mode_cycle_hotkey(nsapp):
    saved = {}

    def _on_save(config, api_key, launch_enabled):
        saved["config"] = config
        saved["api_key"] = api_key
        saved["launch_enabled"] = launch_enabled

    controller = build_settings_window_controller(
        AppConfig(),
        launch_at_login_enabled=False,
        on_save=_on_save,
    )
    controller._mode_popup.selectItemWithTitle_("Custom")
    controller.promptModeChanged_(None)
    controller._custom_prompt_view.setString_("Rewrite in a concise style.")
    controller._mode_cycle_recorder.setValue_(["cmd", "shift", "char:m"])

    controller.saveSettings_(None)

    assert saved["config"].online_prompt_mode == "custom"
    assert saved["config"].online_prompt_custom_text == "Rewrite in a concise style."
    assert saved["config"].mode_cycle_keys == ["cmd", "shift", "char:m"]
