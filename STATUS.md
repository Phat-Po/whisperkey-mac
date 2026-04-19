# WhisperKey Mac — Status Log

---

## 2026-04-19 | VoiceInput pill redesign planned — handoff ready for next agent

**Done this session:**
- User rejected aurora orb design; wants new overlay matching VoiceInput component (molecule-lab-rushil/21st.dev).
- Fetched and analyzed VoiceInput React source code.
- Planned full native PyObjC translation of the design.
- Created handoff doc: `HANDOFF-20260419-voiceinput-redesign.md`.

**Current state:**
- No code changed this session. Uncommitted changes exist from prior session (overlay.py, tests, app_entry, etc.).
- The aurora orb overlay is still live in `whisperkey_mac/overlay.py`.
- Next agent must snapshot first, then replace `AuroraOrbView` + aurora renderer with VoiceInput pill design.

**Next steps:**
1. Read `HANDOFF-20260419-voiceinput-redesign.md`.
2. Snapshot: `git add -A && git commit -m "snapshot: before voiceinput pill redesign"`.
3. Rewrite `whisperkey_mac/overlay.py` — only this file.
4. Run `pytest tests/test_overlay.py tests/test_keyboard_listener.py -q` — all must pass.
5. Tell user to visually verify overlay.

**Decisions / notes:**
- No React, npm, shadcn, or WebView — pure PyObjC/Core Graphics translation only.
- Do NOT run `build_app.sh` — breaks TCC permissions. Terminal relaunch only.
- Do NOT git push without operator confirmation.
- Keep RESULT state (shows transcribed text) — that's core functionality.

---

## 2026-04-17 | Orb shader-match attempt rejected — next: thick smooth torus renderer

**Done this session:**
- Implemented a first native `AuroraOrbView` ring-only attempt in `whisperkey_mac/overlay.py`.
- Verified functional behavior still passed:
  - `./.venv/bin/python -m pytest tests/test_overlay.py tests/test_keyboard_listener.py -q` -> `42 passed`
  - `./.venv/bin/python -m compileall whisperkey_mac` -> passed
- User rebuilt/previewed and rejected the visual result as still far from the supplied React/OGL shader.
- Refreshed handoff: `HANDOFF-20260417-orb-redesign.md`.

**Current state:**
- Current source draws a small noisy segmented ring. It is functionally safe but visually wrong.
- The target is a thick, smooth, luminous torus: transparent center, broad blurred glow, cyan-left/purple-right gradient, dark-blue bridge, and an integrated white-blue upper-right crescent highlight.
- The next agent must not repeat the thin noisy arc/stroke approach.

**Next steps:**
1. Read `HANDOFF-20260417-orb-redesign.md`.
2. Rework `AuroraOrbView` from segmented noisy strokes into a broad layered annular alpha-field approximation.
3. Preserve compact recording/transcribing behavior and result expansion.
4. Validate focused tests and compile check.

**Decisions / constraints:**
- Native Python/PyObjC only; no React, Tailwind, shadcn, `ogl`, WebView, or recording button.
- Do not touch saved config, bundle id, LaunchAgent path, permissions identity, packaging, or service state unless explicitly approved.
- Rebuild remains a separate explicit approval because ad-hoc signing can force macOS TCC reauthorization.

---

## 2026-04-17 | Orb redesign handoff prepared — next: native ring-only visual match

**Done this session:**
- Confirmed the functional hotkey/compact-overlay changes are present in source.
- Confirmed the local `dist/WhisperKey.app` timestamp was newer than the changed source files during the check, so a rebuild did not appear necessary for the already-working version.
- Ran focused verification: `./.venv/bin/python -m pytest tests/test_overlay.py tests/test_keyboard_listener.py -q` -> `42 passed`.
- Created handoff: `HANDOFF-20260417-orb-redesign.md`.

**Current state:**
- The app works functionally, but the user rejected the current overlay design as visually far from the supplied React/OGL reference.
- Next task is design-only: replicate the reference as a native PyObjC/Core Graphics aurora ring, not a React/WebView component.
- User explicitly does not want rebuild, Privacy & Security reauthorization, config changes, or service interruption as part of the redesign.

