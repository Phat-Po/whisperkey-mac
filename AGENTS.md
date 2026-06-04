# Vibemouse Mac / WhisperKey Agent Protocol

## Purpose
macOS voice-input app: hold a hotkey to record, transcribe locally with faster-whisper, optionally clean/correct text with an OpenAI-compatible service, and paste into the active app.

## Stack And Runtime
- Python 3.10+ package `whisperkey-mac`.
- faster-whisper, OpenAI SDK, pynput, sounddevice/soundfile, pyobjc.
- PyInstaller packaging scripts for macOS app bundles.
- macOS permissions: Accessibility, Input Monitoring, Microphone.

## Source Of Truth
- `README.md` and `README.zh.md` for product behavior and setup.
- `pyproject.toml` for dependencies, entry points, and package metadata.
- `.planning/` files for current phase work.
- `CONTEXT.md` is auto-generated and incomplete.

## Commands
- `python3 -m venv .venv && source .venv/bin/activate`
- `pip install -e .`
- `whisperkey`
- `pytest`
- `python -m pytest`
- `packaging/macos/build_app.sh`
- `packaging/macos/package_release.sh`

## Release And Announcement Routing
- GitHub release target is `Phat-Po/whisperkey-mac`.
- Do not use the Feishu chat named `肥泼's Feishu Assistant` for release announcements.
- Release announcements go to `野生指挥部` and `AI学习交流群（日不落版）`.
- `野生指挥部` uses the known WPD Feishu bot chat route: `oc_ffbb508c573771fd23c0b6e4ef2e78c8`.
- `AI学习交流群（日不落版）` uses the external Feishu bot webhook stored in the WPD agent configuration as `FEISHU_AI_GROUP_WEBHOOK`; do not hardcode the webhook URL in this repo or in memory files.

## Risk Gates
- Do not edit Keychain storage behavior, API key handling, or launch-at-login behavior casually.
- Confirm before installing/uninstalling LaunchAgents, modifying macOS permissions flows, or changing packaging/signing/notarization outputs.
- Do not commit real API keys, local model caches, generated app bundles, or release zips unless explicitly requested.
- Confirm before deleting build/dist artifacts.
- Confirm before `git push`.

## Workflow
- Prefer focused tests in `tests/` for behavior changes.
- Keep local-first/offline transcription as a core product principle.
- For UI behavior, verify menu bar, overlay, settings window, and fallback behavior when feasible.
- Preserve bilingual UI strings unless the task explicitly changes copy.

## Checkup Notes
- The folder name says vibemouse, but package and README brand are WhisperKey. Use the repo's current package name in code and commands.
