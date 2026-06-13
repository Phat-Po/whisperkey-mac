# WhisperKey — Status

## Current

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
