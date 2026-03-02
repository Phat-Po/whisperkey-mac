from __future__ import annotations

import subprocess
import time

import pyperclip
from pynput.keyboard import Controller, Key

from whisperkey_mac.config import AppConfig


class TextOutput:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._kb = Controller()

    def inject(self, text: str) -> str:
        """
        Inject text via clipboard paste (bypasses IME) and keep it in clipboard.
        Returns: "pasted" | "clipboard" | "empty"

        Using clipboard+paste instead of keyboard.type() because:
        - Cmd+V inserts raw Unicode, bypassing the active input method (pinyin, etc.)
        - Text stays in clipboard so user can manually paste with Cmd+V anytime
        """
        normalized = text.strip()
        if not normalized:
            return "empty"

        # Always copy to clipboard first — text is always available via Cmd+V
        pyperclip.copy(normalized)

        # Auto-paste via AppleScript Cmd+V (bypasses IME)
        try:
            self._paste_clipboard()
            return "pasted"
        except Exception:
            # Paste failed but text is still in clipboard — user can Cmd+V manually
            return "clipboard"

    def send_enter(self) -> None:
        mode = self._config.enter_mode.strip().lower()
        if mode == "none":
            return
        if mode == "enter":
            self._tap(Key.enter)
        elif mode == "shift_enter":
            self._tap_with_modifier(Key.shift, Key.enter)
        elif mode == "cmd_enter":
            self._tap_with_modifier(Key.cmd, Key.enter)

    def _paste_clipboard(self) -> None:
        # Use AppleScript to send Cmd+V — more reliable than pynput on macOS
        subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
            check=True,
            timeout=2.0,
        )
        time.sleep(0.05)  # give app time to paste

    def _tap(self, key: Key) -> None:
        self._kb.press(key)
        time.sleep(0.012)
        self._kb.release(key)

    def _tap_with_modifier(self, modifier: Key, key: Key) -> None:
        self._kb.press(modifier)
        self._kb.press(key)
        time.sleep(0.012)
        self._kb.release(key)
        self._kb.release(modifier)
