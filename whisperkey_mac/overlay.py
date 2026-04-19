"""Overlay NSPanel module for WhisperKey macOS.

Provides:
- OverlayState: enum of 5 panel states (HIDDEN, IDLE, RECORDING, TRANSCRIBING, RESULT)
- OverlayStateMachine: pure-Python state machine with transition guards and stale-dismiss protection
- AuroraOrbView: custom NSView that draws the aurora glass orb using Core Graphics
- AuroraRenderer: CA-layer + timer-driven renderer that owns the orb view and text fields
- OverlayPanel: creates and configures an always-on-top, transparent NSPanel with
  a compact idle bubble and an expanded HUD for active states
- dispatch_to_main(): thread-safe utility that queues any callable onto the main run loop
"""

from __future__ import annotations

import enum
import math
import time
from typing import Callable

import objc

from AppKit import (
    NSAnimationContext,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFloatingWindowLevel,
    NSFont,
    NSGraphicsContext,
    NSRoundLineCapStyle,
    NSLineBreakByWordWrapping,
    NSMakePoint,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSTextAlignmentCenter,
    NSTextField,
    NSView,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialHUDWindow,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from PyObjCTools.AppHelper import callAfter, callLater
from Quartz import (
    CAGradientLayer,
    CALayer,
    CAMediaTimingFunction,
    CATransaction,
    kCAMediaTimingFunctionEaseInEaseOut,
    kCAMediaTimingFunctionEaseOut,
)

from whisperkey_mac.diagnostics import diag


def dispatch_to_main(fn, *args) -> None:
    """Queue fn(*args) on the main run loop. Safe to call from any thread."""
    callAfter(fn, *args)


class OverlayState(enum.Enum):
    HIDDEN = "hidden"
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    RESULT = "result"


_VALID_TRANSITIONS: dict[OverlayState, set[OverlayState]] = {
    OverlayState.HIDDEN: {OverlayState.IDLE},
    OverlayState.IDLE: {OverlayState.RECORDING, OverlayState.HIDDEN},
    OverlayState.RECORDING: {OverlayState.TRANSCRIBING, OverlayState.IDLE},
    OverlayState.TRANSCRIBING: {OverlayState.RESULT, OverlayState.IDLE},
    OverlayState.RESULT: {OverlayState.IDLE},
}


def _aurora_clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _aurora_mix(left: tuple[float, float, float], right: tuple[float, float, float], amount: float):
    amount = _aurora_clamp_unit(amount)
    return tuple(l + (r - l) * amount for l, r in zip(left, right))


def _aurora_unit_noise(angle: float, t: float, seed: float) -> float:
    a = math.sin(angle * 12.9898 + seed * 78.233 + t * 4.1) * 43758.5453
    b = math.sin(angle * 4.1414 - seed * 19.19 + t * 2.7) * 24634.6345
    value = (a + b * 0.35) - math.floor(a + b * 0.35)
    return _aurora_clamp_unit(value)


def _aurora_smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge0 == edge1:
        return 1.0 if value >= edge1 else 0.0
    x = _aurora_clamp_unit((value - edge0) / (edge1 - edge0))
    return x * x * (3.0 - 2.0 * x)


def _aurora_angle_delta(angle: float, center: float) -> float:
    return math.atan2(math.sin(angle - center), math.cos(angle - center))


def _aurora_angular_peak(angle: float, center: float, width: float) -> float:
    distance = abs(_aurora_angle_delta(angle, center))
    return 1.0 - _aurora_smoothstep(width * 0.22, width, distance)


# ---------------------------------------------------------------------------
# Aurora Orb View — custom NSView with Core Graphics drawing
# ---------------------------------------------------------------------------

class AuroraOrbView(NSView):
    """NSView subclass that draws the aurora glass orb.

    Attributes set directly by the renderer before triggering setNeedsDisplay_:
      _orb_state   — "idle" | "recording" | "transcribing" | "result"
      _elapsed     — float, seconds since current state started
      _audio_level — float 0.0–1.0, current normalized mic RMS
      _reduced_motion — bool, disables wave scaling and fast rotation
    """

    def initWithFrame_(self, frame):
        self = objc.super(AuroraOrbView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._orb_state = "idle"
        self._elapsed = 0.0
        self._audio_level = 0.0
        self._reduced_motion = False
        self._draw_error_reported = False
        return self

    def isFlipped(self):
        return False

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def drawRect_(self, dirtyRect):
        try:
            self._draw_rect(dirtyRect)
        except Exception as exc:
            if not getattr(self, "_draw_error_reported", False):
                self._draw_error_reported = True
                diag("overlay_draw_error", error_type=type(exc).__name__, error=str(exc))
            self._draw_fallback()

    def _draw_rect(self, dirtyRect):
        # Start transparent
        NSColor.clearColor().set()
        NSBezierPath.fillRect_(self.bounds())

        bounds = self.bounds()
        cx = bounds.size.width / 2.0
        cy = bounds.size.height / 2.0

        t = self._elapsed
        level = self._audio_level
        state = self._orb_state
        reduced = self._reduced_motion

        radius, glow_alpha, glow_blur = self._compute_orb_params(t, level, state, reduced)
        radius = max(28.0, min(radius, 31.5))

        # Ring-first shader approximation: the center stays transparent.
        self._draw_glow(cx, cy, radius, glow_alpha, glow_blur, t, state, level, reduced)
        self._draw_aurora_ring(cx, cy, radius, t, state, level, reduced)

    def _draw_fallback(self):
        try:
            bounds = self.bounds()
            cx = bounds.size.width / 2.0
            cy = bounds.size.height / 2.0
            radius = min(bounds.size.width, bounds.size.height) * 0.34
            NSColor.clearColor().set()
            NSBezierPath.fillRect_(bounds)
            path = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(cx - radius, cy - radius, radius * 2.0, radius * 2.0)
            )
            path.setLineWidth_(5.0)
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.30, 0.76, 0.91, 0.82).set()
            path.stroke()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_orb_params(self, t, level, state, reduced):
        breathe = math.sin(t * 1.5) if not reduced else 0.0
        if state == "idle":
            radius = 29.7 + 0.45 * breathe
            glow_alpha = 0.34 + 0.05 * breathe
            glow_blur = 20.0
        elif state == "recording":
            voice_push = level * 1.15 if not reduced else 0.0
            fast_breathe = (math.sin(t * 4.0) if not reduced else 0.0)
            radius = 30.0 + voice_push + 0.45 * fast_breathe
            glow_alpha = 0.45 + min(level * 0.36, 0.34)
            glow_blur = 22.0 + level * 7.0
        elif state == "transcribing":
            slow_pulse = math.sin(t * 1.2) if not reduced else 0.0
            radius = 29.9 + 0.55 * slow_pulse
            glow_alpha = 0.38 + 0.05 * slow_pulse
            glow_blur = 20.0
        else:  # result
            radius = 29.6
            glow_alpha = 0.34
            glow_blur = 19.0
        return radius, glow_alpha, glow_blur

    def _draw_glow(self, cx, cy, radius, alpha, blur, t, state, level, reduced):
        shimmer_t = 0.0 if reduced else t
        hover = level if state == "recording" else 0.0
        drift = 0.0 if reduced else shimmer_t * (0.08 + hover * 0.04)

        # Broad low-alpha bands create the shader's blurred glow body. The line
        # widths are intentionally large so the ring reads as a luminous torus.
        glow_layers = (
            (radius + 0.6, blur * 0.86, alpha * 0.055),
            (radius + 0.2, blur * 0.64, alpha * 0.070),
            (radius - 0.9, blur * 0.48, alpha * 0.055),
        )
        for layer_index, (layer_radius, width, layer_alpha) in enumerate(glow_layers):
            self._draw_gradient_arc_band(
                cx,
                cy,
                layer_radius,
                width,
                layer_alpha,
                drift,
                shimmer_t,
                segment_count=64,
                arc_scale=1.72,
                noise_amount=0.012 if layer_index == 0 else 0.006,
            )

    def _draw_orb(self, cx, cy, radius, t, state, reduced):
        # Kept for compatibility with older tests/patches. The shader target is
        # ring-first, so drawRect_ intentionally does not call this helper.
        return

    def _draw_aurora_ring(self, cx, cy, radius, t, state, level, reduced):
        gc = NSGraphicsContext.currentContext()
        gc.saveGraphicsState()

        hover = level if state == "recording" else 0.0
        rotation = 0.0 if reduced else t * (0.11 + hover * 0.05)
        shimmer_t = 0.0 if reduced else t

        self._draw_gradient_arc_band(
            cx,
            cy,
            radius + 0.4,
            18.0 + hover * 1.4,
            0.28 + hover * 0.08,
            rotation,
            shimmer_t,
            segment_count=96,
            arc_scale=1.54,
            noise_amount=0.018,
        )
        self._draw_gradient_arc_band(
            cx,
            cy,
            radius - 1.4,
            12.5 + hover * 1.2,
            0.38 + hover * 0.11,
            rotation * 0.55,
            shimmer_t,
            segment_count=112,
            arc_scale=1.45,
            noise_amount=0.012,
        )
        self._draw_gradient_arc_band(
            cx,
            cy,
            radius + 4.2,
            7.6 + hover * 0.7,
            0.18 + hover * 0.06,
            rotation * 0.35,
            shimmer_t,
            segment_count=88,
            arc_scale=1.55,
            noise_amount=0.006,
        )

        # A faint inner fade gives depth without drawing the rejected crisp
        # center outline.
        self._draw_gradient_arc_band(
            cx,
            cy,
            radius - 7.1,
            4.8,
            0.070 + hover * 0.025,
            rotation * 0.2,
            shimmer_t,
            segment_count=72,
            arc_scale=1.48,
            noise_amount=0.0,
        )
        self._draw_highlight_crescent(cx, cy, radius, t, state, level, reduced)

        gc.restoreGraphicsState()

    def _draw_wave_rings(self, cx, cy, radius, level):
        # Kept for compatibility with older tests/patches. Recording pulse is
        # folded into the shader ring edge instead of drawn as assistant circles.
        return

    def _draw_energy_point(self, cx, cy, radius, t, state, level, reduced):
        self._draw_highlight_crescent(cx, cy, radius, t, state, level, reduced)

    def _draw_gradient_arc_band(
        self,
        cx,
        cy,
        radius,
        width,
        alpha,
        rotation,
        t,
        segment_count,
        arc_scale,
        noise_amount,
    ):
        step = math.tau / segment_count
        for i in range(segment_count):
            angle = i * step
            visual_angle = angle + rotation
            noise = (_aurora_unit_noise(angle, t * 0.35, 31.0 + width) - 0.5) * noise_amount
            color = self._shader_color(visual_angle + noise, t, self._reduced_motion)
            luminance = self._ring_luminance(visual_angle, t, rotation)
            band_alpha = alpha * (0.74 + luminance * 0.26)
            start = math.degrees(visual_angle - step * 0.34)
            end = math.degrees(visual_angle + step * arc_scale)
            self._stroke_arc(cx, cy, radius, start, end, width, (*color, band_alpha))

    def _draw_highlight_crescent(self, cx, cy, radius, t, state, level, reduced):
        hover = level if state == "recording" else 0.0
        orbit = 0.0 if reduced else math.sin(t * (0.42 + hover * 0.12)) * 0.12
        angle = 0.72 + orbit
        intensity = 0.72 + hover * 0.22
        if state == "transcribing" and not reduced:
            intensity += 0.06 * math.sin(t * 1.5)

        start = math.degrees(angle - 0.33)
        end = math.degrees(angle + 0.34)
        self._stroke_arc(
            cx, cy, radius + 1.7, start - 8.0, end + 8.0, 14.0 + hover * 1.8,
            (0.30, 0.76, 0.91, intensity * 0.15),
        )
        self._stroke_arc(
            cx, cy, radius + 1.0, start - 4.0, end + 3.0, 9.0 + hover * 1.2,
            (0.70, 0.86, 1.0, intensity * 0.23),
        )
        self._stroke_arc(
            cx, cy, radius + 0.2, start + 2.0, end - 7.0, 4.6 + hover * 0.8,
            (0.92, 0.98, 1.0, intensity * 0.68),
        )

    def _stroke_arc(self, cx, cy, radius, start_deg, end_deg, width, rgba):
        path = NSBezierPath.alloc().init()
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            NSMakePoint(cx, cy), radius, start_deg, end_deg, False
        )
        path.setLineWidth_(width)
        path.setLineCapStyle_(NSRoundLineCapStyle)
        red, green, blue, alpha = rgba
        NSColor.colorWithSRGBRed_green_blue_alpha_(
            _aurora_clamp_unit(red),
            _aurora_clamp_unit(green),
            _aurora_clamp_unit(blue),
            _aurora_clamp_unit(alpha),
        ).set()
        path.stroke()

    def _ring_luminance(self, angle, t, rotation):
        crescent = _aurora_angular_peak(angle, 0.72, 0.86)
        left_cyan = _aurora_angular_peak(angle, math.pi * 0.92, 1.28)
        lower_bridge = _aurora_angular_peak(angle, -math.pi * 0.48, 0.88)
        band = 0.5 + 0.5 * math.sin(angle * 1.4 - t * 0.18)
        return _aurora_clamp_unit(crescent * 0.42 + left_cyan * 0.20 + lower_bridge * 0.10 + band * 0.13)

    def _shader_color(self, angle, t, reduced):
        purple = (0.611765, 0.262745, 0.996078)
        cyan = (0.298039, 0.760784, 0.913725)
        dark_blue = (0.062745, 0.078431, 0.600000)
        white_blue = (0.88, 0.97, 1.0)
        drift = 0.0 if reduced else math.sin(t * 0.18) * 0.05
        a = angle + drift

        cyan_weight = max(
            _aurora_angular_peak(a, math.pi * 0.96, 1.32),
            _aurora_angular_peak(a, -math.pi * 0.78, 1.05) * 0.86,
        )
        purple_weight = max(
            _aurora_angular_peak(a, -0.16, 1.18),
            _aurora_angular_peak(a, -0.82, 0.92) * 0.82,
        )
        bridge_weight = max(
            _aurora_angular_peak(a, -math.pi * 0.50, 0.95),
            _aurora_angular_peak(a, math.pi * 0.47, 0.72) * 0.45,
        )
        highlight_weight = _aurora_angular_peak(a, 0.72, 0.48)

        color = _aurora_mix(dark_blue, purple, 0.70 + purple_weight * 0.30)
        color = _aurora_mix(color, cyan, cyan_weight * 0.92)
        color = _aurora_mix(color, dark_blue, bridge_weight * 0.48)
        return _aurora_mix(color, white_blue, highlight_weight * 0.48)


