# Pitfalls Research: macOS Python Overlay in Background Process

## Critical Pitfalls (will break the feature)

### 1. Calling AppKit UI from a background thread
**What goes wrong:** Silent failure — no exception, overlay never appears or crashes randomly.
**Why:** All NSView/NSWindow methods must run on the main thread. WhisperKey's pynput callbacks and transcription run on background threads.
**Prevention:** Use `performSelectorOnMainThread_withObject_waitUntilDone_` for every UI call. Build a `dispatch_to_main()` utility and use it everywhere.
**Phase:** Phase 1 (threading scaffolding)

### 2. NSRunLoop not running — existing main loop is `stop_event.wait()`
**What goes wrong:** AppKit windows require a Cocoa run loop. Without it, timers don't fire, animations don't run, window doesn't respond.
**Why:** The current `App.run()` uses `stop_event.wait()` which has no Cocoa run loop.
**Prevention:** Replace `stop_event.wait()` with `NSApplication.sharedApplication().run()`. Launch all worker threads before calling `NSApp.run()`.
**Phase:** Phase 1 (threading scaffolding) — this is the first and most fundamental change.

### 3. LSUIElement / activation policy steals focus
**What goes wrong:** When the overlay appears, NSApp steals keyboard focus from the user's text field, breaking text injection.
**Prevention:** Set `NSApplicationActivationPolicyAccessory` in `Info.plist` or via `NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)` before `NSApp.run()`. Never call `NSApp.activateIgnoringOtherApps_()`.
**Phase:** Phase 1

### 4. Wrong window level — overlay hidden behind fullscreen apps
**What goes wrong:** Overlay appears on normal desktop but disappears when user has a fullscreen app.
**Prevention:** Use `NSFloatingWindowLevel` (or `NSStatusWindowLevel` for above-fullscreen). Also set `NSWindowCollectionBehaviorCanJoinAllSpaces` + `NSWindowCollectionBehaviorFullScreenAuxiliary`.
**Phase:** Phase 1

### 5. Transparent window missing flags — solid black background
**What goes wrong:** Overlay shows with solid black or gray background instead of transparent.
**Prevention:** Must set ALL of: `setOpaque_(False)`, `setBackgroundColor_(NSColor.clearColor())`, `setHasShadow_(False)`. Missing any one causes solid background.
**Phase:** Phase 1

### 6. LaunchAgent crashes at boot — no Window Server before user login
**What goes wrong:** App crashes during boot sequence before user has logged in.
**Prevention:** Add `LimitLoadToSessionType = Aqua` to the LaunchAgent plist (already present in the existing WhisperKey plist — verify it's still there after changes).
**Phase:** Phase 1 (verify during testing)

### 7. pynput + NSRunLoop conflict — hotkeys stop working
**What goes wrong:** After adding NSApp.run(), pynput event tap may conflict with the Cocoa run loop.
**Prevention:** Register pynput listener on a daemon thread BEFORE calling `NSApp.run()`. Test hotkeys immediately after the architectural change in Phase 1.
**Phase:** Phase 1

## Moderate Pitfalls

### 8. NSTimer vs threading.Timer for animations
**What goes wrong:** `threading.Timer` firing on a background thread calling UI code → crash.
**Prevention:** Use `NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_()` from the main thread for all animation timers.
**Phase:** Phase 2 (animations)

### 9. AX API unreliable for text field detection in some apps
**What goes wrong:** `AXFocusedUIElement` returns None for certain apps (Electron apps, some games, Terminal).
**Prevention:** Treat None/error as "not in text field" and fall back to clipboard path. Never block on AX API result.
**Phase:** Phase 2

### 10. PyObjC import side effects — importing AppKit starts NSApp prematurely
**What goes wrong:** Importing `from AppKit import *` at module top level can start side effects before `setActivationPolicy_` is called.
**Prevention:** Import AppKit only inside the overlay module, not at top of `main.py`. Call `setActivationPolicy_` as the very first NSApp call.
**Phase:** Phase 1

### 11. Retina coordinates — overlay positioned at wrong location on HiDPI displays
**What goes wrong:** Overlay appears at wrong position on Retina displays because frame coordinates are in points, not pixels.
**Prevention:** Use `NSScreen.mainScreen().visibleFrame()` to get screen dimensions — AppKit already works in points, so this should be transparent. Verify on both Retina and non-Retina.
**Phase:** Phase 2

### 12. Multi-monitor — overlay appears on wrong screen
**What goes wrong:** Overlay appears on the primary/external screen instead of the screen with the active window.
**Prevention:** Use `NSScreen.mainScreen()` (the screen with the key window/menu bar) for v1. Document as known limitation.
**Phase:** Phase 2 (acceptable v1 limitation)

### 13. Memory leak — NSTimer retained cycle
**What goes wrong:** NSTimer retains its target strongly, causing memory leak if overlay object is deallocated.
**Prevention:** Always call `timer.invalidate()` before releasing overlay, or use `__weak` reference pattern via a trampoline object.
**Phase:** Phase 2

### 14. Rapid key presses — overlay state machine gets confused
**What goes wrong:** User presses hotkey again before first transcription finishes, leaving overlay in wrong state.
**Prevention:** Implement explicit state machine: `hidden → recording → transcribing → result → hidden`. Ignore state transitions that don't follow the valid sequence. Add state logging.
**Phase:** Phase 2 (edge cases)

---
*Research date: 2026-03-09 | Confidence: HIGH for AppKit/LaunchAgent domain (stable APIs)*
