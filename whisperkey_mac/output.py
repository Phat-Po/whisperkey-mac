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

    def inject(self, text: str, target_bundle_id: str | None = None) -> str:
        """
        Inject text into the focused app and keep it in clipboard.
        Returns: "inserted" | "applescript" | "clipboard" | "empty"

        Preferred path is targeted AppleScript paste because some chat inputs only
        react reliably to a real paste event. AX direct insertion remains a fallback
        for controls where scripted paste is unavailable.
        """
        normalized = text.strip()
        if not normalized:
            return "empty"

        # Always copy to clipboard first — text is always available via Cmd+V
        pyperclip.copy(normalized)

        try:
            self._paste_clipboard(target_bundle_id)
            return "applescript"
        except Exception:
            pass

        try:
            if self._insert_via_ax(normalized):
                return "inserted"
        except Exception:
            pass

        # All active injection paths failed but text is still in clipboard — user can Cmd+V manually
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

    def _paste_clipboard(self, target_bundle_id: str | None = None) -> None:
        # AppleScript paste proved more reliable in earlier builds than posting
        # low-level key events via pynput when overlays and hands-free timing are involved.
        script = ["osascript"]
        if target_bundle_id:
            escaped = target_bundle_id.replace('"', '\\"')
            script.extend(["-e", f'tell application id "{escaped}" to activate'])
        script.extend([
            "-e",
            'tell application "System Events" to keystroke "v" using command down',
        ])
        subprocess.run(
            script,
            check=True,
            timeout=2.0,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.08)  # let the re-activated target app process the paste

    def _insert_via_ax(self, text: str) -> bool:
        from whisperkey_mac.ax_detect import insert_text_at_cursor

        return insert_text_at_cursor(text)

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
