from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pynput import keyboard
try:
    from Quartz import kCGEventKeyDown, kCGEventKeyUp
except Exception:  # pragma: no cover - non-macOS test/import fallback
    kCGEventKeyDown = 10
    kCGEventKeyUp = 11

from whisperkey_mac.diagnostics import diag

# Minimum hold duration before recording starts (avoids accidental taps)
MIN_HOLD_S = 0.15
HOLD_CONFLICT_GRACE_S = 0.35

# Map config string names → pynput Key objects
_KEY_MAP: dict[str, keyboard.Key] = {
    "alt_l": keyboard.Key.alt,
    "alt_r": keyboard.Key.alt_r,
    "alt": keyboard.Key.alt,
    "cmd_l": keyboard.Key.cmd,
    "cmd_r": keyboard.Key.cmd_r,
    "cmd": keyboard.Key.cmd,
    "ctrl_l": keyboard.Key.ctrl,
    "ctrl_r": keyboard.Key.ctrl_r,
    "ctrl": keyboard.Key.ctrl,
    "shift_l": keyboard.Key.shift,
    "shift_r": keyboard.Key.shift_r,
    "shift": keyboard.Key.shift,
    "f13": keyboard.Key.f13,
    "f14": keyboard.Key.f14,
    "f15": keyboard.Key.f15,
    "f16": keyboard.Key.f16,
    "f17": keyboard.Key.f17,
    "f18": keyboard.Key.f18,
    "f19": keyboard.Key.f19,
    "page_up": keyboard.Key.page_up,
    "page_down": keyboard.Key.page_down,
    "caps_lock": keyboard.Key.caps_lock,
}

_GENERIC_MODIFIER_MATCHES: dict[str, set[str]] = {
    "alt": {"alt", "alt_l", "alt_r"},
    "cmd": {"cmd", "cmd_l", "cmd_r"},
    "ctrl": {"ctrl", "ctrl_l", "ctrl_r"},
    "shift": {"shift", "shift_l", "shift_r"},
}

_RIGHT_MODIFIER_NAMES: dict[keyboard.Key, str] = {
    keyboard.Key.alt_r: "alt_r",
    keyboard.Key.cmd_r: "cmd_r",
    keyboard.Key.ctrl_r: "ctrl_r",
    keyboard.Key.shift_r: "shift_r",
}

_GENERIC_MODIFIER_NAMES: dict[keyboard.Key, str] = {
    keyboard.Key.alt: "alt",
    keyboard.Key.cmd: "cmd",
    keyboard.Key.ctrl: "ctrl",
    keyboard.Key.shift: "shift",
}


def key_name_to_pynput(name: str) -> keyboard.Key | keyboard.KeyCode | None:
    if name.startswith("char:") and len(name) > 5:
        return keyboard.KeyCode.from_char(name[5:])
    return _KEY_MAP.get(name)


def pynput_key_to_name(key: keyboard.Key | keyboard.KeyCode) -> str | None:
    if key in _RIGHT_MODIFIER_NAMES:
        return _RIGHT_MODIFIER_NAMES[key]
    if key in _GENERIC_MODIFIER_NAMES:
        return _GENERIC_MODIFIER_NAMES[key]
    for name, mapped_key in _KEY_MAP.items():
        if name.endswith("_l") or name in _GENERIC_MODIFIER_MATCHES:
            continue
        if mapped_key == key:
            return name
    if isinstance(key, keyboard.KeyCode) and key.char:
        return f"char:{key.char}"
    return None


def _normalize_key_name(name: str) -> str | None:
    if key_name_to_pynput(name) is None:
        return None
    return name


def _key_matches_name(key: keyboard.Key | keyboard.KeyCode, configured_name: str) -> bool:
    actual_name = pynput_key_to_name(key)
    if actual_name is None:
        return False
    if configured_name in _GENERIC_MODIFIER_MATCHES:
        return actual_name in _GENERIC_MODIFIER_MATCHES[configured_name]
    return actual_name == configured_name


def _names_overlap(left: str, right: str) -> bool:
    left_matches = _GENERIC_MODIFIER_MATCHES.get(left, {left})
    right_matches = _GENERIC_MODIFIER_MATCHES.get(right, {right})
    return bool(left_matches & right_matches)