**Next steps:**
1. Next agent reads `HANDOFF-20260417-orb-redesign.md`.
2. Preserve the existing compact recording/transcribing behavior and result expansion.
3. Redesign `AuroraOrbView` in `whisperkey_mac/overlay.py` so the compact overlay is ring-first with transparent center, purple/cyan/dark-blue palette, organic noisy edge, moving highlight, and voice-level pulse.
4. Validate with focused overlay/hotkey tests before any visual runtime check.

**Decisions / constraints:**
- Do not add a recording button.
- Do not install React, Tailwind, shadcn, `ogl`, or a WebView runtime.
- Do not change bundle id, LaunchAgent path, packaging identity, saved config, or permissions strings unless explicitly approved.
- Do not run `packaging/macos/build_app.sh` unless the user explicitly approves the rebuild and possible TCC permission impact.

---

## 2026-04-15 | gpt-5.4 models + usage tab + ASR plain text; codesign fix planned

**Done this session:**
- ASR correction switched from JSON output to plain text (`_extract_plain_text`, no `json_object` format flag)
- Custom mode `max_output_tokens` raised 256 → 1024
- `ONLINE_MODEL_OPTIONS` prepended with gpt-5.4/mini/nano/pro; default model → `gpt-5.4`
- Created `whisperkey_mac/usage_log.py`: logs every API call to `~/.config/whisperkey/usage_log.jsonl`
- `online_correct.py` calls `log_usage()` after each API call (wrapped in try/except)
- Settings: added 5th "Usage" tab — token totals (today/week/all-time) + disk usage (audio temp + whisper model cache) + Refresh button
- Updated 2 tests that expected old JSON behavior; all 110 pass
- Diagnosed TCC permission loss: caused by ad-hoc signing (`--sign -`), CDHash changes each rebuild
- Handoff written: `HANDOFF-20260415-codesign.md`

**Current state:**
- All changes committed as `67bd12d`. Tests: 110 passed. App builds cleanly.
- TCC permission loss on rebuild is NOT fixed yet — that is the next task.

**Next steps:**
1. Operator: create self-signed cert in Keychain Access (Keychain Access → Certificate Assistant → Create Certificate → Code Signing, name: `WhisperKey Dev`)
2. Next agent: read `HANDOFF-20260415-codesign.md` and follow Steps 3–8
3. Change `build_app.sh` + `WhisperKey.spec` to use `"WhisperKey Dev"` instead of `-`
4. Rebuild twice, confirm hotkey works on second build without re-granting TCC

**Decisions / notes:**
- Self-signed cert should stabilize TCC on most macOS versions; if not, fallback is free Apple Developer account (instructions in handoff doc)
- Operator does NOT have $99/year Apple Developer subscription — self-signed path is the first attempt

---

## 2026-04-15 | Voice cleanup handoff prepared — next: refine feature/prompt

**Done this session:**
- Resolved hotkey-does-nothing bug (TCC CDHash invalidation after rebuild — re-granted permissions)
- Confirmed full pipeline working: hold-to-record → transcribe → voice_cleanup → inject via AppleScript
- Live test: 19.8s English audio → 1.64s transcription → 3.44s voice_cleanup → injected correctly
- Handoff written: `HANDOFF-20260415-voice-cleanup.md`

**Current state:**
- App running from Terminal. Voice cleanup is functional with `output_language=en`, `model=gpt-4o-mini`, `timeout=15s`.
- Known remaining: AX insertion falls back to AppleScript (works, not blocking); LaunchAgent log blind (console=False → stdout goes to /dev/null in service mode).
- All code committed as of `5b8818b`. Only `STATUS.md` is uncommitted.

**Next steps:**
1. Read `HANDOFF-20260415-voice-cleanup.md`
2. Ask operator what specifically to improve (prompt quality, note mode, output language, custom prompt UI, min_chars tuning)
3. Edit prompts in `whisperkey_mac/online_correct.py` (no rebuild needed for prompt-only changes)
4. Test: relaunch app, record, verify `online_correction_end changed=True` and check injected text

