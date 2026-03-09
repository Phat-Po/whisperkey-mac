# Roadmap: WhisperKey — Recording Overlay UI

## Overview

This roadmap delivers a floating visual overlay to the existing WhisperKey dictation tool. The overlay must display recording, transcribing, and result states without stealing focus or mouse events from the user's active application. The build order is architecture-prescribed and non-negotiable: threading foundation first, state machine second, visual polish third, hardening last. Every phase delivers a verifiable capability; no phase can be safely skipped.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Threading Foundation** - Replace stop_event.wait() with NSApp run loop; invisible NSPanel correctly configured; all existing threads intact
- [x] **Phase 2: State Machine & Thread Wiring** - Connect worker threads to overlay states; branch logic (paste vs clipboard); auto-dismiss timer (completed 2026-03-09)
- [ ] **Phase 3: Visual Polish & Animation** - Waveform bars, pulsing dots, fade transitions, result text — all at specified timings
- [ ] **Phase 4: Edge Cases & Hardening** - Rapid keypress guards, NSTimer leak prevention, LaunchAgent boot verification

## Phase Details

### Phase 1: Threading Foundation
**Goal**: NSApp run loop is running; all existing hotkey, audio capture, and transcription threads work as before; an invisible NSPanel exists that is correctly configured for overlay use
**Depends on**: Nothing (first phase)
**Requirements**: OVL-01, OVL-02, OVL-03
**Success Criteria** (what must be TRUE):
  1. Hotkey press starts recording and key release triggers transcription — identical behavior to before the architectural change
  2. An NSPanel window exists at floating level, configured as borderless, transparent, click-through, and visible on all Spaces
  3. The overlay window never steals keyboard focus from the active application when it appears or when NSApp.run() starts
  4. The `dispatch_to_main()` utility exists and routes UI calls safely from worker threads to the main run loop
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — Create overlay.py (OverlayPanel + dispatch_to_main) and pytest scaffold (Wave 1)
- [x] 01-02-PLAN.md — Wire NSApp.run() into main.py replacing stop_event.wait(); declare pyobjc dep; smoke test (Wave 2)

### Phase 2: State Machine & Thread Wiring
**Goal**: Overlay responds correctly to the full hotkey lifecycle — press shows overlay, release transitions to transcribing state, transcription completion routes to paste-or-clipboard branch and auto-dismisses
**Depends on**: Phase 1
**Requirements**: RST-01, RST-02, RST-03, RST-04, DET-01, DET-02
**Success Criteria** (what must be TRUE):
  1. Pressing the hotkey causes the overlay to appear; releasing it transitions overlay to a "transcribing" placeholder state
  2. When transcription completes and cursor is in a text input field, text is silently injected and the overlay disappears within 200ms
  3. When transcription completes and cursor is not in a text input field, the overlay shows the transcribed text and "已复制到剪贴板", then auto-dismisses after 3 seconds
  4. Accessibility API failure or None result defaults to the clipboard path without crashing
  5. State machine rejects invalid transitions — a second hotkey press mid-transcription does not corrupt overlay state
**Plans**: 2 plans

Plans:
- [ ] 02-01-PLAN.md — State machine (OverlayState enum + OverlayStateMachine), content view (NSVisualEffectView), AX detect module, unit tests (Wave 1)
- [ ] 02-02-PLAN.md — Wire keyboard callbacks and transcription branch to overlay; paste vs clipboard branch in main.py (Wave 2)

### Phase 3: Visual Polish & Animation
**Goal**: Overlay displays waveform bars during recording, pulsing dots during transcribing, and result text in the clipboard branch — all with the exact animation timings from the spec
**Depends on**: Phase 2
**Requirements**: REC-01, REC-02, TRN-01, TRN-02
**Success Criteria** (what must be TRUE):
  1. During recording, the overlay displays 4-6 animated bars moving in a sine-wave pattern at ~30fps — motion is visible and continuous
  2. The overlay appears with a 150ms fade-in and 8pt upward slide (ease-out) when recording starts
  3. After key release, the overlay smoothly transitions to 3 pulsing dots (300ms per dot, 900ms full cycle) without any flash or blank frame
  4. After paste, the overlay fades out in 200ms; after clipboard display, it fades out in 400ms — transitions are smooth with no abrupt cut
**Plans**: TBD

Plans:
- [ ] 03-01: Implement waveform bar animation (NSTimer 30fps, NSBezierPath, idle sine-wave) and pulsing dots (NSTimer, NSAttributedString or custom drawing)
- [ ] 03-02: Implement fade-in appear animation (150ms, 8pt slide-up, ease-out) and fade-out dismiss animations (200ms paste / 400ms clipboard) using NSAnimationContext

### Phase 4: Edge Cases & Hardening
**Goal**: Overlay handles rapid keypresses gracefully, NSTimer instances are invalidated on hide to prevent memory leaks, and LaunchAgent boot behavior is verified with the correct session type
**Depends on**: Phase 3
**Requirements**: (none new — hardening of Phase 1-3 behavior)
**Success Criteria** (what must be TRUE):
  1. Pressing and releasing the hotkey rapidly 5+ times in a row does not leave the overlay stuck in a wrong state
  2. After the overlay hides, no NSTimer continues firing — verified by console log or memory profiler showing no retained cycles
  3. WhisperKey starts correctly after macOS login via LaunchAgent — overlay appears on first hotkey press with no crash
**Plans**: TBD

Plans:
- [ ] 04-01: Add rapid-keypress protection (state machine transition guards); audit and invalidate all NSTimer instances on overlay hide; verify LaunchAgent plist uses LimitLoadToSessionType = Aqua

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Threading Foundation | 2/2 | Complete | 2026-03-09 |
| 2. State Machine & Thread Wiring | 2/2 | Complete   | 2026-03-09 |
| 3. Visual Polish & Animation | 0/2 | Not started | - |
| 4. Edge Cases & Hardening | 0/1 | Not started | - |
