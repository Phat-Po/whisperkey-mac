# Handoff: Doubao should become an ASR engine, not a processing mode — 2026-06-14

## Operator intent

Doubao streaming ASR now works in the packaged app, but the product model is wrong.

The operator wants Doubao moved out of the text processing mode selector. Doubao should be one speech recognition engine / voice model option. It should only replace the ASR input layer. The text processing mode should remain a separate choice for what happens after recognition.

In product terms:

- Speech recognition engine / voice model: local faster-whisper or Doubao streaming ASR.
- Text processing mode: the existing post-recognition behavior, such as raw output vs cleanup/correction/summarization.

Operator's core wording:

> 豆包这个功能应该放在语音模型的选择里面，而不是处理模式，处理模式应该是还是那两种为主的。豆包只负责识别输入的部分。

## Current repo state

Project path:

```bash
/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main
```

Relevant latest commit before this handoff work:

```bash
1a967ef snapshot: before doubao H1 audio-send debug
```

There are currently local changes from the successful Doubao packaged-app ASR fix:

- `whisperkey_mac/doubao_asr.py`
- `tests/test_doubao_asr.py`

Those changes should be preserved and committed with this handoff/status work unless already committed by the time the next agent reads this.

## What was fixed this session

The previous bug was: packaged `.app` sent audio to Doubao but always ended with `streaming_asr_stopped text_len=0`.

H1 diagnostics showed audio was being sent, but in pathological chunking:

- packaged app callback produced `chunk_bytes=28`;
- around 4.1 seconds produced 4507 tiny WebSocket audio messages;
- total byte count was plausible, but server returned no recognition.

Fix implemented in `DoubaoStreamingASR`:

- `feed_audio()` now buffers tiny PCM fragments.
- It only enqueues send-sized chunks once the buffer reaches `CHUNK_BYTES` (100ms / 3200 bytes at 16kHz mono int16).
- `finish()` flushes any remaining tail audio before enqueuing the `None` sentinel.
- `_run_loop` remains the sole WebSocket owner.

Constraints preserved:

- Did not change request params.
- Did not change `NEG_SEQUENCE` final detection.
- Did not revert to multi-thread send/recv.

Validation already completed:

```bash
.venv/bin/python -m pytest tests/test_doubao_asr.py
# 26 passed

.venv/bin/python -m pytest
# 284 passed

bash packaging/macos/build_app.sh
bash tasks/doubao-debug/whisperkey-install-fix.sh
```

Packaged app installed to `/Applications/WhisperKey.app` with build time `2026-06-14 17:23`.

The operator manually verified the packaged app after reinstall:

> 有了有了。能实时识别了。

## Next task

Refactor product semantics so Doubao is selected as a speech recognition engine / voice model, not as a text processing mode.

Target behavior:

1. User chooses ASR engine separately:
   - local faster-whisper
   - Doubao streaming ASR
2. User chooses text processing mode separately:
   - keep the existing two primary processing modes as the operator expects
   - Doubao must not imply summarize/cleanup behavior by itself
3. If ASR engine is Doubao:
   - Doubao handles speech-to-text recognition only
   - recognized text then flows into the selected post-processing mode
4. If ASR engine is local:
   - existing local recorder/transcriber flow remains available
   - recognized text still flows into the selected post-processing mode

## Minimum reading list

Read in this order:

1. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/AGENTS.md`
2. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/whisperkey_mac/config.py`
3. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/whisperkey_mac/settings_window.py`
4. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/whisperkey_mac/service_controller.py`
5. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/whisperkey_mac/menu_bar.py`
6. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/whisperkey_mac/i18n.py`
7. `/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main/tests/`

## Likely implementation shape

Use existing project patterns and keep the change focused.

Possible config model:

- Add a dedicated ASR engine field, e.g. `speech_engine` or `asr_engine`.
- Values could be `local` and `doubao`.
- Keep post-processing mode separate. Do not keep using `online_prompt_mode == "streaming"` as the long-term Doubao trigger.
- Add a migration/default so existing users do not break.

Service flow should become:

```text
record audio / stream audio
  -> ASR engine produces recognized text
  -> selected text processing mode transforms or preserves that text
  -> inject/copy result
```

For Doubao:

- use streaming ASR for recognition;
- show live text while speaking;
- on final text, pass the recognized text through the selected processing mode.

For local faster-whisper:

- preserve existing recording and local transcription behavior;
- then pass recognized text through the selected processing mode.

## Important constraints

Do not change the working Doubao protocol details:

- `result_type: "single"`
- `show_utterances: False`
- `vad.force_to_speech_time: 100`
- final detection via `NEG_SEQUENCE`
- single-thread WebSocket I/O
- PCM coalescing into `CHUNK_BYTES` before queueing

Do not:

- reintroduce multi-thread send/recv;
- push to GitHub;
- edit `.env*` or credentials;
- change packaging/signing/notarization casually;
- change LaunchAgents or macOS permissions flows without explicit confirmation.

Preserve bilingual UI strings unless the operator explicitly changes copy.

## Suggested verification

Before edits:

```bash
git status --short
```

Before staging:

```bash
grep -RIn "sk-\|supabase\|Bearer\|password\|secret\|token" \
  --include="*.ts" --include="*.js" --include="*.py" .
```

Tests/build:

```bash
.venv/bin/python -m pytest
bash packaging/macos/build_app.sh
bash tasks/doubao-debug/whisperkey-install-fix.sh
```

Manual packaged-app verification:

1. Choose Doubao as speech recognition engine.
2. Choose each post-processing mode separately.
3. Hold `alt_r`, speak, release.
4. Confirm live Doubao recognition appears.
5. Confirm final output follows the selected processing mode, not an implicit Doubao summarize mode.

