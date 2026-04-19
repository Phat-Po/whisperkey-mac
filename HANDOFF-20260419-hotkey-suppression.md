# Handoff — Suppress cmd+\ Character Insertion
**Date:** 2026-04-19  
**Task:** Fix the hands-free hotkey so `cmd+\` starts/stops recording without typing `\` into the focused app.

---

## Implementation Update — 2026-04-20

The focused code fix has been implemented.

Changed files:

- `whisperkey_mac/keyboard_listener.py`
- `tests/test_keyboard_listener.py`
- `STATUS.md`
- `HANDOFF-20260419-hotkey-suppression.md`

What changed:

- `HotkeyListener.start()` now installs a `darwin_intercept` callback for the macOS `pynput` backend.
- The callback suppresses only the configured hands-free character key when the full combo is active, for example `cmd+char:\`.
- The paired key-up is also suppressed after a suppressed key-down.
- Plain `\` and other shortcuts are expected to pass through normally.
- Diagnostics use sanitized labels like `char:backslash`.

Verification completed:

```bash
.venv/bin/python -m compileall whisperkey_mac -q
.venv/bin/python -m pytest tests/test_keyboard_listener.py -q
```

Result: keyboard listener tests passed (`14 passed`).

Remaining validation:

- Manual source runtime test with `./start.sh` in a focused text field:
  - Plain `\` types normally.
  - `cmd+\` starts recording and does not insert `\`.
  - `cmd+\` again stops/transcribes and does not insert `\`.
  - Other shortcuts and normal typing are unaffected.

---

## Current Handoff Update — 2026-04-19

The VoiceInput pill visual test is good enough to move on. The user confirmed:

- Transcription works.
- Speaking Chinese outputs English as intended.
- Voice cleanup works.
- The new overlay appears centered after setting the external display as the macOS main monitor.

The remaining bug is hotkey event pass-through: pressing the current hands-free hotkey `cmd+\` starts recording, but the focused app also receives the `\` character.

### Current Project State

- Working directory:
  - `/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac`
- Native macOS Python app using PyObjC/AppKit and `pynput`.
- Current relevant config, observed from `~/.config/whisperkey/config.json` via `load_config()`:
  - `hold_key='alt_r'`
  - `handsfree_keys=['cmd', 'char:\\']`
  - `record_hotkey=''`
  - `enter_hotkey=''`
- Current uncommitted files before this handoff:
  - `whisperkey_mac/overlay.py`
  - `STATUS.md`
  - `HANDOFF-20260419-voiceinput-redesign.md`
- This handoff adds:
  - `HANDOFF-20260419-hotkey-suppression.md`

### Source Of Truth For Next Agent

Read in this order:

1. `STATUS.md`
2. `HANDOFF-20260419-hotkey-suppression.md`
3. `whisperkey_mac/keyboard_listener.py`
4. `tests/test_keyboard_listener.py`
5. Only if needed: `whisperkey_mac/config.py`

Older handoff warning:

- `HANDOFF-20260419-voiceinput-redesign.md` is now mostly historical. It still explains why `overlay.py` has uncommitted visual changes, but the next task is not overlay redesign.

---

## Exact Next Task

Prevent the character key in the hands-free combo from reaching the focused application when it is used as the WhisperKey command.

User-facing expected behavior:

- Press `cmd+\`:
  - WhisperKey starts hands-free recording.
  - No `\` is inserted into the active text field.
- Press `cmd+\` again:
  - WhisperKey stops recording/transcribes.
  - No `\` is inserted into the active text field.
- Press plain `\` without `cmd`:
  - The key still types normally.
- Other keys and normal shortcuts should not be blocked.

---

## Technical Finding So Far

`whisperkey_mac/keyboard_listener.py` currently creates the listener like this:

```python
self._listener = keyboard.Listener(
    on_press=self._on_press,
    on_release=self._on_release,
)
```

That listens but does not suppress events. On macOS, the installed `pynput` backend supports an `intercept` option:

```python
keyboard.Listener(..., intercept=callback)
```

The Darwin backend uses a CGEventTap. If `intercept` is present, the callback can return the original event to allow it through, or `None` to suppress it.

Likely implementation direction:

1. Add an intercept callback in `HotkeyListener`.
2. Convert the incoming CGEvent to a pynput key using listener/backend helpers if possible.
3. Suppress only the character event belonging to the configured hands-free combo when the other required combo keys are already down.
4. Suppress both key-down and key-up for that combo character, so focused apps do not receive a mismatched release.
5. Keep `on_press` / `on_release` state transitions working exactly as they do now.
6. Add sanitized diagnostics such as `hotkey_event_suppressed`, without logging raw secret-like text.

Important: the suppression logic must be narrow. It must not set `suppress=True` globally.

---

## Suggested Implementation Boundaries

Allowed files for this task:

- `whisperkey_mac/keyboard_listener.py`
- `tests/test_keyboard_listener.py`
- `STATUS.md`
- this handoff file, if refreshing after work

Avoid touching unless the user explicitly approves:

- `whisperkey_mac/overlay.py`
- app config files under `~/.config/whisperkey/`
- packaging scripts
- LaunchAgent files
- permissions setup code
- transcriber / correction / output pipeline

Hard constraints:

- Do not run `packaging/macos/build_app.sh`.
- Do not git push.
- Do not change the user's hotkey config.
- Do not switch libraries unless the `pynput` intercept path proves impossible.

---

## Validation Plan

Focused automated checks:

```bash
.venv/bin/python -m compileall whisperkey_mac -q
.venv/bin/python -m pytest tests/test_keyboard_listener.py -q
```

Known unrelated stale tests:

```bash
.venv/bin/python -m pytest tests/test_overlay.py tests/test_keyboard_listener.py -q
```

This currently has 3 expected failures in `tests/test_overlay.py` because those tests still assert old overlay geometry. Do not treat those as caused by this hotkey task unless they change.

Manual source test:

```bash
cd "/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac"
./start.sh
```

Then test in Notes/TextEdit/browser text field:

1. Plain `\` types normally.
2. `cmd+\` starts recording and does not insert `\`.
3. `cmd+\` again stops/transcribes and does not insert `\`.
4. Other shortcuts and regular typing are unaffected.
5. Terminal diagnostics show the combo firing and the character event being suppressed.

---

## Starter Prompt For Next Agent

```text
You are continuing `/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac`.

