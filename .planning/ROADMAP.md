# Roadmap: WhisperKey Native Menu Bar Redesign

## Overview

The completed overlay-era work is now baseline. The active roadmap is the native menu bar redesign defined in `tasks/20260331__native-menubar-redesign/`. Execution should stay coarse-grained until the new shell architecture is in place.

## Current Baseline

Already complete in code:

- CLI-driven runtime
- overlay HUD
- LaunchAgent login startup
- optional online correction
- Keychain integration

Archived planning history for that baseline lives under:

- `archive/20260331__overlay-era-snapshot/`

## Active Workstreams

- [ ] `WS1` Native Shell And Service Lifecycle
- [ ] `WS2` Settings And Prompt Architecture
- [ ] `WS3` Floating Bar Redesign

## Workstream Details

### WS1 Native Shell And Service Lifecycle

**Goal**

Introduce the app shell and separate it from transcription service control.

**Primary scope**

- menu bar item
- app lifecycle separated from service lifecycle
- start / stop service behavior
- no-Terminal daily launch path
- LaunchAgent management surface

**Likely files**

- `whisperkey_mac/main.py`
- `whisperkey_mac/menu_bar.py`
- `whisperkey_mac/service_controller.py`
- `whisperkey_mac/launch_agent.py`

**Exit criteria**

- menu bar icon exists
- app stays alive when service is stopped
- service can start and stop repeatedly
- login-start management is handled from app UI or app-owned logic

### WS2 Settings And Prompt Architecture

**Goal**

Replace setup-first user flow with native settings and stabilize config shape for future prompt modes.

**Primary scope**

- native settings window
- config migration and persistence cleanup
- Keychain bridge for API key editing
- extensible prompt mode model

**Likely files**

- `whisperkey_mac/config.py`
- `whisperkey_mac/settings_window.py`
- `whisperkey_mac/keychain.py`
- `whisperkey_mac/online_correct.py`
- `whisperkey_mac/main.py`

**Exit criteria**

- settings can be edited natively
- config no longer expects manual JSON editing for normal use
- API key remains outside config JSON
- prompt modes can expand without rewriting the core app flow

### WS3 Floating Bar Redesign

**Goal**

Turn the current transient HUD into a quiet persistent idle bar with cleaner active-state expansion.

**Primary scope**

- persistent idle bar
- recording / transcribing / result motion redesign
- compact return-to-idle behavior
- visual cleanup for bottom-center daily use

**Likely files**

- `whisperkey_mac/overlay.py`
- `whisperkey_mac/service_controller.py`
- `whisperkey_mac/main.py`

**Exit criteria**

- idle bar stays visible and restrained
- recording feedback is immediate and obvious
- transcribing and result states remain readable
- overlay collapses back to idle cleanly after each cycle

## Dependency Order

1. `WS1` Native Shell And Service Lifecycle
2. `WS2` Settings And Prompt Architecture
3. `WS3` Floating Bar Redesign

## Deferred After This Cycle

- manual legacy verification of online correction with a real API key
- streaming / incremental ASR research
- broader packaging and release hardening

## Progress

| Workstream | Status | Notes |
|---|---|---|
| WS1 Native Shell And Service Lifecycle | Not started | Current code is still CLI-centric |
| WS2 Settings And Prompt Architecture | Not started | Current primary surface is still `setup_wizard.py` |
| WS3 Floating Bar Redesign | Not started | Current overlay is transient HUD, not persistent idle bar |

---
Last updated: 2026-03-31
