---
phase: 01-threading-foundation
verified: 2026-03-09T00:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 1: Threading Foundation — Verification Report

**Phase Goal:** Establish a stable Cocoa run loop on the main thread so that all subsequent AppKit UI work (overlay, animations, state machine) has a correct threading foundation.
**Verified:** 2026-03-09
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | OverlayPanel class exists in overlay.py and can be imported without NSApp.run() being active | VERIFIED | `from whisperkey_mac.overlay import OverlayPanel, dispatch_to_main` — import succeeds; `.venv/bin/python -c "from whisperkey_mac.overlay import OverlayPanel, dispatch_to_main; print('OK')"` returns OK |
| 2 | NSPanel is created with correct style mask (borderless + non-activating) at init time | VERIFIED | overlay.py line 74: `style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel`; set at `initWithContentRect_styleMask_backing_defer_()` time; test_panel_flags passes (styleMask & 128 == 128) |
| 3 | Panel is fully transparent: opaque=False, clearColor background, no shadow, alpha=0.0 | VERIFIED | overlay.py lines 84-86, 104: all three transparency flags set; test_panel_flags + test_panel_invisible pass |
| 4 | Panel is click-through: ignoresMouseEvents=True | VERIFIED | overlay.py line 92: `self._panel.setIgnoresMouseEvents_(True)`; test_panel_flags passes |
| 5 | Panel is positioned at bottom-center of main screen with 40px bottom margin | VERIFIED | overlay.py lines 65-69: x=(screen_width-280)/2, y=40.0, size=(280,56); test_panel_position passes |
| 6 | Panel collection behavior includes CanJoinAllSpaces, Stationary, and FullScreenAuxiliary | VERIFIED | overlay.py lines 95-100: all three bits ORed; test_collection_behavior passes (bits 1, 16, 256 set) |
| 7 | dispatch_to_main() utility exists in overlay.py and wraps callAfter() | VERIFIED | overlay.py lines 27-34: `def dispatch_to_main(fn, *args): callAfter(fn, *args)`; test_dispatch_to_main passes |
| 8 | Unit tests confirm all NSPanel flags without requiring NSApp.run() | VERIFIED | All 6 tests pass in 0.14s; no app.run() called in test suite |
| 9 | WhisperKey starts with NSApp.run() instead of stop_event.wait() | VERIFIED | main.py line 100: `app.run()`; grep confirms no `stop_event` in main.py; callLater polling pattern replaces blocking wait |

