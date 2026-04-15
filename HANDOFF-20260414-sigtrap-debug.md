# Handoff — WhisperKey Mac native crash after repeated transcription

**Date**: 2026-04-15  
**Project**: WhisperKey Mac  
**Path**: `/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac`  
**Branch**: `main`, ahead of origin; local working tree has uncommitted edits.

---

## Current Task

Diagnostic instrumentation has now been added for the intermittent native crash in the macOS menu bar app, two evidence-based mitigation rounds have been applied, and LaunchAgent crash supervision has been added.

The next task is another reproduction run to see whether this mitigation removes the crash.

The crash is no longer tied to only one action. It has appeared after:

- repeated successful transcription + injection
- opening Settings after prior transcriptions
- saving Settings after a previous injection

Observed process exits include both:

- `zsh: segmentation fault`
- `zsh: trace trap`

The Python shutdown warning often follows:

```text
resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
```

Do not assume this warning is the direct root cause; it may be a side effect of native crash shutdown or dependency processes.

---

## Most Recent User Observation

Latest run succeeded for:

1. one transcription with clipboard path
2. one long transcription with AppleScript fallback
3. one Chinese transcription with AppleScript fallback

Then the process crashed with `segmentation fault`. The user reports that another run survived two transcriptions and one Settings change, then crashed immediately on the third menu bar Settings click.

Important latest log fragment:

```text
[whisperkey] AX insert unavailable; falling back to AppleScript paste.
[whisperkey] 已输入 applescript.
[whisperkey] inject_path=applescript
zsh: segmentation fault
```

This means AppleScript fallback is still being used in real usage after AX insertion fails.

---

## Current Working Hypothesis

Do not continue guessing single fixed trigger paths. The behavior now looks like native state corruption or lifecycle pressure around these components:

- PyObjC/AppKit menu bar and Settings windows
- overlay NSPanel animations and AppKit timers
- `pynput` keyboard listener / macOS CGEventTap
- AppleScript/System Events synthetic Cmd+V paste
- faster-whisper / ctranslate2 native runtime and multiprocessing cleanup
- online correction network call path

CPU/memory overload is not ruled out, but it is not the leading explanation. Resource and fatal-crash instrumentation is now present, so the next reproduction should provide evidence before further functional changes.

New diagnostic output format:

```text
[wkdiag] event=<event-name> rss_mb=<mb> cpu_pct=<pct> threads=<count> maxrss_kb=<kb> ...
```

Fatal dumps are written to:

```text
/tmp/whisperkey-faulthandler.log
```

Most recent captured fatal stack showed:

- Current/main thread: `App.open_settings()` at `whisperkey_mac/main.py:108`, before `SettingsWindowController.show`.
- Another thread: `sounddevice.py:stop` inside `AudioRecorder.stop_and_save()`, called from `ServiceController._stop_and_transcribe()`, called by `pynput` keyboard `_on_release` / macOS CGEventTap callback.

Interpretation: the crash is strongly associated with opening Settings while audio stream stop/close is still running on the native keyboard event callback thread.

Second reproduction after that fix showed:

- `sounddevice.stop` was no longer on the fatal stack.
- Crash moved to `_retry_open_settings -> App.open_settings -> build_settings_window_controller`, after repeated deferred Settings attempts during heavy recording/transcribe churn.
- User also observed stale/previous recording content being emitted later; logs confirmed new recordings were allowed to start while a previous stop/transcribe/correct/inject worker was still busy.

Interpretation: Settings native window construction and config application must be kept out of high-churn service states, and recording state must not be allowed to overlap with processing state.

---

## Current Uncommitted Code Changes

These edits are already in the working tree and should be preserved unless the user explicitly asks to revert them:

- `whisperkey_mac/diagnostics.py`
  - new standard-library-only diagnostics module.
  - enables `faulthandler` to `/tmp/whisperkey-faulthandler.log`.
  - logs RSS, CPU, thread count, and `ru_maxrss` for event and periodic diagnostics.
- `whisperkey_mac/main.py`
  - enables diagnostics at app startup.
  - logs AppKit readiness, run loop entry/exit, Settings open/save.
  - defers Settings opening while the service is busy.
  - reuses one Settings window controller instead of rebuilding native AppKit windows on every click.
  - defers Settings save/apply while the service is busy.
- `whisperkey_mac/supervisor.py`
  - new outer wrapper intended for LaunchAgent runs.
  - launches `whisperkey_mac.main` as a child process.
  - writes `/tmp/whisperkey-last-crash.log` and sends a macOS notification when the child exits with non-zero or signal status.
  - restarts with backoff up to 3 crashes within 5 minutes, then stops.
- `whisperkey_mac/launch_agent.py`
  - generated plist now runs `whisperkey_mac.supervisor`.
  - `KeepAlive` is false so supervisor, not launchd, owns crash restart/backoff.
- `whisperkey_mac/transcriber.py`
  - logs model load/unload and transcribe start/end.
- `whisperkey_mac/overlay.py`
  - logs overlay panel creation and display/hide events.
- `whisperkey_mac/settings_window.py`
  - logs Settings show/save/cancel events.
  - calls `setReleasedWhenClosed_(False)` and exposes `refresh(...)` so the native window can be reused safely.
- `tests/test_keyboard_listener.py`
  - synced tests with the current pause-style listener behavior.
- `tests/test_main.py`
  - added regression coverage for non-blocking stop/transcribe dispatch, Settings busy deferral, Settings save deferral, busy recording-start rejection, and own-Python-app paste blocking.
