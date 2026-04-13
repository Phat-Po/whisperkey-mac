# Stack Research: macOS Overlay UI for WhisperKey

## Bottom Line

**Zero new dependencies required.** PyObjC 12.1 is already installed in `.venv/`. The correct stack is `NSPanel + NSView + NSTimer + PyObjCTools.AppHelper`.

## Installed PyObjC Packages (confirmed from .venv)

| Package | Version | Provides |
|---------|---------|----------|
| `pyobjc-core` | 12.1 | PyObjC bridge runtime |
| `pyobjc-framework-Cocoa` | 12.1 | AppKit, Foundation, Cocoa |
| `pyobjc-framework-Quartz` | 12.1 | Quartz/CoreGraphics |
| `pyobjc-framework-CoreText` | 12.1 | Text rendering |
| `pyobjc-framework-ApplicationServices` | 12.1 | AXUIElement (Accessibility API) |

Built against macOS 26.1 SDK.

## Recommended Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Overlay window | `AppKit.NSPanel` | Subclass of NSWindow; supports borderless, transparent, always-on-top, ignoresMouseEvents |
| Drawing | `NSView.drawRect_` + `NSBezierPath` | Native, smooth — no additional dependency |
| Animation timer | `NSTimer` (30fps repeating) | Must use NSTimer (not threading.Timer) to fire on main run loop |
| Cross-thread dispatch | `PyObjCTools.AppHelper.callAfter(fn)` | The correct PyObjC way to dispatch to main thread from worker threads |
| Text display | `NSTextField` + `NSAttributedString` | Native macOS text rendering |
| Fade animation | `NSAnimationContext` + `animator().alphaValue` | Smooth Core Animation-backed fade |
| App loop | `NSApplication.sharedApplication().run()` | **Replaces existing `stop_event.wait()`** |
| Shutdown | `AppHelper.stopEventLoop()` | Clean exit from NSApp run loop |

## Critical Architectural Change

The existing `main.py` blocks on `stop_event.wait()`. This **must** be replaced with `NSApplication.sharedApplication().run()` to spin the AppKit main run loop. All background work (keyboard listener, audio, transcription) stays on daemon threads launched before `NSApp.run()`.

```python
# BEFORE (current main.py)
stop_event.wait()

# AFTER
from AppKit import NSApplication
from PyObjCTools import AppHelper
NSApp = NSApplication.sharedApplication()
NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
# ... start all daemon threads here ...
AppHelper.runEventLoop()  # blocks until stopEventLoop() called
```

## What NOT to Use

| Option | Reason to avoid |
|--------|----------------|
| `tkinter` | Transparent/always-on-top broken on macOS 12+ |
| `rumps` | Menu bar only, no custom windows |
| `PyQt6` / `PySide6` | Adds ~50MB dependency, event loop conflict with pynput |
| `pygame` | Designed for games, terrible for system overlay UI |
| Second process with IPC | Unnecessary complexity — PyObjC handles this natively |

---
*Research date: 2026-03-09 | Confidence: HIGH — confirmed from installed .venv packages, not training data*
