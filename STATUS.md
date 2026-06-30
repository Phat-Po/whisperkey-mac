# WhisperKey — Status

## Current

### 2026-06-30 | v3.6.0 — OpenAI key "Test Connection" button + public-repo cleanup

Done this session:
- Diagnosed why Agent mode (`voice_cleanup`) sometimes "didn't organize": the OpenAI call intermittently took 47–91s (network/VPN stall) and exceeded the 30s timeout; the SDK's 2 auto-retries compounded one stall into a ~90s wait, then the `except` branch silently returned the raw transcript (no usage logged, no error shown). API/model/prompt/pipeline themselves verified healthy (3–5s, correct output). Root cause was transient network, amplified by silent retry + silent fallback.
- Confirmed GitHub sync (local `main` == `origin/main`) and ran a full secret audit: no real keys in the tree or in git history; secrets live only in `~/.config/whisperkey/config.json` (gitignored) + Keychain.
- Untracked internal dev docs + debug scripts (`git rm --cached` whole `tasks/`, kept on disk) and added `/tasks/` to `.gitignore` so the public repo stays clean.
- Added **OpenAI "Test Connection"** button in Settings → Advanced: `verify_openai_connection()` in `online_correct.py` makes a real `models.list()` check (no token cost, `max_retries=0` so it fails fast), run on a background thread; status label shows ✅ connected / ❌ invalid key / ❌ network failure. Bilingual i18n (zh+en). 5 new unit tests; full suite 335 green. Live-verified against the real key (✅ 2s) and a bad key (❌ invalid).

Current state:
- App is WhisperKey `3.6.0`. ASR engine `doubao`, Agent (`voice_cleanup`) mode.

Next steps:
1. Operator: in the new build, open Settings → Advanced → "Test Connection" to confirm the key.
2. Optional follow-up (not done): make the live correction path itself surface timeouts to the overlay + drop its auto-retries (H2 from the diagnosis), so a stall is visible instead of silently pasting raw text.

Decisions / notes:
- The Test button uses `models.list()` (connectivity + auth), not a `responses.create`, to stay free and fast.
- Summary mode (`summary`) remains reachable only via the menu bar, not the hotkey cycle — unchanged this session.

---

### 2026-06-22 | v3.5.1 — fix CoreAudio teardown deadlock (recording couldn't be stopped)

Done this session:
- Diagnosed a live "recording can't be stopped, no text, app permanently stuck" incident by sampling the hung process: the stop worker deadlocked inside PortAudio/CoreAudio `stream.stop()` (`__psynch_mutexwait` in `AudioUnitGetProperty`) after a Continuity mic disconnected mid-recording. `_processing_busy` never cleared → every later recording rejected with `service_busy`. Sequence that triggered it: iPhone Continuity mic out of range → user switched to default mic in Settings (app crashed once there) → reopened, recorded, then stop deadlocked.
- The hung session's transcribed text was unrecoverable: diag logs store only `text_len` (not content), and the Doubao final never returned.
- Fix 1 (`audio.py`): `stream.stop()/close()` now runs on a daemon thread with a 2s timeout (`_close_stream_safely`); on timeout the zombie stream is abandoned and a PortAudio re-init is flagged for the next `start()`. The stop worker always returns.
- Fix 2 (`service_controller.py`): `_recover_if_busy_stuck` backstop force-clears `_processing_busy` if it stays wedged > `BUSY_BACKSTOP_S` (90s).
- Fix 3 (`service_controller.py`): `recorder_changed` now includes `input_device`, so switching mics rebuilds the recorder (safe teardown) instead of swapping config under a live/dead stream — the device-switch crash path.
- Added 9 targeted tests (deadlocking-teardown for cancel()/stop_and_save(), PA-reset on next start, busy backstop, mic-switch rebuild). Full suite 330 green. Fix commit `b6260e6`.
- Built + signed (stable Apple Development cert), packaged v3.5.1 zip+dmg, tagged `v3.5.1`, pushed, GitHub release published.

Current state:
- App is WhisperKey `3.5.1`. ASR engine `doubao`, processing mode unchanged.

Next steps:
1. Operator on-device validation: disconnect a Continuity mic mid-recording, confirm stop completes within ~2s and the next recording works (no permanent `service_busy`).
2. Watch the wild for `stream_close_timeout` and `processing_busy_backstop_reset` diag events.

Decisions / notes:
- A truly deadlocked CoreAudio device may still cost one lost recording; the fix guarantees the *app* recovers, not that the wedged C-level thread unblocks. The next `start()` re-inits PortAudio to clear wedged global state.
- Transcriptions captured during a hang are NOT recoverable (logs store length only, final never arrives).

---

## Milestones

- 2026-06-22 | v3.5.1 released — CoreAudio teardown deadlock fix (recording-stuck/service_busy) | ✅
- 2026-06-21 | v3.5.0 released — mic robustness + auto-stop on disconnect + Doubao dedup | ✅
- 2026-06-15 | Doubao ASR engine refactor installed; utterance accumulation next | ✅
- 2026-06-14 | Doubao packaged-app live ASR fixed; ASR-engine UX refactor next | ✅
- 2026-06-14 | Doubao app audio no-text fixed by PCM coalescing; live packaged recognition confirmed | ✅
- 2026-06-14 | Single-thread WebSocket I/O fixed packaged-app TLS crash | ✅
- 2026-06-14 | Doubao v3 empty-text fixed via request params + NEG_SEQUENCE final detection | ✅
- 2026-06-14 | Doubao Mode UX implemented; initial packaged test failed no-output | ⚠️
- 2026-06-12 | Model download UX + Doubao streaming ASR + security fixes landed | ✅
- 2026-06-11 | v3.1.0 released with self-update, auto TCC recovery, check-for-updates
- 2026-06-11 | v3.0.2 packaged with hotkey self-healing for restored permissions
- 2026-06-04 | v3.0.1 shipped with handsfree hotkey fix and public release

## Archive

_(empty)_
