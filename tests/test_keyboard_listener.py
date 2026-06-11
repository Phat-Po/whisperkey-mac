"""Regression tests for hands-free key sequencing."""

import unittest.mock

from pynput import keyboard

from whisperkey_mac import keyboard_listener as keyboard_listener_module
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


class _FakeDarwinListener(_FakeListener):
    def _event_to_key(self, event):
        return event


class _ConstructedListener:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.started = False

    def start(self) -> None:
        self.started = True


def _unpause(listener: HotkeyListener) -> None:
    listener._paused = False


def _cmd_backslash_listener() -> HotkeyListener:
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
    )
    listener._listener = _FakeDarwinListener()
    _unpause(listener)
    return listener


def test_start_installs_darwin_intercept_without_global_suppression():
    created: list[_ConstructedListener] = []

    def _make_listener(*args, **kwargs):
        constructed = _ConstructedListener(*args, **kwargs)
        created.append(constructed)
        return constructed

    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
    )

    with (
        unittest.mock.patch("whisperkey_mac.keyboard_listener.keyboard.Listener", side_effect=_make_listener),
        unittest.mock.patch("whisperkey_mac.keyboard_listener.AXIsProcessTrusted", return_value=True),
    ):
        listener.start()

    assert len(created) == 1
    assert created[0].started is True
    assert created[0].kwargs["on_press"] == listener._on_press
    assert created[0].kwargs["on_release"] == listener._on_release
    assert created[0].kwargs["darwin_intercept"] == listener._intercept_darwin_event
    assert "suppress" not in created[0].kwargs
    assert listener._paused is False


def test_start_uses_active_raw_combo_tap_when_trusted():
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
    )

    with (
        unittest.mock.patch("whisperkey_mac.keyboard_listener.keyboard.Listener", return_value=_ConstructedListener()),
        unittest.mock.patch("whisperkey_mac.keyboard_listener.AXIsProcessTrusted", return_value=True),
        unittest.mock.patch("whisperkey_mac.keyboard_listener._HAS_QUARTZ", True),
        unittest.mock.patch.object(listener, "_start_raw_combo_tap") as mock_raw_tap,
    ):
        listener.start()

    mock_raw_tap.assert_called_once_with(active=True)


def test_start_uses_listen_only_raw_combo_tap_when_not_trusted():
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
    )

    with (
        unittest.mock.patch("whisperkey_mac.keyboard_listener.keyboard.Listener", return_value=_ConstructedListener()),
        unittest.mock.patch("whisperkey_mac.keyboard_listener.AXIsProcessTrusted", return_value=False),
        unittest.mock.patch("whisperkey_mac.keyboard_listener._HAS_QUARTZ", True),
        unittest.mock.patch.object(listener, "_start_raw_combo_tap") as mock_raw_tap,
    ):
        listener.start()

    mock_raw_tap.assert_called_once_with(active=False)


def test_raw_combo_press_and_release_toggles_handsfree():
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

    listener._handle_raw_combo_press()

    on_start.assert_called_once_with()
    on_stop.assert_not_called()
    assert listener._mode == "handsfree"

    listener._handle_raw_combo_release()
    on_stop.assert_not_called()

    listener._handle_raw_combo_press()
    on_stop.assert_not_called()
    assert listener._handsfree_stop_pending is True

    listener._handle_raw_combo_release()

    on_stop.assert_called_once_with()
    assert listener._mode == "idle"


def test_intercept_suppresses_cmd_backslash_character_down_and_up():
    listener = _cmd_backslash_listener()
    slash = keyboard.KeyCode.from_char("\\")

    listener._on_press(keyboard.Key.cmd)
    listener._on_press(slash)

    with unittest.mock.patch("whisperkey_mac.keyboard_listener.diag") as mock_diag:
        down_result = listener._intercept_darwin_event(keyboard_listener_module.kCGEventKeyDown, slash)
        listener._on_release(slash)
        up_result = listener._intercept_darwin_event(keyboard_listener_module.kCGEventKeyUp, slash)

    assert down_result is None
    assert up_result is None
    suppressed_calls = [
        call for call in mock_diag.call_args_list
        if call.args and call.args[0] == "hotkey_event_suppressed"
    ]
    assert [call.kwargs["phase"] for call in suppressed_calls] == ["down", "up"]
    assert suppressed_calls[0].kwargs["key"] == "char:backslash"
    assert suppressed_calls[0].kwargs["combo"] == "cmd+char:backslash"
    assert "\\" not in suppressed_calls[0].kwargs["key"]
    assert "\\" not in suppressed_calls[0].kwargs["combo"]


