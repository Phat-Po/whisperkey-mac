# Handoff: Fix WhisperKey Overlay Ring To Match Reference Shader

Project:
`/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac`

## Current Situation

The first native redesign attempt was implemented in `whisperkey_mac/overlay.py`, focused on `AuroraOrbView`, and it passed the functional tests. The user then rebuilt/previewed and rejected the visual result.

The user supplied two comparison images in chat:

- Image #1: current failed implementation. It looks like a small noisy blue/purple ring inside a pale circular bubble.
- Image #2: target from the user's React/OGL `VoicePoweredOrb` shader. It is a large, thick, smooth, luminous torus with a transparent center, broad blurred glow, cyan-left/purple-right gradient, and a bright white-blue crescent/highlight near the upper-right edge.

Critical user statement:
> "i want the ring to be the exactly same ring of which i pasted the codes"

Do not treat the shader as loose inspiration. The next task is to make the native PyObjC/Core Graphics approximation visually much closer to the shader output.

## Governance / Execution Gate

Follow project governance. Do not implement until the user says `批准执行` in the new session.

Risk gates:
- Do not edit saved config.
- Do not change bundle id, LaunchAgent path, app permissions identity, or packaging unless explicitly approved.
- Do not touch `.env*` or credential-bearing files.
- Do not interrupt the running service unless explicitly approved.
- Do not rebuild unless the user explicitly approves it. Rebuild can change ad-hoc signing CDHash and force macOS Privacy & Security reauthorization.

## What Was Changed In The Failed Attempt

File touched:
- `whisperkey_mac/overlay.py`

The attempted approach:
- `AuroraOrbView.drawRect_()` no longer calls `_draw_orb()` or `_draw_wave_rings()`.
- It draws many segmented `NSBezierPath` arc strokes.
- It uses deterministic noise helpers, the reference purple/cyan/dark-blue palette, audio-level pulse, and an orbiting bright point.
- Tests passed:
  - `./.venv/bin/python -m pytest tests/test_overlay.py tests/test_keyboard_listener.py -q` -> `42 passed`
  - `./.venv/bin/python -m compileall whisperkey_mac` -> passed

Why this failed visually:
1. It became a thin, noisy stroke ring, not a thick luminous shader torus.
2. Ring thickness is much too small.
3. The target has a huge transparent center and no crisp inner outline; the failed version has a visible inner circle and small center.
4. Noise is too visible and reads like rough particles/waveform jitter.
5. The broad Gaussian-like glow body is missing or too faint.
6. Color placement is broken into small pieces instead of a smooth angular gradient: target is cyan on left/lower-left, purple on right/lower-right, dark-blue bridge, white-blue highlight near upper-right.
7. The bright point was drawn as a dot/blob instead of an integrated crescent/rim highlight.
8. Scale is too small inside the 84x84 panel.
9. The macOS material/backdrop still makes the overlay feel like a pale contained bubble.
10. The implementation copied feature names from the shader but not the shader's image-formation model.

## Correct Mental Model For Next Attempt

The target is not a set of thin arcs. It is a pixel/alpha-field style annulus:

- thick annular alpha field
- smooth radial falloff
- broad blurred outer and inner glow
- transparent center, with no crisp inner stroke
- smooth angular color gradient
- one integrated high-energy crescent/highlight near the rim
- very subtle organic distortion, blurred enough that it does not read as jagged noise

Within native PyObjC constraints, the better approximation should use layered broad bands, not narrow noisy strokes.

## Recommended Native Implementation Direction

Stay in `AuroraOrbView` in `whisperkey_mac/overlay.py` unless there is a strong reason not to.

Do not add:
- React
- Tailwind
- shadcn
- `ogl`
- WebView/browser runtime
- a recording button

Suggested drawing strategy:

1. Remove or suppress the pale bubble feel.
   - Inspect `_style_backdrop()` and compact mode backdrop visibility.
   - Compact recording/transcribing should feel like transparent overlay with the ring only.
   - Keep result layout expansion behavior intact.

2. Replace the segmented stroke-ring approach with a broad annulus renderer.
   - Use many concentric arc bands or filled annular wedges.
   - Outer radius should nearly fill the `80x80` orb view, roughly `35-39px`.
   - Inner transparent radius should be large, roughly `21-25px`, matching shader `innerRadius = 0.6` relative to the outer radius.
   - Main luminous band thickness should be about `12-18px`, not `3-7px`.
   - Avoid a crisp inner circle. If there is any inner edge, it must be a soft low-alpha gradient.

3. Build radial falloff with layers.
   - Outer glow: large soft strokes or translucent bands outside the ring.
   - Main body: wide semi-transparent bands with smooth alpha.
   - Inner fade: low-alpha bands that fade into the transparent center.
   - Do not fill the center.

