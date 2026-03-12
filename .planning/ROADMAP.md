# Roadmap: WhisperKey — Recording Overlay UI

## Overview

This roadmap delivers a floating visual overlay to the existing WhisperKey dictation tool. The overlay must display recording, transcribing, and result states without stealing focus or mouse events from the user's active application. The build order is architecture-prescribed and non-negotiable: threading foundation first, state machine second, visual polish third, hardening last. Every phase delivers a verifiable capability; no phase can be safely skipped. Post-MVP improvements are queued separately so the current v1 milestone stays stable.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Threading Foundation** - Replace stop_event.wait() with NSApp run loop; invisible NSPanel correctly configured; all existing threads intact
- [x] **Phase 2: State Machine & Thread Wiring** - Connect worker threads to overlay states; branch logic (paste vs clipboard); auto-dismiss timer (completed 2026-03-09)
- [x] **Phase 3: Visual Polish & Animation** - Manual smoke passed on 2026-03-12; waveform bars, pulsing dots, fade transitions, and result text are live
- [x] **Phase 4: Edge Cases & Hardening** - Rapid keypress regression fixed, stale dismiss callbacks guarded, LaunchAgent Aqua session verified on 2026-03-12

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
  2. When transcription completes and cursor is in a text input field, text is silently injected and the overlay briefly shows the transcript with "已输入"
  3. When transcription completes and cursor is not in a text input field, the overlay shows the transcribed text and "已复制到剪贴板", then auto-dismisses after 3 seconds
  4. Accessibility API failure or None result defaults to the clipboard path without crashing
  5. State machine rejects invalid transitions — a second hotkey press mid-transcription does not corrupt overlay state
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — State machine (OverlayState enum + OverlayStateMachine), content view (NSVisualEffectView), AX detect module, unit tests (Wave 1)
- [x] 02-02-PLAN.md — Wire keyboard callbacks and transcription branch to overlay; paste vs clipboard branch in main.py (Wave 2)

### Phase 3: Visual Polish & Animation
**Goal**: Overlay displays waveform bars during recording, pulsing dots during transcribing, and result text in the clipboard branch — all with the exact animation timings from the spec
**Depends on**: Phase 2
**Requirements**: REC-01, REC-02, TRN-01, TRN-02
**Success Criteria** (what must be TRUE):
  1. During recording, the overlay displays 4-6 animated bars moving in a sine-wave pattern at ~30fps — motion is visible and continuous
  2. The overlay appears with a 150ms fade-in and 8pt upward slide (ease-out) when recording starts
  3. After key release, the overlay smoothly transitions to 3 pulsing dots (300ms per dot, 900ms full cycle) without any flash or blank frame
  4. After direct input, the overlay keeps the transcript visible briefly, then fades out in 250ms; after clipboard display, it fades out in 400ms; cancel/no-speech paths dismiss quickly with no abrupt cut
**Plans**: 2 plans

Plans:
- [x] 03-01: Implement waveform bar animation (CALayer 30fps idle sine-wave bars) and pulsing dots (CALayer pulses, 300ms/dot, 900ms cycle)
- [x] 03-02: Implement fade-in appear animation (150ms, 8pt slide-up, ease-out) and result dismiss animations (250ms input-result / 400ms clipboard / 200ms cancel)

### Phase 4: Edge Cases & Hardening
**Goal**: Overlay handles rapid keypresses gracefully, stale timer callbacks become harmless after hide/state changes, and LaunchAgent boot behavior is verified with the correct session type
**Depends on**: Phase 3
**Requirements**: (none new — hardening of Phase 1-3 behavior)
**Success Criteria** (what must be TRUE):
  1. Pressing and releasing the hotkey rapidly 5+ times in a row does not leave the overlay stuck in a wrong state
  2. After the overlay hides, stale dismiss callbacks are ignored and do not resurrect or re-hide the overlay incorrectly
  3. WhisperKey starts correctly after macOS login via LaunchAgent — verified LaunchAgent uses `LimitLoadToSessionType = Aqua` and is running in the GUI session
**Plans**: 1 plan

Plans:
- [x] 04-01: Add rapid-keypress protection and cancel-path cleanup; guard stale dismiss callbacks after hide; verify LaunchAgent plist uses LimitLoadToSessionType = Aqua

## Post-MVP Queue

These items are explicitly outside the current MVP scope. They should only start after Phase 4 is complete and the existing overlay flow is stable in daily use.

### Plan 5: Result Readability & Optional Online Correction
**Goal**: Improve readability for longer transcripts and offer optional OpenAI-backed transcript correction without introducing a WhisperKey-hosted backend
**Depends on**: Phase 4
**Success Criteria** (what must be TRUE):
  1. Long result text can display up to 2-3 lines with adaptive overlay height before truncation
  2. Optional OpenAI correction can refine common ASR wording mistakes using the user's own API key
  3. If online correction is unavailable or fails, WhisperKey falls back to the raw transcript with no crash or noticeable hang
**Plans**: 2 plans

Plans:
- [x] 05-01: Expand result HUD to multiline layout (2-3 lines max), adaptive height, and truncation only after line budget is exhausted
- [x] 05-02: Add optional OpenAI correction after ASR using the user's own API key via Keychain or `OPENAI_API_KEY`, with failure-safe fallback to raw text

### Plan 6: Streaming Transcription Research Spike
**Goal**: Determine whether WhisperKey should support real-time or near-real-time transcript previews while preserving the local-first constraint
**Depends on**: Plan 5
**Success Criteria** (what must be TRUE):
  1. A written comparison exists for latency, accuracy, CPU usage, memory usage, and integration complexity on Apple Silicon
  2. At least one viable local-first architecture is identified for incremental transcript rendering
  3. No production code is merged until the research spike shows clear benefit over the current batch transcription flow
**Plans**: 1 plan

Plans:
- [ ] 06-01: Run a local streaming ASR research spike comparing [whisper.cpp](https://github.com/ggml-org/whisper.cpp) and [SimulStreaming](https://github.com/ufal/SimulStreaming) as future architectures for incremental transcript display

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4, then the Post-MVP queue begins at Plans 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Threading Foundation | 2/2 | Complete | 2026-03-09 |
| 2. State Machine & Thread Wiring | 2/2 | Complete | 2026-03-09 |
| 3. Visual Polish & Animation | 2/2 | Complete | 2026-03-12 |
| 4. Edge Cases & Hardening | 1/1 | Complete | 2026-03-12 |
| 5. Result Readability & Optional Online Correction | 2/2 | Verification pending | - |
| 6. Streaming Transcription Research Spike | 0/1 | Queued (Post-MVP) | - |
