"""Regression tests for whisperkey_mac.output."""

import unittest.mock

from whisperkey_mac.config import AppConfig
from whisperkey_mac.output import TextOutput


def test_inject_returns_empty_for_blank_text():
    output = TextOutput(AppConfig())

    with unittest.mock.patch("whisperkey_mac.output.pyperclip.copy") as mock_copy:
        result = output.inject("   ")

    assert result == "empty"
    mock_copy.assert_not_called()


def test_inject_returns_pasted_after_successful_paste():
    output = TextOutput(AppConfig())

    with (
        unittest.mock.patch("whisperkey_mac.output.pyperclip.copy") as mock_copy,
        unittest.mock.patch.object(output, "_paste_clipboard") as mock_paste,
        unittest.mock.patch.object(output, "_insert_via_ax") as mock_insert,
    ):
        result = output.inject("  hello world  ")

    assert result == "applescript"
    mock_copy.assert_called_once_with("hello world")
    mock_paste.assert_called_once_with(None)
    mock_insert.assert_not_called()


def test_inject_returns_clipboard_when_paste_fails():
    output = TextOutput(AppConfig())

    with (
        unittest.mock.patch("whisperkey_mac.output.pyperclip.copy") as mock_copy,
        unittest.mock.patch.object(output, "_paste_clipboard", side_effect=RuntimeError("paste failed")),
        unittest.mock.patch.object(output, "_insert_via_ax", return_value=False) as mock_insert,
    ):
        result = output.inject("fallback")

    assert result == "clipboard"
    mock_copy.assert_called_once_with("fallback")
    mock_insert.assert_called_once_with("fallback")


def test_inject_returns_inserted_when_ax_write_succeeds():
    output = TextOutput(AppConfig())

    with (
        unittest.mock.patch("whisperkey_mac.output.pyperclip.copy") as mock_copy,
        unittest.mock.patch.object(output, "_paste_clipboard", side_effect=RuntimeError("paste failed")),
        unittest.mock.patch.object(output, "_insert_via_ax", return_value=True) as mock_insert,
    ):
        result = output.inject("直接输入")

    assert result == "inserted"
    mock_copy.assert_called_once_with("直接输入")
    mock_insert.assert_called_once_with("直接输入")


def test_inject_passes_target_bundle_id_to_applescript_fallback():
    output = TextOutput(AppConfig())

    with (
        unittest.mock.patch("whisperkey_mac.output.pyperclip.copy"),
        unittest.mock.patch.object(output, "_paste_clipboard") as mock_paste,
        unittest.mock.patch.object(output, "_insert_via_ax") as mock_insert,
    ):
        result = output.inject("hello", target_bundle_id="com.apple.TextEdit")

    assert result == "applescript"
    mock_paste.assert_called_once_with("com.apple.TextEdit")
    mock_insert.assert_not_called()


def test_paste_clipboard_activates_target_bundle_before_keystroke():
    output = TextOutput(AppConfig())

    with unittest.mock.patch("whisperkey_mac.output.subprocess.run") as mock_run:
        output._paste_clipboard("com.apple.TextEdit")

    assert mock_run.call_args.args[0] == [
        "osascript",
        "-e",
        'tell application id "com.apple.TextEdit" to activate',
        "-e",
        'tell application "System Events" to keystroke "v" using command down',
    ]


def test_inject_tries_ax_after_applescript_failure():
    output = TextOutput(AppConfig())

    with (
        unittest.mock.patch("whisperkey_mac.output.pyperclip.copy"),
        unittest.mock.patch.object(output, "_paste_clipboard", side_effect=RuntimeError("paste failed")),
        unittest.mock.patch.object(output, "_insert_via_ax", return_value=True) as mock_insert,
    ):
        result = output.inject("hello", target_bundle_id="com.apple.TextEdit")

    assert result == "inserted"
    mock_insert.assert_called_once_with("hello")