4. Build angular color gradient smoothly.
   - Use reference colors:
     - Purple `#9C43FE` / `(0.611765, 0.262745, 0.996078)`
     - Cyan `#4CC2E9` / `(0.298039, 0.760784, 0.913725)`
     - Dark blue `#101499` / `(0.062745, 0.078431, 0.600000)`
   - Target color placement:
     - cyan: left/lower-left
     - purple: right/lower-right
     - dark blue: lower bridge and shadowed bridge
     - bright white-blue: upper-right rim/crescent
   - Prefer fewer, broader, smoother angular segments over many tiny noisy pieces.

5. Rework the bright point.
   - It should be an integrated rim crescent/highlight, not a separate dot.
   - Draw as a short, thick, soft arc near the upper-right edge with white-blue core and cyan/violet halo.
   - Orbit slowly in idle/transcribing; during recording, audio level can increase intensity/speed slightly.

6. Use organic noise sparingly.
   - The shader has organic variation, but the reference screenshot appears smooth because alpha/falloff blur it.
   - Apply small radius or alpha modulation only to broad bands.
   - Do not expose jagged per-segment noise at the visible edge.

7. Preserve behavior.
   - Recording/transcribing remain compact `84x84` and text hidden.
   - Result text may expand after transcription.
   - State machine behavior must not change.
   - Reduced motion should keep a static smooth torus with minimal/no orbit.

## Must-Read Files In Order

1. `HANDOFF-20260417-orb-redesign.md` (this file)
2. `whisperkey_mac/overlay.py`
3. `tests/test_overlay.py`
4. `tests/test_keyboard_listener.py`
5. `packaging/macos/build_app.sh` only to understand why rebuild is risky; do not run unless approved

## Important Current-Code Notes

- `AuroraOrbView` currently contains the failed segmented-arc implementation.
- `_draw_orb()` and `_draw_wave_rings()` are kept as no-op compatibility helpers in the failed attempt.
- PyObjC can misinterpret helper methods on `NSView` subclasses as Objective-C selectors. Pure math helpers are currently module-level to avoid `objc.BadPrototypeError`.
- Be careful if adding new helper methods inside `AuroraOrbView`; use Objective-C-compatible selector naming or mark pure Python methods with `@objc.python_method` if appropriate.

## Validation Commands

After approved edits:

```bash
./.venv/bin/python -m pytest tests/test_overlay.py tests/test_keyboard_listener.py -q
./.venv/bin/python -m compileall whisperkey_mac
```

Optional visual source preview without rebuild/service interruption:

```bash
./.venv/bin/python -c 'import math,time; from AppKit import NSApplication,NSApplicationActivationPolicyAccessory,NSApp; from PyObjCTools.AppHelper import callLater; from whisperkey_mac.overlay import OverlayPanel; app=NSApplication.sharedApplication(); app.setActivationPolicy_(NSApplicationActivationPolicyAccessory); o=OverlayPanel.create(result_max_lines=3); started=time.monotonic(); o.set_audio_level_provider(lambda: max(0.0,min(1.0,0.55+0.40*math.sin((time.monotonic()-started)*5.0)))); o.show_idle(); callLater(1.0,o.show_recording); callLater(30.0,lambda: NSApp.terminate_(None)); print("look at bottom center for 30 seconds", flush=True); app.run(); print("preview exited", flush=True)'
```

Do not rebuild unless the user approves:

```bash
./packaging/macos/build_app.sh
```

## Starter Prompt For Next Agent

You are working in:
`/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac`

Use project governance. Do not edit until I say `批准执行`.

Task: Fix the WhisperKey macOS overlay ring so it closely matches the user's supplied React/OGL `VoicePoweredOrb` shader screenshot. The previous implementation failed: it made a small noisy thin stroke ring inside a pale bubble. The target is a thick, smooth, luminous torus with a huge transparent center, broad blurred glow, cyan-left/purple-right angular gradient, dark-blue bridge, and integrated white-blue upper-right crescent highlight.

Start by reading:
1. `HANDOFF-20260417-orb-redesign.md`
2. `whisperkey_mac/overlay.py`
3. `tests/test_overlay.py`
4. `tests/test_keyboard_listener.py`
5. `packaging/macos/build_app.sh` only to understand rebuild risk

Constraints:
- Native Python/PyObjC only.
- Do not add React, Tailwind, shadcn, `ogl`, WebView, or a recording button.
- Preserve state-machine behavior, compact recording/transcribing layout, and result expansion.
- Do not touch saved config, bundle id, LaunchAgent path, app permissions identity, packaging, or running service unless explicitly approved.
- Avoid rebuild unless explicitly approved.

Implementation direction:
Replace the failed segmented noisy arc approach with a broad layered annulus renderer: thick radial falloff bands, smooth angular color gradient, no crisp inner outline, transparent center, broad glow body, and an integrated crescent highlight. Use noise only subtly.

After approval, validate with:
`./.venv/bin/python -m pytest tests/test_overlay.py tests/test_keyboard_listener.py -q`
and:
`./.venv/bin/python -m compileall whisperkey_mac`
