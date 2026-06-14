# WhisperKey — Status

## Current

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
