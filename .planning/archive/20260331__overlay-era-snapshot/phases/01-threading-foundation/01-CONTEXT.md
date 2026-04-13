# Phase 1: Threading Foundation - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the existing `stop_event.wait()` main loop with `NSApp.run()`. Create an invisible NSPanel window correctly configured for overlay use (borderless, transparent, always-on-top, click-through, all Spaces, no focus steal). All existing hotkey/audio/transcription threads must survive the architectural change with identical behavior to before. No visible change to the user — the panel is invisible.

</domain>

<decisions>
## Implementation Decisions

### PyObjC dependency
- Add `pyobjc-framework-Cocoa>=10.0` to `[project.dependencies]` in pyproject.toml
- Minimal install (not the full `pyobjc` meta-package) — only Cocoa/AppKit bindings needed
- After Phase 1 lands, run `pip install -e .` once to pick up the new dep

### NSPanel size and position
- Overlay size: compact pill, ~280×56px
- Bottom margin: ~40px from the bottom of the screen
- Horizontal: centered on screen
- Phase 1 scope: position the NSPanel at final bottom-center coordinates, but set alpha=0 (fully transparent, invisible). Phase 3 only needs to animate alpha — position is already correct.

### Quit signal handling
- SIGINT (Ctrl+C) must still work — wire to NSApp.terminate() via signal handler inside the run loop
- SIGTERM must also quit cleanly — same wiring (needed for LaunchAgent and pkill)
- Terminal shutdown message must remain: `[whisperkey] shutting down (SIGINT)` — keep existing format

### Claude's Discretion
- Exact mechanism for wiring SIGINT/SIGTERM → NSApp.terminate() (signal handler vs NSRunLoop timer vs AppHelper approach)
- Whether to use `NSApp.run()` directly or `AppHelper.runEventLoop()` — choose whichever avoids the pynput + NSRunLoop event tap conflict
- dispatch_to_main() implementation details (performSelectorOnMainThread vs NSRunLoop.mainRunLoop().performBlock_())
- NSPanel subclass vs standalone instance inside overlay.py

</decisions>

<specifics>
## Specific Ideas

- pynput + NSRunLoop conflict is a known risk (from STATE.md). If hotkeys stop working after NSApp.run() switch, AppHelper.runEventLoop() is the documented fix — use whichever approach avoids this problem proactively.
- NSApplicationActivationPolicyAccessory must be set BEFORE NSApp.run() starts — already decided in STATE.md, confirmed here.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `App.run()` in `whisperkey_mac/main.py:32` — this is the exact method where `stop_event.wait()` (line 65) gets replaced with `NSApp.run()`
- Signal handlers at main.py:58-64 (SIGINT, SIGTERM, SIGHUP) — need to be rerouted from `stop_event.set()` to `NSApp.terminate()`
- All existing threads are daemon=True (audio recorder, transcription, hotkey listener) — they will survive NSApp.run() without changes

### Established Patterns
- `threading.Lock()` pattern used throughout — dispatch_to_main() should follow same concurrency discipline
- Print-based logging: `print(f"[whisperkey] ...")` — add any Phase 1 diagnostic prints in this format
- Callback injection pattern (HotkeyListener) — new overlay module should follow the same pattern

### Integration Points
- `whisperkey_mac/main.py` — modify `App.run()` to call NSApp.run() instead of stop_event.wait()
- `pyproject.toml` — add `pyobjc-framework-Cocoa>=10.0` under `[project.dependencies]`
- NEW: `whisperkey_mac/overlay.py` — create this module with NSPanel subclass and dispatch_to_main() utility

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

## Verification Protocol (from discussion)

Phase 1 has no visible UI change. Verify by:

1. **Functional test**: Press hotkey → speak → release → confirm text appears. If this works, all threads survived NSApp.run() switch.
2. **Focus-steal check**: Open TextEdit, start typing, then start WhisperKey in another Terminal tab. Continue typing in TextEdit — confirm characters still go to TextEdit, not intercepted by WhisperKey.
3. **pynput escalation rule**: If hotkeys stop firing after NSApp.run() is live, STOP. Do not proceed to Phase 2. Fix the pynput + NSRunLoop conflict in Phase 1 first.

---

*Phase: 01-threading-foundation*
*Context gathered: 2026-03-09*
