---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verification_pending
stopped_at: Codex input compatibility validated; optional OpenAI correction still needs one manual verification with a real API key
last_updated: "2026-03-13T02:20:00.000Z"
last_activity: 2026-03-13 — Verified direct input in com.openai.codex, added permissions command, removed duplicate installs, and lowered AX detection log noise for known-compatible apps
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 10
  completed_plans: 9
  percent: 90
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-12)

**Core value:** 按住热键说话，松开就出现文字——零延迟感、零打断工作流。
**Current focus:** Post-MVP Queue — Plan 5 manual verification (optional OpenAI correction) and compatibility cleanup for known chat inputs

## Current Position

Phase: Post-MVP Queue
Plan: 5 of 6 (Result Readability & Optional Online Correction)
Status: Verification pending — multiline HUD and Codex direct-input behavior are validated; real OpenAI key path still needs manual check
Last activity: 2026-03-13 — Codex direct-input compatibility confirmed via targeted AppleScript fallback; permission helper and duplicate-install cleanup completed

Progress: [█████████░] 90%

## Performance Metrics

**Velocity:**
- Total plans completed: 7
- Average duration: ~32 min
- Total execution time: ~1.5 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 01-threading-foundation P01 | 3 min | 2 tasks | 4 files |
| Phase 01-threading-foundation P02 | ~60 min | 2 tasks | 2 files |
| Phase 02-state-machine-thread-wiring P01 | 10 min | 3 tasks | 5 files |
| Phase 02-state-machine-thread-wiring P02 | 15 min | 2 tasks | 1 file |
| Phase 03-visual-polish-animation | ad-hoc | 2 tasks | 6 files |
| Phase 04-edge-cases-hardening | ad-hoc | 1 task | 3 files |

**Recent Trend:**
- Last 6 plans/tasks: mixed plan + direct implementation
- Trend: milestone complete; future work is queued as explicit Post-MVP follow-up

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
- [Phase 03-visual-polish-animation]: Use layer-backed CALayer indicators for bars/dots so public OverlayPanel API stays unchanged
- [Phase 03-visual-polish-animation]: Reuse generation tokens for timer invalidation and fade completion guards — stale callLater callbacks become no-ops after a new state change
- [Phase 04-edge-cases-hardening]: Do not enter TRANSCRIBING until `stop_and_save()` returns a valid recording; short/empty captures must fast-dismiss the HUD
- [Phase 04-edge-cases-hardening]: Treat Finder as clipboard-only even if AX reports a text-like element; avoiding false-positive paste attempts is more important than aggressive auto-injection
- [Phase 04-edge-cases-hardening]: LaunchAgent verification is satisfied by an installed GUI-session plist with `LimitLoadToSessionType = Aqua` plus a running `launchctl print gui/<uid>/com.whisperkey` job
- [Plan 05]: Long result text should expand the HUD vertically rather than widening the panel; recording and transcribing states always reset to the base 74pt layout
- [Plan 05]: Online correction is optional and uses the user's own OpenAI API key; no WhisperKey-hosted backend or OAuth flow is introduced
- [Plan 05]: Key lookup order is `OPENAI_API_KEY` first, then macOS Keychain; any unavailable dependency, timeout, or API failure must fall back to the raw transcript
- [Plan 05 follow-up]: Treat `com.openai.codex` as a known injectable app even when AX text-field detection misses; prefer targeted paste and suppress the warning log for that bundle
- [Post-MVP Queue]: Streaming remains a separate research spike after the current optional online-correction path is manually verified

### Pending Todos

- Run a manual Phase 5 smoke with a real OpenAI API key:
  1. `whisperkey setup` can save an OpenAI key to Keychain
  2. Online correction enabled + valid key uses corrected text in overlay and final paste
  3. Missing/invalid key cleanly falls back to the raw transcript
- After Phase 5 manual verification passes, begin Plan 6 as the streaming ASR research spike

### Blockers/Concerns

- [Known issue — Phase 1]: Ctrl+C shutdown message not printed — pynput multiprocessing subprocess calls os._exit() before Python cleanup. Does not affect LaunchAgent/pkill shutdown.
- [Verification gap]: Online correction path still needs one manual run with a real OpenAI API key; automated tests only cover mocks/fallbacks.
- [Operational note]: Online correction now requires the `openai` package in the runtime environment in addition to the repo dependency declaration.

## Session Continuity

Last session: 2026-03-12T13:25:00.000Z
Stopped at: Plan 5 code complete; waiting for manual OpenAI-key verification before starting Plan 6
Resume file: None
