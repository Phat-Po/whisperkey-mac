---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 02-state-machine-thread-wiring-02-PLAN.md (checkpoint:human-verify Task 3 pending)
last_updated: "2026-03-09T09:30:00.000Z"
last_activity: 2026-03-09 — Completed Phase 2 Plan 02 auto-tasks; awaiting smoke test checkpoint
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 4
  completed_plans: 4
  percent: 37
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-09)

**Core value:** 按住热键说话，松开就出现文字——零延迟感、零打断工作流。
**Current focus:** Phase 2 — State Machine & Thread Wiring

## Current Position

Phase: 2 of 4 (State Machine & Thread Wiring)
Plan: 2 of 2 in current phase
Status: Checkpoint — awaiting human smoke test verification (Task 3 of 02-02)
Last activity: 2026-03-09 — Completed Phase 2 Plan 02 auto-tasks (Tasks 1 & 2); checkpoint:human-verify pending

Progress: [████░░░░░░] 37%

## Performance Metrics

**Velocity:**
- Total plans completed: 2
- Average duration: ~32 min
- Total execution time: ~1.05 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 01-threading-foundation P01 | 3 min | 2 tasks | 4 files |
| Phase 01-threading-foundation P02 | ~60 min | 2 tasks | 2 files |

**Recent Trend:**
- Last 5 plans: ~32 min avg
- Trend: baseline

*Updated after each plan completion*
| Phase 02-state-machine-thread-wiring P01 | 10 | 3 tasks | 5 files |
| Phase 02-state-machine-thread-wiring P02 | 15 min | 2 tasks | 1 file |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Pre-Phase 1]: Use PyObjC/AppKit (NSPanel) for overlay — tkinter cannot do transparent windows on macOS
- [Pre-Phase 1]: NSApplicationActivationPolicyAccessory must be set before NSApp.run() to prevent focus steal
- [Pre-Phase 1]: All UI calls must go through dispatch_to_main() — calling AppKit from background thread causes silent crash
- [Phase 01-threading-foundation P01]: Mock callAfter via whisperkey_mac.overlay.callAfter (import site) not PyObjCTools.AppHelper.callAfter — from-import binds name locally
- [Phase 01-threading-foundation P01]: Plain Python class wrapper for NSPanel — no ObjC subclass needed; NSWindowStyleMaskNonactivatingPanel must be set at init time
- [Phase 01-threading-foundation P01]: Panel positioned at final coordinates in Phase 1 (alpha=0) so Phase 3 only animates alpha
- [Phase 01-threading-foundation P02]: callLater polling replaces MachSignals — MachSignals bypassed by pynput subprocess os._exit()
- [Phase 01-threading-foundation P02]: All AppKit imports confined to inside App.run() to prevent activation policy side effects
- [Phase 01-threading-foundation P02]: Ctrl+C shutdown message accepted as known issue — pynput subprocess os._exit() bypasses all Python cleanup; functional exit is correct
- [Phase 01-threading-foundation P02]: stderr=subprocess.DEVNULL added to osascript to suppress accessibility error noise
- [Phase 02-state-machine-thread-wiring]: OverlayStateMachine standalone class (not nested) — testable with mock panel/labels injected at construction
- [Phase 02-state-machine-thread-wiring]: hide_after_paste() force-sets HIDDEN bypassing guard — paste path skips RESULT entirely; no TRANSCRIBING->HIDDEN in guard dict
- [Phase 02-state-machine-thread-wiring]: String literal 'AXSearchField' in _TEXT_INPUT_ROLES — kAXSearchFieldRole does NOT exist as importable constant in PyObjC 12.1
- [Phase 02-state-machine-thread-wiring]: callLater patched at whisperkey_mac.overlay.callLater (import site) in tests — consistent with Phase 1 callAfter pattern
- [Phase 02-state-machine-thread-wiring P02]: Deferred imports (inside methods) for dispatch_to_main and is_cursor_in_text_field — matches existing pattern of confining AppKit-adjacent imports inside run()
- [Phase 02-state-machine-thread-wiring P02]: Safety guard (hasattr '_overlay') applied to all three modified methods to protect against pre-initialization race
- [Phase 02-state-machine-thread-wiring P02]: pyobjc-framework-ApplicationServices was already declared in pyproject.toml by Plan 02-01 — no change needed

### Pending Todos

None yet.

### Blockers/Concerns

- [Known issue — Phase 1]: Ctrl+C shutdown message not printed — pynput multiprocessing subprocess calls os._exit() before Python cleanup. Does not affect LaunchAgent/pkill shutdown. Noted for Phase 4 hardening review.

## Session Continuity

Last session: 2026-03-09T09:30:00.000Z
Stopped at: Checkpoint:human-verify — Task 3 of 02-02-PLAN.md (smoke test, app must be running)
Resume file: None
