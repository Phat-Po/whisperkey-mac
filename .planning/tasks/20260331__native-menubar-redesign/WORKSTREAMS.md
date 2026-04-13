# Workstreams

## WS1 Native Shell And Lifecycle
### Scope
- introduce menu bar app shell
- separate app shell from transcription service
- add service start/stop controls
- add LaunchAgent install/remove/status handling
- ensure packaged app launches without Terminal

### Exit Criteria
- app shell runs with menu bar icon
- service can be started and stopped repeatedly
- stopping service disables hotkeys
- login launch path is managed from app UI

## WS2 Settings And Prompt System
### Scope
- replace setup-first flow with native settings window
- extend config schema for prompt modes and UI state
- preserve Keychain-backed API key storage
- generalize online correction into prompt-mode execution

### Exit Criteria
- settings can be edited natively
- config persists without manual JSON edits
- API key remains outside config JSON
- prompt modes can be added without rewriting the app flow

## WS3 Floating Bar Redesign
### Scope
- convert transient overlay into persistent idle bar
- redesign active recording/transcribing/result transitions
- tighten layout, dimensions, and motion for bottom-center use
- ensure result display collapses back to idle state

### Exit Criteria
- idle bar remains visible and non-intrusive
- recording expansion is visually obvious
- transcribing and result states are readable
- overlay returns to idle cleanly after each cycle

## Dependency Order
1. WS1
2. WS2
3. WS3

## Why This Split
- WS1 de-risks application lifecycle and startup behavior first.
- WS2 defines the config surface before the final UI is wired deeply into it.
- WS3 depends on the finalized lifecycle and settings shape, so it should come last.
