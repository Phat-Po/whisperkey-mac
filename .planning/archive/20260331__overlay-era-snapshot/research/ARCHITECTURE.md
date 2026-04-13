# Architecture Research: macOS Overlay Integration

## Threading Model

```
Main Thread (NSApplication.run())
  └── RecordingOverlay (NSPanel) — all UI updates here

Worker Threads (launched before NSApp.run())
  ├── pynput listener → detects hotkey → dispatch_to_main(overlay.show_recording)
  ├── audio.py → records audio → dispatch_to_main(overlay.show_transcribing)
  └── transcriber.py → runs Whisper → dispatch_to_main(overlay.show_result / hide)
```

**Key change:** Replace `stop_event.wait()` in `App.run()` with `NSApplication.sharedApplication().run()`. All worker threads launch before `NSApp.run()` and continue independently.

## Cross-Thread UI Dispatch

Use PyObjC native method (no extra dependency):

```python
def dispatch_to_main(fn, *args):
    # Safe to call from any thread
    obj.performSelectorOnMainThread_withObject_waitUntilDone_(
        selector, args, False  # waitUntilDone=False to avoid deadlock
    )
```

Alternatively, use `NSObject.performSelectorOnMainThread_withObject_waitUntilDone_` pattern directly on the overlay controller object.

## Window Type

| Property | Value | Reason |
|----------|-------|--------|
| Window class | `NSPanel` | Floats above normal windows, no Dock entry |
| Style mask | `NSWindowStyleMaskBorderless` | No title bar, no controls |
| Window level | `NSFloatingWindowLevel` | Always on top |
| `setIgnoresMouseEvents_(True)` | Yes | Click-through, never steals focus |
| `setCollectionBehavior_` | `NSWindowCollectionBehaviorCanJoinAllSpaces` | Visible on all Spaces |
| Activation policy | `NSApplicationActivationPolicyAccessory` | No Dock icon, no App Switcher |

## Text Input Field Detection

Use macOS Accessibility API from the worker thread (safe), then dispatch UI decision to main thread:

```python
from ApplicationServices import (
    AXUIElementCreateSystemWide,
    AXUIElementCopyAttributeValue,
    kAXFocusedUIElementAttribute,
    kAXRoleAttribute,
)

TEXT_ROLES = {"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"}

def is_cursor_in_text_field() -> bool:
    system = AXUIElementCreateSystemWide()
    err, focused = AXUIElementCopyAttributeValue(system, kAXFocusedUIElementAttribute, None)
    if err or not focused:
        return False
    err, role = AXUIElementCopyAttributeValue(focused, kAXRoleAttribute, None)
    return not err and role in TEXT_ROLES
```

**Requirement:** App must have Accessibility permission (already required by existing `output.py`).

## Build Order

1. **NSApp loop scaffolding** — replace `stop_event.wait()` with `NSApp.run()`; verify existing threads still work
2. **Basic NSPanel** — visible window, click-through, all Spaces, correct level
3. **`dispatch_to_main()` utility + thread wiring** — connect keyboard_listener → overlay state changes
4. **Accessibility detection** — `is_cursor_in_text_field()` + branch logic
5. **Visual polish** — waveform animation, fade in/out, transcription text display
6. **Edge cases** — rapid keypresses, hands-free state transitions

## Integration Point in Existing Code

```
whisperkey_mac/
├── main.py          ← Add NSApp.run(), instantiate OverlayController
├── keyboard_listener.py  ← dispatch_to_main(overlay.show_recording / hide)
├── transcriber.py   ← dispatch_to_main(overlay.show_transcribing)
├── output.py        ← returns "pasted" | "clipboard" → dispatch result to overlay
└── overlay.py       ← NEW: NSPanel, animations, state machine (recording/transcribing/result/hidden)
```

---
*Research date: 2026-03-09 | Confidence: HIGH — AppKit/PyObjC threading model and AXUIElement API are stable, unchanged for many years.*
