"""Overlay NSPanel module for WhisperKey macOS.

Provides:
- OverlayState: enum of 5 panel states (HIDDEN, IDLE, RECORDING, TRANSCRIBING, RESULT)
- OverlayStateMachine: pure-Python state machine with transition guards and stale-dismiss protection
- VoiceInputView: custom NSView that draws the VoiceInput pill (mic icon / recording / transcribing)
- AuroraRenderer: CA-layer + timer-driven renderer that owns the view and text fields
- OverlayPanel: creates and configures an always-on-top, transparent NSPanel
- dispatch_to_main(): thread-safe utility that queues any callable onto the main run loop
"""

from __future__ import annotations

import enum
import math
import time
from typing import Callable

import objc

from AppKit import (
    NSAffineTransform,
    NSAnimationContext,
    NSAttributedString,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFloatingWindowLevel,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSGraphicsContext,
    NSImage,
    NSLineBreakByWordWrapping,
    NSMakePoint,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSTextAlignmentCenter,
    NSTextField,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from PyObjCTools.AppHelper import callAfter, callLater
from Quartz import (
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


# ---------------------------------------------------------------------------
# VoiceInput View — pill-shaped NSView matching the VoiceInput React component
# ---------------------------------------------------------------------------

class VoiceInputView(NSView):
    """NSView that draws the VoiceInput pill.

    Attributes set by renderer before setNeedsDisplay_:
      _orb_state   — "idle" | "recording" | "transcribing" | "result"
      _elapsed     — float, seconds since current state started
      _audio_level — float 0.0–1.0
      _record_secs — int, whole seconds elapsed in recording
    """

    def initWithFrame_(self, frame):
        self = objc.super(VoiceInputView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._orb_state = "idle"
        self._elapsed = 0.0
        self._audio_level = 0.0
        self._record_secs = 0
        self._draw_error_reported = False
        return self

    def isFlipped(self):
        return False

    def drawRect_(self, dirtyRect):
        try:
            self._draw_rect(dirtyRect)
        except Exception as exc:
            if not getattr(self, "_draw_error_reported", False):
                self._draw_error_reported = True
                diag("overlay_draw_error", error_type=type(exc).__name__, error=str(exc))

    def _draw_rect(self, dirtyRect):
        NSColor.clearColor().set()
        NSBezierPath.fillRect_(self.bounds())

        state = self._orb_state
        if state == "idle":
            self._draw_idle()
        elif state == "recording":
            self._draw_recording()
        elif state == "transcribing":
            self._draw_transcribing()
        # result: no-op — text fields handle display

    # ------------------------------------------------------------------
    # State drawers
    # ------------------------------------------------------------------

    def _draw_idle(self):
        w = self.bounds().size.width
        h = self.bounds().size.height

        mic = NSImage.imageWithSystemSymbolName_accessibilityDescription_("mic", None)
        if mic is None:
            self._draw_fallback_mic(w / 2.0, h / 2.0)
            return
        size = 22.0
        x = (w - size) / 2.0
        y = (h - size) / 2.0
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.078, 0.078, 0.078, 0.85).set()
        mic.drawInRect_fromRect_operation_fraction_(
            NSMakeRect(x, y, size, size),
            NSMakeRect(0, 0, 0, 0),
            11,  # NSCompositingOperationSourceOver
            0.85,
        )

    def _draw_fallback_mic(self, cx: float, cy: float) -> None:
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.078, 0.078, 0.078, 0.85).set()

        capsule = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(cx - 4.0, cy - 8.0, 8.0, 14.0), 4.0, 4.0
        )
        capsule.setLineWidth_(1.8)
        capsule.stroke()

        stand = NSBezierPath.bezierPath()
        stand.moveToPoint_(NSMakePoint(cx, cy - 10.0))
        stand.lineToPoint_(NSMakePoint(cx, cy - 15.0))
        stand.moveToPoint_(NSMakePoint(cx - 6.0, cy - 15.0))
        stand.lineToPoint_(NSMakePoint(cx + 6.0, cy - 15.0))
        stand.setLineWidth_(1.8)
        stand.stroke()

    def _draw_recording(self):
        bounds = self.bounds()
        w = bounds.size.width
        h = bounds.size.height
        cy = h / 2.0
        t = self._elapsed
        level = self._audio_level

        # React structure: 24px icon cell, 8px expanded gap, 12 bars, 8px gap, 40px timer.
        icon_cell_w = 24.0
        expanded_gap = 8.0
        bar_w = 2.0
        bar_gap = 2.0
        bar_count = 12
        bars_w = bar_count * bar_w + (bar_count - 1) * bar_gap
        timer_w = 40.0
        block_w = icon_cell_w + expanded_gap + bars_w + expanded_gap + timer_w
        x = (w - block_w) / 2.0

        # --- Rotating stop square (16×16, radius 3) ---
        sq_cx = x + icon_cell_w / 2.0
        sq_cy = cy
        angle_deg = (t / 2.0 * 360.0) % 360.0

        gc = NSGraphicsContext.currentContext()
        gc.saveGraphicsState()

        xform = NSAffineTransform.transform()
        xform.translateXBy_yBy_(sq_cx, sq_cy)
        xform.rotateByDegrees_(angle_deg)
        xform.translateXBy_yBy_(-8.0, -8.0)
        xform.concat()

        sq_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(0, 0, 16, 16), 3.0, 3.0
        )
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.078, 0.078, 0.078, 0.85).set()
        sq_path.fill()

        gc.restoreGraphicsState()

        # --- 12 frequency bars ---
        bars_x = x + icon_cell_w + expanded_gap
        scale = 0.3 + level * 0.7
        for i in range(bar_count):
            phase = i * 0.4
            wave = abs(math.sin(t * 3.0 + phase))
            bar_h = 2.0 + 11.0 * wave * scale
            bx = bars_x + i * (bar_w + bar_gap)
            by = cy - bar_h / 2.0
            bar_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(bx, by, bar_w, bar_h), 1.0, 1.0
            )
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.078, 0.078, 0.078, 0.85).set()
            bar_path.fill()

        # --- MM:SS timer ---
        timer_x = bars_x + bars_w + expanded_gap
        mins = self._record_secs // 60
        secs = self._record_secs % 60
        timer_str = f"{mins:02d}:{secs:02d}"
        attrs = {
            NSFontAttributeName: NSFont.monospacedDigitSystemFontOfSize_weight_(11.0, 0.0),
            NSForegroundColorAttributeName: NSColor.colorWithSRGBRed_green_blue_alpha_(
                0.39, 0.39, 0.39, 0.80
            ),
        }
        ns_str = NSAttributedString.alloc().initWithString_attributes_(timer_str, attrs)
        sz = ns_str.size()
        ns_str.drawAtPoint_(NSMakePoint(timer_x + (40.0 - sz.width) / 2.0, cy - sz.height / 2.0))

    def _draw_transcribing(self):
        bounds = self.bounds()
        w = bounds.size.width
        h = bounds.size.height
        cx = w / 2.0
        cy = h / 2.0
        t = self._elapsed

        # Spinning dot orbiting center
        orbit_r = 10.0
        angle = math.radians(t * 180.0 % 360.0)
        dot_cx = cx - 14 + orbit_r * math.cos(angle)
        dot_cy = cy + orbit_r * math.sin(angle)
        dot_size = 6.0
        dot_path = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(dot_cx - dot_size / 2.0, dot_cy - dot_size / 2.0, dot_size, dot_size)
        )
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.078, 0.078, 0.078, 0.85).set()
        dot_path.fill()

        # "..." label
        attrs = {
            NSFontAttributeName: NSFont.systemFontOfSize_(14.0),
            NSForegroundColorAttributeName: NSColor.colorWithSRGBRed_green_blue_alpha_(
                0.078, 0.078, 0.078, 0.85
            ),
        }
        ns_str = NSAttributedString.alloc().initWithString_attributes_("...", attrs)
        sz = ns_str.size()
        ns_str.drawAtPoint_(NSMakePoint(cx, cy - sz.height / 2.0))


