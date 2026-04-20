import unittest.mock

from whisperkey_mac.menu_bar import (
    MenuBarController,
    button_title_for_state,
    mode_indicator_rgb_for_mode,
    mode_menu_label_for_mode,
    service_menu_title_for_state,
    status_line_title,
)


def test_button_title_for_state_reflects_service_status():
    assert button_title_for_state(True) == "WK"
    assert button_title_for_state(False) == "WK·"


def test_service_menu_title_for_state_reflects_toggle_action():
    assert service_menu_title_for_state(True) == "Stop Service"
    assert service_menu_title_for_state(False) == "Start Service"


def test_mode_indicator_color_mapping():
    assert mode_indicator_rgb_for_mode("disabled") == (0.55, 0.56, 0.60)
    assert mode_indicator_rgb_for_mode("asr_correction") == (0.22, 0.48, 0.95)
    assert mode_indicator_rgb_for_mode("voice_cleanup") == (0.58, 0.36, 0.92)
    assert mode_indicator_rgb_for_mode("custom") == (0.94, 0.68, 0.20)
    assert mode_indicator_rgb_for_mode("unknown") == (0.55, 0.56, 0.60)


def test_status_line_title_includes_current_mode():
    assert mode_menu_label_for_mode("voice_cleanup") == "Voice Cleanup"
    assert status_line_title("Running", "voice_cleanup") == "Status: Running · Mode: Voice Cleanup"
    assert status_line_title("Stopped", "disabled") == "Status: Stopped · Mode: Off"


def test_quit_app_only_terminates_nsapp():
    controller = MenuBarController.alloc().init()
    nsapp = unittest.mock.MagicMock()

    with unittest.mock.patch("AppKit.NSApp", return_value=nsapp):
        controller.quitApp_(None)

    nsapp.terminate_.assert_called_once_with(None)
