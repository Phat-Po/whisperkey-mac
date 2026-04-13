# Project Research Summary

**Project:** VibeMouse Mac — WhisperKey macOS Overlay UI
**Domain:** macOS native UI overlay, Python/PyObjC, background process integration
**Researched:** 2026-03-09
**Confidence:** HIGH

## Executive Summary

This project adds a floating visual overlay to an existing Python-based dictation tool (WhisperKey). The overlay must display recording state, transcribing state, and result state without ever stealing keyboard focus or mouse events from the user's active application. The correct technical approach is a pure PyObjC/AppKit implementation using `NSPanel` — no new dependencies are required because `pyobjc-framework-Cocoa` 12.1 is already installed in the project's `.venv`. The implementation pattern is well-understood and follows Apple's own macOS Dictation visual conventions.

The single most critical architectural change is replacing the current `stop_event.wait()` main loop with `NSApplication.sharedApplication().run()`. Without a Cocoa run loop, no AppKit features work — no windows appear, no timers fire, no animations run. This is the foundation everything else builds on. All existing worker threads (pynput listener, audio capture, Whisper transcription) must be launched as daemon threads before `NSApp.run()` is called, and all UI updates from those threads must be dispatched to the main thread using `performSelectorOnMainThread_withObject_waitUntilDone_`.

The main risk is threading mistakes: calling any AppKit UI method from a background thread causes silent failures or random crashes. Every UI state transition — show recording, show transcribing, show result, hide — must go through a `dispatch_to_main()` utility. Beyond that, this is a well-documented domain with stable APIs. The pitfalls are concrete and preventable, and research has identified all of them in advance.

## Key Findings

### Recommended Stack

The project already has everything it needs in `.venv`. No new packages required. PyObjC 12.1 (built against macOS 26.1 SDK) provides the full AppKit/Cocoa stack. The overlay window should be an `NSPanel` subclass with `NSWindowStyleMaskBorderless`, `NSFloatingWindowLevel`, and `NSApplicationActivationPolicyAccessory`. Drawing uses `NSView.drawRect_` with `NSBezierPath`. Animation timers must use `NSTimer` (not `threading.Timer`) because timers must fire on the main run loop. Cross-thread dispatch uses `performSelectorOnMainThread_withObject_waitUntilDone_`. Fade animations use `NSAnimationContext` + Core Animation.

**Core technologies:**
- `AppKit.NSPanel`: Overlay window — floats above all app windows, supports borderless transparent always-on-top, no Dock entry
- `NSView.drawRect_` + `NSBezierPath`: Waveform and pill drawing — native, no extra dependency
- `NSTimer` (30fps): Animation loop — must run on main thread run loop, not background threads
- `NSAnimationContext` + `animator().alphaValue`: Fade in/out — Core Animation-backed, smooth
- `performSelectorOnMainThread_withObject_waitUntilDone_`: Cross-thread dispatch — the safe PyObjC idiom for worker-thread-to-UI updates
- `AXUIElement` (ApplicationServices): Text field detection — already installed, already required by existing `output.py`

### Expected Features

The overlay has four states: hidden, recording, transcribing, result. The UX convention follows macOS Dictation and AquaVoice: a floating pill at bottom-center, never interactive.

**Must have (table stakes):**
- Always-on-top floating pill at bottom-center — without this overlay disappears behind active app
- Waveform animation during recording (4-6 bars, 30fps) — users think the app froze without motion
- Distinct "transcribing" state with pulsing dots — covers the 0.5-3s gap between key release and paste
- Silent dismiss on paste (200ms fade) — overlay disappearing IS the confirmation
- "已复制到剪贴板" text on clipboard path — user must know what was captured
- Click-through (`setIgnoresMouseEvents_(True)`) — any focus steal is a fatal UX bug
- Auto-dismiss timer — overlay cannot require user action to close

**Should have (v2 differentiators):**
- RMS-driven waveform using real audio amplitude — ship idle sine-wave animation first to reduce threading complexity
- Multi-monitor: overlay follows active screen — acceptable v1 limitation to use `NSScreen.mainScreen()`

**Defer (v2+):**
- Draggable overlay position — not needed for solo use, adds state complexity
- Streaming partial transcription — faster-whisper returns full result; faking it would be dishonest
- Position memory — out of scope

**Specific animation timings (do not improvise):**

| Animation | Timing |
|-----------|--------|
| Appear | 150ms fade-in + 8pt slide-up, ease-out |
| Dismiss (normal) | 400ms fade-out |
| Silent dismiss (paste) | 200ms fade-out |
| Pulsing dots | 3 dots, 300ms/dot, 900ms full cycle |
| Waveform bars | 4-6 bars, 30fps, height 4-20pt |

