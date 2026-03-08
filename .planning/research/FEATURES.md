# Features Research: macOS Recording Overlay UI

## Table Stakes (must have or UX breaks)

| Feature | Why | Complexity |
|---------|-----|------------|
| Always-on-top floating pill | `NSWindowLevel.floating` — without this overlay disappears behind active app | Low |
| Bottom-center position | Matches macOS Dictation + AquaVoice convention; doesn't cover active text fields | Low |
| Waveform animation during recording | Without motion, users think the app froze; 4-6 bars at ~30fps | Medium |
| Distinct "transcribing" state | 0.5-3s gap between key release and text appearing; needs spinner/dots | Low |
| Silent dismiss on paste | Overlay disappearing IS the confirmation; no text needed | Low |
| Text + "已复制到剪贴板" on clipboard path | User must know what was captured when not in a text field | Low |
| Non-interactive / click-through | `setIgnoresMouseEvents_(True)` mandatory — any focus steal is a fatal UX bug | Low |
| Auto-dismiss timer | Overlay cannot require user action to close | Low |

## Differentiators (nice to have, not v1)

| Feature | Notes |
|---------|-------|
| RMS-driven waveform (real audio amplitude) | Requires audio callback → overlay thread; ship idle sine-wave animation first |
| Partial transcription streaming | faster-whisper isn't streaming; faking it would be dishonest |
| Position memory / drag | Solo user doesn't need it; adds state complexity |

## Anti-Features (deliberately excluded from v1)

| Feature | Reason |
|---------|--------|
| Draggable overlay | Adds state complexity; not needed for solo use |
| Click-to-dismiss | Would steal mouse events from active app |
| Streaming partial transcription | faster-whisper returns full result; don't fake it |
| Animated char-by-char text reveal | Text is ready all at once; fake streaming is dishonest |
| Menu bar changes | Explicitly out of scope per PROJECT.md |
| Sound effects | Not requested |

## Animation Timings (specific)

| Animation | Timing |
|-----------|--------|
| Overlay appear | 150ms fade-in + 8pt slide-up, ease-out |
| Overlay dismiss (normal) | 400ms fade-out only |
| Silent dismiss (paste succeeded) | 200ms fade-out only |
| Pulsing dots (transcribing state) | 3 dots, 300ms per dot, 900ms full cycle |
| Waveform bars | 4-6 bars, 30fps, height 4-20pt |

## Branch Logic Note

The existing `output.py` already returns `"pasted"` or `"clipboard"` — this is exactly the condition for the two post-transcription overlay behaviors. No new return values needed.

## v1 Risk

Biggest risk: RMS-driven waveform requires pushing audio amplitude values from audio callback to overlay thread. If threading complexity is high, ship an idle sine-wave animation first (no audio data needed) and upgrade to RMS-driven in v2.

---
*Research date: 2026-03-09*
