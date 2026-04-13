# WhisperKey

## What This Is

WhisperKey is a macOS local voice input tool. Hold a hotkey to record, release to transcribe, then inject or copy the text into the current app. The current codebase already delivers a stable CLI-driven background workflow with a bottom HUD overlay.

## Current Product Baseline

Implemented and validated in the current codebase:

- CLI entrypoint: `whisperkey`
- interactive setup wizard
- permission helper and diagnostics helper
- configurable hold-to-talk and hands-free hotkeys
- local faster-whisper transcription
- bottom overlay HUD with recording, transcribing, and result states
- multiline result HUD
- optional OpenAI online correction using the user's own API key
- Keychain-backed OpenAI key lookup
- LaunchAgent-based login autostart

## Active Initiative

Current primary initiative:

- `tasks/20260331__native-menubar-redesign/`

This initiative supersedes the old overlay-era project root docs. The old root planning set has been archived under:

- `archive/20260331__overlay-era-snapshot/`

## Target Outcome

WhisperKey should evolve from a Terminal-oriented background tool into a native-feeling macOS menu bar app that:

- launches without showing Terminal in daily use
- appears in the menu bar after login
- can start and stop the transcription service without quitting the app
- exposes a native settings window instead of relying on JSON edits and setup-first CLI flow
- keeps a quiet bottom-center idle bar and expands into the active HUD only when needed

## Current Reality Check

What exists today:

- `whisperkey_mac/main.py` still owns app lifecycle, hotkey lifecycle, transcription flow, and CLI command routing in one place
- `whisperkey_mac/overlay.py` already provides the current HUD implementation
- `whisperkey_mac/setup_wizard.py` is still the main user-facing configuration surface
- `README.md` and `README.zh.md` still document the CLI-first workflow

What does not exist yet:

- menu bar shell (`NSStatusItem`)
- native settings window
- dedicated service controller
- in-app LaunchAgent manager
- extensible prompt-mode architecture beyond the current online-correction flow
- persistent idle bar behavior replacing the current transient-only overlay behavior

## Constraints

- Platform: macOS only
- Language: Python only for this redesign cycle
- UI stack: PyObjC/AppKit, not Swift rewrite
- Startup scope: per-user `LaunchAgent`, not system daemon
- Secrets: API key stays in Keychain, not config JSON
- Migration rule: preserve current dictation reliability while refactoring app shell and settings UX

## Non-Goals For First Pass

- full Swift rewrite
- deep visual theming system
- settings sync across devices
- history database
- multi-widget overlay system

## Success Standard

Planning is considered healthy only if these root docs match actual current direction:

- root docs describe the menubar redesign as the active mainline
- legacy overlay planning stays preserved but archived
- active task package and root docs do not contradict each other

---
Last updated: 2026-03-31
