---
phase: 02-state-machine-thread-wiring
plan: "01"
subsystem: ui
tags: [pyobjc, appkit, nspanel, nsvisualeffectview, state-machine, ax-api, accessibility]

# Dependency graph
requires:
  - phase: 01-threading-foundation
    provides: OverlayPanel (NSPanel), dispatch_to_main(), callLater polling, conftest NSApplication fixture

provides:
  - OverlayState enum (HIDDEN, RECORDING, TRANSCRIBING, RESULT)
  - OverlayStateMachine with transition guards, generation counter stale-dismiss protection
  - OverlayPanel extended with NSVisualEffectView content + 2 NSTextField labels
  - OverlayPanel delegation methods (show_recording/show_transcribing/show_result/hide_after_paste)
  - ax_detect.is_cursor_in_text_field() — thread-safe AX API wrapper with safe degradation

affects:
  - 02-02-thread-wiring (wires overlay state machine + AX detection into main.py)
  - 03-animation (replaces TODO Phase 3 lines in overlay.py with NSAnimationContext transitions)

# Tech tracking
tech-stack:
  added:
    - pyobjc-framework-ApplicationServices>=10.0 (declared in pyproject.toml; was transitive dep of pynput)
    - NSVisualEffectView with NSVisualEffectMaterialHUDWindow (frosted glass HUD pill)
    - Python enum.Enum for 4-state machine (no external state machine library)
  patterns:
    - Transition guard dict (_VALID_TRANSITIONS) — silent rejection of invalid transitions
    - Generation counter (_dismiss_gen) — stale callLater auto-dismiss cancellation without token
    - Delegation pattern — OverlayPanel.show_*() delegates to OverlayStateMachine for caller convenience
    - Mock at import site — patch whisperkey_mac.overlay.callLater (not PyObjCTools.AppHelper.callLater)
    - AX third-arg None pattern — AXUIElementCopyAttributeValue(element, attr, None) returns (err, value)

key-files:
  created:
    - whisperkey_mac/ax_detect.py
    - tests/test_ax_detect.py
  modified:
    - whisperkey_mac/overlay.py
    - tests/test_overlay.py
    - pyproject.toml

key-decisions:
  - "OverlayStateMachine as standalone class (not nested); OverlayPanel holds reference and delegates — keeps state logic testable without NSPanel"
  - "hide_after_paste() bypasses _VALID_TRANSITIONS guard (force-hide) — paste success is unambiguous; TRANSCRIBING->HIDDEN via guard would require adding an extra valid transition"
  - "kAXSearchFieldRole does NOT exist as importable constant in PyObjC 12.1 — use string literal 'AXSearchField' in _TEXT_INPUT_ROLES frozenset"
  - "_dismiss_gen increments on show_recording() AND hide_after_paste() — both events invalidate any pending 3s auto-dismiss timers"
  - "setAlphaValue_(1.0) called BEFORE orderFront_(None) in show_recording() — avoids compositor race that causes one-frame black flash"
  - "Phase 3 TODO comments placed at exact lines where NSAnimationContext replaces setAlphaValue_/orderFront_/orderOut_ calls"

patterns-established:
  - "State machine: pure Python enum + dict of valid transitions; all methods on main thread; no threading.Lock needed"
  - "Generation counter pattern for non-cancellable timers (callLater returns no token)"
  - "AX detection on worker thread (thread-safe); dispatch result to main thread via dispatch_to_main()"
  - "TDD: write test file importing non-existent name -> RED; implement -> GREEN; run full suite to confirm"

requirements-completed: [RST-01, RST-02, RST-03, RST-04, DET-01, DET-02]

# Metrics
duration: 10min
completed: 2026-03-09
---

# Phase 2 Plan 01: State Machine and AX Detection Summary

**4-state overlay state machine (enum + transition guard dict) with stale-dismiss generation counter, NSVisualEffectView HUD content view, and thread-safe AX cursor detection — 22 tests green, no hardware required**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-09T09:05:00Z
- **Completed:** 2026-03-09T09:15:00Z
- **Tasks:** 3 (TDD: RED commit + GREEN commit x2)
- **Files modified:** 5

## Accomplishments
- OverlayStateMachine with 4 states, transition guard dict, generation counter for stale callLater cancellation
- NSVisualEffectView content view (HUDWindow material, 12pt corner radius) with 2 NSTextField labels (14pt white primary, 10pt lightGray secondary)
- is_cursor_in_text_field() AX wrapper covering AXTextField/AXTextArea/AXComboBox/AXSearchField with safe degradation (any error = False = clipboard path)
- 22 unit tests all green — 14 overlay (including 8 state machine) + 8 AX detection (parametrized roles)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests** - `6eafa69` (test — RED)
2. **Task 2: Implement OverlayStateMachine in overlay.py** - `fdfaa28` (feat — GREEN)
3. **Task 3: Create ax_detect.py** - `3c0a90f` (feat — GREEN)

**Plan metadata:** (docs commit follows)

_Note: TDD tasks have RED commit (test) + GREEN commit (feat) per task_

## Files Created/Modified
- `whisperkey_mac/overlay.py` - Extended with OverlayState enum, _VALID_TRANSITIONS, OverlayStateMachine, _build_content() NSVisualEffectView, delegation methods on OverlayPanel
- `whisperkey_mac/ax_detect.py` - New module: is_cursor_in_text_field() with AXUIElement calls, _TEXT_INPUT_ROLES frozenset
- `tests/test_overlay.py` - Extended with 8 state machine tests using MagicMock panel + callLater patch
- `tests/test_ax_detect.py` - New file: 4 test classes/functions (parametrized to 8 cases) mocking AX API at import site
- `pyproject.toml` - Added pyobjc-framework-ApplicationServices>=10.0 as explicit dependency

## Decisions Made
- OverlayStateMachine is a standalone class (not nested in OverlayPanel) so it can be tested in isolation with mock panel/labels injected at construction
- hide_after_paste() bypasses the transition guard — force-sets state to HIDDEN — because the paste branch skips RESULT entirely and adding TRANSCRIBING->HIDDEN to the guard dict would create an unintended valid transition for other callers
- String literal "AXSearchField" used in _TEXT_INPUT_ROLES instead of kAXSearchFieldRole (which does not exist as an importable constant in PyObjC 12.1)
- callLater patched at `whisperkey_mac.overlay.callLater` (import site) in tests — consistent with Phase 1 decision for callAfter

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None — all constants and API patterns were pre-verified in RESEARCH.md.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- overlay.py exports OverlayPanel, OverlayState, OverlayStateMachine, dispatch_to_main — ready for 02-02 wiring
- ax_detect.py exports is_cursor_in_text_field() — ready for transcription thread branch in 02-02
- Phase 3 TODO comments at exact lines in overlay.py where NSAnimationContext replaces setAlphaValue_/orderFront_/orderOut_
- All 22 tests green; no blockers

---
*Phase: 02-state-machine-thread-wiring*
*Completed: 2026-03-09*

## Self-Check: PASSED

- FOUND: whisperkey_mac/overlay.py
- FOUND: whisperkey_mac/ax_detect.py
- FOUND: tests/test_overlay.py
- FOUND: tests/test_ax_detect.py
- FOUND: .planning/phases/02-state-machine-thread-wiring/02-01-SUMMARY.md
- FOUND commit: 6eafa69 (test RED)
- FOUND commit: fdfaa28 (feat GREEN overlay)
- FOUND commit: 3c0a90f (feat GREEN ax_detect)
- 22 tests passed (0 failures)