**Decisions / notes:**
- Prompt-only changes don't require rebuild. Just quit + relaunch the app.
- After any code change that triggers `build_app.sh`, re-grant TCC permissions before testing.

---

## 2026-04-15 | Hotkey debug resolved — full pipeline working

**Root cause:** Ad-hoc CDHash invalidation. Every `build_app.sh` run re-signs the binary with a new ad-hoc hash. macOS TCC ties trust records to the exact CDHash, so the previous session's packaging rebuild silently dropped the old permission grants. No code changes were needed.

**Fix applied:**
1. Killed stale supervisor (82359) and child (86592) processes.
2. Removed old WhisperKey.app entries from System Settings → Accessibility and Input Monitoring.
3. Re-added `dist/WhisperKey.app` to both panes and enabled toggles.
4. Launched from Terminal: `dist/WhisperKey.app/Contents/MacOS/WhisperKey`

**Verified working:**
- No "This process is not trusted!" on startup.
- Hold right Option → `recording_start` fires.
- `cmd + \` hands-free → full transcription + online correction + AppleScript injection confirmed.
- Transcribed 19.8s of English speech in 1.64s with voice_cleanup correction applied.

**Known remaining:**
- AX insertion still unavailable (`path=unavailable`); AppleScript fallback is working. Separate task if direct AX paste is desired.
- `console=False` in WhisperKey.spec means `print()`/`[wkdiag]` output goes to /dev/null when running via LaunchAgent (not a terminal). Faulthandler still works. For LaunchAgent log visibility, would need `console=True` + rebuild.
- LaunchAgent will restart the app on next login (KeepAlive=false, RunAtLoad=true). After any future `build_app.sh` rebuild, permissions must be re-granted because the CDHash changes with each ad-hoc build.

**Rule for future sessions:** After every `build_app.sh` run, re-grant both Accessibility and Input Monitoring in System Settings before testing the packaged hotkey.

---

## 2026-04-15 | Packaged app hotkey still fails after permissions; handoff refreshed and current work ready to commit

**Session summary:**
Debugged `dist/WhisperKey.app` after the app launched but hotkey recording did nothing. Clean terminal launch proved the packaged parent/child app reaches overlay creation, `service_hotkey_start`, and `service_start_end`; the initial blocker was macOS trust, with `pynput` printing `This process is not trusted! Input event monitoring will not be possible until it is added to accessibility clients.` Packaged CLI routing was fixed so `WhisperKey --help` and `permissions` work from the bundled executable and point at `dist/WhisperKey.app` instead of misleading users toward `Python.app`.

**Done this session:**
- Added/kept local `.app` packaging flow:
  - `whisperkey_mac/app_entry.py`
  - `packaging/macos/WhisperKey.spec`
  - `packaging/macos/build_app.sh`
  - `packaging/macos/entitlements.plist`
- Updated packaged runtime/supervisor/LaunchAgent behavior so frozen mode launches the bundled executable and child process correctly.
- Fixed packaged CLI/debug routing for `setup`, `permissions`, `settings`, `help`, `--help`, `-h`, and `detect`.
- Updated permission/help wording in README and i18n strings so packaged users authorize `dist/WhisperKey.app`.
- Added regression tests for packaged app entry routing and packaged permission path output.
- Rebuilt and ad-hoc signed `dist/WhisperKey.app`.

**Current state:**
- User has now opened/authorized both macOS permission panes and restarted, but reports the hotkey still does not work.
- That means the next task is no longer "tell user to grant permissions"; it is a fresh packaged hotkey debug mission.
- The installed user LaunchAgent `~/Library/LaunchAgents/com.whisperkey.plist` previously pointed at an old Python module command and polluted `/tmp/whisperkey.log`; do not edit/unload it without explicit approval.
- Working tree is ready to commit locally. Do not push.

**Verified this session:**
- `.venv/bin/python -m compileall -q whisperkey_mac tests`
- `.venv/bin/python -m pytest -q` -> `111 passed`
- `git diff --check`
- `packaging/macos/build_app.sh`
- `codesign --verify --deep --strict --verbose=2 dist/WhisperKey.app`
- `dist/WhisperKey.app/Contents/MacOS/WhisperKey --help`

**Next task:**
Start a focused debug mission for "permissions granted but packaged hotkey still does nothing":
- confirm the exact TCC entries macOS granted for `dist/WhisperKey.app` versus the bundled executable and any stale app identity
- launch the rebuilt executable from Terminal and capture clean stdout while the user presses the hotkey
- verify whether `pynput` still prints the "not trusted" warning after the permission change
- verify whether `recording_start` appears when holding the configured hotkey
- inspect config hotkey values, especially current hands-free combo `cmd + char:\`
- decide whether the issue is TCC identity, wrong key expectation, stale running binary, stale single-instance/LaunchAgent conflict, event tap failure, or overlay/audio path

**Decisions / constraints:**
- Do not push, notarize, create GitHub release artifacts, edit `.env*`, or modify/unload LaunchAgent/system services without explicit approval.
- Use project `.venv` Python 3.12.10, not system `python3`.
- Keep existing supervisor crash diagnostics behavior.
- Continue to treat `/tmp/whisperkey.log` as polluted unless the next agent separates app stdout from the old LaunchAgent.

---

## 2026-04-15 | Crash diagnostics added; waiting for reproduction logs

**Session summary:**  
Added standard-library-only diagnostic instrumentation, captured real crash stacks, applied targeted concurrency fixes, then added a crash supervisor for LaunchAgent runs. The first stack showed Settings opening while a `pynput` CGEventTap callback thread was inside `sounddevice.py:stop`; the second stack showed Settings being rebuilt from a retry callback after heavy recording/transcribe churn.

**Done this session:**
- Added `whisperkey_mac/diagnostics.py` with:
  - `faulthandler.enable()` writing to `/tmp/whisperkey-faulthandler.log`
  - periodic process metrics logging
  - event-based metrics logging with `rss_mb`, `%cpu`, OS thread count fallback, and `ru_maxrss`
- Instrumented startup, menu Settings, Settings show/save, overlay creation/display, service start/stop/apply_config, recording start/stop, transcribe start/end, online correction start/end, injection start/end, AX insertion, AppleScript fallback, clipboard fallback, model load/unload.
- Synced `tests/test_keyboard_listener.py` with the current pause-style listener behavior so the full suite reflects the existing SIGTRAP mitigation.
- Refactored recording stop/transcribe so the `pynput` callback only dispatches a `WhisperKeyStopTranscribe` worker thread and returns immediately.
- Added service busy tracking and deferred Settings opening while recording, stopping audio, transcribing, correcting, injecting, and for a 2-second quiet period after processing completes.
- Prevented new recordings from starting while the service is busy; ignored starts reset the hotkey listener state.
- Reused the native Settings window instead of rebuilding it on every menu click; Settings window is no longer released on close and its fields are refreshed before show.
- Deferred Settings save/apply while the service is busy to avoid config changes during active audio/transcribe work.
- Blocked automatic direct paste when the target bundle is `org.python.python`, avoiding self-targeted AppleScript/AX injection after Settings focus.
- Added regression tests for non-blocking audio stop dispatch, Settings deferral while busy, Settings save deferral while busy, busy recording-start rejection, and Python-app paste blocking.
- Added `whisperkey_mac/supervisor.py`, a separate wrapper process for LaunchAgent runs:
  - starts `whisperkey_mac.main`
  - detects non-zero/signal exits such as SIGSEGV
  - writes `/tmp/whisperkey-last-crash.log`
  - sends a macOS notification via `osascript`
  - restarts with backoff up to 3 crashes within 5 minutes, then stops
- Changed generated LaunchAgent plist to run `whisperkey_mac.supervisor` and set `KeepAlive` false so supervisor controls restart behavior.
- Added `whisperkey-supervisor` console script and updated English/Chinese README LaunchAgent examples.

**Current state:**
- No new packages were added.
- AppleScript fallback behavior was not disabled; only the self Python app target is now blocked from direct automatic paste.
- Diagnostics avoid logging transcript text, API keys, or secret values.
- The existing installed LaunchAgent will not use the supervisor until it is regenerated by saving Settings with Launch at Login enabled, toggling Launch at Login off/on, or reinstalling the plist.
- Working tree remains uncommitted and `main` is still ahead of `origin/main`.

**Verified this session:**
- `.venv/bin/python --version` -> Python 3.12.10
- `/Users/pohanlee/.codex/skills/codex-preflight/scripts/preflight.sh --path ... --mode implement --stack python --approval yes`
  - reported system `python3` below baseline, but project `.venv` satisfies the Python requirement.
- `.venv/bin/python -m compileall -q whisperkey_mac tests`
- diagnostics smoke test imported `diag()` and `enable_faulthandler()` successfully
- `.venv/bin/python -m pytest -q` -> `104 passed`

**Next task:**
Run the menu bar app from the project venv again and try the same reproduction sequence:
- repeated hands-free recording/transcription
- open/save Settings between runs
- click Settings while a recording is stopping if possible
- try pressing hands-free while transcription/online correction is still running; expected behavior is that recording start is ignored rather than queued

Then collect:
- Terminal output containing `[wkdiag]` lines
- `/tmp/whisperkey-faulthandler.log`
- if running via LaunchAgent/supervisor, `/tmp/whisperkey-last-crash.log`

**Decisions / constraints:**
- Do not commit/push/deploy unless explicitly asked.
- Do not install packages or add `psutil`.
- Do not disable AppleScript fallback globally unless the next diagnostic logs show it is still a consistent risky path.
- Continue preserving the current uncommitted crash mitigations.

---

## 2026-04-15 | Native crash remains intermittent; next step is diagnostics

**Session summary:**  
Repeated transcription now often works for 2-3 rounds, including one Settings save in one run, but the app still exits with `segmentation fault` or `trace trap` around repeated injection/menu bar interactions.

**Done recently:**
- Settings menu action now dispatches `open_settings` to the main run loop.
- `TextOutput.inject()` tries AX insertion before AppleScript fallback.
- Terminal/iTerm/Warp are blocked from automatic paste and should fall back to clipboard.
- `ServiceController.apply_config()` no longer recreates `AudioRecorder` unless audio config changes.
- Regression tests updated for AX-first injection and recorder reuse.
- Verified with `.venv/bin/python -m pytest tests/test_output.py tests/test_main.py -q` (`25 passed`).

**Current state:**
- The crash is not isolated to a single Settings or Save action anymore.
- Latest logs still show `AX insert unavailable; falling back to AppleScript paste.` and `inject_path=applescript` before later native crash.
- No reliable CPU/RSS/thread-count data has been captured yet because the process exits before inspection.
- Working tree has uncommitted edits in:
  - `whisperkey_mac/menu_bar.py`
  - `whisperkey_mac/output.py`
  - `whisperkey_mac/service_controller.py`
  - `tests/test_main.py`
  - `tests/test_output.py`
- Handoff file has been refreshed at `HANDOFF-20260414-sigtrap-debug.md`.

**Next task:**
Add standard-library-only diagnostics before further functional fixes:
- enable `faulthandler` to `/tmp/whisperkey-faulthandler.log`
- add periodic and event-based resource logs (`rss_mb`, `%cpu`, thread count, `ru_maxrss`)
- instrument startup, overlay, recording, transcribe, online correction, injection, menu bar Settings, Settings show/save, and `apply_config`
- then ask the user to reproduce and provide Terminal output plus the faulthandler log

**Decisions / constraints:**
- Do not install packages; use `.venv/bin/python` and standard library/system `ps`.
- Do not push/deploy/commit unless explicitly asked.
- Do not disable AppleScript fallback yet; first collect evidence.
- Do not revert current uncommitted crash mitigations without explicit approval.
- System `/usr/bin/python3` is 3.9.6 and below project baseline; project venv is Python 3.12.10.

---

## 2026-04-14 | SIGTRAP crash debug — old status, now superseded

Earlier work identified and mitigated a `pynput` listener stop/start SIGTRAP path by moving toward pause-style listener behavior and avoiding unnecessary hotkey/transcriber/overlay rebuilds on Settings save.

This entry is now superseded by the 2026-04-15 status: the remaining crash still occurs after those mitigations and requires diagnostics first.