def test_intercept_allows_plain_backslash():
    listener = _cmd_backslash_listener()
    slash = keyboard.KeyCode.from_char("\\")

    listener._on_press(slash)

    result = listener._intercept_darwin_event(keyboard_listener_module.kCGEventKeyDown, slash)

    assert result is slash


def test_intercept_allows_other_cmd_shortcuts():
    listener = _cmd_backslash_listener()
    c_key = keyboard.KeyCode.from_char("c")

    listener._on_press(keyboard.Key.cmd)
    listener._on_press(c_key)

    result = listener._intercept_darwin_event(keyboard_listener_module.kCGEventKeyDown, c_key)

    assert result is c_key


def test_intercept_suppresses_only_matching_keyup_once():
    listener = _cmd_backslash_listener()
    slash = keyboard.KeyCode.from_char("\\")

    listener._on_press(keyboard.Key.cmd)
    listener._on_press(slash)
    assert listener._intercept_darwin_event(keyboard_listener_module.kCGEventKeyDown, slash) is None
    listener._on_release(slash)

    assert listener._intercept_darwin_event(keyboard_listener_module.kCGEventKeyUp, slash) is None
    assert listener._intercept_darwin_event(keyboard_listener_module.kCGEventKeyUp, slash) is slash


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


def test_mode_cycle_combo_triggers_callback_once_per_press():
    on_cycle = unittest.mock.MagicMock()
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["alt_r", "cmd_r"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
        mode_cycle_keys=["cmd", "shift", "char:m"],
        on_mode_cycle=on_cycle,
    )
    _unpause(listener)
    m_key = keyboard.KeyCode.from_char("m")

    listener._on_press(keyboard.Key.cmd)
    listener._on_press(keyboard.Key.shift)
    listener._on_press(m_key)
    listener._on_press(m_key)

    on_cycle.assert_called_once_with()


def test_intercept_suppresses_mode_cycle_character_down_and_up():
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["alt_r", "cmd_r"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
        mode_cycle_keys=["cmd", "char:m"],
        on_mode_cycle=unittest.mock.MagicMock(),
    )
    listener._listener = _FakeDarwinListener()
    _unpause(listener)
    m_key = keyboard.KeyCode.from_char("m")

    listener._on_press(keyboard.Key.cmd)
    listener._on_press(m_key)

    down_result = listener._intercept_darwin_event(keyboard_listener_module.kCGEventKeyDown, m_key)
    listener._on_release(m_key)
    up_result = listener._intercept_darwin_event(keyboard_listener_module.kCGEventKeyUp, m_key)

    assert down_result is None
    assert up_result is None


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


def test_key_matches_name_falls_back_to_vk_for_option_layer_char():
    from whisperkey_mac.keyboard_listener import _key_matches_name

    option_equal = keyboard.KeyCode.from_char("≠", vk=0x18)
    assert _key_matches_name(option_equal, "char:=") is True
    assert _key_matches_name(option_equal, "char:-") is False

    plain_backslash = keyboard.KeyCode.from_char("\\", vk=0x2A)
    assert _key_matches_name(plain_backslash, "char:\\") is True

    plain_m = keyboard.KeyCode.from_char("m", vk=0x2E)
    assert _key_matches_name(plain_m, "char:m") is True


def test_combo_pressed_matches_option_plus_equal():
    from whisperkey_mac.keyboard_listener import _combo_pressed

    option_equal = keyboard.KeyCode.from_char("≠", vk=0x18)
    held = {keyboard.Key.alt, option_equal}
    assert _combo_pressed(["alt", "char:="], held) is True


def test_mode_cycle_fires_on_option_equal_combo():
    on_cycle = unittest.mock.MagicMock()
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
        mode_cycle_keys=["alt", "char:="],
        on_mode_cycle=on_cycle,
    )
    _unpause(listener)

    listener._on_press(keyboard.Key.alt)
    listener._on_press(keyboard.KeyCode.from_char("≠", vk=0x18))

    on_cycle.assert_called_once_with()


def test_release_of_option_layer_char_clears_held_by_vk():
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
        mode_cycle_keys=["alt", "char:="],
        on_mode_cycle=unittest.mock.MagicMock(),
    )
    _unpause(listener)

    listener._on_press(keyboard.Key.alt)
    listener._on_press(keyboard.KeyCode.from_char("≠", vk=0x18))
    listener._on_release(keyboard.Key.alt)
    listener._on_release(keyboard.KeyCode.from_char("=", vk=0x18))

    assert listener._held_keys == set()
    assert listener._mode_cycle_combo_active is False


