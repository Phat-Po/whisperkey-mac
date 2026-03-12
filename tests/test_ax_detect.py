"""Unit tests for whisperkey_mac.ax_detect — DET-01 and DET-02.

All AX API calls are mocked — no real Accessibility permission required.
Tests cover: text input roles (True), non-text roles (False),
AX enabled/editable guards (False), AX error codes (False), and exceptions (False).
"""
import unittest.mock

import pytest

from whisperkey_mac.ax_detect import insert_text_at_cursor, is_cursor_in_text_field


class TestTextInputRoles:
    """DET-01: is_cursor_in_text_field() returns True for all text input roles."""

    @pytest.mark.parametrize("role", ["AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"])
    def test_text_input_roles(self, role):
        """Returns True when focused element has a text input role."""
        mock_element = unittest.mock.MagicMock()
        with (
            unittest.mock.patch("whisperkey_mac.ax_detect.AXUIElementCreateSystemWide") as mock_sw,
            unittest.mock.patch(
                "whisperkey_mac.ax_detect.AXUIElementCopyAttributeValue",
                side_effect=[(0, mock_element), (0, role), (0, True), (0, True)],
            ),
        ):
            mock_sw.return_value = unittest.mock.MagicMock()
            result = is_cursor_in_text_field()
        assert result is True, f"Expected True for role {role!r}"


class TestNonTextRoles:
    """DET-01: is_cursor_in_text_field() returns False for non-text roles."""

    @pytest.mark.parametrize("role", ["AXButton", "AXWindow"])
    def test_non_text_roles(self, role):
        """Returns False when focused element has a non-text role."""
        mock_element = unittest.mock.MagicMock()
        with (
            unittest.mock.patch("whisperkey_mac.ax_detect.AXUIElementCreateSystemWide") as mock_sw,
            unittest.mock.patch(
                "whisperkey_mac.ax_detect.AXUIElementCopyAttributeValue",
                side_effect=[(0, mock_element), (0, role)],
            ),
        ):
            mock_sw.return_value = unittest.mock.MagicMock()
            result = is_cursor_in_text_field()
        assert result is False, f"Expected False for role {role!r}"


def test_disabled_text_role_returns_false():
    mock_element = unittest.mock.MagicMock()
    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.AXUIElementCreateSystemWide") as mock_sw,
        unittest.mock.patch(
            "whisperkey_mac.ax_detect.AXUIElementCopyAttributeValue",
            side_effect=[(0, mock_element), (0, "AXTextField"), (0, False), (0, True)],
        ),
    ):
        mock_sw.return_value = unittest.mock.MagicMock()
        result = is_cursor_in_text_field()
    assert result is False


def test_non_editable_text_role_returns_false():
    mock_element = unittest.mock.MagicMock()
    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.AXUIElementCreateSystemWide") as mock_sw,
        unittest.mock.patch(
            "whisperkey_mac.ax_detect.AXUIElementCopyAttributeValue",
            side_effect=[(0, mock_element), (0, "AXTextField"), (0, True), (0, False)],
        ),
    ):
        mock_sw.return_value = unittest.mock.MagicMock()
        result = is_cursor_in_text_field()
    assert result is False


def test_ax_error_returns_false():
    """DET-02: Returns False when AXUIElementCopyAttributeValue returns non-zero error code for focused element."""
    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.AXUIElementCreateSystemWide") as mock_sw,
        unittest.mock.patch(
            "whisperkey_mac.ax_detect.AXUIElementCopyAttributeValue",
            return_value=(-25211, None),  # kAXErrorAPIDisabled
        ),
    ):
        mock_sw.return_value = unittest.mock.MagicMock()
        result = is_cursor_in_text_field()
    assert result is False


def test_ax_exception_returns_false():
    """DET-02: Returns False when AXUIElementCreateSystemWide raises an exception."""
    with unittest.mock.patch(
        "whisperkey_mac.ax_detect.AXUIElementCreateSystemWide",
        side_effect=RuntimeError("AX not available"),
    ):
        result = is_cursor_in_text_field()
    assert result is False


def test_insert_text_at_cursor_replaces_current_selection():
    mock_element = unittest.mock.MagicMock()
    selected_range = object()

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.AXUIElementCreateSystemWide", return_value=object()),
        unittest.mock.patch(
            "whisperkey_mac.ax_detect.AXUIElementCopyAttributeValue",
            side_effect=[
                (0, mock_element),
                (0, "AXTextField"),
                (0, True),
                (0, True),
                (0, "hello world"),
                (0, selected_range),
            ],
        ),
        unittest.mock.patch("whisperkey_mac.ax_detect.AXValueGetValue", return_value=(True, (6, 5))),
        unittest.mock.patch("whisperkey_mac.ax_detect.AXValueCreate", return_value="next-range") as mock_create,
        unittest.mock.patch(
            "whisperkey_mac.ax_detect.AXUIElementSetAttributeValue",
            side_effect=[0, 0],
        ) as mock_set,
    ):
        assert insert_text_at_cursor("WhisperKey") is True

    assert mock_set.call_args_list[0].args[1:] == ("AXValue", "hello WhisperKey")
    assert mock_create.call_args.args == (4, (16, 0))
    assert mock_set.call_args_list[1].args[1:] == ("AXSelectedTextRange", "next-range")


def test_insert_text_at_cursor_returns_false_when_selected_range_missing():
    mock_element = unittest.mock.MagicMock()

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.AXUIElementCreateSystemWide", return_value=object()),
        unittest.mock.patch(
            "whisperkey_mac.ax_detect.AXUIElementCopyAttributeValue",
            side_effect=[
                (0, mock_element),
                (0, "AXTextField"),
                (0, True),
                (0, True),
                (0, "hello world"),
                (-25212, None),
            ],
        ),
    ):
        assert insert_text_at_cursor("WhisperKey") is False


def test_insert_text_at_cursor_returns_false_when_setting_value_fails():
    mock_element = unittest.mock.MagicMock()
    selected_range = object()

    with (
        unittest.mock.patch("whisperkey_mac.ax_detect.AXUIElementCreateSystemWide", return_value=object()),
        unittest.mock.patch(
            "whisperkey_mac.ax_detect.AXUIElementCopyAttributeValue",
            side_effect=[
                (0, mock_element),
                (0, "AXTextField"),
                (0, True),
                (0, True),
                (0, "hello world"),
                (0, selected_range),
            ],
        ),
        unittest.mock.patch("whisperkey_mac.ax_detect.AXValueGetValue", return_value=(True, (6, 0))),
        unittest.mock.patch("whisperkey_mac.ax_detect.AXUIElementSetAttributeValue", return_value=-25205),
    ):
        assert insert_text_at_cursor("WhisperKey ") is False
