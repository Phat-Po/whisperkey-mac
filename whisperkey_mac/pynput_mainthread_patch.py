"""Make pynput's macOS keyboard-layout lookup main-thread-safe.

Background
----------
On macOS 26 (Tahoe) the Text Input Source / Text Services Manager (TIS/TSM)
APIs that pynput calls inside ``pynput._util.darwin.keycode_context`` now assert
that they run on the main dispatch queue (``dispatch_assert_queue``). pynput's
keyboard *Listener* calls ``keycode_context`` from its own background thread the
moment it starts (``pynput.keyboard._darwin.Listener._run``), and the
*Controller* calls it (via ``get_unicode_to_keycode_map``) from whatever thread
constructs it.

While the Mac is idle/asleep macOS invalidates the TSM input-source cache. The
next time our watchdog rebuilds the event taps it constructs a fresh
``keyboard.Listener`` on a background thread; its ``_run`` calls
``keycode_context`` which now has to *rebuild* the input-source list
(``islGetInputSourceListWithAdditions``) off the main thread, trips the
assertion, and kills the whole process with ``SIGTRAP``. Symptom: after the app
sits unused for a while, recording can no longer be stopped and the menu-bar
icon stops responding because the process has died.

Fix
---
Read the keyboard layout exactly once, on the main thread, at startup and cache
it. Then replace ``keycode_context`` with a context manager that always yields
the cached value, so pynput never touches TIS off the main thread again.

This is safe for WhisperKey because the keyboard layout is read only to build a
char->keycode map. WhisperKey injects text via the clipboard/AppleScript/AX
path and only uses the pynput Controller to tap ``Enter`` (no char mapping), and
the Listener resolves keys with ``CGEventKeyboardGetUnicodeString`` (not the
cached layout). A layout switched after launch therefore has no practical
effect on hotkey handling.
"""

from __future__ import annotations

import contextlib
import sys

from whisperkey_mac.diagnostics import diag

_applied = False


def apply_pynput_mainthread_patch() -> bool:
    """Patch pynput so it never calls macOS TIS APIs off the main thread.

    Must be called once, on the main thread, before any pynput keyboard
    ``Listener`` or ``Controller`` is created. Idempotent. Returns ``True`` if
    the patch is in effect, ``False`` if it could not be applied (non-darwin or
    pynput import/warm-up failure — in which case the original behavior stands).
    """
    global _applied
    if _applied:
        return True
    if sys.platform != "darwin":
        _applied = True
        return False

    try:
        from pynput._util import darwin as _pd
        from pynput.keyboard import _darwin as _kd
    except Exception as exc:  # pragma: no cover - pynput is always present on darwin
        diag("pynput_patch_import_failed", error_type=exc.__class__.__name__)
        return False

    # Capture the layout context once, on the current (main) thread. This is the
    # only TIS read we ever perform; everything after this uses the cached value.
    try:
        with _pd.keycode_context() as ctx:
            cached = ctx
    except Exception as exc:  # pragma: no cover - defensive
        diag("pynput_patch_warmup_failed", error_type=exc.__class__.__name__)
        return False

    @contextlib.contextmanager
    def _cached_keycode_context():
        yield cached

    # pynput resolves ``keycode_context`` as a module global at call time, in two
    # namespaces: ``_util.darwin`` (used by get_unicode_to_keycode_map ->
    # Controller) and ``keyboard._darwin`` (imported there, used by
    # Listener._run). Patch both so no code path can reach the real TIS call.
    _pd.keycode_context = _cached_keycode_context
    _kd.keycode_context = _cached_keycode_context

    _applied = True
    diag(
        "pynput_patch_applied",
        keyboard_type=cached[0],
        has_layout=cached[1] is not None,
    )
    return True