**Branch logic note:** The existing `output.py` already returns `"pasted"` or `"clipboard"` — these are the exact conditions for the two overlay dismiss behaviors. No new return values needed.

### Architecture Approach

The architecture is a single new file `overlay.py` containing an `NSPanel`-based overlay controller with an explicit 4-state machine (`hidden → recording → transcribing → result → hidden`). The existing files (`main.py`, `keyboard_listener.py`, `transcriber.py`, `output.py`) each get minimal additions: `main.py` switches its event loop and instantiates the overlay controller; the other files dispatch state changes to the overlay via `dispatch_to_main()`. Text field detection via the AX API runs on a worker thread and dispatches the branch decision to the main thread.

**Major components:**
1. `overlay.py` (new) — NSPanel window, 4-state machine, waveform animation, fade transitions, all AppKit logic
2. `main.py` (modified) — Replace `stop_event.wait()` with `NSApp.run()`; instantiate OverlayController; launch all threads before NSApp.run()
3. `dispatch_to_main()` utility — Safe cross-thread bridge; used by keyboard_listener, transcriber, and output
4. `is_cursor_in_text_field()` — AX API query; runs on worker thread; result dispatched to overlay for paste-vs-clipboard branch

**Build order (architecture prescribes this sequence):**
1. NSApp loop scaffolding — verify existing threads still work
2. Basic NSPanel — visible, click-through, all Spaces, correct level
3. `dispatch_to_main()` + thread wiring — connect existing threads to overlay state
4. Accessibility detection — branch logic
5. Visual polish — waveform, fade, dots
6. Edge cases — rapid keypresses, state machine hardening

### Critical Pitfalls

1. **Calling AppKit UI from background thread** — Silent failure or random crash. Build `dispatch_to_main()` utility first and route ALL UI calls through it without exception.
2. **NSRunLoop not running** — NSApp timers, animations, and windows require a Cocoa run loop. Replace `stop_event.wait()` with `AppHelper.runEventLoop()` as the very first architectural change; verify worker threads still function before proceeding.
3. **Focus stealing via activation policy** — If `NSApplicationActivationPolicyRegular` is used (or default), overlay appearance steals keyboard focus from user's text field. Set `NSApplicationActivationPolicyAccessory` as the very first NSApp call, before `NSApp.run()`.
4. **Transparent window missing flags** — Solid black background if any of three flags are missing. Must set ALL of: `setOpaque_(False)`, `setBackgroundColor_(NSColor.clearColor())`, `setHasShadow_(False)`.
5. **pynput + NSRunLoop conflict** — After switching to `NSApp.run()`, pynput's event tap may conflict with the Cocoa run loop. Mitigate by starting pynput listener on daemon thread BEFORE `NSApp.run()`. Test hotkeys immediately after Phase 1 architectural change.
6. **NSTimer vs threading.Timer for animations** — `threading.Timer` fires on background thread and will crash when it calls UI code. Use `NSTimer.scheduledTimerWithTimeInterval_...` from the main thread only.
7. **Rapid keypresses confuse state machine** — Implement explicit state machine with valid-transition guards. Ignore transitions that don't follow `hidden → recording → transcribing → result → hidden`.

## Implications for Roadmap

Based on combined research, the pitfalls and architecture together prescribe a strict build order. Phase 1 is almost entirely non-visual: it establishes the threading foundation that all visual work depends on. Getting Phase 1 wrong means visual work will appear to work but fail unpredictably. This ordering is non-negotiable.

### Phase 1: Threading Foundation and NSApp Loop

**Rationale:** The NSRunLoop replacement is the most fundamental change — nothing else works without it. Six of the seven critical pitfalls occur in Phase 1 if done incorrectly. This phase has no visual deliverable but is the prerequisite for all visual work.
**Delivers:** A running NSApp loop with all existing worker threads intact, `dispatch_to_main()` utility, and an invisible NSPanel correctly configured (level, activation policy, transparency, mouse ignore, all Spaces).
**Addresses:** Table stakes #1 (always-on-top), table stakes #6 (click-through)
**Avoids:** Pitfalls 1, 2, 3, 4, 5, 10 — all the silent-failure categories
**Verification:** Existing hotkey recording and transcription still works after architectural change; no focus steal on NSPanel creation.

### Phase 2: State Machine and Thread Wiring

**Rationale:** With the NSApp loop running and NSPanel ready, connect the existing worker threads to overlay state transitions. This is the integration layer — no visual polish yet, but the state machine becomes testable.
**Delivers:** Overlay responds to hotkey press (show), key release (transcribing state), and transcription completion (result or hide). `is_cursor_in_text_field()` branch logic determines paste vs clipboard path.
**Addresses:** Table stakes #3 (transcribing state), #4 (silent dismiss on paste), #5 (clipboard text), #7 (auto-dismiss timer)
**Avoids:** Pitfall 7 (rapid keypresses — state machine guards), Pitfall 9 (AX API fallback)

