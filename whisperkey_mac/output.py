from __future__ import annotations

import subprocess
import time

import pyperclip
from pynput.keyboard import Controller, Key

from whisperkey_mac.config import AppConfig
from whisperkey_mac.diagnostics import diag


class TextOutput:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._kb = Controller()

    def inject(self, text: str, target_bundle_id: str | None = None) -> str:
        """
        Inject text into the focused app and keep it in clipboard.
        Returns: "inserted" | "applescript" | "clipboard" | "empty"

        Preferred path is AX direct insertion to avoid sending synthetic Cmd+V
        events through System Events while the global hotkey listener is active.
        AppleScript paste remains a fallback for controls where AX insertion is unavailable.
        """
        normalized = text.strip()
        if not normalized:
            diag("output_inject_empty")
            return "empty"

        # Always copy to clipboard first — text is always available via Cmd+V
        diag("output_clipboard_copy_start")
        pyperclip.copy(normalized)
        diag("output_clipboard_copy_end")

        try:
            diag("output_ax_insert_start")
            if self._insert_via_ax(normalized):
                diag("output_ax_insert_end", path="inserted")
                return "inserted"
            diag("output_ax_insert_end", path="unavailable")
        except Exception as exc:
            diag("output_ax_insert_error", error_type=type(exc).__name__)

        print("[whisperkey] AX insert unavailable; falling back to AppleScript paste.")

        try:
            diag("output_applescript_start", target_bundle_id=target_bundle_id)
            self._paste_clipboard(target_bundle_id)
            diag("output_applescript_end", path="applescript", target_bundle_id=target_bundle_id)
            return "applescript"
        except Exception as exc:
            diag("output_applescript_error", error_type=type(exc).__name__, target_bundle_id=target_bundle_id)
            if target_bundle_id:
                try:
                    diag("output_applescript_retry_start")
                    self._paste_clipboard(None)
                    diag("output_applescript_retry_end", path="applescript")
                    return "applescript"
                except Exception as retry_exc:
                    diag("output_applescript_retry_error", error_type=type(retry_exc).__name__)

        # All active injection paths failed but text is still in clipboard — user can Cmd+V manually
        diag("output_inject_clipboard_only")
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
        diag("applescript_paste_prepare", target_bundle_id=target_bundle_id)
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
        diag("applescript_paste_complete", target_bundle_id=target_bundle_id)

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
