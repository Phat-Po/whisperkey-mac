# Handoff: Doubao app — audio sent but never recognized (text_len=0) — 2026-06-14

## TL;DR

The TLS-concurrency crash is **FIXED** (commit `a6ce19c`): `DoubaoStreamingASR` now does all
socket I/O on a single thread. The packaged `.app` no longer drops the WebSocket on audio start
(no `doubao_recv_error`). But a **new problem** emerged: the server **never returns recognized text**.
Every recording ends with `streaming_asr_stopped text_len=0` — no `doubao_partial`, no `doubao_final`.

Your job: **diagnose why audio chunks reach the server but produce no recognition**, then fix. The
most likely cause is a timing/ordering issue in the new `_run_loop` — see hypotheses below.

**Do NOT revert to the old multi-thread model** — that causes the TLS crash. The single-thread
approach is correct; the loop just needs to send audio chunks while recording, not only after.

---

## What was DONE this session (committed `a6ce19c`, do not redo)

1. Refactored `DoubaoStreamingASR` to single-thread socket I/O:
   - Added `self._audio_queue = queue.Queue()` in `__init__`; removed `self._lock` and `self._sequence`.
   - `feed_audio(pcm)` → just `self._audio_queue.put(pcm)`. No socket access.
   - `finish()` → `self._audio_queue.put(None)` (sentinel). No socket access.
   - `_run_loop` is the sole socket owner: drains queue via `get_nowait()`, sends audio messages,
     then does `recv()` with 100ms timeout. Exits when `_finished` is set or socket closes.
2. Updated `tests/test_doubao_asr.py`: mocks now include `WebSocketTimeoutException` between
   responses; added `test_feed_audio_enqueues_without_socket_access` and `test_finish_enqueues_sentinel`.
3. **283 tests pass.** App rebuilt, installed to `/Applications`, launched.
4. Request params and `NEG_SEQUENCE` final-detection are **unchanged and correct** (from `56ce536`).

---

## The REMAINING bug (your task)

### Symptom (from `/tmp/whisperkey-diag.log`, packaged app only)

Consistent across 3 test recordings:

```
recording_start → doubao_connected → streaming_asr_started → recording_started
  (user speaks ~3-5 seconds)
→ recording_stop_requested → recording_stop_start → doubao_finish_sent
→ streaming_asr_stopped text_len=0
```

**Key observations:**
- `doubao_connected` ✅ — WebSocket connects and stays open (TLS fix works)
- NO `doubao_feed_error` — audio queue draining does not crash
- NO `doubao_recv_error` — socket is stable throughout
- NO `doubao_partial` or `doubao_final` — server never sends recognized text
- `doubao_finish_sent` fires — the end-of-stream packet IS sent
- `streaming_asr_stopped text_len=0` — final text is empty
- `recording_start_ignored reason=service_busy` floods after stop — the stop flow hangs for the
  full 5s `_finished.wait()` timeout, during which the user keeps pressing the hotkey

### Three hypotheses (ranked by likelihood)

**H1 (most likely): Audio chunks are never actually sent to the server.**

The `_run_loop` structure is: drain queue → recv (100ms timeout) → loop. But `_run_loop` starts
and connects BEFORE `recording_started`. Audio chunks arrive from CoreAudio at ~20ms intervals
and queue up. The loop should drain them, but consider:

- The loop may be spending all its time in the recv() call (blocking 100ms per iteration), and
  during that 100ms, 5 audio chunks (20ms each) pile up. When it finally drains, it sends them
  all in a burst, then blocks on recv again. This may work OR may not — depends on whether the
  server can handle burst sends.
- **More critically**: if the loop is somehow stuck in recv and never reaches the drain phase,
  audio piles up indefinitely. When `finish()` enqueues `None`, the loop drains everything in
  one go — audio + sentinel — and sends the end packet immediately after the audio, giving the
  server no time to process.

**Verification for H1:** Add `diag("doubao_audio_sent", queue_size=self._audio_queue.qsize())`
right after each successful `send_binary` of an audio chunk in `_run_loop`. If this never fires
in the packaged app log, audio is never being sent. If it fires many times right before
`doubao_finish_sent`, audio is being sent too late (burst at end).

**H2: Audio is sent but too late — all chunks arrive after the end-of-stream packet.**

Even if chunks are sent, the timeline might be: recv blocks → drain ALL queued chunks + sentinel
in one pass → end packet sent immediately after last audio chunk. The server needs time between
the last audio and the end signal to do recognition. The reference implementation (`zhouruhui/
volcengine-asr-ha`) uses real-time pacing (sleeps between sends to simulate mic timing). The
current loop sends everything as fast as it can.

