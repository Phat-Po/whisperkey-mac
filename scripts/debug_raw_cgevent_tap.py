#!/usr/bin/env python3
"""Standalone CGEventTap diagnostic for WhisperKey hands-free hotkeys.

Run from the project root with:

    .venv/bin/python scripts/debug_raw_cgevent_tap.py

Then press the target combo, for example cmd+backslash. The script logs raw
event type, virtual keycode, and flags without going through pynput.
"""

from __future__ import annotations

import signal
import sys
import time

from ApplicationServices import AXIsProcessTrusted
from Quartz import (
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventTapCreate,
    CGEventTapEnable,
    kCFRunLoopDefaultMode,
    kCGEventFlagsChanged,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGEventTapOptionDefault,
    kCGHeadInsertEventTap,
    kCGKeyboardEventKeycode,
    kCGSessionEventTap,
)


EVENT_NAMES = {
    kCGEventKeyDown: "down",
    kCGEventKeyUp: "up",
    kCGEventFlagsChanged: "flags",
}


def callback(_proxy, event_type, event, _refcon):
    vk = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
    flags = CGEventGetFlags(event)
    name = EVENT_NAMES.get(event_type, str(event_type))
    print(f"{time.time():.3f} type={name:<5} vk={vk:<3} flags={flags:#010x}", flush=True)
    return event


def main() -> int:
    print(f"AXIsProcessTrusted={AXIsProcessTrusted()}", flush=True)
    event_mask = (1 << kCGEventKeyDown) | (1 << kCGEventKeyUp) | (1 << kCGEventFlagsChanged)
    tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionDefault,
        event_mask,
        callback,
        None,
    )
    if tap is None:
        print("CGEventTapCreate returned NULL. Accessibility trust is required.", file=sys.stderr)
        return 1

    source = CFMachPortCreateRunLoopSource(None, tap, 0)
    loop = CFRunLoopGetCurrent()
    CFRunLoopAddSource(loop, source, kCFRunLoopDefaultMode)
    CGEventTapEnable(tap, True)
    print("Raw active CGEventTap running. Press Ctrl+C to stop.", flush=True)
    CFRunLoopRun()
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda _sig, _frame: sys.exit(0))
    raise SystemExit(main())
