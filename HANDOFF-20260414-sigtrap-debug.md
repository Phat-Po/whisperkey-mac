# Handoff — WhisperKey.app hotkey still fails after permissions

**Date**: 2026-04-15  
**Project**: WhisperKey Mac  
**Path**: `/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac`  
**Branch**: `main`, ahead of origin. Do not push.

---

## Current Mission

Debug the local PyInstaller-built `dist/WhisperKey.app`.

User report:

- `WhisperKey.app` opens.
- Both macOS permission panes were opened/enabled for the app.
- App was restarted.
- Pressing the recording hotkey still does nothing visibly: no overlay, no recording start.

The previous obvious blocker was missing macOS trust. That is no longer enough as the final answer because the user says they granted both permissions and restarted.

---

## What Was Just Completed

Packaged `.app` MVP work and local diagnostics were implemented and committed-ready:

- `whisperkey_mac/app_entry.py`
  - packaged app entrypoint
  - creates `~/Library/Application Support/WhisperKey`
  - parent process starts `Supervisor(app_executable=sys.executable)`
  - child process runs `whisperkey_mac.main.main()` when `WHISPERKEY_APP_CHILD=1`
  - packaged CLI/debug commands now route directly to `whisperkey_mac.main.main()`:
    - `setup`
    - `permissions`
    - `settings`
    - `help`
    - `--help`
    - `-h`
    - `detect`
- `whisperkey_mac/supervisor.py`
  - supports `app_executable`
  - packaged child is launched as the same bundled executable
  - sets `WHISPERKEY_SUPERVISED=1` and `WHISPERKEY_APP_CHILD=1`
- `whisperkey_mac/launch_agent.py`
  - frozen mode LaunchAgent ProgramArguments use bundled executable
  - dev mode still uses Python module command
- `packaging/macos/WhisperKey.spec`
  - PyInstaller app bundle spec
  - bundle id `com.phatpo.whisperkey`
  - `LSUIElement=true`
  - microphone and Apple Events usage strings
- `packaging/macos/build_app.sh`
  - builds `dist/WhisperKey.app`
  - ad-hoc signs it
  - verifies codesign
- `packaging/macos/entitlements.plist`
  - minimal ad-hoc signing entitlements
- `whisperkey_mac/help_cmd.py`, `whisperkey_mac/i18n.py`, `README.md`
  - packaged permission/help wording now points to the actual app path instead of saying only `Python.app`
- Tests added for packaged entry routing and packaged permission path output.

---

## Evidence Already Collected

Clean terminal launch of `dist/WhisperKey.app/Contents/MacOS/WhisperKey` before the user re-granted permissions showed the packaged child started correctly:

```text
[wkdiag] event=app_start ...
[wkdiag] event=appkit_ready ...
[wkdiag] event=overlay_create_start ...
[wkdiag] event=overlay_create_end ...
[wkdiag] event=service_start_begin ...
[wkdiag] event=service_hotkey_start ...
[wkdiag] event=service_start_end ...
This process is not trusted! Input event monitoring will not be possible until it is added to accessibility clients.
```

Interpretation at that time:

- packaged child was alive
- overlay creation worked
- service startup worked
- hotkey listener attempted to start
- bundled `pynput`, Quartz, ApplicationServices, objc, and sounddevice were present
- missing Input Monitoring / Accessibility was the likely immediate blocker

After the user granted both permissions and restarted, the bug persists.

---

## Important Complication

There is an existing installed LaunchAgent:

```text
~/Library/LaunchAgents/com.whisperkey.plist
```

Earlier it pointed to the old Python module command and repeatedly failed with:

```text
ModuleNotFoundError: No module named 'numpy'
```

It writes to:

```text
/tmp/whisperkey.log
```

Treat `/tmp/whisperkey.log` as polluted unless you separate a fresh packaged app run from old LaunchAgent output.

Do not unload, edit, replace, or bootstrap this LaunchAgent unless the user explicitly approves that specific system-service action.

---

## High-Probability Debug Areas

1. **TCC identity mismatch**
   - User may have authorized a previous build, a copied app, Terminal, Python.app, or a stale app identity.
   - Rebuilding/ad-hoc signing can change the code identity enough that macOS privacy grants may not apply as expected.
   - Need evidence from a fresh terminal run after permissions were granted.

2. **Wrong hotkey expectation**
   - Current config from this session showed:

     ```json
     "hold_key": "alt_r",
     "handsfree_keys": ["cmd", "char:\\"]
     ```

   - The user may be pressing the old/default hands-free combo instead of the configured one.
   - Need verify hold-to-record with right Option (`alt_r`) and the configured hands-free combo separately.

3. **Stale running binary or single-instance conflict**
   - A previous app instance, old LaunchAgent child, or stale process could hold the lock or consume attention.
   - Confirm exact running PIDs and executable paths before any new run.

4. **Event tap starts but receives no events**
   - If `pynput` no longer prints "not trusted" but hotkey callbacks still never fire, add temporary diagnostics around `HotkeyListener._on_press`, `_on_release`, and `_start_hold_recording`.

5. **Recording starts but overlay/audio does not**
   - If `recording_start` appears but no overlay is visible, debug overlay/AppKit dispatch and audio recorder separately.

---

## Must-Read Files In Order

