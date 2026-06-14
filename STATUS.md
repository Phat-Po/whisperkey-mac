# WhisperKey — Status

## Current

### 2026-06-14 | Single-thread I/O fix applied; TLS crash fixed but audio not recognized in app

Done this session:
- Implemented single-thread socket I/O in `DoubaoStreamingASR` (commit `a6ce19c`): `feed_audio` now enqueues PCM to a `queue.Queue`; `_run_loop` is the sole socket owner (drain queue → send → recv with 100ms timeout). Removed `self._lock` and multi-thread send/recv.
- Updated `tests/test_doubao_asr.py` with `WebSocketTimeoutException` mocking and 2 new tests.
- 283 tests pass. Rebuilt app, installed to `/Applications`.

Current state:
- TLS race crash is **FIXED** — no more `doubao_recv_error` on audio start.
- **New problem**: audio chunks queue up but server never returns recognized text. All 3 test recordings end with `streaming_asr_stopped text_len=0`. No `doubao_partial` or `doubao_final` events fire. Most likely the `_run_loop` drain-then-recv cycle has a timing issue (audio sent too late / in burst / loop stuck in recv).
- Local Whisper mode unaffected.

Next steps:
1. Diagnose why audio never produces recognition: add diag events in `_run_loop` to confirm chunks are actually sent and when. See 3 hypotheses in `tasks/HANDOFF-20260614-doubao-app-audio-never-recognized.md`.
2. Fix the loop timing, rebuild, reinstall, test.

Decisions / notes:
- Do NOT revert to multi-thread I/O — TLS crash is real and confirmed fixed.
- Request params and NEG_SEQUENCE final-detection remain correct (proven in terminal).

---

### 2026-06-14 | Doubao empty-text FIXED (committed); packaged-app TLS-concurrency bug handed off

Done this session:
- Fixed the Doubao "empty text" blocker in `doubao_asr.py` (committed `56ce536`): request params aligned to the working reference (`result_type:"single"`, `show_utterances:false`, `vad.force_to_speech_time:100`); final detection now uses the `NEG_SEQUENCE` flag (the `/sauc/bigmodel` endpoint sends no `type` field); cumulative text retained. Removed flood logging.
- Verified end-to-end in terminal: mic test returned real Chinese text. `281 tests pass`.
- Rebuilt + installed the fixed app to `/Applications` (same signing cert, permissions persisted).
- Diagnosed a NEW packaged-app-only failure: the Doubao WebSocket connects then drops immediately (`doubao_recv_error` → feed_error flood → empty). Isolated root cause to concurrent TLS read/write (recv thread + audio-callback send thread) that the app's bundled OpenSSL won't tolerate.
- Saved protocol notes to memory `ref-doubao-v3-asr-protocol.md`; preserved debug scripts in `tasks/doubao-debug/`.

Current state:
- Terminal/venv Doubao path: ✅ works (params + protocol correct, proven 3 ways).
- Packaged `/Applications/WhisperKey.app` (v3.2.3, 06-14 build): ⚠️ Doubao mode records but recognizes nothing — connection drops at audio start. Local Whisper mode unaffected. Repo clean at `56ce536`.
- The fix is NOT yet implemented — handed off.

Next steps:
1. Implement single-thread socket I/O in `DoubaoStreamingASR`: `feed_audio` enqueues PCM; `_run_loop` becomes the only thread that sends+recvs (settimeout + drain queue). Full spec in `tasks/HANDOFF-20260614-doubao-app-tls-concurrency.md`.
2. Update `tests/test_doubao_asr.py` mocks for the queue model; run `pytest`.
3. Rebuild, reinstall to `/Applications` (update the SRC path in the install script first), test a real recording.

Decisions / notes:
- Do NOT change the request params or the `NEG_SEQUENCE` final-detection — proven correct.
- Bug is packaged-app-only; venv tests only prove no-regression. True validation = rebuilt app.
- Ruled out: rate/concurrency limit, chunk size, proxy/VPN env, missing module, certs.

---

### 2026-06-14 | Doubao Mode UX implemented, packaged test fails streaming/no-output

Done this session:
- Implemented Doubao Mode UI/flow changes: mode naming, bottom bar click-to-start/stop, live streaming text surface, settings paste buttons, mode/status labels, and post-processing after Doubao ASR.
- Fixed misleading onboarding footer so it no longer says permissions are fully ready while permission rows still show ❌.
- Built signed local app at `dist/WhisperKey.app` and verified codesign.
- Ran full tests: `269 passed`.

Current state:
- Code/tests/build pass, but manual packaged-app test failed: Doubao Mode did not show streaming text and produced no output after recording ended.
- The likely issue is not the overlay UX layer; next debug should focus on `doubao_asr.py`, WebSocket dependency packaging, live auth/protocol, and diagnostics.
- Handoff doc: `tasks/HANDOFF-20260614-doubao-streaming-no-output.md`.

Next steps:
1. Reproduce with packaged app and inspect `/tmp/whisperkey-diag.log` for `doubao_*` / `streaming_asr_*` events.
2. Check WebSocket dependency mismatch: `doubao_asr.py` imports `websocket`, but `pyproject.toml` does not list `websocket-client`.
3. Validate Doubao binary protocol/auth against official Volcengine docs and make Settings Test Connection a real network check.

Decisions / notes:
- Do not silently fall back to local Whisper in Doubao Mode.
- Do not ask operator to paste credentials into chat; keep credentials local.
- Rebuilding `dist/WhisperKey.app` requires confirmation because build script clears generated artifacts.

---

### 2026-06-12 | Model download UX + Doubao streaming ASR + security fixes

Done this session:
- **Model download**: `model_manager.py` with tqdm progress, network check, cumulative byte tracking. Menu bar model submenu with download confirmation + progress. Settings Model tab with download buttons.
- **Doubao streaming ASR**: `doubao_asr.py` WebSocket client for real-time transcription. AudioRecorder `on_chunk` callback. Streaming mode in processing pipeline. Overlay `show_streaming_text()` for live results.
- **Security**: Updater URL domain allowlist, bundle ID verification before rmtree.
- **Updater fix**: GitHub API rate limit (use `gh auth token` for 5000/hr quota).
- **Auto TCC reset**: Detects signing identity changes, clears stale permission records.
- 262 tests passing. App builds to `dist/WhisperKey.app`.

Current state:
- ✅ All features committed and building
- ⚠️ **Two unresolved UX bugs** — see `tasks/HANDOFF-20260612-model-ux-bugs.md`

Next steps:
1. **Fix Bug 1**: Menu bar hangs after model download completes (callback deadlock in `_on_model_download_finished`)
2. **Fix Bug 2**: Settings Model tab shows stale "downloaded" status after cache clear (check `model_local_path` logic)
3. Verify fixes with clean cache test
4. Rebuild and test end-to-end
5. If bugs fixed → bump version, build release, push to GitHub

Decisions / notes:
- tqdm subclass must use `disable=False` (huggingface_hub passes `disable=True` based on log level)
- tqdm subclass must strip `name` kwarg (huggingface_hub passes it, tqdm.std rejects it)
- Model cache is at `~/.cache/huggingface/hub/models--{org}--{name}/`
- Menu bar uses `dispatch_to_main` for thread-safe UI updates; watch for deadlocks

---

## Milestones

- 2026-06-11 | v3.1.0 released with self-update, auto TCC recovery, check-for-updates
- 2026-06-11 | v3.0.2 packaged with hotkey self-healing for restored permissions
- 2026-06-04 | v3.0.1 shipped with handsfree hotkey fix and public release

## Archive

_(empty)_