Use the project governance in AGENTS.md. Start by reading:
1. STATUS.md
2. HANDOFF-20260419-hotkey-suppression.md
3. whisperkey_mac/keyboard_listener.py
4. tests/test_keyboard_listener.py

Current user-confirmed state:
- VoiceInput overlay visual is acceptable.
- Transcription works.
- Chinese speech outputs English.
- Voice cleanup works.
- External monitor centering works when the external display is set as macOS main monitor.

Task:
Fix the hands-free hotkey `cmd+\` so it starts/stops recording without inserting `\` into the focused app. Current config is `handsfree_keys=['cmd', 'char:\\']`. The issue is only event pass-through; recording/transcription behavior is otherwise fine.

Likely fix:
Use the macOS `pynput.keyboard.Listener(..., intercept=...)` path in `whisperkey_mac/keyboard_listener.py` to suppress only the hands-free combo character event when the combo is triggering. Do not globally suppress all keys. Preserve existing listener state-machine behavior. Add focused tests in `tests/test_keyboard_listener.py` and sanitized diagnostics.

Constraints:
- Do not run `packaging/macos/build_app.sh`.
- Do not git push.
- Do not change user config.
- Do not touch overlay, packaging, LaunchAgent, transcriber, correction, or output pipeline unless explicitly approved.
- Run `.venv/bin/python -m compileall whisperkey_mac -q` and `.venv/bin/python -m pytest tests/test_keyboard_listener.py -q`.
- Manual test from source with `./start.sh`; verify plain `\` still types but `cmd+\` does not insert `\`.
```
