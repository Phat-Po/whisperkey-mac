from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pynput import keyboard
try:
    from Quartz import (
        kCGEventKeyDown,
        kCGEventKeyUp,
        kCGEventFlagsChanged,
        CGEventTapCreate,
        CGEventTapEnable,
        CGEventTapIsEnabled,
        CFMachPortCreateRunLoopSource,
        CFRunLoopGetCurrent,
        CFRunLoopAddSource,
        CFRunLoopRunInMode,
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly,
        kCGEventTapOptionDefault,
        kCFRunLoopDefaultMode,
        kCFRunLoopRunTimedOut,
        kCGEventTapDisabledByTimeout,
        kCGEventTapDisabledByUserInput,
        CGEventGetIntegerValueField,
        CGEventGetFlags,
        kCGKeyboardEventKeycode,
    )
    _HAS_QUARTZ = True
except Exception:  # pragma: no cover - non-macOS test/import fallback
    kCGEventKeyDown = 10
    kCGEventKeyUp = 11
    kCGEventFlagsChanged = 12
    kCGEventTapDisabledByTimeout = 0xFFFFFFFE
    kCGEventTapDisabledByUserInput = 0xFFFFFFFF
    _HAS_QUARTZ = False

try:
    from ApplicationServices import AXIsProcessTrusted
except Exception:  # pragma: no cover - non-macOS
    AXIsProcessTrusted = None

from whisperkey_mac.diagnostics import diag

# Minimum hold duration before recording starts (avoids accidental taps)
MIN_HOLD_S = 0.15
HOLD_CONFLICT_GRACE_S = 0.35

# Ghost key TTL: no normal hold exceeds this; guards against key-up events
# lost to a Bluetooth keyboard disconnect/sleep mid-press.
HELD_KEY_TTL_S = 45.0

# Verbose per-keystroke diag output is opt-in; F1 made diag() cheap, but
# print+flush on every key is still wasted I/O in normal operation.
_DEBUG_KEYS = os.getenv("WHISPERKEY_DEBUG_KEYS") == "1"

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

# macOS US-ANSI virtual keycode → base (no-modifier) character.
# pynput reports KeyCode.char after applying the Option layer
# (e.g. Option+= → '≠'), but recorder stores the base character
# via charactersIgnoringModifiers. This table lets _key_matches_name
# fall back to physical-key equality via KeyCode.vk.
_VK_TO_BASE_CHAR: dict[int, str] = {
    0x00: "a", 0x0B: "b", 0x08: "c", 0x02: "d", 0x0E: "e",
    0x03: "f", 0x05: "g", 0x04: "h", 0x22: "i", 0x26: "j",
    0x28: "k", 0x25: "l", 0x2E: "m", 0x2D: "n", 0x1F: "o",
    0x23: "p", 0x0C: "q", 0x0F: "r", 0x01: "s", 0x11: "t",
    0x20: "u", 0x09: "v", 0x0D: "w", 0x07: "x", 0x10: "y",
    0x06: "z",
    0x12: "1", 0x13: "2", 0x14: "3", 0x15: "4", 0x17: "5",
    0x16: "6", 0x1A: "7", 0x1C: "8", 0x19: "9", 0x1D: "0",
    0x1B: "-", 0x18: "=",
    0x21: "[", 0x1E: "]", 0x2A: "\\",
    0x29: ";", 0x27: "'",
    0x2B: ",", 0x2F: ".", 0x2C: "/",
    0x32: "`",
    0x31: " ",
}

# Reverse map: base character → virtual keycode (for raw combo detection)
_CHAR_TO_VK: dict[str, int] = {ch: vk for vk, ch in _VK_TO_BASE_CHAR.items()}

# CGEvent modifier flag masks (from IOLLEvent.h / CGEventTypes.h)
_CG_FLAG_MASKS: dict[str, int] = {
    "cmd":   0x100000,  # kCGEventFlagMaskCommand
    "cmd_l": 0x100000,
    "cmd_r": 0x100000,
    "alt":   0x080000,  # kCGEventFlagMaskAlternate
    "alt_l": 0x080000,
    "alt_r": 0x080000,
    "ctrl":  0x040000,  # kCGEventFlagMaskControl
    "ctrl_l": 0x040000,
    "ctrl_r": 0x040000,
    "shift": 0x020000,  # kCGEventFlagMaskShift
    "shift_l": 0x020000,
    "shift_r": 0x020000,
}


