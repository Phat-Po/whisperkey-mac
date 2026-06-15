# Handoff: Doubao live display and final output should preserve full utterance history — 2026-06-15

## Operator Intent

The operator provided a screen recording and asked for analysis of two related Doubao ASR behaviors:

- Live transcription display has sentence-level delay / switching behavior.
- After recording ends, the final output / clipboard contains only the last spoken sentence, not the full corrected content.

Important operator constraints:

- Use the video as the main reference.
- Do not assume Summary was enabled.
- Preserve the current use case: correction + filler-word cleanup (`voice_cleanup`) is enough unless the user explicitly asks for Summary.
- Do not invent unsupported fixes.

Video path:

```bash
/Users/pohanlee/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/sexybubu_7f99/msg/video/2026-06/bf1257b3a4871b40649d6223cabc41ea_raw.mp4
```

Video facts already observed:

- Duration: 47.23s.
- Resolution: 1716x136; it mostly records the WhisperKey overlay.
- Timeline:
  - ~3-10s: first sentence appears: `好的，我们这个新的功能已经上线了。`
  - ~12-36s: second sentence appears and replaces the first: `鉴别我们的这个讲话的，呃，这个字，而...`
  - ~37-40s: third sentence appears and replaces the second: `呃，但他有一个免费的使用，是否可以连续...`
  - ~41-43s: processing indicator.
  - ~44s: final output is only the third sentence after cleanup: `呃，但他有一个免费的使用，是否可以连续录20个小时都是免费的。`

Conclusion from video: Doubao live results are behaving like current utterance / current sentence text, not complete cumulative transcript text. The app currently overwrites stored final text with each latest response, so only the last utterance survives into post-processing and clipboard/output.

## Current Repo State

Project root:

```bash
/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main
```

Recent completed work in the same working tree:

- Doubao was refactored from a text processing mode into a dedicated ASR engine field (`asr_engine = local | doubao`).
- Processing mode is now separate (`disabled`, `asr_correction`, `voice_cleanup`, `custom`).
- `/Applications/WhisperKey.app` was rebuilt and installed from `dist/WhisperKey.app`.
- Installed app version: `3.2.3`; installed build time: `2026-06-14 17:51:03`; signature verification passed.

At handoff time, that ASR-engine refactor is uncommitted until the handoff snapshot commit is created. Do not assume a clean worktree if continuing before the snapshot commit.

## Relevant Current Configuration

Config read from `~/.config/whisperkey/config.json` during analysis:

```text
asr_engine=local
online_prompt_mode=voice_cleanup
online_correct_enabled=True
online_correct_model=gpt-5.4-mini
online_prompt_custom_text=
output_language=auto
transcribe_language=zh
doubao_app_id=SET
doubao_access_key=SET
```

Notes:

- The screen recording clearly shows the Doubao real-time overlay, so the recording likely happened before the user later switched `asr_engine` back to `local`, or before/around the ASR-engine refactor.
- `online_prompt_mode=voice_cleanup` explains why there was no Summary. This is expected and should not be treated as a bug.

## Root Cause Hypothesis

Primary issue:

- `DoubaoStreamingASR._handle_response()` currently treats every `text` as the latest complete transcript:

```python
self._final_text = text
```

- This was based on an earlier assumption/test that `/sauc` bigmodel text is cumulative.
- The video shows real app behavior is utterance-like: the result text resets when a new sentence starts.
- Therefore `_final_text` becomes only the last sentence, and `_stop_streaming_asr()` returns only the last sentence.
- `ServiceController._stop_and_transcribe_worker()` then sends only that last sentence into `_process_and_inject_text()`, so `voice_cleanup` only sees and outputs the last sentence.

Live display issue:

- `ServiceController._start_streaming_asr()` currently passes every partial directly to `overlay.show_streaming_text(text)`.
- This is acceptable if the intended live UI is “current sentence only”.
- The perceived delay before switching to a new sentence is mostly bounded by when Doubao emits the first partial for the new utterance. The app cannot show text for a sentence before the ASR service emits it.
- A UI-only improvement is possible: clear/fade old sentence after a pause or when a shorter replacement appears, but this is secondary and should not be mixed into the first correctness fix unless tests already pass.

## Minimum Reading List

Read in this order:

1. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/AGENTS.md`
2. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/STATUS.md`
3. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/tasks/HANDOFF-20260615-doubao-streaming-utterance-accumulation.md`
4. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/whisperkey_mac/doubao_asr.py`
5. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/whisperkey_mac/service_controller.py`
6. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/whisperkey_mac/overlay.py`
7. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/whisperkey_mac/online_correct.py`
8. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/tests/test_doubao_asr.py`
9. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/tests/test_main.py`
10. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/tests/test_overlay.py`

## Suggested Implementation Plan

### 1. Preserve current ASR-engine refactor state

