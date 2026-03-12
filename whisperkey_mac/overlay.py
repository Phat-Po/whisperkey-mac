"""Overlay NSPanel module for WhisperKey macOS.

Provides:
- OverlayState: enum of 4 panel states (HIDDEN, RECORDING, TRANSCRIBING, RESULT)
- OverlayStateMachine: pure-Python state machine with transition guards and stale-dismiss protection
- OverlayPanel: creates and configures an always-on-top, transparent NSPanel with
  a darker glass HUD, animated recording/transcribing visuals, and result text display
- dispatch_to_main(): thread-safe utility that queues any callable onto the main run loop
"""

import enum
import math
import time

from AppKit import (
    NSAnimationContext,
    NSBackingStoreBuffered,
    NSColor,
    NSFloatingWindowLevel,
    NSFont,
    NSLineBreakByWordWrapping,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSTextAlignmentCenter,
    NSTextField,
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
    CALayer,
    CAGradientLayer,
    CAMediaTimingFunction,
    CATransaction,
    kCAMediaTimingFunctionEaseInEaseOut,
    kCAMediaTimingFunctionEaseOut,
)


def dispatch_to_main(fn, *args) -> None:
    """Queue fn(*args) on the main run loop. Safe to call from any thread."""
    callAfter(fn, *args)


class OverlayState(enum.Enum):
    HIDDEN = "hidden"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    RESULT = "result"


_VALID_TRANSITIONS: dict[OverlayState, set[OverlayState]] = {
    OverlayState.HIDDEN: {OverlayState.RECORDING},
    OverlayState.RECORDING: {OverlayState.TRANSCRIBING},
    OverlayState.TRANSCRIBING: {OverlayState.RESULT},
    OverlayState.RESULT: {OverlayState.HIDDEN},
}