def _parse_combo_raw(combo_names: list[str]) -> tuple[int, int | None]:
    """Parse combo config names into (required_modifier_flags, char_vk).

    Returns (flags_mask, vk) where *flags_mask* is the OR of all modifier
    flag bits the combo requires, and *vk* is the virtual keycode of the
    character key (or None if the combo has no char: component).
    """
    flags = 0
    char_vk: int | None = None
    for name in combo_names:
        if name in _CG_FLAG_MASKS:
            flags |= _CG_FLAG_MASKS[name]
        elif name.startswith("char:") and len(name) > 5:
            char = name[5:]
            char_vk = _CHAR_TO_VK.get(char)
    return flags, char_vk


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
        actual_name = ""
    if configured_name in _GENERIC_MODIFIER_MATCHES:
        return actual_name in _GENERIC_MODIFIER_MATCHES[configured_name]
    if actual_name == configured_name:
        return True
    if configured_name.startswith("char:") and isinstance(key, keyboard.KeyCode):
        vk = getattr(key, "vk", None)
        if vk is not None:
            base_char = _VK_TO_BASE_CHAR.get(int(vk))
            if base_char is not None and f"char:{base_char}" == configured_name:
                return True
    return False


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
        mode_cycle_keys: list[str] | None = None,
        on_mode_cycle: Callable[[], None] | None = None,
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
        self._mode_cycle_names = [
            name for name in (mode_cycle_keys or [])
            if _normalize_key_name(name) is not None
        ]
        self._mode_cycle_pkeys: list[keyboard.Key | keyboard.KeyCode] = [
            key_name_to_pynput(name) for name in self._mode_cycle_names
        ]
        self._hold_conflicts_with_handsfree = any(
            _names_overlap(self._hold_name, name) for name in self._handsfree_names
        )

        self._on_record_start = on_record_start
        self._on_record_stop_transcribe = on_record_stop_transcribe
        self._on_mode_cycle = on_mode_cycle or (lambda: None)

        self._lock = threading.Lock()
        self._held_keys: dict = {}
        # "idle" | "hold_recording" | "handsfree"
        self._mode = "idle"
        self._hold_press_time: float = 0.0
        self._hold_timer: threading.Timer | None = None
        self._active_hold_key: keyboard.Key | keyboard.KeyCode | None = None
        self._hold_consumed_until_release: bool = False
        self._handsfree_combo_active = False
        self._mode_cycle_combo_active = False
        self._handsfree_stop_pending = False
        self._suppressed_handsfree_keyups: set[str] = set()
        self._suppressed_mode_cycle_keyups: set[str] = set()

        self._listener: keyboard.Listener | None = None
        self._raw_tap: object | None = None  # CGEventTap for direct combo detection
        self._raw_tap_starting: bool = False
        self._raw_combo_held: bool = False
        self._paused: bool = True  # start paused; activated by start()
        # Watchdog: macOS disables event taps after a slow callback
        # (kCGEventTapDisabledByTimeout), user input, or sleep/wake. Neither
        # pynput nor our raw tap self-heal, so a background thread periodically
        # re-enables any tap macOS has silently switched off.
        self._watchdog_thread: threading.Thread | None = None
        self._watchdog_stop = threading.Event()
        self._watchdog_generation: int = 0
        self._watchdog_interval_s: float = 5.0
        self._listener_ax_trusted: bool | None = None
        self._rebuild_lock = threading.Lock()
        self._rebuild_pending: bool = False
        self._last_rebuild_at: float = 0.0
        self._rebuild_cooldown_s: float = 8.0
        self._disabled_tap_counts: dict[str, int] = {}
        self._tap_rebuild_disabled_threshold: int = 3
        diag(
            "hotkey_listener_config",
            hold_key=_safe_name_label(self._hold_name),
            handsfree_keys=_safe_names_label(self._handsfree_names),
            mode_cycle_keys=_safe_names_label(self._mode_cycle_names),
            hold_conflicts_with_handsfree=self._hold_conflicts_with_handsfree,
        )

    def update_keys(
        self,
        hold_key: str,
        handsfree_keys: list[str],
        mode_cycle_keys: list[str] | None = None,
    ) -> None:
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
            self._mode_cycle_names = [
                name for name in (mode_cycle_keys or [])
                if _normalize_key_name(name) is not None
            ]
            self._mode_cycle_pkeys = [
                key_name_to_pynput(name) for name in self._mode_cycle_names
            ]
            self._hold_conflicts_with_handsfree = any(
                _names_overlap(self._hold_name, name) for name in self._handsfree_names
            )
            self._held_keys.clear()
            self._handsfree_combo_active = False
            self._mode_cycle_combo_active = False
            self._handsfree_stop_pending = False
            self._suppressed_handsfree_keyups.clear()
            self._suppressed_mode_cycle_keyups.clear()
            self._mode = "idle"
            self._active_hold_key = None
            self._hold_consumed_until_release = False
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None
        diag(
            "hotkey_listener_update",
            hold_key=_safe_name_label(self._hold_name),
            handsfree_keys=_safe_names_label(self._handsfree_names),
            mode_cycle_keys=_safe_names_label(self._mode_cycle_names),
            hold_conflicts_with_handsfree=self._hold_conflicts_with_handsfree,
        )

    def start(self) -> None:
        """Unpause the listener. Creates the CGEventTap once on first call.

        On macOS 26+ active-mode taps (``kCGEventTapOptionDefault``) require
        confirmed Accessibility trust. When trust is available, a separate raw
        CGEventTap handles modifier+character combos before pynput's key
        translation can drop them. Without trust it falls back to listen-only
        mode as a best-effort diagnostic path.
        """
        created = False
        intercept = None
        if self._listener is None:
            trusted = AXIsProcessTrusted() if AXIsProcessTrusted is not None else True
            self._listener_ax_trusted = bool(trusted)
            # Use active intercept only when accessibility trust is confirmed;
            # otherwise fall back to listen-only so the tap is created at all.
            intercept = self._intercept_darwin_event if trusted else None
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
                darwin_intercept=intercept,
            )
            self._capture_pynput_tap(self._listener)
            self._listener.start()
            created = True
            if _HAS_QUARTZ and self._handsfree_names:
                self._start_raw_combo_tap(active=bool(trusted))
            self._start_watchdog()
        else:
            intercept = getattr(self._listener, "_darwin_intercept", None)
        self._paused = False
        trusted = AXIsProcessTrusted() if AXIsProcessTrusted is not None else None
        diag("hotkey_listener_start", created=created, paused=self._paused, ax_trusted=trusted, has_intercept=intercept is not None, has_raw_tap=self._raw_tap is not None)

    def stop(self) -> None:
        """Pause the listener without destroying the CGEventTap."""
        self._paused = True
        self.reset_state()

    def full_stop(self) -> None:
        """Fully stop and destroy the CGEventTap, then forget the listener.

        Used while the settings window is capturing a new hotkey: pynput 1.8.1
        crashes the whole process (SIGTRAP in keyboard/_darwin.py _handle_message)
        when its global tap processes a caps_lock event during capture. Merely
        pausing (stop()) leaves the tap alive and still feeding events to pynput,
        so we must tear it down. A subsequent start() recreates it.
        """
        self._paused = True
        self._stop_watchdog()
        listener = self._listener
        self._listener = None
        self._listener_ax_trusted = None
        self._disabled_tap_counts.clear()
        if listener is not None:
            try:
                listener.stop()
            except Exception as exc:  # pragma: no cover - defensive teardown
                diag("hotkey_listener_full_stop_error", error_type=exc.__class__.__name__)
        # Also tear down the raw combo tap if present.
        if self._raw_tap is not None:
            try:
                from Quartz import CGEventTapEnable
                CGEventTapEnable(self._raw_tap, False)
            except Exception:
                pass
            self._raw_tap = None
        self._raw_tap_starting = False
        self._raw_combo_held = False
        self.reset_state()
        diag("hotkey_listener_full_stop", had_listener=listener is not None)

    # ── tap watchdog ──────────────────────────────────────────────────────

    def _capture_pynput_tap(self, listener: keyboard.Listener) -> None:
        """Wrap the listener's _create_event_tap so we keep the tap handle.

        pynput's darwin backend stores the CGEventTap only as a local variable
        inside its run loop, so there is no public way to re-enable it after
        macOS disables it. We wrap the bound factory method on this instance to
        stash the returned tap on ``listener._wk_tap`` for the watchdog.
        """
        create = getattr(listener, "_create_event_tap", None)
        if create is None:
            return

        def _capturing_create():
            tap = create()
            try:
                listener._wk_tap = tap
            except Exception:  # pragma: no cover - defensive
                pass
            return tap

        try:
            listener._create_event_tap = _capturing_create
        except Exception:  # pragma: no cover - defensive
            pass

    def _start_watchdog(self) -> None:
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return
        if not _HAS_QUARTZ:
            return
        self._watchdog_generation += 1
        generation = self._watchdog_generation
        self._watchdog_stop.clear()
        t = threading.Thread(
            target=self._watchdog_loop,
            args=(generation,),
            name="TapWatchdog",
            daemon=True,
        )
        self._watchdog_thread = t
        t.start()
        diag("tap_watchdog_start", interval_s=f"{self._watchdog_interval_s:.1f}")

    def _stop_watchdog(self) -> None:
        self._watchdog_generation += 1
        self._watchdog_stop.set()
        self._watchdog_thread = None

    def _watchdog_loop(self, generation: int) -> None:
        while not self._watchdog_stop.wait(self._watchdog_interval_s):
            if generation != self._watchdog_generation:
                break
            try:
                self._reenable_disabled_taps()
            except Exception as exc:  # pragma: no cover - defensive
                diag("tap_watchdog_error", error_type=exc.__class__.__name__)
            if generation != self._watchdog_generation:
                break

    def _reenable_disabled_taps(self) -> None:
        """Re-enable any tap macOS has silently disabled (timeout/sleep/wake)."""
        if self._schedule_rebuild_if_authorization_restored():
            return
        if self._listener_ax_trusted is False:
            # Without Accessibility trust, macOS keeps disabling the taps no
            # matter how often we re-enable or rebuild them. Stay quiet and
            # wait — the trust check above triggers a rebuild once granted.
            return
        listener = self._listener
        pynput_tap = getattr(listener, "_wk_tap", None) if listener is not None else None
        self._reenable_tap_if_disabled("pynput", pynput_tap)
        raw_tap = self._raw_tap
        self._reenable_tap_if_disabled("raw_combo", raw_tap)

    def _schedule_rebuild_if_authorization_restored(self) -> bool:
        if AXIsProcessTrusted is None or self._listener_ax_trusted is None:
            return False
        trusted = bool(AXIsProcessTrusted())
        if not trusted and self._listener_ax_trusted:
            self._listener_ax_trusted = False
            diag("tap_watchdog_trust_lost")
            return False
        if trusted and not self._listener_ax_trusted:
            self._schedule_tap_rebuild("authorization_restored")
            return True
        return False

    def _reenable_tap_if_disabled(self, tap_name: str, tap: object | None) -> None:
        if tap is None:
            self._disabled_tap_counts.pop(tap_name, None)
            return
        try:
            enabled = bool(CGEventTapIsEnabled(tap))
        except Exception as exc:
            diag("tap_watchdog_check_failed", tap=tap_name, error_type=exc.__class__.__name__)
            self._record_disabled_tap(tap_name)
            return
        if enabled:
            self._disabled_tap_counts.pop(tap_name, None)
            return

        try:
            CGEventTapEnable(tap, True)
            diag("tap_watchdog_reenabled", tap=tap_name)
        except Exception as exc:
            diag("tap_watchdog_reenable_failed", tap=tap_name, error_type=exc.__class__.__name__)
        self._record_disabled_tap(tap_name)

    def _record_disabled_tap(self, tap_name: str) -> None:
        count = self._disabled_tap_counts.get(tap_name, 0) + 1
        self._disabled_tap_counts[tap_name] = count
        if count >= self._tap_rebuild_disabled_threshold:
            self._disabled_tap_counts[tap_name] = 0
            self._schedule_tap_rebuild(f"{tap_name}_repeatedly_disabled")

    def _schedule_tap_rebuild(self, reason: str) -> None:
        with self._rebuild_lock:
            if self._rebuild_pending:
                diag("tap_rebuild_ignored", reason=reason, pending=True)
                return
            since_last = time.monotonic() - self._last_rebuild_at
            if self._last_rebuild_at and since_last < self._rebuild_cooldown_s:
                diag("tap_rebuild_ignored", reason=reason, cooldown_s=round(since_last, 2))
                return
            self._rebuild_pending = True
            self._last_rebuild_at = time.monotonic()
        t = threading.Thread(
            target=self._rebuild_event_taps,
            args=(reason,),
            name="TapRebuild",
            daemon=True,
        )
        t.start()
        diag("tap_rebuild_scheduled", reason=reason)

    def _rebuild_event_taps(self, reason: str) -> None:
        was_paused = self._paused
        diag("tap_rebuild_start", reason=reason, paused=was_paused)
        try:
            self.full_stop()
            if not was_paused:
                self.start()
                restarted = True
            else:
                restarted = False
            diag("tap_rebuild_end", reason=reason, restarted=restarted)
        except Exception as exc:  # pragma: no cover - defensive
            diag("tap_rebuild_error", reason=reason, error_type=exc.__class__.__name__)
        finally:
            with self._rebuild_lock:
                self._rebuild_pending = False

    # ── raw combo tap ─────────────────────────────────────────────────────

    def _start_raw_combo_tap(self, *, active: bool) -> None:
        """Create a CGEventTap that detects modifier+char combos.

        This tap runs alongside pynput's listener and detects combos by
        checking raw CGEvent modifier flags + virtual keycodes, bypassing
        pynput's ``_event_to_key`` which fails for characters like ``\\``
        when a modifier (e.g. cmd) is held.

        When Accessibility trust is available the tap runs in active mode so
        macOS delivers the same raw stream that pynput's translation layer may
        drop, and so the combo's character key can be suppressed. Without trust
        it falls back to listen-only mode as a best-effort diagnostic path.

        The tap runs on its own daemon thread with its own CFRunLoop, since
        the main thread's run loop is occupied by the AppKit event loop.
        """
        if self._raw_tap is not None or self._raw_tap_starting:
            return
        try:
            mod_flags, char_vk = _parse_combo_raw(self._handsfree_names)
        except Exception:
            diag("raw_combo_tap_parse_failed")
            return

        if char_vk is None:
            diag("raw_combo_tap_no_char_vk")
            return

        event_mask = (1 << kCGEventKeyDown) | (1 << kCGEventKeyUp) | (1 << kCGEventFlagsChanged)
        tap_option = kCGEventTapOptionDefault if active else kCGEventTapOptionListenOnly
        self._raw_tap_starting = True

        def _tap_callback(_proxy, event_type, event, _refcon):
            if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
                if self._raw_tap is not None:
                    try:
                        CGEventTapEnable(self._raw_tap, True)
                        diag("raw_combo_tap_reenabled", reason=f"{event_type:#x}")
                    except Exception as exc:
                        diag("raw_combo_tap_reenable_failed", error_type=exc.__class__.__name__)
                return event
            if self._paused:
                return event
            try:
                if event_type == kCGEventKeyDown:
                    vk = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
                    flags = CGEventGetFlags(event)
                    if vk == char_vk and (flags & mod_flags) == mod_flags:
                        if not self._raw_combo_held:
                            self._raw_combo_held = True
                            diag("raw_combo_detected", vk=vk, flags=f"{flags:#x}")
                            self._handle_raw_combo_press()
                        if active:
                            return None
                elif event_type == kCGEventKeyUp:
                    vk = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
                    if vk == char_vk:
                        was_held = self._raw_combo_held
                        self._raw_combo_held = False
                        if was_held:
                            self._handle_raw_combo_release()
                            if active:
                                return None
                elif event_type == kCGEventFlagsChanged:
                    # Modifier released — if combo was active and modifier
                    # is no longer held, mark combo released.
                    flags = CGEventGetFlags(event)
                    if self._raw_combo_held and (flags & mod_flags) != mod_flags:
                        self._raw_combo_held = False
                        self._handle_raw_combo_release()
            except Exception as exc:
                diag("raw_combo_tap_error", error_type=exc.__class__.__name__)
            return event

        def _tap_thread():
            tap = CGEventTapCreate(
                kCGSessionEventTap,
                kCGHeadInsertEventTap,
                tap_option,
                event_mask,
                _tap_callback,
                None,
            )
            if tap is None:
                self._raw_tap_starting = False
                diag("raw_combo_tap_create_failed", active=active)
                return

            loop_source = CFMachPortCreateRunLoopSource(None, tap, 0)
            loop = CFRunLoopGetCurrent()
            CFRunLoopAddSource(loop, loop_source, kCFRunLoopDefaultMode)
            CGEventTapEnable(tap, True)
            self._raw_tap = tap
            self._raw_tap_starting = False
            diag("raw_combo_tap_started", active=active, mod_flags=f"{mod_flags:#x}", char_vk=char_vk)

            # Run the loop — this blocks until the loop is stopped.
            while self._raw_tap is tap:
                result = CFRunLoopRunInMode(kCFRunLoopDefaultMode, 5.0, False)
                try:
                    if result != kCFRunLoopRunTimedOut:
                        break
                except AttributeError:
                    break

        t = threading.Thread(target=_tap_thread, name="RawComboTap", daemon=True)
        t.start()

    def _handle_raw_combo_press(self) -> None:
        """Handle a combo press detected by the raw CGEventTap.

        Mirrors the combo handling in _on_press but works independently of
        pynput's key resolution.
        """
        should_start_handsfree = False
        with self._lock:
            combo_active = self._handsfree_combo_active
            stop_pending = self._handsfree_stop_pending
            if stop_pending:
                diag("raw_combo_match", action="ignored_stop_pending", mode=self._mode)
                return
            if not combo_active:
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
                    "raw_combo_match",
                    action="start" if should_start_handsfree else "stop_pending",
                    mode=mode,
                    combo=_safe_names_label(self._handsfree_names),
                )
        if should_start_handsfree:
            print("[whisperkey] Hands-free ON — recording...")
            self._on_record_start()

    def _handle_raw_combo_release(self) -> None:
        """Finish a pending hands-free stop after the raw combo is released."""
        should_stop_handsfree = False
        with self._lock:
            self._handsfree_combo_active = False
            if self._handsfree_stop_pending and self._mode == "handsfree":
                self._handsfree_stop_pending = False
                self._mode = "idle"
                should_stop_handsfree = True
        if should_stop_handsfree:
            diag("raw_combo_stop", combo=_safe_names_label(self._handsfree_names))
            self._on_record_stop_transcribe()

    def reset_state(self) -> None:
        """Clear key state after an ignored/cancelled recording transition."""
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None
        with self._lock:
            self._held_keys.clear()
            self._handsfree_combo_active = False
            self._mode_cycle_combo_active = False
            self._handsfree_stop_pending = False
            self._mode = "idle"
            self._active_hold_key = None
            self._hold_consumed_until_release = False

    # ── internal ──────────────────────────────────────────────────────────────

    def _intercept_darwin_event(self, event_type: int, event: object) -> object | None:
        """Suppress only the character event that completes the hands-free combo."""
        if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            tap = getattr(self._listener, "_wk_tap", None)
            if tap is not None:
                try:
                    CGEventTapEnable(tap, True)
                    diag("pynput_tap_reenabled", reason=f"{event_type:#x}")
                except Exception as exc:
                    diag("pynput_tap_reenable_failed", error_type=exc.__class__.__name__)
            return event
        if event_type not in (kCGEventKeyDown, kCGEventKeyUp):
            return event

        # DIAGNOSTIC: log raw vk for every keydown/keyup to trace cmd+backslash
        try:
            from Quartz import CGEventGetIntegerValueField, kCGKeyboardEventKeycode, CGEventGetFlags
            vk = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            flags = CGEventGetFlags(event)
            phase = "down" if event_type == kCGEventKeyDown else "up"
            diag("intercept_raw", phase=phase, vk=vk, flags=f"{flags:#x}")
        except Exception:
            pass

        key = self._key_from_darwin_event(event)
        if key is None:
            return event

        if event_type == kCGEventKeyDown:
            suppressed_name = self._handsfree_character_to_suppress_on_press(key)
            combo_name = "handsfree"
            combo_keys = self._handsfree_names
            if suppressed_name is None:
                suppressed_name = self._mode_cycle_character_to_suppress_on_press(key)
                combo_name = "mode_cycle"
                combo_keys = self._mode_cycle_names
            if suppressed_name is None:
                return event

            with self._lock:
                if combo_name == "handsfree":
                    self._suppressed_handsfree_keyups.add(suppressed_name)
                else:
                    self._suppressed_mode_cycle_keyups.add(suppressed_name)
            diag(
                "hotkey_event_suppressed",
                key=_safe_name_label(suppressed_name),
                phase="down",
                combo=_safe_names_label(combo_keys),
                combo_type=combo_name,
            )
            return None

        suppressed_name = self._handsfree_character_to_suppress_on_release(key)
        combo_name = "handsfree"
        combo_keys = self._handsfree_names
        if suppressed_name is None:
            suppressed_name = self._mode_cycle_character_to_suppress_on_release(key)
            combo_name = "mode_cycle"
            combo_keys = self._mode_cycle_names
        if suppressed_name is None:
            return event

        diag(
            "hotkey_event_suppressed",
            key=_safe_name_label(suppressed_name),
            phase="up",
            combo=_safe_names_label(combo_keys),
            combo_type=combo_name,
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

    def _mode_cycle_character_name_for_key(
        self,
        key: keyboard.Key | keyboard.KeyCode,
    ) -> str | None:
        for name in self._mode_cycle_names:
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

    def _mode_cycle_character_to_suppress_on_press(
        self,
        key: keyboard.Key | keyboard.KeyCode,
    ) -> str | None:
        with self._lock:
            if self._paused:
                return None
            mode_cycle_names = list(self._mode_cycle_names)
            held = set(self._held_keys)

        name = self._mode_cycle_character_name_for_key(key)
        if name is None:
            return None
        if not _combo_pressed(mode_cycle_names, held):
            return None
        return name

    def _mode_cycle_character_to_suppress_on_release(
        self,
        key: keyboard.Key | keyboard.KeyCode,
    ) -> str | None:
        name = self._mode_cycle_character_name_for_key(key)
        if name is None:
            return None

        with self._lock:
            if name not in self._suppressed_mode_cycle_keyups:
                return None
            self._suppressed_mode_cycle_keyups.remove(name)
        return name

    def _prune_stale_held_keys_locked(self) -> None:
        """Drop held-key entries older than HELD_KEY_TTL_S. Caller must hold self._lock."""
        now = time.monotonic()
        stale = [k for k, pressed_at in self._held_keys.items() if now - pressed_at > HELD_KEY_TTL_S]
        for k in stale:
            del self._held_keys[k]
            diag("hotkey_stale_key_pruned", key=_safe_key_label(k))

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if self._paused or key is None:
            if key is None and not self._paused:
                # DIAGNOSTIC (issue 1): pynput delivered a keydown it could not
                # resolve to a KeyCode. If this fires when pressing the combo's
                # character key with a modifier held, the combo can never
                # complete because _on_press has no key to add to held_keys.
                diag("hotkey_press_none")
            elif key is not None:
                diag("hotkey_press_ignored", key=_safe_key_label(key), reason="paused")
            return

        should_start_handsfree = False
        with self._lock:
            self._prune_stale_held_keys_locked()
            self._held_keys[key] = time.monotonic()
            mode = self._mode
            held = set(self._held_keys)
            combo_active = self._handsfree_combo_active
            mode_cycle_active = self._mode_cycle_combo_active
            stop_pending = self._handsfree_stop_pending
            hold_match = _key_matches_name(key, self._hold_name)

        # Check hands-free combo (all handsfree keys held simultaneously)
        combo_pressed = _combo_pressed(self._handsfree_names, held)
        mode_cycle_pressed = _combo_pressed(self._mode_cycle_names, held)
        if _DEBUG_KEYS:
            diag(
                "hotkey_press",
                key=_safe_key_label(key),
                vk=getattr(key, "vk", None),
                char=getattr(key, "char", None),
                mode=mode,
                hold_match=hold_match,
                combo_complete=combo_pressed,
                mode_cycle_complete=mode_cycle_pressed,
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

        if mode_cycle_pressed:
            should_cycle = False
            cancelled_timer: threading.Timer | None = None
            with self._lock:
                if self._mode == "idle" and not mode_cycle_active:
                    self._mode_cycle_combo_active = True
                    should_cycle = True
                    if self._active_hold_key is not None:
                        self._hold_consumed_until_release = True
                        cancelled_timer = self._hold_timer
                        self._hold_timer = None
            if cancelled_timer is not None:
                cancelled_timer.cancel()
                diag("hotkey_hold_timer_cancel", reason="mode_cycle_consumed")
            if should_cycle:
                diag("hotkey_mode_cycle_match", combo=_safe_names_label(self._mode_cycle_names))
                self._on_mode_cycle()
            return

        if self._handsfree_names and _DEBUG_KEYS:
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
            self._prune_stale_held_keys_locked()
            self._held_keys.pop(key, None)
            release_vk = getattr(key, "vk", None)
            if release_vk is not None:
                for held_key in list(self._held_keys):
                    if getattr(held_key, "vk", None) == release_vk:
                        self._held_keys.pop(held_key, None)
            mode = self._mode
            held = set(self._held_keys)
            hold_match = _key_matches_name(key, self._hold_name)
            should_handle_hold_release = (
                self._active_hold_key is not None
                and key == self._active_hold_key
            )

            combo_pressed = _combo_pressed(self._handsfree_names, held)
            mode_cycle_pressed = _combo_pressed(self._mode_cycle_names, held)
            if self._handsfree_combo_active and not combo_pressed:
                self._handsfree_combo_active = False
            if self._mode_cycle_combo_active and not mode_cycle_pressed:
                self._mode_cycle_combo_active = False

            if self._handsfree_stop_pending:
                any_handsfree_held = _any_configured_key_held(self._handsfree_names, held)
                if not any_handsfree_held and self._mode == "handsfree":
                    self._handsfree_stop_pending = False
                    self._mode = "idle"
                    should_stop_handsfree = True
        if _DEBUG_KEYS:
            diag(
                "hotkey_release",
                key=_safe_key_label(key),
                mode=mode,
                hold_match=hold_match,
                active_hold_release=should_handle_hold_release,
                combo_complete=combo_pressed,
                mode_cycle_complete=mode_cycle_pressed,
                held_count=len(held),
            )

        if should_handle_hold_release:
            # Cancel pending timer (accidental tap — released before MIN_HOLD_S)
            with self._lock:
                timer = self._hold_timer
                self._hold_timer = None
                self._active_hold_key = None
                was_consumed = self._hold_consumed_until_release
                self._hold_consumed_until_release = False

            if timer is not None:
                timer.cancel()
                diag("hotkey_hold_timer_cancel", key=_safe_key_label(key), reason="released")

            # Hold was consumed by a combo (e.g. mode_cycle) — skip recording paths
            if was_consumed:
                diag("hotkey_hold_release_after_combo", key=_safe_key_label(key))
                return

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
            if self._hold_consumed_until_release:
                diag("hotkey_hold_start_ignored", reason="consumed_by_combo")
                self._hold_timer = None
                return
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