def test_mode_cycle_consumes_hold_prevents_recording():
    timers: list[_FakeTimer] = []

    def _make_timer(*args, **kwargs):
        timer = _FakeTimer(*args, **kwargs)
        timers.append(timer)
        return timer

    on_start = unittest.mock.MagicMock()
    on_cycle = unittest.mock.MagicMock()
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=on_start,
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
        mode_cycle_keys=["alt", "char:="],
        on_mode_cycle=on_cycle,
    )
    _unpause(listener)

    with unittest.mock.patch("whisperkey_mac.keyboard_listener.threading.Timer", side_effect=_make_timer):
        listener._on_press(keyboard.Key.alt_r)
        listener._on_press(keyboard.KeyCode.from_char("≠", vk=0x18))

    on_cycle.assert_called_once_with()
    assert len(timers) == 1
    assert timers[0].cancelled is True
    assert listener._hold_consumed_until_release is True

    # Even if the timer callback fires (simulated), recording must not start.
    listener._start_hold_recording()
    on_start.assert_not_called()
    assert listener._mode == "idle"


def test_mode_cycle_consumed_flag_resets_on_release():
    timers: list[_FakeTimer] = []

    def _make_timer(*args, **kwargs):
        timer = _FakeTimer(*args, **kwargs)
        timers.append(timer)
        return timer

    on_start = unittest.mock.MagicMock()
    listener = HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=on_start,
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
        mode_cycle_keys=["alt", "char:="],
        on_mode_cycle=unittest.mock.MagicMock(),
    )
    _unpause(listener)

    with unittest.mock.patch("whisperkey_mac.keyboard_listener.threading.Timer", side_effect=_make_timer):
        listener._on_press(keyboard.Key.alt_r)
        listener._on_press(keyboard.KeyCode.from_char("≠", vk=0x18))
        assert listener._hold_consumed_until_release is True

        listener._on_release(keyboard.KeyCode.from_char("=", vk=0x18))
        listener._on_release(keyboard.Key.alt_r)

    assert listener._hold_consumed_until_release is False
    on_start.assert_not_called()

    # A fresh alt_r press must be able to start hold recording again.
    with unittest.mock.patch("whisperkey_mac.keyboard_listener.threading.Timer", side_effect=_make_timer):
        listener._on_press(keyboard.Key.alt_r)

    assert len(timers) == 2
    assert timers[1].started is True
    assert timers[1].cancelled is False


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


def _basic_listener() -> HotkeyListener:
    return HotkeyListener(
        hold_key="alt_r",
        handsfree_keys=["cmd", "char:\\"],
        on_record_start=unittest.mock.MagicMock(),
        on_record_stop_transcribe=unittest.mock.MagicMock(),
        on_enter=unittest.mock.MagicMock(),
    )


class _TapCapturingListener:
    """Mimics pynput's darwin listener: _create_event_tap returns a local tap."""

    def __init__(self, tap) -> None:
        self._tap = tap

    def _create_event_tap(self):
        return self._tap


def test_capture_pynput_tap_stashes_handle_on_create():
    listener = _basic_listener()
    sentinel_tap = object()
    pynput_listener = _TapCapturingListener(sentinel_tap)

    listener._capture_pynput_tap(pynput_listener)
    returned = pynput_listener._create_event_tap()

    assert returned is sentinel_tap
    assert pynput_listener._wk_tap is sentinel_tap


def test_watchdog_reenables_disabled_pynput_and_raw_taps():
    listener = _basic_listener()
    pynput_tap = object()
    raw_tap = object()
    listener._listener = type("L", (), {})()
    listener._listener._wk_tap = pynput_tap
    listener._raw_tap = raw_tap

    with (
        unittest.mock.patch(
            "whisperkey_mac.keyboard_listener.CGEventTapIsEnabled", return_value=False
        ),
        unittest.mock.patch(
            "whisperkey_mac.keyboard_listener.CGEventTapEnable"
        ) as mock_enable,
    ):
        listener._reenable_disabled_taps()

    enabled = {call.args[0] for call in mock_enable.call_args_list}
    assert pynput_tap in enabled
    assert raw_tap in enabled
    for call in mock_enable.call_args_list:
        assert call.args[1] is True


