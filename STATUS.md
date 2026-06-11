# WhisperKey — Status

## Current

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
