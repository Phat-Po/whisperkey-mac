---
phase: 02-state-machine-thread-wiring
plan: "02"
subsystem: ui
tags: [pyobjc, appkit, overlay, state-machine, threading, ax-api, dispatch]

# Dependency graph
requires:
  - phase: 02-state-machine-thread-wiring plan 01
    provides: OverlayPanel with show_recording/show_transcribing/show_result/hide_after_paste; dispatch_to_main(); is_cursor_in_text_field()
provides:
  - main.py keyboard callbacks dispatch overlay state transitions via dispatch_to_main()
  - main.py transcription thread routes paste-vs-clipboard based on AX cursor detection
  - Full Phase 2 wiring connecting state machine to real application events
affects: [03-animation-polish, 04-launchagent-packaging]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Safety guard pattern: hasattr(self, '_overlay') check before dispatching to overlay (pre-init protection)"
    - "Threading: pynput daemon thread -> dispatch_to_main() -> overlay state transition (non-blocking)"
    - "AX detection on transcription worker thread before main-thread dispatch (thread-safe pattern)"
    - "Paste branch: inject() only (inject already calls pyperclip.copy internally)"
    - "Clipboard branch: pyperclip.copy() only (no paste attempt)"

key-files:
  created: []
  modified:
    - whisperkey_mac/main.py
    - pyproject.toml (ApplicationServices dep already present from Plan 02-01)

key-decisions:
  - "Imports of dispatch_to_main and is_cursor_in_text_field kept inside methods (deferred import) to match existing pattern of confining AppKit imports inside run()"
  - "Safety guard (hasattr _overlay) added to all three callback methods to protect against pre-initialization race"
  - "pyobjc-framework-ApplicationServices was already declared in pyproject.toml by Plan 02-01 - no change needed"

patterns-established:
  - "Dispatch pattern: pynput daemon thread always uses dispatch_to_main() — never calls overlay methods directly"
  - "Branch dispatch: both paste and clipboard branches end with a dispatch_to_main() call for overlay update"
  - "Fallback path: if _overlay not initialized, _transcribe_and_inject() falls back to Phase 1 behavior (always inject)"

requirements-completed: [RST-01, RST-02, RST-03, RST-04, DET-01, DET-02]

# Metrics
duration: 15min
completed: 2026-03-09
---

# Phase 2 Plan 02: State Machine Thread Wiring Summary

**Overlay state machine wired to keyboard callbacks and transcription thread: hotkey press dispatches show_recording, release dispatches show_transcribing, and transcription completion routes to paste-silent (inject + hide_after_paste) or clipboard (pyperclip.copy + show_result) based on live AX cursor detection.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-09T09:15:30Z
- **Completed:** 2026-03-09T09:30:00Z
- **Tasks:** 2 of 3 complete (Task 3 = checkpoint:human-verify, pending)
- **Files modified:** 1 (whisperkey_mac/main.py)

## Accomplishments
- `_start_recording()` dispatches `show_recording()` via `dispatch_to_main()` on pynput daemon thread
- `_stop_and_transcribe()` dispatches `show_transcribing()` via `dispatch_to_main()` on pynput daemon thread
- `_transcribe_and_inject()` implements full paste-vs-clipboard branch with AX cursor detection
- Paste branch: `inject()` (silent clipboard+paste) + `dispatch_to_main(hide_after_paste)` — RST-01
- Clipboard branch: `pyperclip.copy()` + `dispatch_to_main(show_result, text)` — RST-02/03/04
- No double pyperclip.copy() in paste branch (inject() handles it internally)
- All 22 unit tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Declare ApplicationServices dep and wire keyboard callbacks to overlay** - `3ab20eb` (feat)
2. **Task 2: Implement paste-vs-clipboard branch in _transcribe_and_inject** - `f38cea5` (feat)
3. **Task 3: Smoke test — verify full hotkey lifecycle** - PENDING (checkpoint:human-verify)

## Files Created/Modified
- `whisperkey_mac/main.py` - Added overlay state dispatches in _start_recording, _stop_and_transcribe, and paste-vs-clipboard branch in _transcribe_and_inject

## Decisions Made
- Deferred imports (inside methods) for dispatch_to_main and is_cursor_in_text_field to match existing pattern of confining AppKit-adjacent imports inside run() method
- Safety guard pattern (hasattr check for '_overlay') applied consistently to all three modified methods

## Deviations from Plan

None — plan executed exactly as written.

Note: pyproject.toml already had `pyobjc-framework-ApplicationServices>=10.0` declared (added by Plan 02-01 via ax_detect.py creation). No change needed to pyproject.toml.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Full Phase 2 wiring complete (pending human smoke test confirmation at Task 3 checkpoint)
- Phase 3 (animation polish) can begin after Task 3 approval: overlay transitions have placeholder alpha=1.0/0.0; Phase 3 replaces with NSAnimationContext fade-in/fade-out animations
- TODO Phase 3 comments in overlay.py show_recording(), hide_after_paste(), _auto_dismiss() mark exact animation insertion points

---
*Phase: 02-state-machine-thread-wiring*
*Completed: 2026-03-09*
