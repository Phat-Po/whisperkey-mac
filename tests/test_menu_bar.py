import unittest.mock

from whisperkey_mac.menu_bar import (
    MenuBarController,
    button_title_for_state,
    service_menu_title_for_state,
)


def test_button_title_for_state_reflects_service_status():
    assert button_title_for_state(True) == "WK"
    assert button_title_for_state(False) == "WK·"


def test_service_menu_title_for_state_reflects_toggle_action():
    assert service_menu_title_for_state(True) == "Stop Service"
    assert service_menu_title_for_state(False) == "Start Service"


def test_quit_app_only_terminates_nsapp():
    controller = MenuBarController.alloc().init()
    nsapp = unittest.mock.MagicMock()

    with unittest.mock.patch("AppKit.NSApp", return_value=nsapp):
        controller.quitApp_(None)

    nsapp.terminate_.assert_called_once_with(None)
