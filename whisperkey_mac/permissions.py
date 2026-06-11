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

import re
import subprocess
import threading
from pathlib import Path

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


# ── Stale TCC grant recovery ──────────────────────────────────────────────────
#
# macOS TCC stores a code-signing requirement with each grant. When the app's
# signing identity changes (ad-hoc → Apple Development, certificate renewal),
# old grants silently stop matching: System Settings shows the toggle ON while
# AXIsProcessTrusted() stays False. The fix is to delete the stale records so
# fresh ones are created against the new signature.

BUNDLE_ID = "com.phatpo.whisperkey"
TCC_RESET_SERVICES = ["Accessibility", "ListenEvent", "Microphone", "AppleEvents"]
SIGNING_STAMP_PATH = Path.home() / "Library" / "Application Support" / "WhisperKey" / "signing-stamp.txt"


def reset_tcc_permissions(bundle_id: str = BUNDLE_ID) -> bool:
    """Delete this app's own TCC records so macOS re-registers the grants.

    Only touches WhisperKey's entries; the user re-grants afterwards. Safe to
    run when no records exist (no-op).
    """
    all_ok = True
    for service in TCC_RESET_SERVICES:
        try:
            result = subprocess.run(
                ["tccutil", "reset", service, bundle_id],
                capture_output=True,
                text=True,
                check=False,
                timeout=10.0,
            )
            ok = result.returncode == 0
        except Exception:
            ok = False
        if not ok:
            all_ok = False
        diag("tcc_reset", service=service, ok=ok)
    return all_ok


def current_signature_stamp(bundle_path: str) -> str | None:
    """Stable identifier of the bundle's signing identity.

    Returns "team:<id>" for certificate signatures (stable across rebuilds),
    "adhoc" for ad-hoc signatures, or None when unreadable.
    """
    try:
        result = subprocess.run(
            ["codesign", "-dvv", bundle_path],
            capture_output=True,
            text=True,
            check=False,
            timeout=10.0,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    info = result.stderr
    if "Signature=adhoc" in info:
        return "adhoc"
    team_match = re.search(r"TeamIdentifier=(\S+)", info)
    if team_match and team_match.group(1) != "not":  # "TeamIdentifier=not set"
        return f"team:{team_match.group(1)}"
    return "signed:unknown-team"


def auto_reset_stale_grants(
    bundle_path: str,
    stamp_path: Path = SIGNING_STAMP_PATH,
) -> bool:
    """On signature change with missing permissions, clear stale TCC records.

    Called once at packaged-app startup. The stamp file remembers which
    signing identity last ran; a mismatch (or missing stamp) combined with
    denied permissions means the existing TCC records are useless — clearing
    them lets the onboarding flow create fresh, matching grants. Partial
    grants under the SAME identity are never touched.
    """
    current = current_signature_stamp(bundle_path)
    if current is None:
        return False

    previous: str | None = None
    try:
        previous = stamp_path.read_text(encoding="utf-8").strip() or None
    except OSError:
        pass

    if previous == current:
        return False

    acted = False
    if not required_granted():
        diag("tcc_auto_reset", previous=previous or "none", current=current)
        reset_tcc_permissions()
        acted = True

    try:
        stamp_path.parent.mkdir(parents=True, exist_ok=True)
        stamp_path.write_text(current + "\n", encoding="utf-8")
    except OSError:
        pass
    return acted