def _combo_pressed(configured_names: list[str], held_keys: set[keyboard.Key | keyboard.KeyCode]) -> bool:
    if len(configured_names) < 2:
        return False
    held = list(held_keys)
    used: set[int] = set()

    def _search(index: int) -> bool:
        if index >= len(configured_names):
            return True
        configured_name = configured_names[index]
        for held_index, held_key in enumerate(held):
            if held_index in used:
                continue
            if not _key_matches_name(held_key, configured_name):
                continue
            used.add(held_index)
            if _search(index + 1):
                return True
            used.remove(held_index)
        return False

    return _search(0)


def _any_configured_key_held(
    configured_names: list[str],
    held_keys: set[keyboard.Key | keyboard.KeyCode],
) -> bool:
    return any(_key_matches_name(held_key, name) for name in configured_names for held_key in held_keys)


def _safe_key_label(key: keyboard.Key | keyboard.KeyCode | None) -> str:
    if key is None:
        return "none"
    name = pynput_key_to_name(key)
    if name is None:
        return "unknown"
    return _safe_name_label(name)


def _safe_name_label(name: str) -> str:
    if name.startswith("char:"):
        char = name[5:]
        if char == "\\":
            return "char:backslash"
        if char == " ":
            return "char:space"
        if char == "\t":
            return "char:tab"
        return f"char_len:{len(char)}"
    return name


def _safe_names_label(names: list[str]) -> str:
    return "+".join(_safe_name_label(name) for name in names)


