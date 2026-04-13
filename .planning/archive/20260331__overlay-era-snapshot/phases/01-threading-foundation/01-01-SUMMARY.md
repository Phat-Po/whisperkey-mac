---
phase: 01-threading-foundation
plan: "01"
subsystem: ui

tags: [pyobjc, appkit, nspanel, pytest, overlay, transparency]

# Dependency graph
requires: []

provides:
  - "whisperkey_mac/overlay.py: OverlayPanel class with NSPanel creation (borderless, transparent, click-through, all-Spaces, alpha=0)"
  - "whisperkey_mac/overlay.py: dispatch_to_main() utility wrapping PyObjCTools.AppHelper.callAfter"
  - "tests/__init__.py: pytest package marker"
  - "tests/conftest.py: session-scoped NSApplication fixture with Accessory activation policy"
  - "tests/test_overlay.py: 6 passing unit tests covering OVL-01/02/03 structural checks"

affects:
  - 01-02-run-loop
  - phase-03-ui-animation

# Tech tracking
tech-stack:
  added: [pytest]
  patterns: [NSPanel plain-Python wrapper (no Objective-C subclass), from-import mock patching at import site, session-scoped NSApplication fixture]

key-files:
  created:
    - whisperkey_mac/overlay.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_overlay.py
  modified: []

key-decisions:
  - "Mock callAfter via whisperkey_mac.overlay.callAfter (import site), not PyObjCTools.AppHelper.callAfter (source module), because from-import binds the name locally"
  - "Plain Python class wrapper for NSPanel — no Objective-C subclass needed at this stage"
  - "Panel stays invisible (alpha=0.0) in Phase 1 — position is final, Phase 3 only needs to animate alpha"

patterns-established:
  - "NSPanel style: NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel MUST be set at init time, not after"
  - "Transparency triple: setOpaque_(False) + setBackgroundColor_(clearColor()) + setHasShadow_(False) — all three required"
  - "Test isolation: module-scoped panel fixture avoids repeated NSPanel creation cost per test"

requirements-completed: [OVL-01, OVL-02, OVL-03]

# Metrics
duration: 3min
completed: 2026-03-09
---

# Phase 1 Plan 01: Threading Foundation — Overlay Scaffold Summary

**NSPanel overlay scaffold: borderless transparent click-through panel at bottom-center (280x56, alpha=0), with dispatch_to_main() wrapper and 6-test pytest suite covering all OVL flags**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-08T22:01:35Z
- **Completed:** 2026-03-08T22:03:58Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- OverlayPanel.create() configures NSPanel with all required flags in one call: borderless + non-activating style mask, transparent (triple-flag transparency), floating level, click-through, all-Spaces collection behavior, alpha=0.0
- dispatch_to_main(fn, *args) provides thread-safe main-loop dispatch via callAfter — ready for Phase 2 signal handler wiring
- Pytest scaffold with session NSApplication fixture enables headless NSPanel testing without app.run()
- All 6 unit tests pass: structural flags, position/dimensions, invisibility, activation policy, collection behavior, and dispatch wiring

## Task Commits

Each task was committed atomically:

1. **Task 1: Create pytest scaffold** - `e833dbc` (test)
2. **Task 2: Create whisperkey_mac/overlay.py** - `02b1c4c` (feat)

## Files Created/Modified

- `whisperkey_mac/overlay.py` — OverlayPanel class + dispatch_to_main() utility function
- `tests/__init__.py` — empty package marker for pytest discovery
- `tests/conftest.py` — session-scoped NSApplication fixture (Accessory activation policy)
- `tests/test_overlay.py` — 6 unit tests for OVL-01/02/03 structural verification

## Decisions Made

- Mock target for dispatch_to_main test: `whisperkey_mac.overlay.callAfter` (not `PyObjCTools.AppHelper.callAfter`) because Python's `from X import Y` binds the name Y in the importing module's namespace at import time. Patching the source module after import has no effect on already-bound names.
- Plain Python class chosen for OverlayPanel (no NSPanel subclass) — no Objective-C method overrides needed in Phase 1; a wrapper is simpler and sufficient.
- Panel created at full final position (bottom-center, 280x56, 40px margin) in Phase 1 so Phase 3 only needs to animate alpha, not reposition.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed mock patch target for test_dispatch_to_main**
- **Found during:** Task 2 (overlay.py implementation)
- **Issue:** Test used `unittest.mock.patch("PyObjCTools.AppHelper.callAfter")` but overlay.py uses `from PyObjCTools.AppHelper import callAfter`, binding the name locally. Patching the source module does not affect the local binding — mock was called 0 times.
- **Fix:** Changed patch target to `whisperkey_mac.overlay.callAfter` (the import site), which correctly intercepts the call.
- **Files modified:** tests/test_overlay.py
- **Verification:** All 6 tests pass with the corrected mock target.
- **Committed in:** `02b1c4c` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in mock patch target)
**Impact on plan:** Fix required for test correctness. No scope creep. All 6 tests pass.

## Issues Encountered

None — beyond the mock target fix documented above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- overlay.py exports OverlayPanel and dispatch_to_main — Plan 01-02 can import both immediately
- Plan 01-02 will modify main.py to replace stop_event.wait() with NSApp.run() and wire signal handlers to dispatch_to_main(NSApp.terminate_)
- Blocker still tracked: pynput + NSRunLoop event tap conflict is a known risk — must verify hotkeys fire after NSApp.run() goes live before proceeding to Phase 2

---
*Phase: 01-threading-foundation*
*Completed: 2026-03-09*

## Self-Check: PASSED

- whisperkey_mac/overlay.py: FOUND
- tests/__init__.py: FOUND
- tests/conftest.py: FOUND
- tests/test_overlay.py: FOUND
- .planning/phases/01-threading-foundation/01-01-SUMMARY.md: FOUND
- Commit e833dbc: FOUND
- Commit 02b1c4c: FOUND
- All 6 tests: PASS
