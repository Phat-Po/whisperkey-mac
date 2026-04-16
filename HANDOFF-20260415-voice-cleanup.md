# Handoff — Voice Cleanup Feature & Prompt Work

**Date**: 2026-04-15  
**Project**: WhisperKey Mac  
**Path**: `/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac`  
**Branch**: `main`, ahead of `origin/main`. Do not push without operator confirmation.

---

## Current State — Feature is Working

Voice cleanup is fully functional. Confirmed live this session:

```
[wkdiag] event=online_correction_start mode=voice_cleanup
[wkdiag] event=online_correction_end elapsed_s=3.44 changed=True
[whisperkey] 已应用在线纠错
[whisperkey] → "If it's any sort of construction, I think you would excel at it..."
```

Active config (`~/.config/whisperkey/config.json`):
```json
"online_prompt_mode": "voice_cleanup",
"output_language": "en",
"online_correct_model": "gpt-4o-mini",
"online_correct_timeout_s": 15.0,
"online_correct_min_chars": 6,
"online_correct_enabled": true
```

No code changes are needed just to use the feature — it's wired up and working.

---

## Key Files

| File | Purpose |
|------|---------|
| `whisperkey_mac/online_correct.py` | All 3 prompts + pipeline logic |
| `whisperkey_mac/config.py` | `AppConfig` fields; `load_config()` / `save_config()` |
| `whisperkey_mac/settings_window.py` | Settings UI — mode popup, model field, timeout |
| `~/.config/whisperkey/config.json` | Live config written by Settings save |

---

## The Three Prompts (online_correct.py lines 20–118)

The prompt selected is based on `config.output_language`:

| `output_language` value | Prompt constant | Behavior |
|------------------------|-----------------|----------|
| `"zh"` | `_VOICE_CLEANUP_PROMPT_ZH` | Traditional Chinese expert; translate any non-ZH input to ZH first |
| `"en"` | `_VOICE_CLEANUP_PROMPT_EN` | English expert; translate any non-EN input to EN first |
| `"auto"` | `_VOICE_CLEANUP_PROMPT_AUTO` | Language-agnostic; output in same language(s) as input |

All three prompts share the same 3-layer structure:
1. **Denoise** — remove fillers, fix ASR errors
2. **Dedup & merge** — collapse hesitation, keep final conclusion
3. **Restructure** — semantic reorder, segment by topic

Special trigger: if user starts recording with `"笔记模式"` / `"note mode"`, prompt switches to bullet-note style output.

---

## Pipeline Flow

```
HotkeyListener._start_hold_recording()
  → ServiceController._start_recording()
  → AudioRecorder.stop_and_save()
  → Transcriber.transcribe(path)           # faster-whisper, respects config.language
  → _apply_word_replacements(text, cfg)    # config.word_replacements dict
  → maybe_correct_online(text, cfg)        # → maybe_process_online()
      → _prompt_mode(cfg)                  # reads online_prompt_mode
      → _should_process_online()           # min_chars=6, mode check
      → client.responses.create(...)       # openai Responses API
      → _extract_plain_text(output_text)   # plain string, not JSON
  → TextOutput.inject(final_text)          # AX → AppleScript → clipboard
```

The `"voice_cleanup"` path skips `max_chars` and `CJK ratio` guards (intentional — handles long/mixed text).

---

## What Might Need Work

The operator said "work on voice cleanup feature/prompt" without specifics. Likely candidates:

1. **Prompt quality** — test with real recordings and tune the 3 prompts in `online_correct.py`. The ZH/EN/AUTO variants are independent strings; any can be edited without touching logic.
2. **Output language control** — currently works; `output_language` in config maps to prompt selection. May want clearer UI labeling.
3. **Note mode trigger** — the prompt text mentions `"笔记模式"` / `"note mode"` prefix to switch style, but this is prompt-only (GPT follows instruction; no code detection). May want to make this more reliable or add a UI shortcut.
4. **Min chars threshold** — `online_correct_min_chars=6` means even very short transcriptions go to GPT. May want a longer minimum for voice_cleanup mode specifically.
5. **Custom prompt tab** — `online_prompt_custom_text` field exists in config; the settings UI has a custom mode but no textarea to edit it. Could add a text editor in the Custom tab.

**Ask the operator** what specifically they want to improve before starting.

---

## Constraints

- Do not push (`git push`) without explicit operator confirmation.
- Do not edit `.env*` files.
- Do not modify/unload LaunchAgent at `~/Library/LaunchAgents/com.whisperkey.plist`.
- After any `build_app.sh` rebuild, TCC permissions must be re-granted (Accessibility + Input Monitoring) — see STATUS.md for details.
- Use project venv: `.venv/bin/python`, not system `python3`.
- Tests: `.venv/bin/python -m pytest -q` (should be 111 passed).

---

## Validation Before Any Changes

```bash
cd "/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac"
.venv/bin/python -m pytest -q
git status
git diff --check
```

After prompt edits (no rebuild needed for prompt-only changes):
- Quit running app (Ctrl+C in terminal or menu → Quit)
- Relaunch: `dist/WhisperKey.app/Contents/MacOS/WhisperKey`
- Record and verify `online_correction_end changed=True` in terminal output
- Check the injected text quality

After any code changes, run full validation before rebuild:
```bash
.venv/bin/python -m compileall -q whisperkey_mac tests
.venv/bin/python -m pytest -q
packaging/macos/build_app.sh
```
Then re-grant TCC permissions and test.

---

## Uncommitted Changes

One file has uncommitted changes:
- `STATUS.md` — session log updated this session (safe to commit any time)

All other working code was committed in `5b8818b`.