### Phase 3: Visual Polish and Animation

**Rationale:** State machine is proven correct before adding visual complexity. Animations built on top of a working state machine are easier to tune and debug.
**Delivers:** Waveform bars (idle sine-wave, not RMS-driven for v1), pulsing dots for transcribing state, fade-in/fade-out transitions, result text display with exact animation timings specified in FEATURES.md.
**Addresses:** Table stakes #2 (waveform animation), all animation timing specs
**Avoids:** Pitfall 6 (NSTimer on main thread), Pitfall 8 (NSTimer retained cycle — invalidate on hide), Pitfall 11 (Retina coordinate verification)
**Uses:** `NSTimer` (30fps), `NSAnimationContext`, `NSBezierPath`, `NSTextField` + `NSAttributedString`

### Phase 4: Edge Cases and Hardening

**Rationale:** Polish and edge case handling after core flows are verified.
**Delivers:** Rapid keypress protection (state machine guards), multi-monitor documentation (v1 uses mainScreen()), LaunchAgent boot verification (`LimitLoadToSessionType = Aqua` confirmed), memory leak prevention (NSTimer invalidation).
**Avoids:** Pitfall 12 (multi-monitor — documented v1 limitation), Pitfall 13 (NSTimer memory leak), Pitfall 14 (rapid keypresses)

### Phase Ordering Rationale

- Phase 1 before Phase 2 because AppKit windows and dispatchers must exist before threads can call them
- Phase 2 before Phase 3 because visual animations on top of a broken state machine produce misleading test results
- Phase 3 before Phase 4 because edge cases are meaningless to harden until core paths are confirmed working
- The AX API (`is_cursor_in_text_field()`) is placed in Phase 2 rather than Phase 3 because it drives branch logic (paste vs clipboard), not visual behavior — it must be correct before animations are added

### Research Flags

Phases with standard patterns (no additional research needed):
- **Phase 1:** NSApp loop and NSPanel configuration are stable, well-documented AppKit patterns. PITFALLS.md identifies every failure mode in advance.
- **Phase 2:** `performSelectorOnMainThread_` dispatch and AX API usage are established patterns. The existing `output.py` return values already match what's needed.
- **Phase 3:** NSTimer, NSAnimationContext, and NSBezierPath are standard AppKit animation patterns.
- **Phase 4:** Edge case handling follows from state machine design decisions already made.

No phases require `/gsd:research-phase` — all technical unknowns were resolved during this research pass.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Confirmed from actual installed `.venv` packages — not training data assumptions |
| Features | HIGH | UX requirements are specific and complete; animation timings are explicit; branch logic identified from existing code |
| Architecture | HIGH | AppKit/PyObjC threading model and AXUIElement API are stable APIs unchanged for many years |
| Pitfalls | HIGH | All 14 pitfalls are concrete and specific to this exact project's code structure |

**Overall confidence:** HIGH

### Gaps to Address

- **RMS-driven waveform (v1 vs v2):** Research recommends shipping idle sine-wave animation in v1 and upgrading to real audio amplitude in v2. The roadmapper should treat RMS waveform as a v2 item unless threading complexity assessment during Phase 3 shows it's trivial to add.
- **pynput + NSRunLoop conflict:** Known risk but not confirmed to be an actual problem with this specific codebase. Phase 1 testing will confirm immediately — if pynput stops working after NSApp.run() switch, a daemon thread ordering fix or `AppHelper.runEventLoop()` variant resolves it.
- **Multi-monitor behavior:** v1 uses `NSScreen.mainScreen()` (screen with menu bar). If user's active window is on a different monitor, overlay appears on wrong screen. Document as known v1 limitation; address in v2 with `NSScreen.screens()` + active window screen detection.

## Sources

### Primary (HIGH confidence)
- Installed `.venv` packages (confirmed via direct inspection) — PyObjC 12.1, pyobjc-framework-Cocoa, Quartz, ApplicationServices
- Apple AppKit documentation — NSPanel, NSWindowLevel, NSAnimationContext, NSTimer, NSApplicationActivationPolicy
- PyObjC documentation — `performSelectorOnMainThread_withObject_waitUntilDone_`, `AppHelper.runEventLoop()`
- Existing project code — `output.py` return values, `main.py` event loop structure, LaunchAgent plist

### Secondary (MEDIUM confidence)
- AquaVoice and macOS Dictation UI conventions — overlay position and animation timing benchmarks
- Community experience with pynput + NSRunLoop interaction — known compatibility consideration

---
*Research completed: 2026-03-09*
*Ready for roadmap: yes*
