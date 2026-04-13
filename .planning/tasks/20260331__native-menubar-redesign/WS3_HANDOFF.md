# WS3 Handoff

## Scope

This handoff is for `WS3` only:

- persistent bottom-center idle bar
- active recording expansion
- transcribing state polish
- result-state collapse back to idle

Do not reopen `WS1` or `WS2` architecture unless required by a concrete blocker.

## Current Baseline

Completed before this handoff:

- `WS1` minimal native shell
  - menu bar app exists
  - service can start and stop without quitting app shell
  - LaunchAgent can be toggled from the app
- `WS2` minimal native settings flow
  - native settings window exists
  - config saves and reapplies live
  - online processing now supports prompt modes:
    - `disabled`
    - `asr_correction`
    - `custom`

Current verification baseline:

- `83 passed in 10.15s`

## Relevant Files

Primary files for `WS3`:

- `whisperkey_mac/overlay.py`
- `whisperkey_mac/service_controller.py`

Secondary files that may need small touch points:

- `whisperkey_mac/main.py`
- `tests/test_overlay.py`

Files that now exist and should be treated as stable inputs:

- `whisperkey_mac/menu_bar.py`
- `whisperkey_mac/settings_window.py`
- `whisperkey_mac/launch_agent.py`
- `whisperkey_mac/config.py`

## What The Current Overlay Does

Current overlay behavior is still the old transient HUD:

- hidden by default
- shows recording bars on activation
- shows transcribing dots
- shows result text
- dismisses back to hidden

It is not yet a persistent idle bar.

## WS3 Target

Replace the transient-only posture with:

1. Idle state
- thin, persistent, bottom-center bar
- visually quiet
- always present while service is running

2. Recording state
- expands from the idle bar
- obvious within roughly 200 ms
- keeps the current clarity of the recording signal

3. Transcribing state
- smooth transition from recording
- no harsh jump or flash

4. Result state
- compact readable result
- collapses back to idle bar
- should not fully disappear unless service stops

## Important Constraints

- Preserve current service lifecycle from `service_controller.py`
- Preserve current menu bar and settings behavior
- Do not regress existing dictation flow
- Do not introduce a second overlay system beside `overlay.py`
- Keep AppKit work on the main thread

## Technical Notes

- `ServiceController.ensure_overlay()` currently creates the overlay once and reuses it
- `ServiceController.stop_service()` currently hides the overlay immediately
- `OverlayPanel.create(...)` and the existing state machine already support recording / transcribing / result transitions
- The main redesign likely belongs inside `overlay.py` rather than higher up

## Likely Implementation Direction

1. Introduce a real idle visual state in `overlay.py`
2. Ensure the idle bar is shown when service starts
3. Keep idle visible after result dismissal
4. Only fully hide overlay when service stops
5. Update tests to reflect the new hidden-vs-idle semantics

## Risk Areas

- Existing tests assume `HIDDEN` as the post-result resting state in several paths
- `hide_after_paste()` semantics may need split behavior:
  - collapse to idle during normal runtime
  - fully hide when stopping service
- layout and animation code in `overlay.py` is already non-trivial; avoid widening write scope into unrelated modules

## Recommended First Step For Next Agent

Read and modify:

- `whisperkey_mac/overlay.py`
- `tests/test_overlay.py`

Start by defining the new resting-state model clearly:

- decide whether to add a new `IDLE` state or reinterpret `HIDDEN`
- then update renderer and dismiss paths to converge on that model

---
Prepared: 2026-03-31