class OverlayRenderer:
    """Owns panel animations and layer-based indicators."""

    APPEAR_DURATION_S = 0.15
    DEFAULT_PASTE_DISMISS_DURATION_S = 0.2
    DEFAULT_RESULT_DISMISS_DURATION_S = 0.4
    RECORDING_FPS = 30.0
    DOT_FPS = 20.0
    RECORDING_BAR_COUNT = 5
    TRANSCRIBING_DOT_COUNT = 3
    BAR_WIDTH = 10.0
    BAR_GAP = 10.0
    BAR_MIN_HEIGHT = 12.0
    BAR_MAX_HEIGHT = 34.0
    DOT_SIZE = 10.0
    DOT_GAP = 14.0
    CENTER_Y = 40.0
    ENTRY_OFFSET_Y = 8.0
    HORIZONTAL_INSET = 18.0
    TOP_PADDING = 18.0
    BOTTOM_PADDING = 12.0
    TEXT_GAP = 6.0
    SUBLABEL_HEIGHT = 16.0
    BASE_LABEL_HEIGHT = 22.0

    def __init__(
        self,
        panel,
        label,
        sublabel,
        content_view,
        base_frame,
        backdrop_layers: dict[str, object] | None = None,
        result_max_lines: int = 3,
    ) -> None:
        self._panel = panel
        self._label = label
        self._sublabel = sublabel
        self._content_view = content_view
        self._base_frame = base_frame
        self._current_frame = base_frame
        self._backdrop_layers = backdrop_layers or {}
        self._result_max_lines = max(1, result_max_lines)
        self._visual_gen = 0
        self._mode = OverlayState.HIDDEN
        self._phase_started_at = time.monotonic()
        self._bar_layers: list = []
        self._dot_layers: list = []

        self._configure_text_fields()
        self._build_indicator_layers()
        self._reset_visuals()

    def show_recording(self, gen: int) -> None:
        self._visual_gen = gen
        self._mode = OverlayState.RECORDING
        self._phase_started_at = time.monotonic()
        self._apply_base_layout()
        self._clear_text()
        self._hide_text()
        self._show_bar_layers()
        self._hide_dot_layers()
        self._update_recording_layers(0.0)
        self._panel.setFrame_display_(
            self._frame_for_height(self._base_frame.size.height, self._base_frame.origin.y - self.ENTRY_OFFSET_Y),
            False,
        )
        self._panel.setAlphaValue_(0.0)
        self._panel.orderFront_(None)
        self._animate_panel(
            target_alpha=1.0,
            target_frame=self._base_frame,
            duration_s=self.APPEAR_DURATION_S,
            timing_name=kCAMediaTimingFunctionEaseOut,
        )
        self._schedule_recording_tick(gen)

    def show_transcribing(self, gen: int) -> None:
        self._visual_gen = gen
        self._mode = OverlayState.TRANSCRIBING
        self._phase_started_at = time.monotonic()
        self._apply_base_layout()
        self._clear_text()
        self._hide_text()
        self._hide_bar_layers()
        self._show_dot_layers()
        self._update_dot_layers(0.0)
        self._panel.setFrame_display_(self._base_frame, False)
        self._panel.setAlphaValue_(1.0)
        self._schedule_dot_tick(gen)

    def show_result(self, gen: int, text: str) -> None:
        self._visual_gen = gen
        self._mode = OverlayState.RESULT
        self._hide_bar_layers()
        self._hide_dot_layers()
        self._show_text()
        self._apply_result_layout(text)
        self._panel.setAlphaValue_(1.0)

    def hide_after_paste(self, gen: int, duration_s: float | None = None) -> None:
        self._start_hide(gen, duration_s or self.DEFAULT_PASTE_DISMISS_DURATION_S)

    def hide_after_result(self, gen: int, duration_s: float | None = None) -> None:
        self._start_hide(gen, duration_s or self.DEFAULT_RESULT_DISMISS_DURATION_S)

    def _start_hide(self, gen: int, duration_s: float) -> None:
        self._visual_gen = gen
        self._mode = OverlayState.HIDDEN

        def _complete_hide() -> None:
            if gen != self._visual_gen or self._mode != OverlayState.HIDDEN:
                return
            self._panel.orderOut_(None)
            self._panel.setFrame_display_(self._base_frame, False)
            self._panel.setAlphaValue_(0.0)
            self._apply_base_layout()
            self._reset_visuals()

        self._animate_panel(
            target_alpha=0.0,
            target_frame=self._current_frame,
            duration_s=duration_s,
            timing_name=kCAMediaTimingFunctionEaseInEaseOut,
            completion=_complete_hide,
        )

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
        context = NSAnimationContext.currentContext()
        context.setDuration_(duration_s)
        context.setTimingFunction_(CAMediaTimingFunction.functionWithName_(timing_name))
        self._panel.animator().setAlphaValue_(target_alpha)
        self._panel.animator().setFrame_display_(target_frame, False)
        NSAnimationContext.endGrouping()
        if completion is not None:
            callLater(duration_s, completion)

    def _schedule_recording_tick(self, gen: int) -> None:
        callLater(1.0 / self.RECORDING_FPS, lambda: self._tick_recording(gen))

    def _tick_recording(self, gen: int) -> None:
        if gen != self._visual_gen or self._mode != OverlayState.RECORDING:
            return
        self._update_recording_layers(time.monotonic() - self._phase_started_at)
        self._schedule_recording_tick(gen)

    def _schedule_dot_tick(self, gen: int) -> None:
        callLater(1.0 / self.DOT_FPS, lambda: self._tick_dots(gen))

    def _tick_dots(self, gen: int) -> None:
        if gen != self._visual_gen or self._mode != OverlayState.TRANSCRIBING:
            return
        self._update_dot_layers(time.monotonic() - self._phase_started_at)
        self._schedule_dot_tick(gen)

    def _update_recording_layers(self, elapsed: float) -> None:
        total_width = (
            self.RECORDING_BAR_COUNT * self.BAR_WIDTH
            + (self.RECORDING_BAR_COUNT - 1) * self.BAR_GAP
        )
        start_x = (self._base_frame.size.width - total_width) / 2

        CATransaction.begin()
        CATransaction.setDisableActions_(True)
        for index, layer in enumerate(self._bar_layers):
            phase = elapsed * 6.4 + index * 0.8
            amplitude = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(phase))
            height = self.BAR_MIN_HEIGHT + (self.BAR_MAX_HEIGHT - self.BAR_MIN_HEIGHT) * amplitude
            x = start_x + index * (self.BAR_WIDTH + self.BAR_GAP)
            y = self.CENTER_Y - (height / 2)
            layer.setFrame_(NSMakeRect(x, y, self.BAR_WIDTH, height))
            layer.setCornerRadius_(self.BAR_WIDTH / 2)
        CATransaction.commit()

    def _update_dot_layers(self, elapsed: float) -> None:
        total_width = (
            self.TRANSCRIBING_DOT_COUNT * self.DOT_SIZE
            + (self.TRANSCRIBING_DOT_COUNT - 1) * self.DOT_GAP
        )
        start_x = (self._base_frame.size.width - total_width) / 2
        cycle = 0.9

        CATransaction.begin()
        CATransaction.setDisableActions_(True)
        for index, layer in enumerate(self._dot_layers):
            phase = (elapsed - index * 0.3) % cycle
            pulse = math.sin((phase / 0.3) * math.pi) if phase < 0.3 else 0.0
            size = self.DOT_SIZE + pulse * 6.0
            opacity = 0.34 + pulse * 0.66
            x = start_x + index * (self.DOT_SIZE + self.DOT_GAP) + (self.DOT_SIZE - size) / 2
            y = self.CENTER_Y - (size / 2)
            layer.setFrame_(NSMakeRect(x, y, size, size))
            layer.setCornerRadius_(size / 2)
            layer.setOpacity_(opacity)
        CATransaction.commit()

    def _build_indicator_layers(self) -> None:
        root_layer = self._content_view.layer()
        bar_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.97, 0.98, 1.0, 0.94).CGColor()
        dot_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.80, 0.85, 0.92, 0.82).CGColor()

        for _ in range(self.RECORDING_BAR_COUNT):
            layer = CALayer.layer()
            layer.setBackgroundColor_(bar_color)
            layer.setHidden_(True)
            root_layer.addSublayer_(layer)
            self._bar_layers.append(layer)

        for _ in range(self.TRANSCRIBING_DOT_COUNT):
            layer = CALayer.layer()
            layer.setBackgroundColor_(dot_color)
            layer.setHidden_(True)
            root_layer.addSublayer_(layer)
            self._dot_layers.append(layer)

    def _reset_visuals(self) -> None:
        self._hide_bar_layers()
        self._hide_dot_layers()
        self._clear_text()
        self._hide_text()

    def _show_bar_layers(self) -> None:
        for layer in self._bar_layers:
            layer.setHidden_(False)
            layer.setOpacity_(1.0)

    def _hide_bar_layers(self) -> None:
        for layer in self._bar_layers:
            layer.setHidden_(True)

    def _show_dot_layers(self) -> None:
        for layer in self._dot_layers:
            layer.setHidden_(False)

    def _hide_dot_layers(self) -> None:
        for layer in self._dot_layers:
            layer.setHidden_(True)

    def _show_text(self) -> None:
        self._label.setHidden_(False)
        self._sublabel.setHidden_(False)

    def _hide_text(self) -> None:
        self._label.setHidden_(True)
        self._sublabel.setHidden_(True)

    def _clear_text(self) -> None:
        self._label.setStringValue_("")
        self._sublabel.setStringValue_("")

    def _configure_text_fields(self) -> None:
        self._label.setUsesSingleLineMode_(False)
        self._label.setMaximumNumberOfLines_(self._result_max_lines)
        self._label.setLineBreakMode_(NSLineBreakByWordWrapping)
        self._label.cell().setWraps_(True)
        self._label.cell().setScrollable_(False)
        self._label.cell().setLineBreakMode_(NSLineBreakByWordWrapping)

    def _apply_base_layout(self) -> None:
        width = self._base_frame.size.width
        height = self._base_frame.size.height
        self._current_frame = self._base_frame
        self._content_view.setFrame_(NSMakeRect(0, 0, width, height))
        self._content_view.layer().setFrame_(NSMakeRect(0, 0, width, height))
        self._update_backdrop_frames(width, height)
        self._label.setFrame_(NSMakeRect(self.HORIZONTAL_INSET, 34.0, width - (self.HORIZONTAL_INSET * 2), self.BASE_LABEL_HEIGHT))
        self._sublabel.setFrame_(NSMakeRect(self.HORIZONTAL_INSET, 12.0, width - (self.HORIZONTAL_INSET * 2), self.SUBLABEL_HEIGHT))

    def _apply_result_layout(self, text: str) -> None:
        width = self._base_frame.size.width
        content_width = width - (self.HORIZONTAL_INSET * 2)
        measured_height = self._label.cell().cellSizeForBounds_(NSMakeRect(0, 0, content_width, 1000)).height
        visible_lines = max(1, min(self._result_max_lines, math.ceil(measured_height / self.BASE_LABEL_HEIGHT)))
        label_height = max(self.BASE_LABEL_HEIGHT, math.ceil(measured_height))
        if visible_lines > 1:
            label_height = max(label_height, self.BASE_LABEL_HEIGHT * visible_lines)
        target_height = max(
            self._base_frame.size.height,
            self.TOP_PADDING + label_height + self.TEXT_GAP + self.SUBLABEL_HEIGHT + self.BOTTOM_PADDING,
        )
        self._current_frame = self._frame_for_height(target_height)
        self._content_view.setFrame_(NSMakeRect(0, 0, width, target_height))
        self._content_view.layer().setFrame_(NSMakeRect(0, 0, width, target_height))
        self._update_backdrop_frames(width, target_height)
        self._label.setFrame_(
            NSMakeRect(
                self.HORIZONTAL_INSET,
                self.BOTTOM_PADDING + self.SUBLABEL_HEIGHT + self.TEXT_GAP,
                content_width,
                label_height,
            )
        )
        self._sublabel.setFrame_(
            NSMakeRect(
                self.HORIZONTAL_INSET,
                self.BOTTOM_PADDING,
                content_width,
                self.SUBLABEL_HEIGHT,
            )
        )
        self._panel.setFrame_display_(self._current_frame, False)

    def _update_backdrop_frames(self, width: float, height: float) -> None:
        base_gradient = self._backdrop_layers.get("base")
        if base_gradient is not None:
            base_gradient.setFrame_(NSMakeRect(0, 0, width, height))

        sheen_gradient = self._backdrop_layers.get("sheen")
        if sheen_gradient is not None:
            sheen_gradient.setFrame_(NSMakeRect(0, height * 0.42, width, height * 0.58))

        bottom_tint = self._backdrop_layers.get("bottom")
        if bottom_tint is not None:
            bottom_tint.setFrame_(NSMakeRect(0, 0, width, height * 0.52))

    def _frame_for_height(self, height: float, y: float | None = None):
        return NSMakeRect(
            self._base_frame.origin.x,
            self._base_frame.origin.y if y is None else y,
            self._base_frame.size.width,
            height,
        )