# ---------------------------------------------------------------------------
# Aurora Renderer — owns the panel, orb view, and text fields
# ---------------------------------------------------------------------------

class AuroraRenderer:
    """Drives panel animations, the aurora orb view, and text fields."""

    # Panel geometry
    IDLE_W: float = 84.0
    IDLE_H: float = 84.0
    IDLE_CORNER_RADIUS: float = 42.0

    ACTIVE_W: float = 300.0
    ACTIVE_H: float = 140.0
    ACTIVE_CORNER_RADIUS: float = 20.0

    BOTTOM_MARGIN: float = 40.0

    ORB_VIEW_SIZE: float = 80.0
    ORB_TOP_PAD: float = 8.0

    HORIZONTAL_INSET: float = 18.0
    BOTTOM_PADDING: float = 4.0
    TEXT_GAP: float = 4.0
    SUBLABEL_HEIGHT: float = 16.0
    BASE_LABEL_HEIGHT: float = 20.0

    APPEAR_DURATION_S: float = 0.18
    DISMISS_DURATION_S: float = 0.30
    FPS: float = 30.0

    def __init__(
        self,
        panel,
        orb_view,
        label,
        sublabel,
        content_view,
        root_layer,
        backdrop_layers: dict,
        result_max_lines: int = 3,
        level_fn: Callable[[], float] | None = None,
    ) -> None:
        self._panel = panel
        self._orb_view = orb_view
        self._label = label
        self._sublabel = sublabel
        self._content_view = content_view
        self._root_layer = root_layer
        self._backdrop_layers = backdrop_layers
        self._result_max_lines = max(1, result_max_lines)
        self._level_fn = level_fn

        self._visual_gen: int = 0
        self._mode: OverlayState = OverlayState.HIDDEN
        self._phase_started_at: float = time.monotonic()
        self._elapsed: float = 0.0

        # Compute frame helpers
        screen = NSScreen.mainScreen()
        sf = screen.frame()
        self._screen_w = sf.size.width

        self._configure_text_fields()
        self._reset_visuals()

    def set_level_fn(self, fn: Callable[[], float] | None) -> None:
        self._level_fn = fn

    # ------------------------------------------------------------------
    # State entry points (called on main thread)
    # ------------------------------------------------------------------

    def show_idle(self, gen: int) -> None:
        self._visual_gen = gen
        self._mode = OverlayState.IDLE
        self._phase_started_at = time.monotonic()
        self._elapsed = 0.0

        idle_frame = self._idle_frame()

        self._orb_view._orb_state = "idle"
        self._orb_view._elapsed = 0.0
        self._orb_view._audio_level = 0.0
        self._hide_text()
        self._clear_text()
        self._update_root_for_idle()

        # Resize content view to idle dimensions
        self._content_view.setFrame_(NSMakeRect(0, 0, self.IDLE_W, self.IDLE_H))
        self._content_view.layer().setFrame_(NSMakeRect(0, 0, self.IDLE_W, self.IDLE_H))
        self._root_layer.setCornerRadius_(self.IDLE_CORNER_RADIUS)
        self._update_backdrop_frames(self.IDLE_W, self.IDLE_H)

        # Center orb view in idle panel
        orb_x = (self.IDLE_W - self.ORB_VIEW_SIZE) / 2.0
        orb_y = (self.IDLE_H - self.ORB_VIEW_SIZE) / 2.0
        self._orb_view.setFrame_(NSMakeRect(orb_x, orb_y, self.ORB_VIEW_SIZE, self.ORB_VIEW_SIZE))
        self._orb_view.setNeedsDisplay_(True)

        # Animate panel to idle size
        current_alpha = self._panel.alphaValue()
        if current_alpha < 0.05:
            # Coming from hidden — slide in
            entry_frame = NSMakeRect(
                idle_frame.origin.x,
                idle_frame.origin.y - 8,
                idle_frame.size.width,
                idle_frame.size.height,
            )
            self._panel.setFrame_display_(entry_frame, False)
            self._panel.setAlphaValue_(0.0)
            self._panel.orderFront_(None)
            self._animate_panel(
                target_alpha=1.0,
                target_frame=idle_frame,
                duration_s=self.APPEAR_DURATION_S,
                timing_name=kCAMediaTimingFunctionEaseOut,
            )
        else:
            # Already visible — resize to idle
            self._animate_panel(
                target_alpha=1.0,
                target_frame=idle_frame,
                duration_s=self.APPEAR_DURATION_S,
                timing_name=kCAMediaTimingFunctionEaseOut,
            )

        self._schedule_tick(gen)

    def show_recording(self, gen: int) -> None:
        self._visual_gen = gen
        self._mode = OverlayState.RECORDING
        self._phase_started_at = time.monotonic()
        self._elapsed = 0.0

        compact_frame = self._idle_frame()

        self._orb_view._orb_state = "recording"
        self._orb_view._elapsed = 0.0
        self._orb_view._audio_level = 0.0
        self._hide_text()
        self._clear_text()
        self._update_root_for_compact()

        # Keep active recording as ring-only; no expanded HUD until result text is shown.
        self._panel.setFrame_display_(compact_frame, False)
        self._panel.setAlphaValue_(1.0)
        self._animate_panel(
            target_alpha=1.0,
            target_frame=compact_frame,
            duration_s=self.APPEAR_DURATION_S,
            timing_name=kCAMediaTimingFunctionEaseOut,
        )
        self._schedule_tick(gen)

    def show_transcribing(self, gen: int) -> None:
        self._visual_gen = gen
        self._mode = OverlayState.TRANSCRIBING
        self._phase_started_at = time.monotonic()
        self._elapsed = 0.0

        compact_frame = self._idle_frame()

        self._orb_view._orb_state = "transcribing"
        self._orb_view._elapsed = 0.0
        self._orb_view._audio_level = 0.0
        self._hide_text()
        self._clear_text()
        self._update_root_for_compact()
        self._panel.setFrame_display_(compact_frame, False)
        self._panel.setAlphaValue_(1.0)
        self._schedule_tick(gen)

    def show_result(self, gen: int, text: str) -> None:
        self._visual_gen = gen
        self._mode = OverlayState.RESULT

        self._orb_view._orb_state = "result"
        self._orb_view._audio_level = 0.0
        self._show_text()
        self._apply_result_layout(text)
        self._panel.setAlphaValue_(1.0)

    def hide_to_idle(self, gen: int) -> None:
        """Return to idle bubble without fully hiding. Used for cancel / result dismiss."""
        self.show_idle(gen)

    def hide_fully(self, gen: int, duration_s: float = 0.20) -> None:
        """Fully hide the panel (service stop). Transitions to HIDDEN."""
        self._visual_gen = gen
        self._mode = OverlayState.HIDDEN

        def _complete() -> None:
            if gen != self._visual_gen:
                return
            self._panel.orderOut_(None)
            self._panel.setAlphaValue_(0.0)
            self._reset_visuals()

        self._animate_panel(
            target_alpha=0.0,
            target_frame=self._panel.frame(),
            duration_s=duration_s,
            timing_name=kCAMediaTimingFunctionEaseInEaseOut,
            completion=_complete,
        )

    # Backward-compat alias used by existing callers (service stop with duration=0.0,
    # and test code that verifies the panel goes to HIDDEN).
    def hide_after_paste(self, gen: int, duration_s: float | None = None) -> None:
        self.hide_fully(gen, duration_s if duration_s is not None else 0.20)

    def hide_after_result(self, gen: int, duration_s: float | None = None) -> None:
        """Called by auto-dismiss — return to idle, not fully hidden."""
        self.hide_to_idle(gen)

    # ------------------------------------------------------------------
    # Tick loop
    # ------------------------------------------------------------------

    def _schedule_tick(self, gen: int) -> None:
        callLater(1.0 / self.FPS, lambda: self._tick(gen))

    def _tick(self, gen: int) -> None:
        if gen != self._visual_gen:
            return
        if self._mode not in (
            OverlayState.IDLE,
            OverlayState.RECORDING,
            OverlayState.TRANSCRIBING,
        ):
            return

        self._elapsed += 1.0 / self.FPS
        level = self._level_fn() if self._level_fn is not None else 0.0

        self._orb_view._elapsed = self._elapsed
        self._orb_view._audio_level = level
        self._orb_view.setNeedsDisplay_(True)

        self._schedule_tick(gen)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _idle_frame(self):
        x = (self._screen_w - self.IDLE_W) / 2.0
        return NSMakeRect(x, self.BOTTOM_MARGIN, self.IDLE_W, self.IDLE_H)

    def _active_frame(self, height: float):
        x = (self._screen_w - self.ACTIVE_W) / 2.0
        return NSMakeRect(x, self.BOTTOM_MARGIN, self.ACTIVE_W, height)

    def _update_root_for_idle(self) -> None:
        self._update_root_for_compact()

    def _update_root_for_compact(self) -> None:
        self._content_view.setFrame_(NSMakeRect(0, 0, self.IDLE_W, self.IDLE_H))
        self._content_view.layer().setFrame_(NSMakeRect(0, 0, self.IDLE_W, self.IDLE_H))
        self._root_layer.setCornerRadius_(self.IDLE_CORNER_RADIUS)
        self._root_layer.setBorderWidth_(0.0)
        self._update_backdrop_frames(self.IDLE_W, self.IDLE_H)
        self._set_backdrop_visible(False)
        orb_x = (self.IDLE_W - self.ORB_VIEW_SIZE) / 2.0
        orb_y = (self.IDLE_H - self.ORB_VIEW_SIZE) / 2.0
        self._orb_view.setFrame_(NSMakeRect(orb_x, orb_y, self.ORB_VIEW_SIZE, self.ORB_VIEW_SIZE))
        self._orb_view.setNeedsDisplay_(True)
        self._reposition_text_for_active(self.ACTIVE_H)

    def _update_root_for_active(self, height: float) -> None:
        w = self.ACTIVE_W
        self._content_view.setFrame_(NSMakeRect(0, 0, w, height))
        self._content_view.layer().setFrame_(NSMakeRect(0, 0, w, height))
        self._root_layer.setCornerRadius_(self.ACTIVE_CORNER_RADIUS)
        self._root_layer.setBorderWidth_(1.0)
        self._update_backdrop_frames(w, height)
        self._set_backdrop_visible(True)
        self._reposition_orb_for_active(height)
        self._reposition_text_for_active(height)

    def _reposition_orb_for_active(self, height: float) -> None:
        orb_x = (self.ACTIVE_W - self.ORB_VIEW_SIZE) / 2.0
        orb_y = height - self.ORB_VIEW_SIZE - self.ORB_TOP_PAD
        self._orb_view.setFrame_(NSMakeRect(orb_x, orb_y, self.ORB_VIEW_SIZE, self.ORB_VIEW_SIZE))
        self._orb_view.setNeedsDisplay_(True)

    def _reposition_text_for_active(self, height: float) -> None:
        w = self.ACTIVE_W
        content_w = w - self.HORIZONTAL_INSET * 2
        self._sublabel.setFrame_(
            NSMakeRect(self.HORIZONTAL_INSET, self.BOTTOM_PADDING, content_w, self.SUBLABEL_HEIGHT)
        )
        self._label.setFrame_(
            NSMakeRect(
                self.HORIZONTAL_INSET,
                self.BOTTOM_PADDING + self.SUBLABEL_HEIGHT + self.TEXT_GAP,
                content_w,
                self.BASE_LABEL_HEIGHT,
            )
        )

    def _apply_result_layout(self, text: str) -> None:
        w = self.ACTIVE_W
        content_w = w - self.HORIZONTAL_INSET * 2
        measured_h = self._label.cell().cellSizeForBounds_(NSMakeRect(0, 0, content_w, 1000)).height
        visible_lines = max(1, min(self._result_max_lines, math.ceil(measured_h / self.BASE_LABEL_HEIGHT)))
        label_h = max(self.BASE_LABEL_HEIGHT, math.ceil(measured_h))
        if visible_lines > 1:
            label_h = max(label_h, self.BASE_LABEL_HEIGHT * visible_lines)

        text_block_h = label_h + self.TEXT_GAP + self.SUBLABEL_HEIGHT
        target_h = max(
            self.ACTIVE_H,
            self.ORB_TOP_PAD + self.ORB_VIEW_SIZE + 8.0 + text_block_h + self.BOTTOM_PADDING,
        )

        self._update_root_for_active(target_h)
        self._reposition_orb_for_active(target_h)

        # Text positioned from bottom
        self._sublabel.setFrame_(
            NSMakeRect(self.HORIZONTAL_INSET, self.BOTTOM_PADDING, content_w, self.SUBLABEL_HEIGHT)
        )
        self._label.setFrame_(
            NSMakeRect(
                self.HORIZONTAL_INSET,
                self.BOTTOM_PADDING + self.SUBLABEL_HEIGHT + self.TEXT_GAP,
                content_w,
                label_h,
            )
        )
        self._panel.setFrame_display_(self._active_frame(target_h), False)

    def _update_backdrop_frames(self, width: float, height: float) -> None:
        base_g = self._backdrop_layers.get("base")
        if base_g is not None:
            base_g.setFrame_(NSMakeRect(0, 0, width, height))
        sheen_g = self._backdrop_layers.get("sheen")
        if sheen_g is not None:
            sheen_g.setFrame_(NSMakeRect(0, height * 0.42, width, height * 0.58))
        bottom_t = self._backdrop_layers.get("bottom")
        if bottom_t is not None:
            bottom_t.setFrame_(NSMakeRect(0, 0, width, height * 0.52))

    def _set_backdrop_visible(self, visible: bool) -> None:
        for layer in self._backdrop_layers.values():
            if layer is not None:
                layer.setHidden_(not visible)

    # ------------------------------------------------------------------
    # Panel animation
    # ------------------------------------------------------------------

    def _animate_panel(
        self,
        *,
        target_alpha: float,
        target_frame,
        duration_s: float,
        timing_name: str,
        completion=None,
    ) -> None:
        NSAnimationContext.beginGrouping()
        ctx = NSAnimationContext.currentContext()
        ctx.setDuration_(duration_s)
        ctx.setTimingFunction_(CAMediaTimingFunction.functionWithName_(timing_name))
        self._panel.animator().setAlphaValue_(target_alpha)
        self._panel.animator().setFrame_display_(target_frame, False)
        NSAnimationContext.endGrouping()
        if completion is not None:
            callLater(duration_s, completion)

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    def _configure_text_fields(self) -> None:
        self._label.setUsesSingleLineMode_(False)
        self._label.setMaximumNumberOfLines_(self._result_max_lines)
        self._label.setLineBreakMode_(NSLineBreakByWordWrapping)
        self._label.cell().setWraps_(True)
        self._label.cell().setScrollable_(False)
        self._label.cell().setLineBreakMode_(NSLineBreakByWordWrapping)

    def _show_text(self) -> None:
        self._label.setHidden_(False)
        self._sublabel.setHidden_(False)

    def _hide_text(self) -> None:
        self._label.setHidden_(True)
        self._sublabel.setHidden_(True)

    def _clear_text(self) -> None:
        self._label.setStringValue_("")
        self._sublabel.setStringValue_("")

    def _reset_visuals(self) -> None:
        self._hide_text()
        self._clear_text()
        if self._orb_view is not None:
            self._orb_view._orb_state = "idle"
            self._orb_view._elapsed = 0.0
            self._orb_view._audio_level = 0.0


