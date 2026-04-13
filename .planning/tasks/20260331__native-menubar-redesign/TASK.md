# Native Menu Bar Redesign Task

## Status
- Mode: plan
- Execution gate: wait for user phrase `批准执行`
- Date: 2026-03-31

## Goal
Turn WhisperKey from a Terminal-launched background process into a native-feeling macOS menu bar app that:
- launches without Terminal
- can auto-start after login via LaunchAgent
- exposes clear running state in the menu bar
- provides a native settings window
- keeps a minimal floating bar centered at the bottom of the screen
- expands that bar into an animated recording/transcribing HUD when active

## Confirmed Decisions
- Runtime shell UX should be removed for daily usage.
- The app should stay Python-based and use the existing PyObjC stack instead of being rewritten in Swift.
- Auto-start scope is `LaunchAgent` login start, not system-wide daemon start.
- The floating idle UI lives at the bottom center of the screen.
- Stopping from the menu bar means stopping the service and disabling hotkeys.
- Settings should include:
  - OpenAI API key
  - online model
  - online prompt mode
  - hotkey settings
  - language
  - Whisper model
  - launch-at-login toggle
- Prompt modes must be extensible beyond ASR correction, including future tasks such as Chinese-to-English and prompt polishing.

## Product Outcome
The final user experience should look like this:
1. User logs in and WhisperKey appears in the menu bar.
2. No Terminal window opens.
3. A thin, low-visibility floating bar remains at the bottom center of the screen.
4. When recording starts, the bar expands with motion and stronger visual feedback.
5. The menu bar icon can open settings, start service, stop service, and quit.
6. Settings changes persist without requiring the user to hand-edit JSON.

## Architectural Direction
Do not build a second app beside the current one. Refactor the existing runtime into these layers:

1. App shell
- Owns `NSApplication`, `NSStatusItem`, app lifecycle, and settings window.

2. Service controller
- Starts and stops hotkey listener, recorder, transcriber preload, and overlay state updates.
- Separates app lifecycle from transcription lifecycle.

3. Overlay system
- Reworks the current panel from transient HUD to persistent idle bar plus expanded active states.

4. Settings and config bridge
- Moves user-facing setup from CLI wizard dominance to a native window backed by the existing config and keychain systems.

5. Launch agent manager
- Creates, updates, removes, and inspects the user LaunchAgent entry from inside the app.

## Coarse Workstreams
This task should stay split at coarse granularity only:

1. Native shell and service lifecycle
- Menu bar item
- start/stop service behavior
- no-Terminal launch path
- LaunchAgent management

2. Settings and prompt architecture
- native settings window
- config migration
- keychain integration
- extensible prompt mode design

3. Floating bar redesign
- persistent idle bar
- active recording/transcribing expansion
- compact result behavior and animation

## Affected Code Areas
- `whisperkey_mac/main.py`
- `whisperkey_mac/overlay.py`
- `whisperkey_mac/config.py`
- `whisperkey_mac/online_correct.py`
- `whisperkey_mac/keychain.py`
- `pyproject.toml`
- `README.md`
- `README.zh.md`

Expected new modules:
- `whisperkey_mac/menu_bar.py`
- `whisperkey_mac/settings_window.py`
- `whisperkey_mac/service_controller.py`
- `whisperkey_mac/launch_agent.py`

## Verification Gates
Before completion, verify:
- Python runtime remains `>= 3.10`
- tests pass or any failures are explained
- app can launch without Terminal
- menu bar icon appears and reflects service state
- start/stop disables and re-enables hotkeys correctly
- settings save and reload correctly
- API key stores in Keychain, not config JSON
- LaunchAgent can be enabled and survives logout/login
- idle bar stays visible at bottom center
- recording and transcribing animation transitions are visually correct

## Risks
- Accessibility and Input Monitoring permissions may need to be granted again for the packaged `.app`.
- Global hotkeys and menu bar startup order may race if service startup is not explicitly staged.
- Packaging may surface path differences for config, keychain, and helper binaries.
- Existing tests appear CLI-oriented and will need coverage expansion around Cocoa-facing behavior.

## Non-Goals For First Pass
- Full Swift rewrite
- Deep preference panes with advanced theming
- Multiple floating widgets or drag-and-drop positioning
- Cloud sync of settings

## Immediate Next Step
If approved, execute the three workstreams in order:
1. Native shell and lifecycle
2. Settings and prompt architecture
3. Floating bar redesign and final packaging pass