1. `STATUS.md`
2. `HANDOFF-20260414-sigtrap-debug.md`
3. `whisperkey_mac/app_entry.py`
4. `whisperkey_mac/main.py`
5. `whisperkey_mac/service_controller.py`
6. `whisperkey_mac/keyboard_listener.py`
7. `whisperkey_mac/help_cmd.py`
8. `whisperkey_mac/setup_wizard.py`
9. `whisperkey_mac/supervisor.py`
10. `whisperkey_mac/launch_agent.py`
11. `packaging/macos/WhisperKey.spec`
12. `packaging/macos/build_app.sh`

---

## Non-Mutating First Checks

Start with read-only/runtime inspection:

```bash
pgrep -af 'WhisperKey|whisperkey_mac|com.whisperkey' || true
ps -axo pid,ppid,stat,command | rg 'WhisperKey|whisperkey_mac|com\.whisperkey' || true
plutil -p dist/WhisperKey.app/Contents/Info.plist
codesign -dv --verbose=4 dist/WhisperKey.app 2>&1
codesign --verify --deep --strict --verbose=2 dist/WhisperKey.app
dist/WhisperKey.app/Contents/MacOS/WhisperKey --help
stat -f '%Sm %N' /tmp/whisperkey-faulthandler.log /tmp/whisperkey-last-crash.log /tmp/whisperkey.log 2>/dev/null || true
tail -n 120 /tmp/whisperkey-faulthandler.log 2>/dev/null || true
tail -n 80 /tmp/whisperkey-last-crash.log 2>/dev/null || true
```

Then run a clean packaged app foreground session:

```bash
dist/WhisperKey.app/Contents/MacOS/WhisperKey
```

Ask the user to test:

- hold right Option for at least 1 second, then release
- if that fails, test the configured hands-free combo `cmd + \`
- report exactly which physical keys they pressed

Watch for:

- `This process is not trusted`
- `service_start_end`
- `Recording...`
- `recording_start`
- `recording_start_ignored`
- `recording_started`
- overlay events
- sounddevice errors
- `Another WhisperKey instance is already running`

---

## If Evidence Is Still Missing

Plan a tiny diagnostic patch, then ask for approval before implementation if not already approved:

- Add `diag()` calls in:
  - `HotkeyListener.start`
  - `HotkeyListener._on_press`
  - `HotkeyListener._on_release`
  - `HotkeyListener._start_hold_recording`
- Include sanitized fields only:
  - key name from `pynput_key_to_name`
  - paused state
  - current mode
  - whether key matched hold key
  - whether combo is active
- Do not log transcript text, API keys, keychain values, or secrets.

This will distinguish "event tap receives nothing" from "hotkey logic receives events but does not match configured keys."

---

## Validation Commands

Use project venv, not system `python3`:

```bash
.venv/bin/python -m compileall -q whisperkey_mac tests
.venv/bin/python -m pytest -q
git diff --check
packaging/macos/build_app.sh
codesign --verify --deep --strict --verbose=2 dist/WhisperKey.app
dist/WhisperKey.app/Contents/MacOS/WhisperKey --help
```

Manual acceptance after the real fix:

- launch `dist/WhisperKey.app`
- menu bar item appears
- hotkey press logs `recording_start`
- overlay appears
- release/transcribe path starts
- one real recording can be transcribed and pasted or copied
- quit from menu or Apple Events exits parent and child processes

---

## Boundaries / Do Not Do

- Do not push.
- Do not create GitHub release artifacts.
- Do not notarize.
- Do not edit `.env*`.
- Do not unload/replace/edit the current `com.whisperkey` LaunchAgent without explicit approval.
- Do not modify active system services.
- Do not remove supervisor crash diagnostics.
- Do not trust `/tmp/whisperkey.log` as clean packaged app evidence until LaunchAgent noise is separated.

---

## Starter Prompt For Next Agent

```text
批准执行

You are working in:

/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac

Use local governance. This is a debug mission for the local PyInstaller-built dist/WhisperKey.app. Do not push, notarize, create GitHub release artifacts, edit .env*, or modify/unload LaunchAgent/system services unless explicitly approved.

Current user report: WhisperKey.app opens, both macOS Privacy permissions were granted and the app was restarted, but pressing the recording hotkey still does nothing. No overlay appears and recording does not visibly start.

First read:
1. STATUS.md
2. HANDOFF-20260414-sigtrap-debug.md
3. whisperkey_mac/app_entry.py
4. whisperkey_mac/keyboard_listener.py
5. whisperkey_mac/service_controller.py
6. whisperkey_mac/help_cmd.py

Start read-only/runtime diagnostics:
- confirm active processes with pgrep/ps
- verify bundle identity and codesign
- run dist/WhisperKey.app/Contents/MacOS/WhisperKey --help
- launch dist/WhisperKey.app/Contents/MacOS/WhisperKey from Terminal and ask me to press right Option hold-to-record, then cmd+\ hands-free
- watch for "This process is not trusted", service_start_end, Recording..., recording_start, recording_start_ignored, and Another WhisperKey instance is already running

Important: Current config may use hold_key=alt_r and handsfree_keys=["cmd", "char:\\"]. Do not assume the old/default hands-free combo.

If no key events are observed and permissions look granted, propose a tiny diagnostic patch to add sanitized diag() calls inside HotkeyListener.start/_on_press/_on_release/_start_hold_recording, then run compile/tests/build. Do not log secrets or transcript text.
```
