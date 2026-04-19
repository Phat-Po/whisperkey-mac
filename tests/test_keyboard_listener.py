"""Regression tests for hands-free key sequencing."""

import unittest.mock

from pynput import keyboard

from whisperkey_mac.keyboard_listener import HotkeyListener, key_name_to_pynput, pynput_key_to_name


class _FakeTimer:
    def __init__(self, *_args, **_kwargs) -> None:
        self.started = False
        self.cancelled = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True


class _FakeListener:
    def __init__(self) -> None:
        self.stopped = False
        self.joined = False

    def stop(self) -> None:
        self.stopped = True

    def join(self, timeout: float | None = None) -> None:
        self.joined = True


def _unpause(listener: HotkeyListener) -> None:
    listener._paused = False


def test_handsfree_stop_waits_until_combo_is_fully_released():
    timers: list[_FakeTimer] = []

    def _make_timer(*args, **kwargs):
        timer = _FakeTimer(*args, **kwargs)
        timers.append(timer)
        return timer

    on_start = unittest.mock.MagicMock()
    on_stop = unittest.mock.MagicMock()
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["alt_r", "cmd_r"],
        on_record_start=on_start,
        on_record_stop_transcribe=on_stop,
        on_enter=unittest.mock.MagicMock(),
    )
    _unpause(listener)

    with unittest.mock.patch("whisperkey_mac.keyboard_listener.threading.Timer", side_effect=_make_timer):
        listener._on_press(keyboard.Key.alt_r)
        listener._on_press(keyboard.Key.cmd_r)

        on_start.assert_called_once_with()
        on_stop.assert_not_called()
        assert timers[0].cancelled is True

        listener._on_release(keyboard.Key.alt_r)
        listener._on_release(keyboard.Key.cmd_r)
        on_stop.assert_not_called()

        listener._on_press(keyboard.Key.alt_r)
        listener._on_press(keyboard.Key.cmd_r)
        on_stop.assert_not_called()

        listener._on_release(keyboard.Key.cmd_r)
        on_stop.assert_not_called()

        listener._on_release(keyboard.Key.alt_r)

    on_stop.assert_called_once_with()


def test_handsfree_supports_cmd_backslash_keycode_combo():
    on_start = unittest.mock.MagicMock()
    on_stop = unittest.mock.MagicMock()
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=on_start,
        on_record_stop_transcribe=on_stop,
        on_enter=unittest.mock.MagicMock(),
    )
    _unpause(listener)
    slash = keyboard.KeyCode.from_char("\\")

    listener._on_press(keyboard.Key.cmd)
    listener._on_press(slash)
    on_start.assert_called_once_with()
    on_stop.assert_not_called()

    listener._on_release(slash)
    listener._on_release(keyboard.Key.cmd)

    listener._on_press(keyboard.Key.cmd)
    listener._on_press(slash)
    listener._on_release(keyboard.Key.cmd)
    listener._on_release(slash)

    on_stop.assert_called_once_with()


def test_generic_cmd_handsfree_matches_right_command_key():
    on_start = unittest.mock.MagicMock()
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=on_start,
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
    )
    _unpause(listener)

    listener._on_press(keyboard.Key.cmd_r)
    listener._on_press(keyboard.KeyCode.from_char("\\"))

    on_start.assert_called_once_with()


def test_generic_alt_hold_matches_right_option_key():
    timers: list[_FakeTimer] = []

    def _make_timer(*args, **kwargs):
        timer = _FakeTimer(*args, **kwargs)
        timers.append(timer)
        return timer

    listener = HotkeyListener(
        hold_key="alt",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
    )
    _unpause(listener)

    with unittest.mock.patch("whisperkey_mac.keyboard_listener.threading.Timer", side_effect=_make_timer):
        listener._on_press(keyboard.Key.alt_r)

    assert len(timers) == 1
    assert timers[0].started is True


def test_exact_right_alt_hold_does_not_match_left_option_key():
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
    )
    _unpause(listener)

    with unittest.mock.patch("whisperkey_mac.keyboard_listener.threading.Timer") as mock_timer:
        listener._on_press(keyboard.Key.alt)

    mock_timer.assert_not_called()


def test_incomplete_handsfree_combo_logs_sanitized_diagnostic():
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
    )
    _unpause(listener)

    with unittest.mock.patch("whisperkey_mac.keyboard_listener.diag") as mock_diag:
        listener._on_press(keyboard.Key.cmd_r)

    incomplete_calls = [
        call for call in mock_diag.call_args_list
        if call.args and call.args[0] == "hotkey_combo_incomplete"
    ]
    assert incomplete_calls
    assert incomplete_calls[-1].kwargs["key"] == "cmd_r"
    assert incomplete_calls[-1].kwargs["combo"] == "cmd+char:backslash"
    assert "\\" not in incomplete_calls[-1].kwargs["combo"]


def test_keycode_name_round_trip_for_backslash():
    key = key_name_to_pynput("char:\\")

    assert key == keyboard.KeyCode.from_char("\\")
    assert pynput_key_to_name(key) == "char:\\"


def test_handsfree_combo_cancels_conflicting_hold_key_timer():
    timers: list[_FakeTimer] = []

    def _make_timer(*args, **kwargs):
        timer = _FakeTimer(*args, **kwargs)
        timer.delay = args[0]
        timers.append(timer)
        return timer

    on_start = unittest.mock.MagicMock()
    listener = HotkeyListener(
        hold_key="cmd",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=on_start,
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
    )
    _unpause(listener)

    with unittest.mock.patch("whisperkey_mac.keyboard_listener.threading.Timer", side_effect=_make_timer):
        listener._on_press(keyboard.Key.cmd)
        listener._on_press(keyboard.KeyCode.from_char("\\"))

    assert timers[0].delay > 0.15
    assert timers[0].cancelled is True
    on_start.assert_called_once_with()


def test_stop_pauses_without_destroying_underlying_listener_thread():
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["alt_r", "cmd_r"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
    )
    fake_listener = _FakeListener()
    listener._listener = fake_listener
    listener._paused = False
    listener._held_keys.add(keyboard.Key.alt_r)
    listener._handsfree_combo_active = True
    listener._handsfree_stop_pending = True
    listener._mode = "handsfree"

    listener.stop()

    assert listener._paused is True
    assert listener._listener is fake_listener
    assert listener._held_keys == set()
    assert listener._handsfree_combo_active is False
    assert listener._handsfree_stop_pending is False
    assert listener._mode == "idle"
    assert fake_listener.stopped is False
    assert fake_listener.joined is False