**Verification for H2:** Add timestamps to `doubao_audio_sent` and `doubao_finish_sent` events.
If all audio and the finish happen within <100ms of each other, the server sees a burst of audio
+ immediate EOF and returns nothing.

**H3: The `_run_loop` exits prematurely before draining audio.**

The loop condition is `while self._running and not self._finished.is_set()`. If `_finished` gets
set by something else (e.g. a response handler or a race condition), the loop exits before sending
any audio. Check: is there any path where `_finished.set()` fires before the end packet?

**Verification for H3:** Add `diag("doubao_loop_exit", end_sent=end_sent, running=self._running,
finished=self._finished.is_set(), queue_size=self._audio_queue.qsize())` right after the while
loop. If `queue_size > 0` and `end_sent=False`, the loop exited too early.

---

## Files to read / touch

1. **`whisperkey_mac/doubao_asr.py`** — the `_run_loop` method (lines ~389-460). This is where
   the bug is. Focus on the drain-then-recv cycle and whether audio actually reaches `send_binary`.
2. **`whisperkey_mac/service_controller.py`** — `_stop_streaming_asr` (~lines 448-460) and
   `_start_recording` (~lines 505-527). The stop flow calls `asr.finish()` then `asr.stop(5s)`.
   Understand the timing: `on_chunk` is set to `None` BEFORE `finish()` is called, so no more
   audio arrives after stop begins — the queue has whatever was accumulated during recording.
3. **`whisperkey_mac/audio.py`** — the sounddevice callback (~line 120) that calls `on_chunk(pcm)`.
   Confirms chunks arrive at ~20ms intervals from CoreAudio.
4. **`tests/test_doubao_asr.py`** — update mocks as needed after the fix.
5. **`/tmp/whisperkey-diag.log`** — live diagnostic output from the packaged app.

### Key code to examine

The `_run_loop` drain-then-recv cycle:

```python
while self._running and not self._finished.is_set():
    # drain queue
    while True:
        try:
            chunk = self._audio_queue.get_nowait()
        except queue.Empty:
            break
        # ... send chunk or handle sentinel ...

    # recv with 100ms timeout
    try:
        data = self._ws.recv()
        ...
    except websocket.WebSocketTimeoutException:
        pass
```

The question: is the drain phase actually running and sending chunks during the recording?
Or is it only running after `finish()` is called? Add diagnostics to find out.

---

## Constraints

- **Do NOT revert to multi-thread send/recv** — the TLS race crash is real and proven.
- **Do NOT change** request params (`result_type:"single"`, `show_utterances:false`,
  `force_to_speech_time:100`) or `NEG_SEQUENCE` final-detection — proven correct in terminal.
- **Do NOT `git push`** without operator confirmation.
- The venv's editable install points to a different branch — run `pytest` and `build_app.sh`
  from this worktree root. The bug is packaged-app-only; venv tests prove no-regression only.
- After fixing, rebuild: `bash packaging/macos/build_app.sh`, then reinstall using
  `bash tasks/doubao-debug/whisperkey-install-fix.sh` (SRC path is already correct for this worktree).

## Validate

1. `python -m pytest` — all tests pass (no regression).
2. Rebuild and reinstall to `/Applications` (see Constraints above).
3. Menu bar → Doubao mode → hold `alt_r` → speak ~3s → release.
4. Check `/tmp/whisperkey-diag.log`: success = `doubao_connected` → `doubao_partial` (repeated) →
   `doubao_final` with `text_len > 0`. Failure = `streaming_asr_stopped text_len=0`.
5. The overlay should show live text while speaking, then inject into the active app.

---

## Quick reference

- Diag log: `/tmp/whisperkey-diag.log` — grep `doubao_`, `streaming_asr_`, `recording_`.
- Failure signature: `doubao_finish_sent` immediately followed by `streaming_asr_stopped text_len=0`,
  with zero `doubao_partial` events between `doubao_connected` and `doubao_finish_sent`.
- Success signature: `doubao_connected` → multiple `doubao_partial` → `doubao_final`.
- Protocol reference: memory `ref-doubao-v3-asr-protocol.md`.
- Debug scripts: `tasks/doubao-debug/` (verify, conn_probe, repro, install).
- Previous handoff (context chain): `tasks/HANDOFF-20260614-doubao-app-tls-concurrency.md`.
