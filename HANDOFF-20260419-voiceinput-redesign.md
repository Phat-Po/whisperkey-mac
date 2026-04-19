# Handoff — VoiceInput Pill Redesign
**Date:** 2026-04-19  
**Task:** Replace the aurora orb overlay with a minimal animated pill that exactly matches the VoiceInput React component (molecule-lab-rushil on 21st.dev).

---

## Project Context

WhisperKey is a **native macOS Python app** (PyObjC/AppKit). It floats a transparent NSPanel overlay at the bottom-center of screen. The overlay shows state: idle → recording → transcribing → result (shows transcribed text). All drawing is pure Core Graphics — no React, no web view, no npm packages.

Working directory: `/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac`  
Python: `.venv/bin/python` (3.12.10)  
Only file to change: `whisperkey_mac/overlay.py`

---

## What the Current Overlay Looks Like

- A floating circle (84×84px) with an aurora gradient ring (purple/cyan) that pulses with audio level.
- On RESULT state, expands to 300×140px showing transcribed text.
- All visual code lives in `AuroraOrbView` (NSView subclass) and `AuroraRenderer`.

---

## What the New Overlay Must Look Like

Based on the VoiceInput React component. Translate visually — **do not install npm, shadcn, or React**.

### Reference Source Code (for visual reference only)

```typescript
// The component is a pill-shaped div that:
// - Idle: small circle, mic icon centered, border, clean white background
// - Recording: expands horizontally to show rotating stop square + 12 freq bars + MM:SS timer
// See full source at bottom of this doc.
```

### State-by-State Specs

| State | Shape | Width | Height | Content |
|---|---|---|---|---|
| IDLE | Circle | 52px | 52px | Mic icon centered |
| RECORDING | Pill | 220px | 52px | [stop square] + [12 freq bars] + [MM:SS timer] |
| TRANSCRIBING | Pill | 220px | 52px | [spinning dot] + "..." centered |
| RESULT | Pill | 300px | auto (min 52px) | Transcribed text + "已复制到剪贴板" sublabel |
| After result (3s) | Shrinks back → | 52px | 52px | Mic icon |

**Corner radius:** Always `height/2` = full pill rounding (26px for 52px height)  
**Bottom margin:** 40px from screen bottom (keep current)

### Visual Style

Match the VoiceInput component aesthetic:
- **Background:** White semi-transparent frosted glass — `NSVisualEffectMaterialLight` or `NSVisualEffectMaterialSheet`, or manually: RGBA(255, 255, 255, 0.90)
- **Border:** 1px, RGBA(0, 0, 0, 0.10)
- **Icons/bars/stop square:** Dark — RGBA(20, 20, 20, 0.85)
- **Timer text:** Muted — RGBA(100, 100, 100, 0.80), monospace, 11pt
- **Result text:** RGBA(20, 20, 20, 0.90), 14pt
- **Sublabel text:** RGBA(100, 100, 100, 0.80), 11pt

### Content Layout for RECORDING pill (left→right, horizontally centered in pill)

```
[8px pad] [stop_square 16×16] [8px gap] [12 freq bars] [8px gap] [timer 40px wide] [8px pad]
```

- **Stop square:** 16×16px rounded rect (radius 3px), drawn with NSBezierPath, rotates 360° over 2s on infinite loop — driven by `_elapsed` in the tick loop
- **Freq bars:** 12 vertical rounded rects, each 2px wide, gap 2px, heights vary 2–13px, driven by `_audio_level`. Animate per-bar heights using `math.sin(t * speed + phase_offset)` with staggered phase offsets (bar_i * 0.4 radians) so they feel organic. Scale max height by `0.3 + audio_level * 0.7`
- **Timer:** `MM:SS` string, count up from 0:00 when entering RECORDING, stop when leaving. Track `_record_start_at` timestamp in renderer

### Mic Icon (IDLE state)

Draw a simple mic icon with NSBezierPath at center of the 52×52 circle:
- Mic capsule: rounded rect ~8×14px centered slightly above center
- Mic stand: vertical line down from capsule + horizontal base arc

Or use SF Symbol: `NSImage.imageWithSystemSymbolName_accessibilityDescription_("mic", None)` then draw it tinted dark at ~22×22px centered in the view.

SF Symbol approach is simpler — try that first.

---

## What to Keep (Do NOT Remove)

- **RESULT state** — shows transcribed text in expanded pill, auto-dismisses after 3s back to IDLE. This is core app functionality.
- All state machine logic (`OverlayStateMachine`, `OverlayState`, `_VALID_TRANSITIONS`) — keep as-is.
- `dispatch_to_main()` — keep as-is.
- `OverlayPanel.set_audio_level_provider()` — keep as-is.
- All public API methods: `show_idle`, `show_recording`, `show_transcribing`, `show_result`, `hide_after_paste`, `hide_fully`.
- `diag()` calls — keep all of them.

---

## What to Remove / Replace

| Remove | Replace with |
|---|---|
| `AuroraOrbView` (entire class) | `VoiceInputView` (new NSView) |
| All aurora math helpers (`_aurora_*` functions) | Nothing (delete them) |
| `AuroraRenderer._style_backdrop()` gradient layers | Simple white fill |
| Aurora color constants, ring drawing | Simple dark colors |
| `AuroraRenderer` (rename or refactor in place) | Same class name, new geometry constants |

