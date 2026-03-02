from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pynput import keyboard

# Minimum hold duration before recording starts (avoids accidental taps)
MIN_HOLD_S = 0.15

# Map config string names → pynput Key objects
_KEY_MAP: dict[str, keyboard.Key] = {
    "alt_r": keyboard.Key.alt_r,
    "alt": keyboard.Key.alt,
    "cmd_r": keyboard.Key.cmd_r,
    "cmd": keyboard.Key.cmd,
    "ctrl_r": keyboard.Key.ctrl_r,
    "ctrl": keyboard.Key.ctrl,
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


def key_name_to_pynput(name: str) -> keyboard.Key | None:
    return _KEY_MAP.get(name)


def pynput_key_to_name(key: keyboard.Key) -> str | None:
    for name, k in _KEY_MAP.items():
        if k == key:
            return name
    return None


class HotkeyListener:
    """
    Hold-to-talk + hands-free recording listener.

    HOLD MODE (default):
        Press & hold hold_key (>150ms) → start recording
        Release hold_key               → stop + transcribe

    HANDS-FREE MODE:
        Both handsfree_keys held simultaneously → toggle recording on/off
        Press the combo again → stop + transcribe
    """

    def __init__(
        self,
        hold_key: str,
        handsfree_keys: list[str],
        on_record_start: Callable[[], None],
        on_record_stop_transcribe: Callable[[], None],
        on_enter: Callable[[], None],
    ) -> None:
        self._hold_pkey = key_name_to_pynput(hold_key) or keyboard.Key.alt_r
        self._handsfree_pkeys: list[keyboard.Key] = [
            k for name in handsfree_keys
            if (k := key_name_to_pynput(name)) is not None
        ]

        self._on_record_start = on_record_start
        self._on_record_stop_transcribe = on_record_stop_transcribe

        self._lock = threading.Lock()
        self._held_keys: set = set()
        # "idle" | "hold_recording" | "handsfree"
        self._mode = "idle"
        self._hold_press_time: float = 0.0
        self._hold_timer: threading.Timer | None = None

        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

    def stop(self) -> None:
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    # ── internal ──────────────────────────────────────────────────────────────

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key is None:
            return

        with self._lock:
            self._held_keys.add(key)
            mode = self._mode
            held = set(self._held_keys)

        # Check hands-free combo (all handsfree keys held simultaneously)
        if (
            len(self._handsfree_pkeys) >= 2
            and all(k in held for k in self._handsfree_pkeys)
        ):
            with self._lock:
                mode = self._mode
            if mode == "idle":
                # Cancel any pending hold timer
                with self._lock:
                    if self._hold_timer:
                        self._hold_timer.cancel()
                        self._hold_timer = None
                    self._mode = "handsfree"
                print("[whisperkey] Hands-free ON — recording...")
                self._on_record_start()
            elif mode == "handsfree":
                with self._lock:
                    self._mode = "idle"
                self._on_record_stop_transcribe()
            return

        # Hold-key press logic
        if key == self._hold_pkey:
            with self._lock:
                mode = self._mode
                if mode == "idle":
                    self._hold_press_time = time.monotonic()
                    # Schedule recording start after MIN_HOLD_S
                    timer = threading.Timer(MIN_HOLD_S, self._start_hold_recording)
                    self._hold_timer = timer
            if mode == "idle":
                timer.start()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key is None:
            return

        with self._lock:
            self._held_keys.discard(key)
            mode = self._mode

        if key == self._hold_pkey:
            # Cancel pending timer (accidental tap — released before MIN_HOLD_S)
            with self._lock:
                timer = self._hold_timer
                self._hold_timer = None

            if timer is not None:
                timer.cancel()

            # If already in hold_recording, stop and transcribe
            if mode == "hold_recording":
                with self._lock:
                    self._mode = "idle"
                self._on_record_stop_transcribe()

    def _start_hold_recording(self) -> None:
        with self._lock:
            if self._mode != "idle":
                return
            self._mode = "hold_recording"
            self._hold_timer = None
        print("[whisperkey] Recording...")
        self._on_record_start()
