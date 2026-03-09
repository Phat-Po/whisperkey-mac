"""Overlay NSPanel module for WhisperKey macOS.

Provides:
- OverlayState: enum of 4 panel states (HIDDEN, RECORDING, TRANSCRIBING, RESULT)
- OverlayStateMachine: pure-Python state machine with transition guards and stale-dismiss protection
- OverlayPanel: creates and configures an always-on-top, transparent NSPanel with
  NSVisualEffectView content and 2 NSTextField labels; exposes state machine methods directly
- dispatch_to_main(): thread-safe utility that queues any callable onto the main run loop.
  Safe to call from background threads. Non-blocking.

IMPORTANT: OverlayPanel.create() must be called from the main thread (after NSApp is running).
All OverlayStateMachine methods must be called on the main thread (use dispatch_to_main from workers).
"""
import enum

from AppKit import (
    NSPanel,
    NSScreen,
    NSColor,
    NSFont,
    NSTextField,
    NSTextAlignmentCenter,
    NSLineBreakByTruncatingTail,
    NSMakeRect,
    NSVisualEffectView,
    NSVisualEffectMaterialHUDWindow,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectStateActive,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
    NSBackingStoreBuffered,
    NSFloatingWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from PyObjCTools.AppHelper import callAfter, callLater


def dispatch_to_main(fn, *args) -> None:
    """Queue fn(*args) on the main run loop. Safe to call from any thread.

    Non-blocking: caller continues immediately.
    Uses PyObjCTools.AppHelper.callAfter which handles NSAutoreleasePool
    and exception safety correctly.
    """
    callAfter(fn, *args)


class OverlayState(enum.Enum):
    """4 states of the overlay panel lifecycle."""
    HIDDEN = "hidden"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    RESULT = "result"


# Valid state transitions. All public methods use this guard.
# RESULT -> HIDDEN is for auto-dismiss timer.
# hide_after_paste() bypasses the guard (force-hides from any active state).
_VALID_TRANSITIONS: dict[OverlayState, set[OverlayState]] = {
    OverlayState.HIDDEN:       {OverlayState.RECORDING},
    OverlayState.RECORDING:    {OverlayState.TRANSCRIBING},
    OverlayState.TRANSCRIBING: {OverlayState.RESULT},
    OverlayState.RESULT:       {OverlayState.HIDDEN},
}


class OverlayStateMachine:
    """4-state machine for the overlay panel. ALL methods MUST be called on the main thread.

    Callers on background threads must use dispatch_to_main() before calling these methods.
    """

    def __init__(self, panel, label, sublabel) -> None:
        """
        Args:
            panel: NSPanel instance (underlying window)
            label: NSTextField primary label (recording state "...", transcribing state "转录中...", result = text)
            sublabel: NSTextField secondary label ("已复制到剪贴板" in result state)
        """
        self._panel = panel
        self._label = label
        self._sublabel = sublabel
        self._state = OverlayState.HIDDEN
        self._dismiss_gen: int = 0  # increment to cancel stale auto-dismiss callbacks

    def _transition(self, target: OverlayState) -> bool:
        """Attempt a state transition. Returns True if allowed, False if rejected (silent)."""
        if target in _VALID_TRANSITIONS.get(self._state, set()):
            self._state = target
            return True
        return False

    def show_recording(self) -> None:
        """Called on main thread (dispatched from pynput listener thread).

        Transitions HIDDEN -> RECORDING. Rejected if not in HIDDEN state.
        Shows overlay panel with '...' placeholder text.
        """
        if not self._transition(OverlayState.RECORDING):
            return
        self._dismiss_gen += 1  # invalidate any pending auto-dismiss callbacks
        self._label.setStringValue_("...")
        self._sublabel.setStringValue_("")
        # TODO Phase 3: replace with NSAnimationContext 150ms fade-in + 8pt slide-up
        self._panel.setAlphaValue_(1.0)  # CRITICAL: set alpha BEFORE orderFront_ (compositor race)
        self._panel.orderFront_(None)

    def show_transcribing(self) -> None:
        """Called on main thread (dispatched from pynput listener on key-release).

        Transitions RECORDING -> TRANSCRIBING. Rejected if not in RECORDING state.
        """
        if not self._transition(OverlayState.TRANSCRIBING):
            return
        self._label.setStringValue_("转录中...")

    def show_result(self, text: str) -> None:
        """Called on main thread (dispatched from transcription worker thread).

        Transitions TRANSCRIBING -> RESULT. Rejected if not in TRANSCRIBING state.
        Schedules auto-dismiss after 3 seconds (RST-04) with generation guard.
        """
        if not self._transition(OverlayState.RESULT):
            return
        gen = self._dismiss_gen  # capture current generation before any mutation
        self._label.setStringValue_(text)
        self._sublabel.setStringValue_("已复制到剪贴板")
        # RST-04: auto-dismiss after 3 seconds; gen guard makes stale callbacks no-ops
        callLater(3.0, lambda: self._auto_dismiss(gen))

    def hide_after_paste(self) -> None:
        """Called on main thread after successful paste (RST-01).

        Force-hides from any active state — bypasses transition guard because paste
        success is unambiguous and the TRANSCRIBING -> HIDDEN path skips RESULT entirely.
        """
        if self._state in (OverlayState.RECORDING, OverlayState.TRANSCRIBING, OverlayState.RESULT):
            self._state = OverlayState.HIDDEN
            self._dismiss_gen += 1  # cancel any pending auto-dismiss
            self._panel.orderOut_(None)
            # TODO Phase 3: replace with NSAnimationContext 200ms fade-out (paste)
            self._panel.setAlphaValue_(0.0)  # reset alpha for next show

    def _auto_dismiss(self, gen: int) -> None:
        """Fires on main thread via callLater(3.0, ...). Only hides if generation matches.

        If gen != self._dismiss_gen, a newer recording already started — this callback
        is stale and should be ignored. (RST-04 stale-dismiss protection)
        """
        if gen != self._dismiss_gen:
            return  # stale callback — newer transition already happened
        if self._state == OverlayState.RESULT:
            self._state = OverlayState.HIDDEN
            self._panel.orderOut_(None)
            # TODO Phase 3: replace with NSAnimationContext 400ms fade-out (clipboard)
            self._panel.setAlphaValue_(0.0)  # reset alpha for next show


class OverlayPanel:
    """Wrapper around an NSPanel configured for transparent overlay display.

    Extends with OverlayStateMachine and NSVisualEffectView content view.

    Usage:
        overlay = OverlayPanel.create()   # call from main thread
        overlay.show_recording()          # dispatched via dispatch_to_main from worker thread
        overlay.show_result("text")       # dispatched via dispatch_to_main from worker thread
    """

    PANEL_W: int = 280
    PANEL_H: int = 56
    BOTTOM_MARGIN: int = 40

    def __init__(self) -> None:
        self._panel = None   # type: NSPanel | None
        self._label = None   # type: NSTextField | None
        self._sublabel = None  # type: NSTextField | None
        self._state_machine = None  # type: OverlayStateMachine | None

    @classmethod
    def create(cls) -> "OverlayPanel":
        """Create and configure the overlay NSPanel. Call from main thread only.

        Returns OverlayPanel instance. Panel is invisible (alpha=0.0) until show_recording().
        Does NOT call orderFront_() or makeKeyWindow() — panel stays hidden.
        """
        instance = cls()
        instance._build()
        return instance

    def _build(self) -> None:
        screen = NSScreen.mainScreen()
        sf = screen.frame()
        x = (sf.size.width - self.PANEL_W) / 2
        y = float(self.BOTTOM_MARGIN)
        frame = ((x, y), (float(self.PANEL_W), float(self.PANEL_H)))

        # CRITICAL: NSWindowStyleMaskNonactivatingPanel MUST be in the styleMask at
        # initWithContentRect_styleMask_backing_defer_() time. Changing styleMask after
        # init does NOT update the WindowServer tag — the panel will steal focus.
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel

        self._panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            NSBackingStoreBuffered,
            False,  # defer=False: create window buffer immediately
        )

        # Transparency: ALL THREE flags required. Missing any one = solid dark background.
        self._panel.setOpaque_(False)
        self._panel.setBackgroundColor_(NSColor.clearColor())
        self._panel.setHasShadow_(False)

        # Always-on-top: float above normal app windows
        self._panel.setLevel_(NSFloatingWindowLevel)

        # Click-through: mouse events pass to the app beneath
        self._panel.setIgnoresMouseEvents_(True)

        # Visible on all Spaces + survives fullscreen mode
        behavior = (
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        self._panel.setCollectionBehavior_(behavior)

        # Phase 1: fully invisible. show_recording() sets alpha to 1.0 on show.
        # Do NOT call orderFront_() or makeKeyWindow() — that triggers focus evaluation.
        self._panel.setAlphaValue_(0.0)

        # Build content view (NSVisualEffectView + 2 NSTextField labels)
        self._build_content()

        # Instantiate state machine with references to panel and labels
        self._state_machine = OverlayStateMachine(self._panel, self._label, self._sublabel)

        print("[whisperkey] Overlay panel configured (invisible, alpha=0).")

    def _build_content(self) -> None:
        """Create NSVisualEffectView content with two NSTextField labels.

        Called once from _build(). Sets self._label (primary, 14pt white center)
        and self._sublabel (secondary, 10pt lightGray center).
        """
        w, h = float(self.PANEL_W), float(self.PANEL_H)

        # Frosted glass background (HUDWindow = dark material, 13)
        vfx = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        vfx.setMaterial_(NSVisualEffectMaterialHUDWindow)            # 13 — dark frosted glass
        vfx.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow) # 0
        vfx.setState_(NSVisualEffectStateActive)                     # 1

        # Rounded corners via CALayer
        vfx.setWantsLayer_(True)
        vfx.layer().setCornerRadius_(12.0)
        vfx.layer().setMasksToBounds_(True)

        # Primary label: recording "...", transcribing "转录中...", result = transcribed text
        self._label = NSTextField.alloc().initWithFrame_(NSMakeRect(8, 20, w - 16, 22))
        self._label.setEditable_(False)
        self._label.setSelectable_(False)
        self._label.setDrawsBackground_(False)
        self._label.setBezeled_(False)
        self._label.setTextColor_(NSColor.whiteColor())
        self._label.setAlignment_(NSTextAlignmentCenter)
        self._label.setFont_(NSFont.systemFontOfSize_(14.0))
        self._label.setLineBreakMode_(NSLineBreakByTruncatingTail)
        self._label.setStringValue_("")
        vfx.addSubview_(self._label)

        # Secondary label: "已复制到剪贴板" — visible only in clipboard result state
        self._sublabel = NSTextField.alloc().initWithFrame_(NSMakeRect(8, 4, w - 16, 16))
        self._sublabel.setEditable_(False)
        self._sublabel.setSelectable_(False)
        self._sublabel.setDrawsBackground_(False)
        self._sublabel.setBezeled_(False)
        self._sublabel.setTextColor_(NSColor.lightGrayColor())
        self._sublabel.setAlignment_(NSTextAlignmentCenter)
        self._sublabel.setFont_(NSFont.systemFontOfSize_(10.0))
        self._sublabel.setStringValue_("")
        vfx.addSubview_(self._sublabel)

        self._panel.setContentView_(vfx)

    # ------------------------------------------------------------------
    # Delegation pattern: main.py calls overlay.show_recording() etc.
    # These forward to OverlayStateMachine which holds the state logic.
    # ------------------------------------------------------------------

    def show_recording(self) -> None:
        """Transition to RECORDING state. Call via dispatch_to_main() from worker threads."""
        self._state_machine.show_recording()

    def show_transcribing(self) -> None:
        """Transition to TRANSCRIBING state. Call via dispatch_to_main() from worker threads."""
        self._state_machine.show_transcribing()

    def show_result(self, text: str) -> None:
        """Transition to RESULT state and show transcribed text. Call via dispatch_to_main()."""
        self._state_machine.show_result(text)

    def hide_after_paste(self) -> None:
        """Force-hide overlay after paste success. Call via dispatch_to_main() from worker threads."""
        self._state_machine.hide_after_paste()
