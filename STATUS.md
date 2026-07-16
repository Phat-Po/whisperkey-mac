# WhisperKey — Status

## Current

### 2026-07-16 | v3.6.5 — free-release signing switched to self-signed cert (TCC grants persist across updates)

Done this session:
- Root issue: free public releases were ad-hoc signed (`codesign --sign -`), whose designated requirement is `cdhash H"..."` — tied to the exact binary content, so it changes on every rebuild. macOS TCC treats each new release as a brand-new app and drops end users' Accessibility/Input Monitoring/Microphone grants on every update, forcing a manual re-grant after each upgrade. This affects anyone downloading a new version from GitHub Releases, not just local rebuilds.
- Confirmed a self-signed certificate ("WhisperKey Dev", already present in this Mac's login keychain, valid until 2027-04-15, generated 2026-04-15) had never been trusted for code signing (`security dump-trust-settings` showed no entry) — that's why it wasn't showing as a usable identity. Trusted it (`security add-trusted-cert -p codeSign`) and granted its private key "Always Allow" access via Keychain Access (needed once — `codesign --deep` touches 1000+ nested binaries and without this ACL grant it re-prompts per binary).
- Verified this is a real fix, not just cargo-culting the earlier failed attempt: signed a throwaway build with "WhisperKey Dev" and confirmed (a) `codesign -d -r-` now shows `identifier "com.phatpo.whisperkey" and certificate leaf = H"49b459..."` instead of a cdhash — i.e. identity is content-independent — and (b) the app launches and runs standalone outside Xcode/terminal (unlike the earlier `bb36389` attempt at this with an "Apple Development" identity, which got silently killed by AMFI before the process even became "WhisperKey" — confirmed via `log show` at the time, never merged, reverted same night as `2ce27cd`). Self-signed certs aren't subject to that Xcode-trust restriction.
- `packaging/macos/build_app.sh`: `free-release` mode now tries the "WhisperKey Dev" identity first (falls back to ad-hoc + warning if not present on the build machine — e.g. a fresh machine or after the cert expires).
- `packaging/macos/package_free_release.sh`: signature verification updated to accept either ad-hoc or `Authority=WhisperKey Dev`; artifact filenames and install note renamed `free-unsigned` → `free-selfsigned` to reflect what's actually happening (README.md/README.zh.md/RELEASE.md updated to match).
- No app code changed — same binary logic as the v3.6.4 tag, only the signing step differs. Repackaged and re-verified (337 tests green, `codesign --verify --deep --strict` passes, standalone launch confirmed) before bumping to 3.6.5.

Current state:
- Not yet published. Built and pre-release-checked locally; operator wants a version bump (3.6.4 → 3.6.5) and the `free-selfsigned` rename before this goes out, both done.

Next steps:
1. Publish: commit, push, tag `v3.6.5`, create GitHub release with the new `free-selfsigned` artifacts and updated checksums — pending explicit go-ahead (release/deployment risk gate).
2. Caveat to disclose in release notes: this only fixes TCC persistence for future updates onward. Anyone still on v3.6.4-or-earlier (ad-hoc signed) upgrading to v3.6.5 will need to re-grant permissions **once more** (identity type itself is changing), but every release after that should carry over.
3. The unrelated main-thread deadlock noted below (2026-07-16 entry) is still unfixed — do not imply in release notes that this release addresses it.

Decisions / notes:
- The "WhisperKey Dev" certificate lives only on this Mac and is never distributed to end users — they don't need to trust or install anything extra; they still go through the normal Gatekeeper "Open Anyway" flow once per new version (unrelated to TCC).
- If a paid Apple Developer ID Application certificate is ever added to this machine, the more standard fix is switching public releases to `packaging/macos/package_release.sh` (notarized) instead of maintaining this workaround.

---

### 2026-07-16 | v3.6.4 live — main-thread deadlock in a delayed-perform callback froze the whole app

Done this session:
- Operator reported the app "frozen" (not crashed, process still alive, hotkey/UI totally unresponsive). Diagnosed via `sample <pid> -f` (10s, 1ms interval) on the live hung process instead of guessing.
- Root cause: the main thread (`DispatchQueue_1: com.apple.main-thread`) was blocked inside AppKit's `__NSFireDelayedPerform` → a PyObjC-bridged Python callback → `PyThread_acquire_lock` (`lock_PyThread_acquire_lock` → `acquire_timed` → `_pthread_cond_wait`). Something scheduled a delayed perform (likely via `performSelector:withDelay:` / NSTimer-backed `callLater`, the same mechanism flagged in the 2026-07-12 hotkey audit) whose callback tries to acquire a Python lock that was already held and never released by another thread — the main run loop (`NSApplication run` / `CFRunLoopRun`) can't proceed until that lock is granted, so every UI/hotkey event queues forever.
- No crash report was generated for this specific freeze (last `.ips` in `~/Library/Logs/DiagnosticReports/` was the 2026-07-15 SIGTRAP, a different/already-known issue) — this deadlock is silent, only visible via `sample`/`spindump`, which is why it wasn't caught by crash reporting.
- Killed (`kill -9`) both the main process and its watchdog/parent, relaunched `/Applications/WhisperKey.app`. No code fix applied yet — this is a live-incident diagnosis, not a resolution.
- Sample kept at `/tmp/whisperkey-hang-sample.txt` (session-scratch, not committed).

Current state:
- App is WhisperKey `3.6.4`, freshly relaunched, working as of restart.
- The specific lock/callback that deadlocked was NOT identified by name — only the call chain down to `PyThread_acquire_lock` was captured. Needs source-level investigation to find which `threading.Lock`/`RLock` is held across a delayed-perform boundary.

Next steps:
1. Grep `main.py` / `service_controller.py` for `performSelector.*withDelay` / `callLater`-style delayed dispatch and check what locks their callbacks acquire, cross-referencing anything also acquired by a background thread (ASR worker, audio stream teardown) that could stay held.
2. If it recurs, capture a fresh `sample <pid> -f <path> -t 5` immediately (before killing) to confirm whether it's the same lock/call site — this incident's sample already gives the exact frame to match against.
3. Consider a watchdog: if the main thread hasn't processed the run loop in N seconds, log a diag event before the user notices a full freeze (mirrors the tap-liveness watchdog idea already backlogged in `tasks/TASK-2026-07-12-hotkey-stability-fixes.md`).

Decisions / notes:
- Distinct from the 2026-07-15 SIGTRAP crash (`bug-sigtrap-tis-mainthread` memory) and the CoreAudio teardown deadlock (`bug-coreaudio-teardown-deadlock` memory) — this is a *new* deadlock class (Python lock contention inside a main-thread delayed-perform), not previously diagnosed or fixed.

---

### 2026-07-13 | v3.6.4 — hotkey tap stability, zero-fork diagnostics, instant settings apply

Done this session:
- Fixed the "hotkey stops working, especially after switching Bluetooth keyboards" bug via a five-part root-cause chain: `diagnostics.py`'s `diag()` forked a `ps` subprocess on every hotkey press inside the synchronous CGEventTap callback (perceptible lag); macOS's `kCGEventTapDisabledByTimeout` protection silently killed the tap when that callback ran too slow, and pynput 1.8.1 never re-enabled it (hotkey death until app restart); a disconnected Bluetooth key held mid-press left a permanent "ghost key" in `_held_keys` with no expiry.
- `diagnostics.py`: `diag()` now reads from a background-refreshed cache (10s cycle) — zero subprocess forks on the hot path.
- `keyboard_listener.py` / `service_controller.py`: tap reference exposed; auto `CGEventTapEnable` re-enable + logging on `TapDisabledByTimeout`; existing 3s AX-monitor loop now double-checks tap liveness as a watchdog; `_held_keys` changed to `dict[key, timestamp]` with a 45s TTL sweep for ghost keys.
- `main.py` / `service_controller.py`: new `is_actively_working` flag (excludes the 2s post-dictation UI-quiet window) — settings save/apply no longer waits behind it.
- `settings_window.py`: Usage tab lazy-loads (shows "Click Refresh to load" instead of scanning the multi-GB HF cache synchronously on window open).
- `config.py`: `save_config` now writes via tmp file + `os.replace` for atomic saves.
- 337 tests green. Operator confirmed fixed on-device.

Current state:
- App is WhisperKey `3.6.4`.

Next steps:
1. None required — deferred to backlog: Secure Input detection, tap-liveness heartbeat/supervisor, Bluetooth remote HID diagnostics, pynput upgrade evaluation (see `tasks/TASK-2026-07-12-hotkey-stability-fixes.md`).

Decisions / notes:
- Packaged free-unsigned (no paid Developer ID cert on this machine), consistent with v3.6.3.
- Full history/root-cause detail: `tasks/TASK-2026-07-12-hotkey-stability-fixes.md`.

---

### 2026-07-02 | v3.6.3 — fix asr_correction truncating long recordings

Done this session:
- Diagnosed a live report: recordings over ~3-4 minutes got truncated mid-sentence, on both the local Whisper and Doubao ASR backends. Traced it to a shared downstream step — `online_correct.py`'s "Remove Fillers" (`asr_correction`) mode, which runs after either transcription engine when online correction is enabled, had `max_output_tokens=256` hardcoded (vs 512-1024 for the other modes). Long transcripts' corrected output silently hit that cap and got cut off.
- Fix (`online_correct.py`): `max_output_tokens` for `asr_correction` now scales with input length (`min(4096, max(1024, len(text) * 2))`) instead of a flat 256.
- Full suite 335 green. Built + packaged free-unsigned v3.6.3 (zip/dmg/checksums).

Current state:
- App is WhisperKey `3.6.3`.

Next steps:
1. Operator: record 3-4+ minutes with "Remove Fillers" (asr_correction) mode enabled, confirm the pasted text is no longer truncated.
2. If truncation still reproduces, next hypothesis is the Doubao streaming `stop(timeout_s=5.0)` early-return in `service_controller.py` (H2 from the diagnosis, not yet investigated).

Decisions / notes:
- This only affects users with "AI 在线校正 / 去除口癖" (`online_correct_enabled`) turned on — off by default.
- Ceiling of 4096 tokens bounds cost for very long recordings; not a proven-safe max, just a sane guard.

---

### 2026-06-30 | v3.6.1 free-unsigned release published; install failure handoff prepared

Done this session:
- Added professional macOS packaging split: Developer ID notarized release path remains strict, and a new `package_free_release.sh` creates clearly labeled `free-unsigned` ad-hoc+hardened-runtime artifacts.
- Bumped app to `3.6.1`, built `WhisperKey-macOS-arm64-v3.6.1-free-unsigned.{dmg,zip}` plus SHA256SUMS, verified checksums, mounted DMG, confirmed app version/signature, and ran targeted tests (`38 passed`).
- Pushed `main`, tagged `v3.6.1`, and published GitHub Release: https://github.com/Phat-Po/whisperkey-mac/releases/tag/v3.6.1
- Operator reported downloaded app cannot open after dragging to Applications and no service/menu bar appears. Collected first evidence: installed app is `3.6.1`, `Signature=adhoc`, `Runtime Version=15.4.0`, `spctl` rejects it, and Chrome quarantine attributes remain across the bundle.
- Wrote next-agent handoff: `tasks/HANDOFF-20260630-v3.6.1-free-unsigned-install-failure.md`.

Current state:
- Superseded by later releases (v3.6.3, v3.6.4) which shipped as free-unsigned and were confirmed installable/working — the install-failure investigation for this specific v3.6.1 build was not separately closed out, but is moot given later releases work.
- `/Applications/WhisperKey.app` exists; no active WhisperKey process or LaunchAgent was found during the evidence pass.

Next steps:
1. None — moot, later releases confirmed working.

Decisions / notes:
- No Developer ID is available; do not claim a no-warning normal install is possible for the free build.
- Keep free artifacts labeled `free-unsigned`; do not silently replace them with ad-hoc files under normal release names.

---

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