# Backward-compat alias — tests import AuroraOrbView by name
AuroraOrbView = VoiceInputView


# ---------------------------------------------------------------------------
# Aurora Renderer — owns the panel, voice-input view, and text fields
# ---------------------------------------------------------------------------

class AuroraRenderer:
    """Drives panel animations, the VoiceInput view, and text fields."""

    # Idle geometry
    IDLE_W: float = 52.0
    IDLE_H: float = 52.0
    IDLE_CORNER_RADIUS: float = 26.0

    # Recording / transcribing geometry
    ACTIVE_W: float = 220.0
    ACTIVE_H: float = 52.0
    ACTIVE_CORNER_RADIUS: float = 26.0

    # Result geometry
    RESULT_W: float = 300.0
    RESULT_MIN_H: float = 52.0
    RESULT_CORNER_RADIUS: float = 26.0
    RESULT_TOP_PAD: float = 8.0

    BOTTOM_MARGIN: float = 40.0

    HORIZONTAL_INSET: float = 18.0
    BOTTOM_PADDING: float = 4.0
    TEXT_GAP: float = 4.0
    SUBLABEL_HEIGHT: float = 16.0
    BASE_LABEL_HEIGHT: float = 20.0

    APPEAR_DURATION_S: float = 0.40
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
        self._record_start_at: float = 0.0

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
        self._orb_view._record_secs = 0
        self._hide_text()
        self._clear_text()

        self._content_view.setFrame_(NSMakeRect(0, 0, self.IDLE_W, self.IDLE_H))
        self._content_view.layer().setFrame_(NSMakeRect(0, 0, self.IDLE_W, self.IDLE_H))
        self._root_layer.setCornerRadius_(self.IDLE_CORNER_RADIUS)
        self._root_layer.setBorderWidth_(1.0)
        self._root_layer.setBorderColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.10).CGColor()
        )
        self._root_layer.setBackgroundColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.90).CGColor()
        )

        self._orb_view.setFrame_(NSMakeRect(0, 0, self.IDLE_W, self.IDLE_H))
        self._orb_view.setNeedsDisplay_(True)

        current_alpha = self._panel.alphaValue()
        if current_alpha < 0.05:
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
        self._record_start_at = time.monotonic()

        self._orb_view._orb_state = "recording"
        self._orb_view._elapsed = 0.0
        self._orb_view._audio_level = 0.0
        self._orb_view._record_secs = 0
        self._hide_text()
        self._clear_text()

        active_frame = self._active_frame(self.ACTIVE_H)
        self._content_view.setFrame_(NSMakeRect(0, 0, self.ACTIVE_W, self.ACTIVE_H))
        self._content_view.layer().setFrame_(NSMakeRect(0, 0, self.ACTIVE_W, self.ACTIVE_H))
        self._root_layer.setCornerRadius_(self.ACTIVE_CORNER_RADIUS)
        self._root_layer.setBorderWidth_(1.0)
        self._root_layer.setBorderColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.10).CGColor()
        )
        self._root_layer.setBackgroundColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.90).CGColor()
        )

        self._orb_view.setFrame_(NSMakeRect(0, 0, self.ACTIVE_W, self.ACTIVE_H))
        self._orb_view.setNeedsDisplay_(True)

        self._panel.setAlphaValue_(1.0)
        self._animate_panel(
            target_alpha=1.0,
            target_frame=active_frame,
            duration_s=self.APPEAR_DURATION_S,
            timing_name=kCAMediaTimingFunctionEaseOut,
        )
        self._schedule_tick(gen)

    def show_transcribing(self, gen: int) -> None:
        self._visual_gen = gen
        self._mode = OverlayState.TRANSCRIBING
        self._phase_started_at = time.monotonic()
        self._elapsed = 0.0

        self._orb_view._orb_state = "transcribing"
        self._orb_view._elapsed = 0.0
        self._orb_view._audio_level = 0.0
        self._hide_text()
        self._clear_text()

        active_frame = self._active_frame(self.ACTIVE_H)
        self._content_view.setFrame_(NSMakeRect(0, 0, self.ACTIVE_W, self.ACTIVE_H))
        self._content_view.layer().setFrame_(NSMakeRect(0, 0, self.ACTIVE_W, self.ACTIVE_H))
        self._root_layer.setCornerRadius_(self.ACTIVE_CORNER_RADIUS)
        self._root_layer.setBorderWidth_(1.0)
        self._root_layer.setBorderColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.10).CGColor()
        )
        self._root_layer.setBackgroundColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.90).CGColor()
        )

        self._orb_view.setFrame_(NSMakeRect(0, 0, self.ACTIVE_W, self.ACTIVE_H))
        self._orb_view.setNeedsDisplay_(True)

        self._panel.setFrame_display_(active_frame, False)
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
        self.show_idle(gen)

    def hide_fully(self, gen: int, duration_s: float = 0.20) -> None:
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

    def hide_after_paste(self, gen: int, duration_s: float | None = None) -> None:
        self.hide_fully(gen, duration_s if duration_s is not None else 0.20)

    def hide_after_result(self, gen: int, duration_s: float | None = None) -> None:
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

        if self._mode == OverlayState.RECORDING:
            self._orb_view._record_secs = int(time.monotonic() - self._record_start_at)

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

    def _result_frame(self, height: float):
        x = (self._screen_w - self.RESULT_W) / 2.0
        return NSMakeRect(x, self.BOTTOM_MARGIN, self.RESULT_W, height)

    def _apply_result_layout(self, text: str) -> None:
        w = self.RESULT_W
        content_w = w - self.HORIZONTAL_INSET * 2
        measured_h = self._label.cell().cellSizeForBounds_(NSMakeRect(0, 0, content_w, 1000)).height
        visible_lines = max(1, min(self._result_max_lines, math.ceil(measured_h / self.BASE_LABEL_HEIGHT)))
        label_h = max(self.BASE_LABEL_HEIGHT, math.ceil(measured_h))
        if visible_lines > 1:
            label_h = max(label_h, self.BASE_LABEL_HEIGHT * visible_lines)

        text_block_h = label_h + self.TEXT_GAP + self.SUBLABEL_HEIGHT
        target_h = max(
            self.RESULT_MIN_H,
            self.BOTTOM_PADDING + text_block_h + self.RESULT_TOP_PAD,
        )

        self._content_view.setFrame_(NSMakeRect(0, 0, w, target_h))
        self._content_view.layer().setFrame_(NSMakeRect(0, 0, w, target_h))
        self._root_layer.setCornerRadius_(self.RESULT_CORNER_RADIUS)
        self._root_layer.setBorderWidth_(1.0)
        self._root_layer.setBorderColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.10).CGColor()
        )
        self._root_layer.setBackgroundColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.90).CGColor()
        )

        # Orb view placed at top as invisible placeholder (satisfies layout geometry tests)
        orb_y = target_h - 4
        self._orb_view.setFrame_(NSMakeRect((w - 8) / 2.0, orb_y, 8, 2))

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

        self._panel.setFrame_display_(self._result_frame(target_h), False)

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
            self._orb_view._record_secs = 0


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
        if self._state == OverlayState.HIDDEN:
            if not self._transition(OverlayState.IDLE):
                return
        elif self._state != OverlayState.IDLE:
            self._state = OverlayState.IDLE
        else:
            return

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
        self.hide_after_paste(dismiss_duration_s)

    def _auto_dismiss(self, gen: int, dismiss_duration_s: float) -> None:
        if gen != self._dismiss_gen or self._state != OverlayState.RESULT:
            return
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
    """Wrapper around an NSPanel configured for transparent VoiceInput pill display."""

    PANEL_W: int = 52    # idle width
    PANEL_H: int = 52    # idle height
    BOTTOM_MARGIN: int = 40
    CORNER_RADIUS: float = 26.0

    # Result state reference dimensions (used by tests and layout)
    ACTIVE_W: int = 300
    ACTIVE_H: int = 52
    ACTIVE_CORNER_RADIUS: float = 26.0

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

        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        content.setWantsLayer_(True)

        self._root_layer = content.layer()
        self._root_layer.setCornerRadius_(self.CORNER_RADIUS)
        self._root_layer.setMasksToBounds_(True)
        self._root_layer.setBorderWidth_(1.0)
        self._root_layer.setBorderColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.10).CGColor()
        )
        self._root_layer.setBackgroundColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.90).CGColor()
        )
        self._backdrop_layers = {}
        self._content_view = content

        # VoiceInputView — fills the full content view, resized per state by renderer
        self._orb_view = VoiceInputView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        self._orb_view.setWantsLayer_(True)
        self._orb_view.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
        content.addSubview_(self._orb_view)

        # Label (transcript text)
        lw = float(self.ACTIVE_W) - 36.0
        self._label = NSTextField.alloc().initWithFrame_(NSMakeRect(18, 24, lw, 20))
        self._label.setEditable_(False)
        self._label.setSelectable_(False)
        self._label.setDrawsBackground_(False)
        self._label.setBezeled_(False)
        self._label.setTextColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.078, 0.078, 0.078, 0.90)
        )
        self._label.setAlignment_(NSTextAlignmentCenter)
        self._label.setFont_(NSFont.systemFontOfSize_weight_(14.0, 0.20))
        self._label.setLineBreakMode_(NSLineBreakByWordWrapping)
        self._label.setStringValue_("")
        self._label.setHidden_(True)
        content.addSubview_(self._label)

        # Sublabel (hint)
        self._sublabel = NSTextField.alloc().initWithFrame_(NSMakeRect(18, 4, lw, 16))
        self._sublabel.setEditable_(False)
        self._sublabel.setSelectable_(False)
        self._sublabel.setDrawsBackground_(False)
        self._sublabel.setBezeled_(False)
        self._sublabel.setTextColor_(
            NSColor.colorWithSRGBRed_green_blue_alpha_(0.39, 0.39, 0.39, 0.80)
        )
        self._sublabel.setAlignment_(NSTextAlignmentCenter)
        self._sublabel.setFont_(NSFont.systemFontOfSize_weight_(11.0, 0.05))
        self._sublabel.setStringValue_("")
        self._sublabel.setHidden_(True)
        content.addSubview_(self._sublabel)

        self._panel.setContentView_(content)

    # ------------------------------------------------------------------
    # Public API
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
        diag("overlay_hide_after_paste", dismiss_duration_s=dismiss_duration_s)
        self._state_machine.hide_after_paste(dismiss_duration_s)

    def hide_fully(self, dismiss_duration_s: float = 0.2) -> None:
        self.hide_after_paste(dismiss_duration_s)