- `tests/test_launch_agent.py`
  - updated generated plist expectations for supervisor module and `KeepAlive` false.
- `tests/test_supervisor.py`
  - new tests for signal/exit classification, crash report writing, notification escaping, one-crash restart, and repeated-crash stop behavior.
- `pyproject.toml`
  - added `whisperkey-supervisor` console script.
- `README.md` / `README.zh.md`
  - LaunchAgent examples now use supervisor and describe crash notification/log behavior.

- `whisperkey_mac/menu_bar.py`
  - `openSettings_` now dispatches `open_settings` via `dispatch_to_main`.
  - logs the menu Settings action and menu creation.
- `whisperkey_mac/service_controller.py`
  - terminal bundle IDs are blocked from automatic paste.
  - `org.python.python` is blocked from automatic paste to avoid self-targeted injection after Settings focus.
  - `apply_config()` no longer recreates `AudioRecorder` unless audio config changes.
  - logs service lifecycle, config application, recording/transcribe/correction/injection phases.
  - `_stop_and_transcribe()` no longer calls `AudioRecorder.stop_and_save()` inline from the `pynput` callback; it dispatches a `WhisperKeyStopTranscribe` worker and returns.
  - service busy state covers recording, stop/transcribe/correct/inject processing, and a 2-second AppKit quiet period after processing.
  - `_start_recording()` ignores attempts while busy and resets hotkey state to avoid queued/stale recordings.
- `whisperkey_mac/output.py`
  - injection now tries AX insertion before AppleScript fallback.
  - logs when it falls back to AppleScript.
  - logs AX, AppleScript, retry, and clipboard-only injection paths.
- `tests/test_main.py`
  - regression tests for Terminal autopaste blocklist.
  - regression test that `apply_config()` reuses recorder when audio config is unchanged.
- `tests/test_output.py`
  - tests updated for AX-first injection order.

Existing untracked files:

- `STATUS.md`
- `HANDOFF-20260414-sigtrap-debug.md`
- `whisperkey_mac/diagnostics.py`

Do not delete these; they are the project handoff/status files.

---

## Verified Commands

Use the project venv, not system `python3`.

Already passed:

```bash
.venv/bin/python --version
# Python 3.12.10

.venv/bin/python -m compileall -q whisperkey_mac tests/test_output.py tests/test_main.py

.venv/bin/python -m pytest tests/test_output.py tests/test_main.py -q
# 25 passed

.venv/bin/python -m compileall -q whisperkey_mac tests

.venv/bin/python -m pytest -q
# 104 passed
```

System `/usr/bin/python3` is 3.9.6 and below project baseline; avoid using it for project validation.

---

## Next Agent: Exact Next Task

Ask the user to reproduce the same crash sequence and provide:

- Terminal output from the run, especially the last `[wkdiag]` lines before crash.
- `/tmp/whisperkey-faulthandler.log`
- If running via LaunchAgent/supervisor: `/tmp/whisperkey-last-crash.log`

Expected changed behavior:

- Repeated Settings clicks during active recording/transcribe/correction should defer without rebuilding Settings.
- Hands-free attempts during processing should log `recording_start_ignored reason=service_busy` and should not create a queued recording.
- Settings save during processing should log `app_save_settings_deferred reason=service_busy`.
- Once the LaunchAgent plist is regenerated, native crashes should produce a macOS notification and `/tmp/whisperkey-last-crash.log`.

Important operational note:

- Existing installed LaunchAgent files are not rewritten by this code change alone.
- To make the live login item use supervisor, regenerate the LaunchAgent by saving Settings with Launch at Login enabled, toggling Launch at Login off/on, or reinstalling/bootstraping the plist.

If the crash persists, use those logs to determine whether the next fix should target:

- AppleScript/System Events paste path
- AppKit menu/Settings/overlay lifecycle
- `pynput` / CGEventTap state
- faster-whisper / ctranslate2 native runtime
- resource pressure, such as RSS/thread growth
- PortAudio/sounddevice stream shutdown outside the callback worker

---

## Boundaries / Do Not Do Yet

- Do not install new packages.
- Do not use `psutil`.
- Do not commit/push/deploy.
- Do not edit `.env*` or credential/keychain logic except for logging-free flow checks.
- Do not disable AppleScript fallback yet unless diagnostics prove it is consistently the last risky path.
- Do not rewrite overlay or Settings UI before collecting crash evidence.
- Do not revert the existing uncommitted fixes without explicit user approval.

---

## Must-Read Files In Order

1. `STATUS.md`
2. `HANDOFF-20260414-sigtrap-debug.md`
3. `whisperkey_mac/main.py`
4. `whisperkey_mac/service_controller.py`
5. `whisperkey_mac/output.py`
6. `whisperkey_mac/menu_bar.py`
7. `whisperkey_mac/settings_window.py`
8. `whisperkey_mac/overlay.py`
9. `tests/test_main.py`
10. `tests/test_output.py`

---

## Useful Context From Prior Debugging

Earlier crash hypothesis around `pynput` stop/start was partly addressed before this handoff:

- `HotkeyListener` already has `_paused` behavior and does not destroy/recreate CGEventTap on normal service stop/start.
- Settings save no longer rebuilds the hotkey listener.
- `apply_config()` now avoids unnecessary recorder rebuilds.

The remaining crash still occurs after those mitigations, so the next step is evidence collection, not repeating the old SIGTRAP-only fix.
