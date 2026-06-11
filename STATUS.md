# WhisperKey — Status

## Current

### 2026-06-11 | v3.1.0 standard install experience + code audit fixes

Done this session:
- Diagnosed why the downloaded v3.0.2 app had a dead hotkey: no permission onboarding existed, the app never requested Accessibility/Input Monitoring, and ad-hoc signing reset TCC grants on every build (confirmed via `ax_trusted=False` rebuild loop in diag log).
- Built native permission onboarding: `permissions.py` (AX/Input Monitoring/Microphone check + request) and `onboarding.py` (setup window with live status, System Settings jump buttons, restart-to-finish; move-to-/Applications offer for Downloads installs with quarantine removal).
- Supervisor exit code 42 = silent relaunch protocol for the onboarding restart button.
- Audit fixes: watchdog no longer rebuild-loops while untrusted; diag log rotates at 10MB; ps metrics cached 2s with exception safety; keychain key now passed via `security -i` stdin (not ps-visible argv); supervisor notify can't kill the supervisor; malformed numeric env vars ignored; pynput pinned to 1.8.x.
- Menu bar: version line, Processing Mode submenu with checkmarks, permission warning item with fix entry, Open Diagnostics Log.
- Packaging: builds now sign with the stable Apple Development identity (TCC grants survive rebuilds); release produces a drag-install DMG with bilingual install note alongside the zip; READMEs updated.

Current state:
- v3.1.0 built and verified: `dist/release/WhisperKey-macOS-arm64-v3.1.0.dmg` (+ .zip). 221 tests pass.
- Not yet released to GitHub (needs operator confirmation for push/release).
- Operator must do one final interactive test: open the new app, walk the onboarding window, grant permissions once, restart via the window button.

Next steps:
1. Operator installs from the new DMG and verifies onboarding + hotkeys end-to-end.
2. Publish GitHub release v3.1.0 (gated on push confirmation).
3. Announce to 野生指挥部 + AI学习交流群（日不落版） per routing rule.

Decisions / notes:
- Free signing path chosen (Apple Development cert): own-machine TCC is now stable across builds; other users still see a one-time Gatekeeper prompt because the app is not notarized (needs paid Developer ID to remove).
- `WHISPERKEY_SIGN_IDENTITY` env var overrides the auto-detected signing identity.

### 2026-06-11 | v3.0.2 hotkey self-healing release

Done this session:
- Combined the recent hotkey reliability updates into v3.0.2.
- Added CGEventTap watchdog recovery for disabled pynput/raw taps.
- Added self-healing tap rebuild when Accessibility/Input Monitoring trust is restored after launch.
- Added escalation from repeated disabled tap re-enable attempts to full listener rebuild.
- Added regression tests for authorization recovery, repeated disabled taps, rebuild state preservation, and stale watchdog shutdown.

Current state:
- Release artifact target: `dist/release/WhisperKey-macOS-arm64-v3.0.2.zip`.
- GitHub release target: `https://github.com/Phat-Po/whisperkey-mac/releases/tag/v3.0.2`.

### 2026-06-04 | v3.0.1 release and announcement route corrected

Done this session:
- Fixed and released WhisperKey v3.0.1 to GitHub: `Phat-Po/whisperkey-mac`.
- Verified the release artifact path: `dist/release/WhisperKey-macOS-arm64-v3.0.1.zip`.
- Published the release announcement to `野生指挥部` and `AI学习交流群（日不落版）`.
- Corrected the Feishu routing rule: never use `肥泼's Feishu Assistant` as the release announcement target.
- Stored the durable routing rule in local Codex memory without duplicating the webhook secret.

Current state:
- GitHub release target is correct: `https://github.com/Phat-Po/whisperkey-mac/releases/tag/v3.0.1`.
- `AI学习交流群（日不落版）` announcements must use the WPD agent config key `FEISHU_AI_GROUP_WEBHOOK`.
- Do not hardcode external Feishu webhook URLs in this repository.

## Milestones

- 2026-06-11 | v3.0.2 packaged with hotkey self-healing for restored permissions and disabled event taps.
- 2026-06-04 | v3.0.1 shipped with the handsfree `cmd+\` hotkey fix and public release artifact.

## Archive

_(empty)_
