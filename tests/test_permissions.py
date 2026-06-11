"""Tests for permission checks and the onboarding move-to-Applications logic."""

import unittest.mock

from whisperkey_mac import permissions
from whisperkey_mac.onboarding import move_decision


def test_required_granted_needs_accessibility():
    with (
        unittest.mock.patch.object(permissions, "check_accessibility", return_value=False),
        unittest.mock.patch.object(permissions, "check_input_monitoring", return_value=True),
    ):
        assert permissions.required_granted() is False


def test_required_granted_needs_input_monitoring():
    with (
        unittest.mock.patch.object(permissions, "check_accessibility", return_value=True),
        unittest.mock.patch.object(permissions, "check_input_monitoring", return_value=False),
    ):
        assert permissions.required_granted() is False


def test_required_granted_accepts_unknown_input_monitoring():
    with (
        unittest.mock.patch.object(permissions, "check_accessibility", return_value=True),
        unittest.mock.patch.object(permissions, "check_input_monitoring", return_value=None),
    ):
        assert permissions.required_granted() is True


def test_required_granted_all_granted():
    with (
        unittest.mock.patch.object(permissions, "check_accessibility", return_value=True),
        unittest.mock.patch.object(permissions, "check_input_monitoring", return_value=True),
    ):
        assert permissions.required_granted() is True


def test_open_settings_pane_ignores_unknown_pane():
    with unittest.mock.patch("whisperkey_mac.permissions.subprocess.run") as mock_run:
        permissions.open_settings_pane("nonsense")
    mock_run.assert_not_called()


def test_open_settings_pane_opens_known_pane():
    with unittest.mock.patch("whisperkey_mac.permissions.subprocess.run") as mock_run:
        permissions.open_settings_pane("accessibility")
    args = mock_run.call_args.args[0]
    assert args[0] == "open"
    assert "Privacy_Accessibility" in args[1]


def test_move_decision_offers_for_downloads():
    assert move_decision("/Users/popo/Downloads/WhisperKey.app", home="/Users/popo") == "offer"


def test_move_decision_offers_for_desktop():
    assert move_decision("/Users/popo/Desktop/WhisperKey.app", home="/Users/popo") == "offer"


def test_move_decision_ok_for_applications():
    assert move_decision("/Applications/WhisperKey.app", home="/Users/popo") == "ok"


def test_move_decision_ok_for_other_locations():
    assert move_decision("/Users/popo/dev/dist/WhisperKey.app", home="/Users/popo") == "ok"


def test_move_decision_detects_translocation():
    path = "/private/var/folders/ab/xyz/T/AppTranslocation/123-456/d/WhisperKey.app"
    assert move_decision(path, home="/Users/popo") == "translocated"
