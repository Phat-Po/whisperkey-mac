# Requirements: WhisperKey Native Menu Bar Redesign

**Defined:** 2026-03-31
**Supersedes:** overlay-only root requirements archived under `archive/20260331__overlay-era-snapshot/`

## Goal

Turn WhisperKey from a CLI-launched background workflow into a native-feeling macOS menu bar app while preserving the already-working dictation, overlay, and LaunchAgent baseline.

## Baseline Assumptions

The following are already present and should be treated as migration inputs, not fresh scope:

- hotkey recording and transcription
- overlay HUD states
- JSON config loading and saving
- Keychain-backed OpenAI API key lookup
- LaunchAgent login startup
- setup / permissions / help CLI commands

## Current-Cycle Requirements

### App Shell

- [ ] `SHELL-01`: WhisperKey runs as a menu bar app with an `NSStatusItem`.
- [ ] `SHELL-02`: Daily use does not require a visible Terminal window.
- [ ] `SHELL-03`: The menu bar surface clearly reflects service state: running, stopped, or blocked by permissions.
- [ ] `SHELL-04`: The app can stay alive while the transcription service is stopped.
- [ ] `SHELL-05`: Quit is separate from stop-service.

### Service Lifecycle

- [ ] `SRV-01`: Hotkey listener, recorder, transcription preload, and overlay updates are managed by a dedicated service lifecycle layer.
- [ ] `SRV-02`: Stop-service disables hotkeys and active dictation behavior without quitting the app shell.
- [ ] `SRV-03`: Start-service can re-enable the same runtime cleanly more than once in one session.

### Settings And Config

- [ ] `SET-01`: A native settings window replaces setup-first CLI flow as the primary configuration surface.
- [ ] `SET-02`: Settings include language, Whisper model, hotkeys, online model, online prompt mode, and launch-at-login toggle.
- [ ] `SET-03`: Settings persist without requiring manual JSON editing.
- [ ] `SET-04`: OpenAI API key is stored in Keychain, never in config JSON.
- [ ] `SET-05`: Prompt mode architecture is extensible beyond ASR correction.
- [ ] `SET-06`: A custom prompt mode can be represented in config without rewriting the app flow.

### Launch At Login

- [ ] `BOOT-01`: Launch-at-login can be enabled or disabled from the app UI.
- [ ] `BOOT-02`: LaunchAgent management is handled inside the app, not only via README shell instructions.
- [ ] `BOOT-03`: Login startup remains user-scope and survives logout/login.

### Overlay Redesign

- [ ] `BAR-01`: The overlay has a persistent bottom-center idle bar.
- [ ] `BAR-02`: Recording state expands from the idle bar within roughly 200 ms and is visually unmistakable.
- [ ] `BAR-03`: Transcribing state remains readable without abrupt jumps.
- [ ] `BAR-04`: Result state is compact, legible, and collapses back to idle rather than disappearing completely.
- [ ] `BAR-05`: The redesigned bar remains non-intrusive during unrelated work.

### Migration And Backward Safety

- [ ] `MIG-01`: Existing dictation behavior remains functional while the app shell is refactored.
- [ ] `MIG-02`: Existing config values are migrated or reused safely.
- [ ] `MIG-03`: Existing CLI helper commands may remain as fallback tools during migration, but they are no longer the primary daily UX.

### Verification

- [ ] `VER-01`: Automated tests still pass or any failure is explicitly explained.
- [ ] `VER-02`: Native shell launch path works without Terminal-driven daily usage.
- [ ] `VER-03`: Menu bar state changes track service start and stop correctly.
- [ ] `VER-04`: Settings changes save and reload correctly.
- [ ] `VER-05`: LaunchAgent toggle works end to end.
- [ ] `VER-06`: Overlay transitions remain visually correct after redesign.

## Deferred Backlog

These are not part of the current redesign acceptance target:

- manual OpenAI correction verification with a real key as a separate legacy follow-up
- streaming or incremental ASR research
- full packaging and distribution strategy beyond what is needed for this redesign cycle

---
Last updated: 2026-03-31