Before editing, run:

```bash
git status --short
git log --oneline -5
```

If the handoff snapshot commit exists, start from that clean state. If not, do not overwrite the existing ASR-engine refactor changes.

### 2. Change Doubao ASR text state from “latest response only” to “final transcript + current partial”

Recommended shape inside `DoubaoStreamingASR`:

- Add state for finalized utterances, e.g.:
  - `_utterances: list[str]`
  - `_current_text: str`
- On non-final partial:
  - update `_current_text = text`
  - call `on_partial(text)` so the live overlay can continue showing only current sentence.
- On final:
  - append a deduplicated final utterance to `_utterances`
  - update `_final_text = joined utterances`
  - call `on_final(joined full transcript)` or call with the final utterance only only if service code does not rely on it. Be explicit and update tests either way.
- `stop()` should return full joined transcript.

Deduplication is important:

- Some responses may still be cumulative within the same utterance: `OK` -> `OK，我测试一下` -> final `OK，我测试一下有没有东西呀？`.
- Do not append all partials.
- Append only final utterance boundaries.
- If the final text starts with the previous final transcript, treat it as cumulative and store it directly.
- If the final text is a new sentence, append it with a natural separator.
- Avoid duplicating text if the same final arrives twice.

Possible helper:

```python
def _merge_final_text(existing: str, incoming: str) -> str:
    if not existing:
        return incoming
    if incoming.startswith(existing):
        return incoming
    if existing.endswith(incoming):
        return existing
    return existing.rstrip() + "\n" + incoming.lstrip()
```

This is deliberately conservative: newline is fine because `_process_and_inject_text()` and `voice_cleanup` can normalize it. If product prefers punctuation spacing, adjust after tests.

### 3. Update tests first or alongside implementation

Existing stale test:

- `tests/test_doubao_asr.py::test_client_handles_v3_bigmodel_no_type_field`
- It says “recognized text is cumulative”. That assumption is stale after the video.

Add/adjust tests for:

- Single utterance cumulative partials still return one complete final.
- Multiple utterance finals return the joined full transcript.
- Live partial callbacks still receive the current sentence, not the joined full transcript.
- Final callback behavior is explicit and covered.
- Stop returns all finalized utterances, not only the last.

Add a service-level regression if practical:

- Doubao engine stop path calls `_process_and_inject_text()` with full joined text.

### 4. Keep Summary out of scope

Do not add Summary mode or default summary behavior.

The user’s current desired processing is correction / filler-word removal:

- `online_prompt_mode=voice_cleanup`
- no custom summary prompt

If final output looks “not summarized”, that is expected.

### 5. Optional UI adjustment after correctness

Only after final transcript accumulation is fixed:

- Keep current live display behavior if only one current sentence line is acceptable.
- If improving sentence switching, consider clearing or dimming stale text when:
  - a pause threshold is crossed, or
  - a new partial is much shorter than the previous partial, indicating a new utterance.

Do not block the main fix on this. The video supports the need to fix final output more strongly than it supports a required live UI change.

## Commands To Verify

Use the venv, not system Python:

```bash
.venv/bin/python --version
.venv/bin/python -m pytest tests/test_doubao_asr.py tests/test_main.py tests/test_online_correct.py
.venv/bin/python -m pytest
bash packaging/macos/build_app.sh
```

Before staging/committing:

```bash
grep -RIn "sk-\|supabase\|Bearer\|password\|secret\|token" \
  --include="*.ts" --include="*.js" --include="*.py" \
  --exclude-dir=dist --exclude-dir=build --exclude-dir=.venv .
```

Expected matches are existing test placeholders (`sk-test`, `secret`) and variable names only. Do not commit real credentials.

## Risk Gates / Do Not Do

- Do not change Doubao protocol params unless a test/video proves it is necessary:
  - `result_type: "single"`
  - `show_utterances: False`
  - `vad.force_to_speech_time: 100`
  - final detection via `NEG_SEQUENCE`
  - single-thread WebSocket I/O
  - PCM coalescing into `CHUNK_BYTES`
- Do not reintroduce multi-thread WebSocket send/recv.
- Do not change Keychain/API key handling.
- Do not edit `.env*` or credential files.
- Do not change LaunchAgents, macOS permissions, signing, notarization, or packaging outputs casually.
- Do not `git push` without explicit operator confirmation.
- Installing to `/Applications` is an operator-visible app update; ask before doing it unless the operator explicitly says `批准执行`.

## Acceptance Criteria

The next implementation is done when:

- During Doubao ASR, live overlay can still show the current sentence.
- After recording stops, the text sent to `voice_cleanup` contains all spoken sentences, not only the final sentence.
- Clipboard/output contains the full corrected content.
- No Summary behavior is introduced unless the operator explicitly selects a custom summary mode.
- Relevant tests pass.
- Packaged app builds successfully.
