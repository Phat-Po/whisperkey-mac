# v3.5.0 — Combined Plan (mic robustness + auto-stop-on-disconnect + Doubao dedup)

> Single release bundling three workstreams. **A is already implemented in the
> working tree** (built/installed locally as 3.4.1 but never released — re-version
> to 3.5.0). **B and C are not yet implemented.** Execute B and C, then ship one
> release. Follow the repo workflow: snapshot → implement → verify → (push gated).

Status legend: ✅ done · 🔲 to do

| # | Workstream | Status |
|---|-----------|--------|
| A | Mic offline auto-fallback + 🔄 refresh button | ✅ in working tree |
| B | Phone disconnect → auto-stop + auto-process; auto-reconnect next time | 🔲 |
| C | Doubao "去除干扰词" duplicated-output bug | 🔲 |

Target version: **3.5.0** (minor — contains a new feature).
`pyproject.toml` currently says `3.4.1` from workstream A → **change to `3.5.0`**.

---

## Workstream A — Mic robustness (ALREADY DONE — verify only)

Already committed in working tree. The executing agent should NOT re-implement;
just confirm these exist and pass:

- `whisperkey_mac/audio.py`: module fn `_input_device_online(name)`; `start()`
  resolves the configured device, falls back to default if offline (diag
  `input_device_unavailable_fallback`); `_open_stream()` retries once with the
  default device on `ValueError`/`PortAudioError`; recorder exposes
  `active_device_name` + `fell_back_to_default`.
- `whisperkey_mac/service_controller.py::_start_recording`: `self._recorder.start()`
  wrapped in try/except so recording can never crash the hotkey listener.
- `whisperkey_mac/settings_window.py`: `_MIC_OFFLINE_SUFFIX`, 🔄 refresh button
  (`refreshMicDevices_`), `_populate_mic_popup()`, save strips the offline suffix.
- `tests/test_audio.py`: AUD-05 device-resolution/fallback tests.

Verify: `pytest tests/test_audio.py` green (was 14 passed).

> NOTE: B improves A's refresh button — see B-3 (PortAudio re-enumeration). The
> 🔄 button today can return a stale device list; B-3 fixes that.

---

## Workstream B — Auto-stop on phone disconnect + auto-reconnect

### Goal
1. While recording with a **pinned** (non-default) mic, if that device disconnects
   mid-recording → **automatically stop and run the normal downstream task**
   (transcribe → correct → inject), no manual stop needed.
2. Next recording **auto-reconnects** to the same phone once macOS re-exposes it
   (no re-selection). Cannot *force-wake* the phone (OS/Continuity limit) — only
   reconnect when available.

### Key technical constraints (do not violate)
- **Never call `sd._terminate()` / `sd._initialize()` while a stream is open** —
  it will break the active stream / crash. Re-enumerate ONLY when no stream is
  open (before opening one, or in settings while not recording).
- Detect mid-recording disconnect via a **callback-stall watchdog**, NOT by
  polling `query_devices()` (the device list can't be refreshed during an open
  stream anyway). When a CoreAudio input device is removed mid-stream, PortAudio
  stops invoking the callback; "no audio callback for N seconds" = disconnect.

### B-1. Callback-stall tracking — `whisperkey_mac/audio.py`
- Add `self._last_chunk_time: float = 0.0` (init in `__init__`).
- In `start()`, set `self._last_chunk_time = time.monotonic()` right after
  `self._recording = True` (import `time`).
- In `_callback`, update `self._last_chunk_time = time.monotonic()` on every call
  (inside the lock is fine; keep it cheap).
- Add a thread-safe read property:
  ```python
  @property
  def seconds_since_last_chunk(self) -> float:
      with self._lock:
          if not self._recording or self._last_chunk_time == 0.0:
              return 0.0
          return time.monotonic() - self._last_chunk_time
  ```
- Harden teardown against a device that's already gone — wrap the
  `stream.stop()` / `stream.close()` calls in BOTH `stop_and_save()` and
  `cancel()` in `try/except Exception` (log via diag `stream_close_error`).
  A removed device can make these raise.