def test_watchdog_rebuilds_when_authorization_is_restored():
    listener = _basic_listener()
    listener._listener_ax_trusted = False

    with (
        unittest.mock.patch("whisperkey_mac.keyboard_listener.AXIsProcessTrusted", return_value=True),
        unittest.mock.patch.object(listener, "_schedule_tap_rebuild") as mock_rebuild,
    ):
        rebuilt = listener._schedule_rebuild_if_authorization_restored()

    assert rebuilt is True
    mock_rebuild.assert_called_once_with("authorization_restored")


def test_watchdog_marks_lost_authorization_without_rebuild():
    listener = _basic_listener()
    listener._listener_ax_trusted = True

    with (
        unittest.mock.patch("whisperkey_mac.keyboard_listener.AXIsProcessTrusted", return_value=False),
        unittest.mock.patch.object(listener, "_schedule_tap_rebuild") as mock_rebuild,
    ):
        rebuilt = listener._schedule_rebuild_if_authorization_restored()

    assert rebuilt is False
    assert listener._listener_ax_trusted is False
    mock_rebuild.assert_not_called()


def test_watchdog_loop_exits_after_generation_changes():
    listener = _basic_listener()
    listener._watchdog_generation = 1
    calls = []

    def _reenable_once():
        calls.append("reenable")
        listener._watchdog_generation = 2

    with (
        unittest.mock.patch.object(listener._watchdog_stop, "wait", return_value=False),
        unittest.mock.patch.object(listener, "_reenable_disabled_taps", side_effect=_reenable_once),
    ):
        listener._watchdog_loop(1)

    assert calls == ["reenable"]


def test_watchdog_rebuilds_after_repeated_disabled_tap():
    listener = _basic_listener()
    listener._tap_rebuild_disabled_threshold = 2
    tap = object()

    with (
        unittest.mock.patch("whisperkey_mac.keyboard_listener.CGEventTapIsEnabled", return_value=False),
        unittest.mock.patch("whisperkey_mac.keyboard_listener.CGEventTapEnable"),
        unittest.mock.patch.object(listener, "_schedule_tap_rebuild") as mock_rebuild,
    ):
        listener._reenable_tap_if_disabled("pynput", tap)
        mock_rebuild.assert_not_called()

        listener._reenable_tap_if_disabled("pynput", tap)

    mock_rebuild.assert_called_once_with("pynput_repeatedly_disabled")
    assert listener._disabled_tap_counts["pynput"] == 0


def test_tap_rebuild_preserves_paused_state():
    listener = _basic_listener()
    listener._paused = True
    listener._rebuild_pending = True

    with (
        unittest.mock.patch.object(listener, "full_stop") as mock_full_stop,
        unittest.mock.patch.object(listener, "start") as mock_start,
    ):
        listener._rebuild_event_taps("authorization_restored")

    mock_full_stop.assert_called_once_with()
    mock_start.assert_not_called()
    assert listener._rebuild_pending is False


def test_tap_rebuild_restarts_when_active():
    listener = _basic_listener()
    listener._paused = False
    listener._rebuild_pending = True

    with (
        unittest.mock.patch.object(listener, "full_stop") as mock_full_stop,
        unittest.mock.patch.object(listener, "start") as mock_start,
    ):
        listener._rebuild_event_taps("authorization_restored")

    mock_full_stop.assert_called_once_with()
    mock_start.assert_called_once_with()
    assert listener._rebuild_pending is False


def test_watchdog_leaves_enabled_taps_untouched():
    listener = _basic_listener()
    listener._listener = type("L", (), {})()
    listener._listener._wk_tap = object()
    listener._raw_tap = object()

    with (
        unittest.mock.patch(
            "whisperkey_mac.keyboard_listener.CGEventTapIsEnabled", return_value=True
        ),
        unittest.mock.patch(
            "whisperkey_mac.keyboard_listener.CGEventTapEnable"
        ) as mock_enable,
    ):
        listener._reenable_disabled_taps()

    mock_enable.assert_not_called()


def test_intercept_reenables_pynput_tap_on_timeout_disable():
    listener = _basic_listener()
    pynput_tap = object()
    listener._listener = type("L", (), {})()
    listener._listener._wk_tap = pynput_tap

    with unittest.mock.patch(
        "whisperkey_mac.keyboard_listener.CGEventTapEnable"
    ) as mock_enable:
        result = listener._intercept_darwin_event(
            keyboard_listener_module.kCGEventTapDisabledByTimeout, object()
        )

    mock_enable.assert_called_once_with(pynput_tap, True)
    assert result is not None
