import unittest.mock

from whisperkey_mac.menu_bar import (
    MenuBarController,
    button_title_for_state,
    launch_menu_title,
    service_menu_title_for_state,
)


def test_button_title_for_state_reflects_service_status():
    assert button_title_for_state(True) == "WK"
    assert button_title_for_state(False) == "WK·"


def test_service_menu_title_for_state_reflects_toggle_action():
    assert service_menu_title_for_state(True) == "Stop Service"
    assert service_menu_title_for_state(False) == "Start Service"


def test_launch_menu_title_reflects_launch_agent_toggle():
    assert launch_menu_title(True) == "Disable Launch At Login"
    assert launch_menu_title(False) == "Enable Launch At Login"


def test_quit_app_only_terminates_nsapp():
    controller = MenuBarController.alloc().init()
    nsapp = unittest.mock.MagicMock()

    with unittest.mock.patch("AppKit.NSApp", return_value=nsapp):
        controller.quitApp_(None)

    nsapp.terminate_.assert_called_once_with(None)