class HotkeyListener:
    """
    Hold-to-talk + hands-free recording listener.

    HOLD MODE (default):
        Press & hold hold_key (>150ms) → start recording
        Release hold_key               → stop + transcribe

    HANDS-FREE MODE:
        Both handsfree_keys held simultaneously → toggle recording on/off
        Press the combo again, then release it   → stop + transcribe
    """

    def __init__(
        self,
        hold_key: str,
        handsfree_keys: list[str],
        on_record_start: Callable[[], None],
        on_record_stop_transcribe: Callable[[], None],
        on_enter: Callable[[], None],
    ) -> None:
        self._hold_name = _normalize_key_name(hold_key) or "alt_r"
        self._hold_pkey = key_name_to_pynput(self._hold_name) or keyboard.Key.alt_r
        self._handsfree_names = [
            name for name in handsfree_keys
            if _normalize_key_name(name) is not None
        ]
        self._handsfree_pkeys: list[keyboard.Key | keyboard.KeyCode] = [
            key_name_to_pynput(name) for name in self._handsfree_names
        ]
        self._hold_conflicts_with_handsfree = any(
            _names_overlap(self._hold_name, name) for name in self._handsfree_names
        )

        self._on_record_start = on_record_start
        self._on_record_stop_transcribe = on_record_stop_transcribe

        self._lock = threading.Lock()
        self._held_keys: set = set()
        # "idle" | "hold_recording" | "handsfree"
        self._mode = "idle"
        self._hold_press_time: float = 0.0
        self._hold_timer: threading.Timer | None = None
        self._active_hold_key: keyboard.Key | keyboard.KeyCode | None = None
        self._handsfree_combo_active = False
        self._handsfree_stop_pending = False
        self._suppressed_handsfree_keyups: set[str] = set()

        self._listener: keyboard.Listener | None = None
        self._paused: bool = True  # start paused; activated by start()
        diag(
            "hotkey_listener_config",
            hold_key=_safe_name_label(self._hold_name),
            handsfree_keys=_safe_names_label(self._handsfree_names),
            hold_conflicts_with_handsfree=self._hold_conflicts_with_handsfree,
        )

    def update_keys(self, hold_key: str, handsfree_keys: list[str]) -> None:
        """Update key bindings in-place without stopping the listener."""
        with self._lock:
            self._hold_name = _normalize_key_name(hold_key) or "alt_r"
            self._hold_pkey = key_name_to_pynput(self._hold_name) or keyboard.Key.alt_r
            self._handsfree_names = [
                name for name in handsfree_keys
                if _normalize_key_name(name) is not None
            ]
            self._handsfree_pkeys = [
                key_name_to_pynput(name) for name in self._handsfree_names
            ]
            self._hold_conflicts_with_handsfree = any(
                _names_overlap(self._hold_name, name) for name in self._handsfree_names
            )
            self._held_keys.clear()
            self._handsfree_combo_active = False
            self._handsfree_stop_pending = False
            self._suppressed_handsfree_keyups.clear()
            self._mode = "idle"
            self._active_hold_key = None
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None
        diag(
            "hotkey_listener_update",
            hold_key=_safe_name_label(self._hold_name),
            handsfree_keys=_safe_names_label(self._handsfree_names),
            hold_conflicts_with_handsfree=self._hold_conflicts_with_handsfree,
        )

    def start(self) -> None:
        """Unpause the listener. Creates the CGEventTap once on first call."""
        created = False
        if self._listener is None:
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
                darwin_intercept=self._intercept_darwin_event,
            )
            self._listener.start()
            created = True
        self._paused = False
        diag("hotkey_listener_start", created=created, paused=self._paused)

    def stop(self) -> None:
        """Pause the listener without destroying the CGEventTap."""
        self._paused = True
        self.reset_state()

    def reset_state(self) -> None:
        """Clear key state after an ignored/cancelled recording transition."""
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None
        with self._lock:
            self._held_keys.clear()
            self._handsfree_combo_active = False
            self._handsfree_stop_pending = False
            self._mode = "idle"
            self._active_hold_key = None

    # ── internal ──────────────────────────────────────────────────────────────

    def _intercept_darwin_event(self, event_type: int, event: object) -> object | None:
        """Suppress only the character event that completes the hands-free combo."""
        if event_type not in (kCGEventKeyDown, kCGEventKeyUp):
            return event

        key = self._key_from_darwin_event(event)
        if key is None:
            return event

        if event_type == kCGEventKeyDown:
            suppressed_name = self._handsfree_character_to_suppress_on_press(key)
            if suppressed_name is None:
                return event

            with self._lock:
                self._suppressed_handsfree_keyups.add(suppressed_name)
            diag(
                "hotkey_event_suppressed",
                key=_safe_name_label(suppressed_name),
                phase="down",
                combo=_safe_names_label(self._handsfree_names),
            )
            return None

        suppressed_name = self._handsfree_character_to_suppress_on_release(key)
        if suppressed_name is None:
            return event

        diag(
            "hotkey_event_suppressed",
            key=_safe_name_label(suppressed_name),
            phase="up",
            combo=_safe_names_label(self._handsfree_names),
        )
        return None

    def _key_from_darwin_event(
        self,
        event: object,
    ) -> keyboard.Key | keyboard.KeyCode | None:
        listener = self._listener
        event_to_key = getattr(listener, "_event_to_key", None)
        if event_to_key is None:
            return None
        try:
            return event_to_key(event)
        except Exception as exc:
            diag("hotkey_event_parse_failed", reason=exc.__class__.__name__)
            return None

    def _handsfree_character_name_for_key(
        self,
        key: keyboard.Key | keyboard.KeyCode,
    ) -> str | None:
        for name in self._handsfree_names:
            if name.startswith("char:") and _key_matches_name(key, name):
                return name
        return None

    def _handsfree_character_to_suppress_on_press(
        self,
        key: keyboard.Key | keyboard.KeyCode,
    ) -> str | None:
        with self._lock:
            if self._paused:
                return None
            handsfree_names = list(self._handsfree_names)
            held = set(self._held_keys)

        name = self._handsfree_character_name_for_key(key)
        if name is None:
            return None
        if not _combo_pressed(handsfree_names, held):
            return None
        return name

    def _handsfree_character_to_suppress_on_release(
        self,
        key: keyboard.Key | keyboard.KeyCode,
    ) -> str | None:
        name = self._handsfree_character_name_for_key(key)
        if name is None:
            return None

        with self._lock:
            if name not in self._suppressed_handsfree_keyups:
                return None
            self._suppressed_handsfree_keyups.remove(name)
        return name

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if self._paused or key is None:
            if key is not None:
                diag("hotkey_press_ignored", key=_safe_key_label(key), reason="paused")
            return

        should_start_handsfree = False
        with self._lock:
            self._held_keys.add(key)
            mode = self._mode
            held = set(self._held_keys)
            combo_active = self._handsfree_combo_active
            stop_pending = self._handsfree_stop_pending
            hold_match = _key_matches_name(key, self._hold_name)

        # Check hands-free combo (all handsfree keys held simultaneously)
        combo_pressed = _combo_pressed(self._handsfree_names, held)
        diag(
            "hotkey_press",
            key=_safe_key_label(key),
            mode=mode,
            hold_match=hold_match,
            combo_complete=combo_pressed,
            held_count=len(held),
        )
        if combo_pressed:
            if stop_pending:
                diag("hotkey_combo_match", action="ignored_stop_pending", mode=mode)
                return
            if not combo_active:
                with self._lock:
                    self._handsfree_combo_active = True
                    mode = self._mode
                    if mode == "idle":
                        if self._hold_timer:
                            self._hold_timer.cancel()
                            self._hold_timer = None
                        self._mode = "handsfree"
                        self._handsfree_stop_pending = False
                        should_start_handsfree = True
                    elif mode == "handsfree":
                        self._handsfree_stop_pending = True
                diag(
                    "hotkey_combo_match",
                    action="start" if should_start_handsfree else "stop_pending",
                    mode=mode,
                    combo=_safe_names_label(self._handsfree_names),
                )
            if should_start_handsfree:
                print("[whisperkey] Hands-free ON — recording...")
                self._on_record_start()
            return
        if self._handsfree_names:
            diag(
                "hotkey_combo_incomplete",
                key=_safe_key_label(key),
                combo=_safe_names_label(self._handsfree_names),
                held_count=len(held),
            )

        # Hold-key press logic
        if hold_match:
            should_start_hold_timer = False
            delay = MIN_HOLD_S
            timer = None
            with self._lock:
                mode = self._mode
                if mode == "idle" and self._active_hold_key is None:
                    self._hold_press_time = time.monotonic()
                    self._active_hold_key = key
                    # Give a conflicting hands-free combo time to arrive before hold mode starts.
                    delay = HOLD_CONFLICT_GRACE_S if self._hold_conflicts_with_handsfree else MIN_HOLD_S
                    timer = threading.Timer(delay, self._start_hold_recording)
                    self._hold_timer = timer
                    should_start_hold_timer = True
            if should_start_hold_timer and timer is not None:
                diag(
                    "hotkey_hold_timer_start",
                    key=_safe_key_label(key),
                    delay_s=f"{delay:.2f}",
                    conflict_grace=self._hold_conflicts_with_handsfree,
                )
                timer.start()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if self._paused or key is None:
            if key is not None:
                diag("hotkey_release_ignored", key=_safe_key_label(key), reason="paused")
            return

        should_stop_handsfree = False
        should_handle_hold_release = False
        with self._lock:
            self._held_keys.discard(key)
            mode = self._mode
            held = set(self._held_keys)
            hold_match = _key_matches_name(key, self._hold_name)
            should_handle_hold_release = (
                self._active_hold_key is not None
                and key == self._active_hold_key
            )

            combo_pressed = _combo_pressed(self._handsfree_names, held)
            if self._handsfree_combo_active and not combo_pressed:
                self._handsfree_combo_active = False

            if self._handsfree_stop_pending:
                any_handsfree_held = _any_configured_key_held(self._handsfree_names, held)
                if not any_handsfree_held and self._mode == "handsfree":
                    self._handsfree_stop_pending = False
                    self._mode = "idle"
                    should_stop_handsfree = True
        diag(
            "hotkey_release",
            key=_safe_key_label(key),
            mode=mode,
            hold_match=hold_match,
            active_hold_release=should_handle_hold_release,
            combo_complete=combo_pressed,
            held_count=len(held),
        )

        if should_handle_hold_release:
            # Cancel pending timer (accidental tap — released before MIN_HOLD_S)
            with self._lock:
                timer = self._hold_timer
                self._hold_timer = None
                self._active_hold_key = None

            if timer is not None:
                timer.cancel()
                diag("hotkey_hold_timer_cancel", key=_safe_key_label(key), reason="released")

            # If already in hold_recording, stop and transcribe
            if mode == "hold_recording":
                with self._lock:
                    self._mode = "idle"
                diag("hotkey_hold_stop", key=_safe_key_label(key))
                self._on_record_stop_transcribe()
                return

        if should_stop_handsfree:
            diag("hotkey_combo_stop", combo=_safe_names_label(self._handsfree_names))
            self._on_record_stop_transcribe()

    def _start_hold_recording(self) -> None:
        with self._lock:
            if self._mode != "idle":
                diag("hotkey_hold_start_ignored", reason="mode_changed", mode=self._mode)
                self._hold_timer = None
                return
            if self._active_hold_key is None or self._active_hold_key not in self._held_keys:
                diag("hotkey_hold_start_ignored", reason="hold_released")
                self._hold_timer = None
                self._active_hold_key = None
                return
            self._mode = "hold_recording"
            self._hold_timer = None
            active_key = self._active_hold_key
        diag("hotkey_hold_start", key=_safe_key_label(active_key))
        print("[whisperkey] Recording...")
        self._on_record_start()