**Score:** 9/9 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `whisperkey_mac/overlay.py` | OverlayPanel class + dispatch_to_main utility | VERIFIED | 107 lines; exports OverlayPanel and dispatch_to_main; all flags set correctly |
| `tests/__init__.py` | Makes tests/ a Python package | VERIFIED | File exists (0 bytes — correct for package marker) |
| `tests/conftest.py` | Shared pytest fixtures including NSApplication initialization | VERIFIED | Session-scoped nsapp fixture; sets NSApplicationActivationPolicyAccessory |
| `tests/test_overlay.py` | 6 unit tests for OVL-01, OVL-02, OVL-03 structural verification | VERIFIED | 6 tests, all pass: test_panel_flags, test_panel_position, test_panel_invisible, test_activation_policy, test_collection_behavior, test_dispatch_to_main |
| `whisperkey_mac/main.py` | Modified App.run() using NSApp.run() with callLater polling and OverlayPanel init | VERIFIED | stop_event removed; NSApplication.sharedApplication().run() on line 100; OverlayPanel.create() on line 97; AppKit imports deferred inside App.run() |
| `pyproject.toml` | Explicit pyobjc-framework-Cocoa dependency declaration | VERIFIED | Line 19: `"pyobjc-framework-Cocoa>=10.0"` in project dependencies |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tests/test_overlay.py` | `whisperkey_mac/overlay.py` | `from whisperkey_mac.overlay import OverlayPanel` | WIRED | Line 19 of test_overlay.py; module-scoped panel fixture calls `OverlayPanel.create()._panel` |
| `whisperkey_mac/overlay.py` | `PyObjCTools.AppHelper.callAfter` | `dispatch_to_main` wraps `callAfter` | WIRED | overlay.py line 24: `from PyObjCTools.AppHelper import callAfter`; line 34: `callAfter(fn, *args)` |
| `whisperkey_mac/main.py App.run()` | `whisperkey_mac/overlay.py OverlayPanel` | `from whisperkey_mac.overlay import OverlayPanel` | WIRED | main.py line 48: import; line 97: `self._overlay = OverlayPanel.create()` |
| `whisperkey_mac/main.py` | `PyObjCTools.AppHelper.callLater` | callLater polling for signal delivery | WIRED | main.py line 47: `from PyObjCTools.AppHelper import callLater`; lines 81, 83: callLater used |
| `whisperkey_mac/main.py` | `NSApplication.sharedApplication().run()` | replaces stop_event.wait() | WIRED | main.py line 50: `app = NSApplication.sharedApplication()`; line 100: `app.run()` |

**Note on plan 01-02 deviation:** Plan 01-02 specified MachSignals for signal handling. Actual implementation uses callLater polling (threading.Event + 200ms poll). This is a valid and better approach for the pynput subprocess environment. The key link to `PyObjCTools.MachSignals` was substituted with `callLater` — intent (reliable signal delivery inside NSApp.run()) is fully satisfied.

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| OVL-01 | 01-01, 01-02 | 录音中，屏幕底部居中显示半透明圆角浮层（NSPanel，常驻最顶层，点击穿透）| SATISFIED | NSPanel exists at bottom-center (280x56, y=40); transparent (triple-flag); floating level; click-through; all flags confirmed by 6 passing tests |
| OVL-02 | 01-01, 01-02 | 浮层出现时不抢夺焦点，不打断用户当前文字输入 | SATISFIED | NSApplicationActivationPolicyAccessory set before app.run(); NSWindowStyleMaskNonactivatingPanel in styleMask at init time; alpha=0.0 (invisible, no orderFront_ called); manual smoke check 2 passed per SUMMARY |
| OVL-03 | 01-01, 01-02 | 浮层在所有 Space 可见（Mission Control 切换不消失）| SATISFIED | collectionBehavior has CanJoinAllSpaces (1) + Stationary (16) + FullScreenAuxiliary (256) bits set; test_collection_behavior passes |

All 3 requirements assigned to Phase 1 are SATISFIED.

---

## Anti-Patterns Found

No anti-patterns detected.

Scan covered: `whisperkey_mac/overlay.py`, `whisperkey_mac/main.py`, `tests/test_overlay.py`, `tests/conftest.py`
- No TODO/FIXME/XXX/HACK/PLACEHOLDER comments
- No empty implementations (return null/return {}/return [])
- No stub handlers (onSubmit preventDefault only, etc.)
- No orphaned code

---

## Known Accepted Limitation

**Ctrl+C shutdown message not printed**

The plan's success criterion "SIGINT prints '[whisperkey] shutting down (SIGINT)' and exits cleanly" is partially met: the process exits cleanly, but the message is not printed when Ctrl+C is used. This is caused by pynput's multiprocessing internals calling `os._exit()` before Python cleanup runs — bypassing all signal delivery mechanisms (MachSignals, try/except KeyboardInterrupt, and callLater polling were all attempted).

This is documented as a known issue in SUMMARY.md (01-02) and STATE.md. SIGTERM from `pkill` or LaunchAgent works correctly and the shutdown message is printed in that path. Functional exit behavior is correct. This limitation does not affect Phase 2-4 work.

**Accepted as PASSED with note** per phase instructions.

---

## Human Verification Required

The following items were verified by the human operator as part of Plan 01-02's Task 2 checkpoint (blocking gate). Approval was recorded in SUMMARY.md before phase was marked complete.

### 1. Thread Survival (Hotkey -> Speak -> Transcribe)

**Test:** Start whisperkey, hold hotkey, speak, release, confirm text appears in editor
**Expected:** Transcribed text injected; Terminal shows `[whisperkey] -> 'text'`
**Status:** APPROVED — documented in 01-02-SUMMARY.md, all daemon threads survive NSApp.run() switch

### 2. Focus-Steal Prevention

**Test:** Type in active app while starting whisperkey in another terminal
**Expected:** Keystrokes continue going to active app; no focus stolen
**Status:** APPROVED — NSApplicationActivationPolicyAccessory + NSWindowStyleMaskNonactivatingPanel confirmed effective; documented in 01-02-SUMMARY.md

### 3. SIGTERM Clean Shutdown

**Test:** `pkill -f whisperkey` — confirm clean exit with shutdown message
**Expected:** `[whisperkey] shutting down (SIGTERM)` printed, process exits
**Status:** APPROVED — callLater polling catches SIGTERM correctly; documented in 01-02-SUMMARY.md

---

## Summary

Phase 1 goal is fully achieved. The Cocoa run loop is running on the main thread via `NSApplication.sharedApplication().run()`. All threading foundation requirements are in place:

- The overlay NSPanel is created, configured, and invisible — ready for Phase 3 animation
- All existing daemon threads (pynput, audio, transcription) survived the run loop switch intact
- Focus-steal prevention is confirmed working
- Signal handling works correctly for SIGTERM (the path used by LaunchAgent and pkill)
- The callAfter/callLater dispatch infrastructure is in place for Phase 2 state machine wiring
- 6 unit tests confirm all structural NSPanel flags without requiring app.run()

The one known limitation (Ctrl+C shutdown message not printing) is a documented cosmetic issue caused by pynput internals, does not affect functionality, and was accepted before phase sign-off.

---

_Verified: 2026-03-09_
_Verifier: Claude (gsd-verifier)_
