"""System permission checks and requests for WhisperKey.

WhisperKey needs three macOS permissions:
- Accessibility (AX): active CGEventTaps + AX text insertion + AppleScript paste.
- Input Monitoring: listen-only CGEventTaps (keyboard events reach the app at all).
- Microphone: audio recording (macOS prompts automatically on first recording
  thanks to NSMicrophoneUsageDescription; we only pre-trigger the prompt here).

All request_* functions trigger the native macOS permission prompt where the OS
supports it; check_* functions are passive and never prompt.
"""
from __future__ import annotations

import subprocess
import threading

from whisperkey_mac.diagnostics import diag

try:
    from ApplicationServices import (
        AXIsProcessTrusted,
        AXIsProcessTrustedWithOptions,
        kAXTrustedCheckOptionPrompt,
    )
    _HAS_AX = True
except Exception:  # pragma: no cover - non-macOS
    _HAS_AX = False

try:
    from Quartz import CGPreflightListenEventAccess, CGRequestListenEventAccess
    _HAS_LISTEN_ACCESS = True
except Exception:  # pragma: no cover - non-macOS / older macOS
    _HAS_LISTEN_ACCESS = False


SETTINGS_URLS = {
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "input_monitoring": "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
    "microphone": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
}


def check_accessibility() -> bool:
    if not _HAS_AX:
        return False
    try:
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def request_accessibility() -> bool:
    """Trigger the system Accessibility prompt (adds the app to the list)."""
    if not _HAS_AX:
        return False
    try:
        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))
    except Exception:
        diag("perm_request_accessibility_failed")
        return False


def check_input_monitoring() -> bool | None:
    """Return True/False, or None when the preflight API is unavailable."""
    if not _HAS_LISTEN_ACCESS:
        return None
    try:
        return bool(CGPreflightListenEventAccess())
    except Exception:
        return None


def request_input_monitoring() -> bool:
    """Trigger the system Input Monitoring prompt (adds the app to the list)."""
    if not _HAS_LISTEN_ACCESS:
        return False
    try:
        return bool(CGRequestListenEventAccess())
    except Exception:
        diag("perm_request_input_monitoring_failed")
        return False


def request_microphone_async() -> None:
    """Trigger the system Microphone prompt by briefly opening an input stream.

    Runs on a daemon thread: opening the stream blocks until CoreAudio is ready
    and must never stall the UI. The OS shows its own prompt; the stream itself
    records nothing.
    """
    def _worker() -> None:
        try:
            import sounddevice as sd

            with sd.InputStream(channels=1, samplerate=16000):
                import time

                time.sleep(0.2)
            diag("perm_microphone_probe_ok")
        except Exception as exc:
            diag("perm_microphone_probe_failed", error_type=type(exc).__name__)

    threading.Thread(target=_worker, name="WhisperKeyMicProbe", daemon=True).start()


def open_settings_pane(pane: str) -> None:
    url = SETTINGS_URLS.get(pane)
    if not url:
        return
    subprocess.run(["open", url], check=False)


def required_granted() -> bool:
    """True when the permissions needed for hotkeys to work are granted.

    Input Monitoring preflight may be unavailable (None) on older systems; in
    that case Accessibility alone decides, matching the previous behavior.
    """
    if not check_accessibility():
        return False
    input_ok = check_input_monitoring()
    return input_ok is not False