# ---------------------------------------------------------------------------
# State Machine
# ---------------------------------------------------------------------------

class OverlayStateMachine:
    """5-state machine for the overlay panel. All methods must run on the main thread."""

    def __init__(
        self,
        panel,
        label,
        sublabel,
        renderer: AuroraRenderer | None = None,
    ) -> None:
        self._panel = panel
        self._label = label
        self._sublabel = sublabel
        self._renderer = renderer
        self._state = OverlayState.HIDDEN
        self._dismiss_gen = 0

    def _transition(self, target: OverlayState) -> bool:
        if target in _VALID_TRANSITIONS.get(self._state, set()):
            self._state = target
            return True
        return False

    def _advance_gen(self) -> int:
        self._dismiss_gen += 1
        return self._dismiss_gen

    def show_idle(self) -> None:
        """Transition to IDLE bubble. Allowed from HIDDEN and all active states."""
        # Force transition from any non-HIDDEN state, or from HIDDEN
        if self._state == OverlayState.HIDDEN:
            if not self._transition(OverlayState.IDLE):
                return
        elif self._state != OverlayState.IDLE:
            # Allow recovery from RECORDING / TRANSCRIBING / RESULT
            self._state = OverlayState.IDLE
        else:
            return  # already idle

        gen = self._advance_gen()
        if self._renderer is not None:
            self._renderer.show_idle(gen)
            return
        self._panel.setAlphaValue_(1.0)
        self._panel.orderFront_(None)

    def show_recording(self) -> None:
        if not self._transition(OverlayState.RECORDING):
            return
        gen = self._advance_gen()
        self._label.setStringValue_("...")
        self._sublabel.setStringValue_("")
        if self._renderer is not None:
            self._renderer.show_recording(gen)
            return
        self._panel.setAlphaValue_(1.0)
        self._panel.orderFront_(None)

    def show_transcribing(self) -> None:
        if not self._transition(OverlayState.TRANSCRIBING):
            return
        gen = self._advance_gen()
        self._label.setStringValue_("转录中...")
        self._sublabel.setStringValue_("")
        if self._renderer is not None:
            self._renderer.show_transcribing(gen)

    def show_result(
        self,
        text: str,
        hint: str = "已复制到剪贴板",
        display_duration_s: float = 3.0,
        dismiss_duration_s: float = 0.4,
    ) -> None:
        if not self._transition(OverlayState.RESULT):
            return
        gen = self._advance_gen()
        self._label.setStringValue_(text)
        self._sublabel.setStringValue_(hint)
        if self._renderer is not None:
            self._renderer.show_result(gen, text)
        callLater(display_duration_s, lambda: self._auto_dismiss(gen, dismiss_duration_s))

    def hide_after_paste(self, dismiss_duration_s: float = 0.2) -> None:
        """Force-hide the panel (service stop / instant hide). Goes to HIDDEN."""
        if self._state == OverlayState.HIDDEN:
            return
        self._state = OverlayState.HIDDEN
        gen = self._advance_gen()
        if self._renderer is not None:
            self._renderer.hide_fully(gen, dismiss_duration_s)
            return
        self._panel.orderOut_(None)
        self._panel.setAlphaValue_(0.0)

    def hide_fully(self, dismiss_duration_s: float = 0.2) -> None:
        """Alias for hide_after_paste; used by service stop."""
        self.hide_after_paste(dismiss_duration_s)

    def _auto_dismiss(self, gen: int, dismiss_duration_s: float) -> None:
        if gen != self._dismiss_gen or self._state != OverlayState.RESULT:
            return
        # Return to IDLE bubble instead of fully hiding
        self._state = OverlayState.IDLE
        next_gen = self._advance_gen()
        if self._renderer is not None:
            self._renderer.hide_after_result(next_gen, dismiss_duration_s)
            return
        self._panel.orderOut_(None)
        self._panel.setAlphaValue_(0.0)