### B-2. Disconnect watchdog — `whisperkey_mac/service_controller.py`
- Reuse the pattern in `diagnostics.py` (`threading.Thread` + `threading.Event`).
- Start the watchdog at the end of `_start_recording` (after `recording_started`),
  ONLY when a specific device is pinned and actually in use:
  `if getattr(self._recorder, "active_device_name", ""): self._start_disconnect_watchdog()`
  (If we fell back to default, `active_device_name == ""` → no watchdog; default
  mic doesn't "disconnect" the same way. Compatibility preserved.)
- Watchdog loop (daemon thread, ~0.5s tick, stored stop-Event):
  - If recorder no longer recording → exit.
  - If `recorder.seconds_since_last_chunk > STALL_THRESHOLD_S` (use **1.5s**) for
    **2 consecutive ticks** → treat as disconnect.
  - On disconnect: diag `recording_autostop_device_lost`,
    device=active_device_name; show a brief overlay hint (reuse
    `overlay.show_busy_mode_switch_hint` via `dispatch_to_main` with a localized
    "麦克风已断开，正在处理…" / "Mic disconnected, processing…"); then call the
    SAME stop path as hotkey release: `self._stop_and_transcribe()` and
    `self._hotkey.reset_state()`. Then exit the loop.
- Stop the watchdog in `_stop_and_transcribe` (normal path) and in any cancel
  path — set the stop Event so a normal release doesn't leave it running. Make
  start/stop idempotent (guard re-entry).
- Idempotency: if auto-stop fires and later the user releases the hold key,
  `_stop_and_transcribe` is guarded by `_processing_busy` / not-recording → it
  logs "ignored". Confirm this is harmless (it already is).
- Threshold constant: define `STALL_THRESHOLD_S = 1.5` and `WATCHDOG_TICK_S = 0.5`
  near the top of service_controller (or as class attrs). Rationale: callbacks
  arrive every ~10–50ms, so 1.5s with 2-tick confirmation avoids false positives.

### B-3. Auto-reconnect via PortAudio re-enumeration
- **`whisperkey_mac/audio.py::start()`** — before resolving/opening the device,
  when a specific device is configured (`configured` non-empty), refresh the
  device list so a phone that reconnected after app launch is actually visible:
  ```python
  if configured:
      try:
          sd._terminate(); sd._initialize()
      except Exception:
          pass  # never block recording on a refresh failure
  ```
  Place this BEFORE the `_input_device_online(configured)` check. Do NOT do it for
  default-mic users (keeps start latency low; only pinned-device users pay the
  ~100–300ms re-init cost). No stream is open at this point → safe.
- **`whisperkey_mac/settings_window.py::refreshMicDevices_`** (and/or
  `_get_input_devices`) — re-enumerate before querying so the 🔄 button returns a
  truly fresh list:
  ```python
  try:
      import sounddevice as sd
      sd._terminate(); sd._initialize()
  except Exception:
      pass
  ```
  GUARD: skip the re-init if a recording is in progress (a stream is open). The
  settings window has access to the controller/recorder via the app; if not
  reachable, it's acceptable since settings refresh normally happens while idle —
  but prefer to guard. If no easy access, wrap in try/except (above) which already
  prevents a crash.

### B — Tests (`tests/test_audio.py`, maybe `tests/test_service_controller*`)
- `seconds_since_last_chunk`: 0.0 when not recording; grows when recording and no
  callbacks (monkeypatch `time.monotonic`).
- `stop_and_save` / `cancel` swallow a `stream.stop()` that raises (fake stream
  raising in stop/close → no exception propagates).
- Watchdog: if there's a testable seam, assert that a stalled recorder triggers
  `_stop_and_transcribe` once (mock the controller's recorder + hotkey). If
  wiring makes a clean unit test hard, at minimum unit-test the stall predicate.

### B — What is NOT possible (document in release notes)
- The app cannot **force-wake** an iPhone Continuity mic. Availability is decided
  by macOS/iOS (proximity, same Apple ID, Wi-Fi/BT, phone unlocked & offering).
  B-3 ensures we reconnect the instant macOS re-lists it; we cannot summon it.

---

## Workstream C — Doubao duplicated-output bug

### Root cause (confirmed)
`whisperkey_mac/doubao_asr.py` accumulates per-"utterance" text into
`self._utterances` and `"\n".join`s them. Boundary detection
`_is_utterance_continuation()` (doubao_asr.py ~221) uses **strict prefix match**.
In `result_type:"single"` mode Doubao **revises punctuation and re-segments**
mid-stream (e.g. `就是嘛，我` → `就是嘛？我…`, inserts `，`, drops leading
clauses). Each non-prefix revision is misread as a NEW utterance and committed →
the duplicated, progressively-growing lines the user saw.

Protocol facts (from memory `ref-doubao-v3-asr-protocol`): `result.text` is
cumulative **within a sentence** but **resets per sentence**; final marked by
`NEG_SEQUENCE` flag; **no `type` field**; current working params are
`result_type:"single"`, `show_utterances:false`, `vad.force_to_speech_time:100`
(do NOT change result_type to "full" — yields empty text).

### Fix strategy — protocol-correct, with a required verification checkpoint

Because the precise multi-sentence response shape can't be confirmed without a
live recording, do C in two steps. **C-1 requires ONE user test recording.**

#### C-1. Capture ground truth (temporary instrumentation)
- In `doubao_asr.py::_handle_message`, add a TEMPORARY diag that logs the RAW
  decoded payload per message: the full `result` object (str-cast, truncated to
  ~500 chars), `flags`, and whether `utterances` is present. Event:
  `doubao_raw_msg`.
- Also try enabling `show_utterances: true` behind a quick local toggle so the
  capture shows whether the endpoint returns a `result.utterances[]` array with
  `definite` flags in THIS account/endpoint.
- Build + install locally (see Release section's build step, no push), have the
  **user speak one multi-sentence utterance**, then read
  `grep doubao_raw_msg /tmp/whisperkey.log`.
- Decide between Plan C-α and C-β based on what the capture shows.

#### C-2α (PREFERRED if `result.utterances[]` with `definite` is present)
- Set `request.show_utterances = true` (doubao_asr.py ~411).
- Rewrite `_handle_message` accumulation to be **stateless across messages**:
  the latest message's `utterances` array already contains the full segmented
  transcript. Final/partial text = `"".join(u["text"] for u in utterances)`
  (verify joiner — likely no separator; Chinese needs none). Keep the latest
  message's assembly as the answer. **Delete `_is_utterance_continuation`,
  `self._utterances`, `self._current_text`** accumulation entirely.
- `is_final` still from `NEG_SEQUENCE` flag (unchanged).
- Confirm recognition still emits text (the memory warns `show_utterances:false`
  was the proven config — C-1 must prove `true` still recognizes; if it breaks
  recognition, fall back to C-2β).

#### C-2β (FALLBACK if utterances/definite NOT available — stay on show_utterances:false)
- Keep `result_type:"single"`, `show_utterances:false`.
- Replace the broken prefix-boundary model with a **commit-on-reset** model that
  tolerates revision:
  - Treat each incoming `text` as the FULL current-sentence text (it's
    per-sentence cumulative). Maintain only `current_sentence = text` (always
    REPLACE, never append within a sentence).
  - Detect a new sentence ONLY when the incoming text is clearly a fresh sentence
    — use the capture from C-1 to find the real signal (candidates seen in
    practice: a length DROP combined with no shared 4+ char prefix, or an
    `additions`/sentence-id field if present). Commit `current_sentence` to a
    finalized list, start new.
  - Final text = finalized sentences + current, joined appropriately.
  - This is heuristic; only use if C-2α is impossible. Prefer C-2α.

#### C-3. Remove temporary instrumentation
- Delete/guard the `doubao_raw_msg` raw logging from C-1 before shipping (or keep
  it gated behind an env var, off by default).

### C — Tests (`tests/test_doubao_asr.py`)
- Add a regression that feeds the user's exact sequence of revised partials and
  asserts the assembled output is the single correct sentence
  (`我就说是，肯定是因为这个原因，不然人家好端端删你干嘛？但他这样子行为也很奇怪，感觉好像是受了多大的侮辱一样。`),
  NOT the duplicated multi-line blob.
- Keep the existing lock-in test
  `test_client_handles_v3_bigmodel_no_type_field` green.
- If C-2α: add a test feeding a `result.utterances[]` payload and asserting join.

---

## Consolidated execution order (for the next agent)

1. `git status` clean-check; snapshot if needed:
   `git add -A && git commit -m "snapshot: before v3.5.0 work"` (A's changes are
   uncommitted — this snapshot captures them; that's fine).
2. Implement **B** (B-1 → B-2 → B-3) + tests. Run `pytest`.
3. Implement **C-1** (instrument) → build+install locally (NO push) → **ask user
   to record one multi-sentence sample** → inspect `/tmp/whisperkey.log`.
4. Implement **C-2α** (preferred) or **C-2β** based on C-1 → **C-3** cleanup →
   tests. Run full `pytest`.
5. Set `pyproject.toml` version `3.4.1` → **`3.5.0`**.
6. Rebuild + reinstall into `/Applications`:
   `bash packaging/macos/package_release.sh`, then stop app
   (`launchctl bootout gui/$(id -u)/com.whisperkey`), `ditto` new
   `dist/WhisperKey.app` → `/Applications/WhisperKey.app`,
   `xattr -dr com.apple.quarantine`, relaunch
   (`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.whisperkey.plist`).
   Verify Info.plist version = 3.5.0, signature valid (stable Apple Development
   cert keeps TCC grants), clean startup in `/tmp/whisperkey.log`.
7. **STOP for user validation** (mic fallback, auto-stop on phone disconnect,
   auto-reconnect, Doubao no-dup with filler-removal on).
8. After user confirms: commit everything; tag `v3.5.0`.
9. **GATED — ask the user "Ready to push to main. This will deploy to
   production. Confirm?" and wait** before `git push` + `gh release create`.
10. Release: `gh release create v3.5.0 -R Phat-Po/whisperkey-mac` with the
    `dist/release/WhisperKey-macOS-arm64-v3.5.0.{zip,dmg}` assets and the
    description below. Announce per repo CLAUDE.md routing (野生指挥部 bot chat +
    AI学习交流群（日不落版）webhook) — only after push confirmation.
11. Update `STATUS.md` (3-layer format) and the project memory
    (`mic-device-fallback`, add B + C notes; or new memory files).

---

## Affected files summary

| File | A | B | C |
|------|---|---|---|
| `whisperkey_mac/audio.py` | ✅ | B-1 stall tracking, teardown hardening, B-3 re-enumerate | — |
| `whisperkey_mac/service_controller.py` | ✅ | B-2 watchdog | — |
| `whisperkey_mac/settings_window.py` | ✅ | B-3 refresh re-enumerate | — |
| `whisperkey_mac/doubao_asr.py` | — | — | C-1/C-2/C-3 |
| `tests/test_audio.py` | ✅ | B tests | — |
| `tests/test_doubao_asr.py` | — | — | C regression |
| `pyproject.toml` | (→3.5.0) | | |

---

## Release description (draft — finalize after C decision)

**Title:** `WhisperKey v3.5.0 — 麦克风健壮性 + 断开自动处理 + 豆包去重修复`

**Body:**
```
## ✨ 新功能 / New
- 手机/外接麦克风断开连接时，自动停止录音并继续完成转写与输出，无需回到电脑手动停止。
  Auto-stop & auto-process when the selected mic (e.g. iPhone Continuity mic)
  disconnects mid-recording.
- 下次录音自动重连同一台手机（一旦 macOS 重新识别到它），无需重新选择。
  Auto-reconnect to the same phone mic once macOS re-exposes it.

## 🛠 改进 / Improved
- 选定的麦克风离线时自动回退到系统默认麦克风，不再崩溃 / 无法启动。
  Offline mic now falls back to the default device instead of failing to start.
- 麦克风设置新增 🔄 刷新按钮，实时重新枚举可用设备（修复设备列表陈旧问题）。
  New 🔄 refresh button re-enumerates audio devices live.

## 🐞 修复 / Fixed
- 修复豆包语音 + 去除干扰词模式下输出大量重复句子的严重问题（识别中标点修订被误判为新句导致累积）。
  Fixed Doubao ASR producing duplicated/accumulated lines when filler-removal
  mode was on.

## ⚠️ 限制 / Note
- 受 macOS Continuity 限制，App 无法主动“唤醒”iPhone 麦克风；需手机在身边并解锁，
  macOS 重新提供后即自动重连。
```

---

## Risk gates (reminder)
- `git push` + `gh release` = GATED, ask first.
- Rebuild/repackage/reinstall to `/Applications` = the user has been authorizing
  this per session; confirm before reinstalling over the running app.
- Do not commit secrets (run the secret scan before `git add`).
- `show_utterances` change (C-2α) must be proven to still recognize text in C-1
  before shipping — the memory note explicitly set it `false` for a reason.