class OverlayStateMachine:
    """4-state machine for the overlay panel. All methods must run on the main thread."""

    def __init__(self, panel, label, sublabel, renderer: OverlayRenderer | None = None) -> None:
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
        if self._state not in (OverlayState.RECORDING, OverlayState.TRANSCRIBING, OverlayState.RESULT):
            return
        self._state = OverlayState.HIDDEN
        gen = self._advance_gen()
        if self._renderer is not None:
            self._renderer.hide_after_paste(gen, dismiss_duration_s)
            return
        self._panel.orderOut_(None)
        self._panel.setAlphaValue_(0.0)

    def _auto_dismiss(self, gen: int, dismiss_duration_s: float) -> None:
        if gen != self._dismiss_gen or self._state != OverlayState.RESULT:
            return
        self._state = OverlayState.HIDDEN
        next_gen = self._advance_gen()
        if self._renderer is not None:
            self._renderer.hide_after_result(next_gen, dismiss_duration_s)
            return
        self._panel.orderOut_(None)
        self._panel.setAlphaValue_(0.0)


class OverlayPanel:
    """Wrapper around an NSPanel configured for transparent overlay display."""

    PANEL_W: int = 360
    PANEL_H: int = 74
    BOTTOM_MARGIN: int = 40
    CORNER_RADIUS: float = 18.0

    def __init__(self, result_max_lines: int = 3) -> None:
        self._panel = None
        self._label = None
        self._sublabel = None
        self._content_view = None
        self._backdrop_layers = {}
        self._renderer = None
        self._state_machine = None
        self._result_max_lines = max(1, result_max_lines)

    @classmethod
    def create(cls, result_max_lines: int = 3) -> "OverlayPanel":
        instance = cls(result_max_lines)
        instance._build()
        return instance

    def _build(self) -> None:
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
        self._renderer = OverlayRenderer(
            self._panel,
            self._label,
            self._sublabel,
            self._content_view,
            frame,
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

    def _build_content(self) -> None:
        w, h = float(self.PANEL_W), float(self.PANEL_H)

        vfx = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        vfx.setMaterial_(NSVisualEffectMaterialHUDWindow)
        vfx.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        vfx.setState_(NSVisualEffectStateActive)
        vfx.setWantsLayer_(True)

        root_layer = vfx.layer()
        root_layer.setCornerRadius_(self.CORNER_RADIUS)
        root_layer.setMasksToBounds_(True)
        root_layer.setBorderWidth_(1.0)
        root_layer.setBorderColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.97, 0.98, 1.0, 0.18).CGColor()
        )
        root_layer.setBackgroundColor_(NSColor.clearColor().CGColor())
        self._backdrop_layers = self._style_backdrop(root_layer, w, h)
        self._content_view = vfx

        self._label = NSTextField.alloc().initWithFrame_(NSMakeRect(18, 34, w - 36, 22))
        self._label.setEditable_(False)
        self._label.setSelectable_(False)
        self._label.setDrawsBackground_(False)
        self._label.setBezeled_(False)
        self._label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.96, 0.97, 0.99, 0.98))
        self._label.setAlignment_(NSTextAlignmentCenter)
        self._label.setFont_(NSFont.systemFontOfSize_weight_(15.0, 0.25))
        self._label.setLineBreakMode_(NSLineBreakByWordWrapping)
        self._label.setStringValue_("")
        vfx.addSubview_(self._label)

        self._sublabel = NSTextField.alloc().initWithFrame_(NSMakeRect(18, 12, w - 36, 16))
        self._sublabel.setEditable_(False)
        self._sublabel.setSelectable_(False)
        self._sublabel.setDrawsBackground_(False)
        self._sublabel.setBezeled_(False)
        self._sublabel.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.79, 0.83, 0.90, 0.92))
        self._sublabel.setAlignment_(NSTextAlignmentCenter)
        self._sublabel.setFont_(NSFont.systemFontOfSize_weight_(11.0, 0.08))
        self._sublabel.setStringValue_("")
        vfx.addSubview_(self._sublabel)

        self._panel.setContentView_(vfx)

    def _style_backdrop(self, root_layer, width: float, height: float) -> dict[str, object]:
        base_gradient = CAGradientLayer.layer()
        base_gradient.setFrame_(NSMakeRect(0, 0, width, height))
        base_gradient.setColors_([
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.36, 0.38, 0.42, 0.36).CGColor(),
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.17, 0.18, 0.22, 0.72).CGColor(),
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.10, 0.11, 0.14, 0.92).CGColor(),
        ])
        base_gradient.setLocations_([0.0, 0.42, 1.0])
        base_gradient.setStartPoint_((0.5, 1.0))
        base_gradient.setEndPoint_((0.5, 0.0))
        root_layer.addSublayer_(base_gradient)

        sheen_gradient = CAGradientLayer.layer()
        sheen_gradient.setFrame_(NSMakeRect(0, height * 0.42, width, height * 0.58))
        sheen_gradient.setColors_([
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.97, 1.0, 0.16).CGColor(),
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.97, 1.0, 0.04).CGColor(),
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
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.05, 0.06, 0.08, 0.22).CGColor(),
        ])
        bottom_tint.setLocations_([0.0, 1.0])
        bottom_tint.setStartPoint_((0.5, 1.0))
        bottom_tint.setEndPoint_((0.5, 0.0))
        root_layer.addSublayer_(bottom_tint)
        return {
            "base": base_gradient,
            "sheen": sheen_gradient,
            "bottom": bottom_tint,
        }

    def show_recording(self) -> None:
        self._state_machine.show_recording()

    def show_transcribing(self) -> None:
        self._state_machine.show_transcribing()

    def show_result(
        self,
        text: str,
        hint: str = "已复制到剪贴板",
        display_duration_s: float = 3.0,
        dismiss_duration_s: float = 0.4,
    ) -> None:
        self._state_machine.show_result(text, hint, display_duration_s, dismiss_duration_s)

    def hide_after_paste(self, dismiss_duration_s: float = 0.2) -> None:
        self._state_machine.hide_after_paste(dismiss_duration_s)
