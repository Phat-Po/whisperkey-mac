"""Overlay NSPanel module for WhisperKey macOS.

Provides:
- OverlayPanel: creates and configures an always-on-top, transparent, click-through NSPanel
  positioned at bottom-center of the main screen. Panel stays invisible (alpha=0.0) until
  Phase 3 animates it into view.
- dispatch_to_main(): thread-safe utility that queues any callable onto the main run loop.
  Safe to call from background threads. Non-blocking.

IMPORTANT: OverlayPanel.create() must be called from the main thread (after NSApp is running).
"""
from AppKit import (
    NSPanel,
    NSScreen,
    NSColor,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
    NSBackingStoreBuffered,
    NSFloatingWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
)
from PyObjCTools.AppHelper import callAfter


def dispatch_to_main(fn, *args) -> None:
    """Queue fn(*args) on the main run loop. Safe to call from any thread.

    Non-blocking: caller continues immediately.
    Uses PyObjCTools.AppHelper.callAfter which handles NSAutoreleasePool
    and exception safety correctly.
    """
    callAfter(fn, *args)


class OverlayPanel:
    """Wrapper around an NSPanel configured for transparent overlay display.

    Usage:
        overlay = OverlayPanel.create()   # call from main thread
        # overlay._panel is the underlying NSPanel
        # Phase 3 will call overlay._panel.setAlphaValue_(1.0) to show it
    """

    PANEL_W: int = 280
    PANEL_H: int = 56
    BOTTOM_MARGIN: int = 40

    def __init__(self) -> None:
        self._panel = None  # type: NSPanel | None

    @classmethod
    def create(cls) -> "OverlayPanel":
        """Create and configure the overlay NSPanel. Call from main thread only.

        Returns OverlayPanel instance. Panel is invisible (alpha=0.0) until Phase 3.
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

        # Phase 1: fully invisible. Phase 3 animates alphaValue to 1.0 on show.
        # Do NOT call orderFront_() or makeKeyWindow() — that triggers focus evaluation.
        self._panel.setAlphaValue_(0.0)

        print("[whisperkey] Overlay panel configured (invisible, alpha=0).")