# ---------------------------------------------------------------------------
# Overlay Panel
# ---------------------------------------------------------------------------

class OverlayPanel:
    """Wrapper around an NSPanel configured for transparent aurora HUD display."""

    # Start with idle dimensions; active dimensions managed by the renderer
    PANEL_W: int = 84    # initial (idle) width
    PANEL_H: int = 84    # initial (idle) height
    BOTTOM_MARGIN: int = 40
    CORNER_RADIUS: float = 42.0

    # Active state reference dimensions (used by tests and layout)
    ACTIVE_W: int = 300
    ACTIVE_H: int = 140
    ACTIVE_CORNER_RADIUS: float = 20.0

    def __init__(self, result_max_lines: int = 3) -> None:
        self._panel = None
        self._label = None
        self._sublabel = None
        self._content_view = None
        self._root_layer = None
        self._backdrop_layers = {}
        self._renderer = None
        self._state_machine = None
        self._result_max_lines = max(1, result_max_lines)

    @classmethod
    def create(cls, result_max_lines: int = 3) -> "OverlayPanel":
        diag("overlay_panel_create_start", result_max_lines=result_max_lines)
        instance = cls(result_max_lines)
        instance._build()
        diag("overlay_panel_create_end")
        return instance

    def _build(self) -> None:
        diag("overlay_panel_build_start")
        screen = NSScreen.mainScreen()
        sf = screen.frame()
        x = (sf.size.width - self.PANEL_W) / 2
        y = float(self.BOTTOM_MARGIN)
        frame = NSMakeRect(x, y, float(self.PANEL_W), float(self.PANEL_H))

        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        self._panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            NSBackingStoreBuffered,
            False,
        )

        self._panel.setOpaque_(False)
        self._panel.setBackgroundColor_(NSColor.clearColor())
        self._panel.setHasShadow_(False)
        self._panel.setLevel_(NSFloatingWindowLevel)
        self._panel.setIgnoresMouseEvents_(True)
        behavior = (
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        self._panel.setCollectionBehavior_(behavior)
        self._panel.setAlphaValue_(0.0)

        self._build_content()
        self._renderer = AuroraRenderer(
            self._panel,
            self._orb_view,
            self._label,
            self._sublabel,
            self._content_view,
            self._root_layer,
            self._backdrop_layers,
            self._result_max_lines,
        )
        self._state_machine = OverlayStateMachine(
            self._panel,
            self._label,
            self._sublabel,
            self._renderer,
        )

        print("[whisperkey] Overlay panel configured (invisible, alpha=0).")
        diag("overlay_panel_build_end")

    def _build_content(self) -> None:
        w, h = float(self.PANEL_W), float(self.PANEL_H)

        vfx = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        vfx.setMaterial_(NSVisualEffectMaterialHUDWindow)
        vfx.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        vfx.setState_(NSVisualEffectStateActive)
        vfx.setWantsLayer_(True)

        self._root_layer = vfx.layer()
        self._root_layer.setCornerRadius_(self.CORNER_RADIUS)
        self._root_layer.setMasksToBounds_(True)
        self._root_layer.setBorderWidth_(1.0)
        self._root_layer.setBorderColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.55, 0.60, 1.0, 0.22).CGColor()
        )
        self._root_layer.setBackgroundColor_(NSColor.clearColor().CGColor())
        self._backdrop_layers = self._style_backdrop(self._root_layer, w, h)
        self._content_view = vfx

        # Aurora orb view — sized and positioned by renderer
        orb_x = (w - AuroraRenderer.ORB_VIEW_SIZE) / 2.0
        orb_y = (h - AuroraRenderer.ORB_VIEW_SIZE) / 2.0
        self._orb_view = AuroraOrbView.alloc().initWithFrame_(
            NSMakeRect(orb_x, orb_y, AuroraRenderer.ORB_VIEW_SIZE, AuroraRenderer.ORB_VIEW_SIZE)
        )
        self._orb_view.setWantsLayer_(True)
        self._orb_view.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
        vfx.addSubview_(self._orb_view)

        # Label (transcript / status text)
        lw = float(self.ACTIVE_W) - 36.0
        self._label = NSTextField.alloc().initWithFrame_(NSMakeRect(18, 24, lw, 20))
        self._label.setEditable_(False)
        self._label.setSelectable_(False)
        self._label.setDrawsBackground_(False)
        self._label.setBezeled_(False)
        self._label.setTextColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.94, 0.96, 1.0, 0.98)
        )
        self._label.setAlignment_(NSTextAlignmentCenter)
        self._label.setFont_(NSFont.systemFontOfSize_weight_(14.0, 0.20))
        self._label.setLineBreakMode_(NSLineBreakByWordWrapping)
        self._label.setStringValue_("")
        self._label.setHidden_(True)
        vfx.addSubview_(self._label)

        # Sublabel (hint / status)
        self._sublabel = NSTextField.alloc().initWithFrame_(NSMakeRect(18, 4, lw, 16))
        self._sublabel.setEditable_(False)
        self._sublabel.setSelectable_(False)
        self._sublabel.setDrawsBackground_(False)
        self._sublabel.setBezeled_(False)
        self._sublabel.setTextColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.65, 0.72, 0.90, 0.88)
        )
        self._sublabel.setAlignment_(NSTextAlignmentCenter)
        self._sublabel.setFont_(NSFont.systemFontOfSize_weight_(11.0, 0.05))
        self._sublabel.setStringValue_("")
        self._sublabel.setHidden_(True)
        vfx.addSubview_(self._sublabel)

        self._panel.setContentView_(vfx)

    def _style_backdrop(self, root_layer, width: float, height: float) -> dict[str, object]:
        # Aurora-tinted dark glass: deeper dark with subtle violet/cyan tints
        base_gradient = CAGradientLayer.layer()
        base_gradient.setFrame_(NSMakeRect(0, 0, width, height))
        base_gradient.setColors_([
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.22, 0.16, 0.38, 0.40).CGColor(),
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.10, 0.10, 0.22, 0.72).CGColor(),
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.06, 0.06, 0.14, 0.92).CGColor(),
        ])
        base_gradient.setLocations_([0.0, 0.45, 1.0])
        base_gradient.setStartPoint_((0.5, 1.0))
        base_gradient.setEndPoint_((0.5, 0.0))
        root_layer.addSublayer_(base_gradient)

        sheen_gradient = CAGradientLayer.layer()
        sheen_gradient.setFrame_(NSMakeRect(0, height * 0.42, width, height * 0.58))
        sheen_gradient.setColors_([
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.60, 0.70, 1.0, 0.14).CGColor(),
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.60, 0.70, 1.0, 0.04).CGColor(),
            NSColor.clearColor().CGColor(),
        ])
        sheen_gradient.setLocations_([0.0, 0.38, 1.0])
        sheen_gradient.setStartPoint_((0.5, 1.0))
        sheen_gradient.setEndPoint_((0.5, 0.0))
        root_layer.addSublayer_(sheen_gradient)

        bottom_tint = CAGradientLayer.layer()
        bottom_tint.setFrame_(NSMakeRect(0, 0, width, height * 0.52))
        bottom_tint.setColors_([
            NSColor.clearColor().CGColor(),
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.03, 0.04, 0.08, 0.22).CGColor(),
        ])
        bottom_tint.setLocations_([0.0, 1.0])
        bottom_tint.setStartPoint_((0.5, 1.0))
        bottom_tint.setEndPoint_((0.5, 0.0))
        root_layer.addSublayer_(bottom_tint)

        return {"base": base_gradient, "sheen": sheen_gradient, "bottom": bottom_tint}

    # ------------------------------------------------------------------
    # Public API (called from service_controller via dispatch_to_main)
    # ------------------------------------------------------------------

    def set_audio_level_provider(self, fn: Callable[[], float] | None) -> None:
        if self._renderer is not None:
            self._renderer.set_level_fn(fn)

    def show_idle(self) -> None:
        diag("overlay_show_idle")
        self._state_machine.show_idle()

    def show_recording(self) -> None:
        diag("overlay_show_recording")
        self._state_machine.show_recording()

    def show_transcribing(self) -> None:
        diag("overlay_show_transcribing")
        self._state_machine.show_transcribing()

    def show_result(
        self,
        text: str,
        hint: str = "已复制到剪贴板",
        display_duration_s: float = 3.0,
        dismiss_duration_s: float = 0.4,
    ) -> None:
        diag("overlay_show_result", display_duration_s=display_duration_s, dismiss_duration_s=dismiss_duration_s)
        self._state_machine.show_result(text, hint, display_duration_s, dismiss_duration_s)

    def hide_after_paste(self, dismiss_duration_s: float = 0.2) -> None:
        """Force-hide the panel. Used for service stop (goes to HIDDEN)."""
        diag("overlay_hide_after_paste", dismiss_duration_s=dismiss_duration_s)
        self._state_machine.hide_after_paste(dismiss_duration_s)

    def hide_fully(self, dismiss_duration_s: float = 0.2) -> None:
        """Alias for hide_after_paste; used by service_controller.stop_service."""
        self.hide_after_paste(dismiss_duration_s)