---

## New Geometry Constants (replace in AuroraRenderer)

```python
IDLE_W: float = 52.0
IDLE_H: float = 52.0
IDLE_CORNER_RADIUS: float = 26.0

ACTIVE_W: float = 220.0   # recording/transcribing
ACTIVE_H: float = 52.0
ACTIVE_CORNER_RADIUS: float = 26.0

RESULT_W: float = 300.0
RESULT_MIN_H: float = 52.0
RESULT_CORNER_RADIUS: float = 26.0

BOTTOM_MARGIN: float = 40.0
```

---

## New VoiceInputView Drawing Contract

Create `VoiceInputView(NSView)` with these instance attributes set by renderer before `setNeedsDisplay_`:

```python
self._state        # "idle" | "recording" | "transcribing" | "result"
self._elapsed      # float, seconds since state started
self._audio_level  # float 0.0–1.0
self._record_secs  # int, elapsed whole seconds for timer display
```

`drawRect_` dispatches to:
- `_draw_idle()` — SF Symbol mic icon, centered
- `_draw_recording()` — stop square (rotated by elapsed) + freq bars + timer
- `_draw_transcribing()` — spinning dot + "..."
- `_draw_result()` — nothing (text fields handle result display)

---

## Pill Expand/Collapse Animation

Reuse existing `_animate_panel()` with 0.4s duration (already in renderer). Geometry transitions:
- IDLE → RECORDING: panel expands from 52×52 to 220×52 (animate frame)
- RECORDING → TRANSCRIBING: stay at 220×52
- TRANSCRIBING → RESULT: expand to 300×auto
- RESULT → IDLE: shrink back to 52×52

---

## Verification Steps (Run Before Reporting Done)

```bash
cd "/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac"
.venv/bin/python -m compileall whisperkey_mac -q
.venv/bin/python -m pytest tests/test_overlay.py tests/test_keyboard_listener.py -q
```

Both must pass. Fix any test failures before reporting done — do not skip or comment out tests.

After passing: tell the user to run the app (`dist/WhisperKey.app` or terminal launch) and visually verify the overlay looks like the VoiceInput component.

---

## Constraints (Hard Rules)

- **Native Python/PyObjC only.** No React, no npm, no shadcn, no WebView.
- **Only touch `whisperkey_mac/overlay.py`.** Do not touch tests, config, packaging, service_controller, or transcriber.
- **Do not run `build_app.sh`** — every rebuild changes CDHash and forces TCC permission re-grant. Not needed for overlay-only changes; the app can be relaunched from terminal.
- **Do not git push** — always ask operator first.
- Snapshot (commit) uncommitted changes before starting work. Current `git status` shows several modified files — commit them first with `git add -A && git commit -m "snapshot: before voiceinput pill redesign"`.

---

## Full VoiceInput Reference Code (visual guide only)

```typescript
"use client"
import React from "react"
import { Mic } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"

export function VoiceInput({ onStart, onStop }) {
  const [_listening, _setListening] = React.useState(false)
  const [_time, _setTime] = React.useState(0)

  React.useEffect(() => {
    let intervalId
    if (_listening) {
      onStart?.()
      intervalId = setInterval(() => _setTime(t => t + 1), 1000)
    } else {
      onStop?.()
      _setTime(0)
    }
    return () => clearInterval(intervalId)
  }, [_listening])

  const formatTime = (s) => {
    const m = Math.floor(s / 60)
    return `${String(m).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`
  }

  return (
    <motion.div
      className="flex p-2 border items-center justify-center rounded-full cursor-pointer"
      layout
      transition={{ layout: { duration: 0.4 } }}
      onClick={() => _setListening(!_listening)}
    >
      {/* Icon: mic (idle) OR rotating stop square (recording) */}
      <div className="h-6 w-6 flex items-center justify-center">
        {_listening
          ? <motion.div className="w-4 h-4 bg-primary rounded-sm"
              animate={{ rotate: [0, 180, 360] }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }} />
          : <Mic />}
      </div>

      {/* Expanded content: freq bars + timer — only visible when listening */}
      <AnimatePresence mode="wait">
        {_listening && (
          <motion.div
            initial={{ opacity: 0, width: 0, marginLeft: 0 }}
            animate={{ opacity: 1, width: "auto", marginLeft: 8 }}
            exit={{ opacity: 0, width: 0, marginLeft: 0 }}
            transition={{ duration: 0.4 }}
            className="overflow-hidden flex gap-2 items-center"
          >
            {/* 12 animated frequency bars */}
            <div className="flex gap-0.5 items-center">
              {[...Array(12)].map((_, i) => (
                <motion.div key={i} className="w-0.5 bg-primary rounded-full"
                  initial={{ height: 2 }}
                  animate={{ height: [2, 3 + Math.random()*10, 3 + Math.random()*5, 2] }}
                  transition={{ duration: 1, repeat: Infinity, delay: i * 0.05, ease: "easeInOut" }} />
              ))}
            </div>
            {/* Timer */}
            <div className="text-xs text-muted-foreground w-10 text-center">
              {formatTime(_time)}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
```
