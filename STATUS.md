# WhisperKey — Status

## Current

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
