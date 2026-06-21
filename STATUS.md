# WhisperKey — Status

## Current

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

### 2026-06-21 | v3.5.0 released — mic robustness + auto-stop on disconnect + Doubao dedup

Done this session:
- Shipped v3.5.0 (three workstreams). A: mic offline auto-fallback + 🔄 refresh (already in tree, verified). B: auto-stop when a pinned mic disconnects mid-recording (callback-stall watchdog → normal transcribe path) + auto-reconnect via PortAudio re-enumeration. C: fixed severe Doubao duplicated-output bug.
- C root cause (confirmed via a live C-1 capture, instrumentation since removed): the v3 bigmodel re-recognizes the whole stream (rough pass + refined pass with overlapping utterance timestamps); old prefix-match accumulation treated each revision as a new utterance → duplication (captured 117 chars for a 53-char utterance). Fix: `show_utterances:true` + consume `result.utterances[]`, committing `definite` segments across messages and merging by TIME-SPAN OVERLAP (latest wins). Locked in by `test_re_recognition_overlapping_spans_dedup` built from the real capture.
- Full suite 322 green. Built + signed (stable Apple Development cert), reinstalled `/Applications/WhisperKey.app` at 3.5.0 (clean startup verified). Tagged `v3.5.0`, pushed, GitHub release published, announced to 野生指挥部 + AI学习交流群（日不落版）.

Current state:
- Installed app is WhisperKey `3.5.0`. Commits: snapshot `d2f011e`, B `bcf8cbd`, C `3e3e6f1`. ASR engine `doubao`, processing mode `voice_cleanup`.

Next steps:
1. Operator to live-validate on-device (was skipped at publish per operator request): Doubao no-dup with filler-removal on; mic fallback; auto-stop on phone disconnect; auto-reconnect.
2. Watch for any show_utterances:true side effects on the live overlay / online-correction path.

Decisions / notes:
- B watchdog only runs for a pinned (non-default) device; default mic users unaffected.
- C: do NOT revert show_utterances to false — it's required for the dedup and C-1 proved recognition still works with it on.
- App cannot force-wake an iPhone Continuity mic (macOS limit); B-3 only reconnects once macOS re-lists it.

---

### 2026-06-15 | Doubao ASR engine refactor installed; next fix is utterance accumulation

Done this session:
- Refactored Doubao from a processing mode into a dedicated ASR engine (`asr_engine=local|doubao`) while keeping post-recognition processing mode separate.
- Verified the refactor with full tests (`290 passed`), packaged the macOS app, installed it to `/Applications/WhisperKey.app`, and verified code signature.
- Analyzed the operator's 47s overlay recording and identified that Doubao live results behave like current utterance text, not full cumulative transcript text.
- Created the next handoff: `tasks/HANDOFF-20260615-doubao-streaming-utterance-accumulation.md`.

Current state:
The installed app is WhisperKey `3.2.3` with build time `2026-06-14 17:51:03`. Doubao can now be selected as a speech recognition engine, and processing mode remains `voice_cleanup` / ASR correction / custom / disabled. The next known bug is that Doubao final output can contain only the last sentence because `DoubaoStreamingASR` overwrites `_final_text` with each latest response.

Next steps:
1. Preserve the current ASR-engine refactor snapshot and start from the new handoff.
2. Update `DoubaoStreamingASR` so final transcript accumulates finalized utterances while live overlay can keep showing only the current sentence.
3. Add regression tests for multi-utterance Doubao responses, then run full tests and rebuild the app.

Decisions / notes:
- Do not add Summary behavior; current expected post-processing is `voice_cleanup`.
- Do not change Doubao protocol params, single-thread WebSocket I/O, or PCM coalescing unless evidence requires it.
- Installing to `/Applications` and `git push` remain confirm-first actions.

---

### 2026-06-14 | Doubao packaged-app live ASR fixed; next step is ASR-engine UX refactor

Done this session:
- Diagnosed the packaged-app Doubao no-text failure: audio was being sent as thousands of 28-byte fragments, which kept the server from recognizing speech.
- Fixed `DoubaoStreamingASR.feed_audio()` to coalesce PCM fragments into 100ms / 3200-byte chunks before queueing for the single WebSocket I/O thread; `finish()` now flushes any tail audio before the end sentinel.
- Added focused tests for coalescing and final flush behavior.
- Verified `tests/test_doubao_asr.py` (26 passed), full test suite (284 passed), controlled Doubao TTS ASR recognition, app build, and `/Applications` reinstall.
- Operator manually confirmed packaged app now recognizes live Doubao speech.
- Created handoff for the next product refactor: `tasks/HANDOFF-20260614-doubao-asr-engine-refactor.md`.

Current state:
- Doubao TLS race and packaged-app no-text failures are fixed.
- `/Applications/WhisperKey.app` was rebuilt/reinstalled with build time `2026-06-14 17:23`.
- Remaining product issue: Doubao is currently modeled as a processing mode, but it should be a speech recognition engine / voice model option. Text processing mode should remain separate.

Next steps:
1. Preserve and commit the working Doubao ASR fix if not already committed.
2. Refactor config/UI/service flow so Doubao is selected as ASR engine, not text processing mode.
3. Verify that Doubao only performs recognition and the selected post-processing mode still controls final text handling.

Decisions / notes:
- Keep Doubao protocol params and `NEG_SEQUENCE` final detection unchanged.
- Keep single-thread WebSocket I/O; do not reintroduce TLS read/write concurrency.

---

## Milestones

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
