---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: native-menubar-redesign
status: planning_ready
stopped_at: Root planning set reorganized; current code baseline audited; native menu bar redesign is approved but not yet implemented
last_updated: "2026-03-31T12:00:00+08:00"
last_activity: 2026-03-31 — archived overlay-era root docs, promoted native menubar redesign to root planning source of truth, confirmed current test baseline
progress:
  total_workstreams: 3
  completed_workstreams: 0
  total_active_tasks: 3
  completed_active_tasks: 0
  percent: 0
---

# Project State

## Current Position

Current focus:

- Native menu bar redesign from `tasks/20260331__native-menubar-redesign/`

Current code reality:

- stable CLI-first runtime
- stable overlay HUD baseline
- LaunchAgent startup available
- no menu bar shell yet
- no native settings window yet
- no service-controller split yet

## Verification Snapshot

Latest local verification completed during planning cleanup:

- `71 passed in 1.07s`

Meaning:

- existing runtime and tests are stable enough to use as the refactor baseline
- the redesign has not started yet

## What Changed In Planning

Planning cleanup completed on 2026-03-31:

- former root `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, and `STATE.md` archived
- former root `research/` and `phases/` archived
- native menubar redesign promoted to current project mainline
- new root planning docs created to match the current direction

Archive snapshot:

- `archive/20260331__overlay-era-snapshot/`

## Immediate Next Actions

1. Implement `WS1` Native Shell And Service Lifecycle.
2. After shell ownership is stable, implement `WS2` Settings And Prompt Architecture.
3. Redesign the floating bar last in `WS3`.

## Open Risks

- Current runtime ownership is concentrated in `whisperkey_mac/main.py`, so shell extraction can easily tangle lifecycle concerns.
- Existing docs and README still describe the CLI-first workflow and will need later alignment after implementation starts.
- Permissions may need to be re-validated once the app launches through the new shell path.

## Deferred But Preserved

- Legacy online-correction manual verification with a real OpenAI API key
- Streaming or incremental ASR research

Those items remain valid backlog, but they no longer define the active project mainline.

---
Last updated: 2026-03-31
