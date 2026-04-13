# UIUX Brief

## Intent
The UI must feel like a quiet system utility, not a developer tool. It should remain legible and intentional while staying visually restrained when idle.

## Primary Surfaces
1. Menu bar icon
- Always present when the app shell is running.
- Must communicate whether service is active, paused, or blocked by permissions.
- Menu copy should be plain and operational.

2. Settings window
- Native macOS sheet/window feel.
- Small surface area, no wizard framing.
- Group settings into practical sections:
  - General
  - Transcription
  - Online processing
  - Hotkeys
  - Startup and permissions

3. Bottom floating bar
- Idle state should be thin, centered, low contrast, and easy to ignore.
- Active state should expand smoothly rather than pop abruptly.
- Result state should be compact and short-lived, then return to idle bar.

## Visual Direction
- Native-first, glassy, restrained, and precise.
- Use the existing translucent visual effect base but simplify the silhouette.
- Avoid oversized HUD behavior in the idle state.
- Motion should communicate state transitions, not decorate them.

## Motion Rules
- Idle -> recording: expand width and height with a short ease-out animation.
- Recording -> transcribing: maintain position and reduce motion complexity.
- Transcribing -> result: prioritize text legibility, then contract back to idle.
- Any cancel path should collapse quickly and calmly.

## Floating Bar Behavior
- Default anchor: bottom center.
- Default posture: persistent thin pill.
- During recording: increase visual weight, show waveform-style animation.
- During transcribing: quieter animated dots or equivalent restrained processing cue.
- During result: show compact text and a short hint, then collapse to idle instead of disappearing.

## Settings UX Rules
- API key entry should never expose stored secrets in plain text once saved.
- Prompt mode selector must anticipate future additions.
- Custom prompt mode should have a multiline editor, but only when that mode is selected.
- Launch at login should be a direct toggle, not a doc-only instruction.
- Permission shortcuts should open the correct macOS panes from inside the UI.

## UX Acceptance Criteria
- User can understand whether WhisperKey is running by glancing at the menu bar.
- User can stop the service without quitting the app.
- User never needs Terminal for normal daily use.
- Idle overlay does not feel intrusive during unrelated work.
- Recording state is unmistakable within 200 ms of hotkey activation.
- Settings are discoverable in one click from the menu bar.
