# Phase 2: State Machine & Thread Wiring - Research

**Researched:** 2026-03-09
**Domain:** PyObjC state machine, macOS Accessibility API (AXUIElement), NSPanel show/hide, callLater auto-dismiss, paste vs clipboard branch logic
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| RST-01 | Cursor in text field: silent text injection + overlay 200ms fade-out | is_cursor_in_text_field() verified; output.inject() already pastes; callLater(0.2, hide) confirmed |
| RST-02 | Cursor not in text field: overlay shows transcribed text | NSTextField label creation pattern verified in venv |
| RST-03 | Overlay shows "已复制到剪贴板" alongside result text | NSTextField second label verified; pyperclip.copy() confirmed in venv |
| RST-04 | 3-second auto-dismiss with 400ms fade-out | callLater(3.0, ...) confirmed one-shot main-thread timer; generation counter pattern for cancel guard |
| DET-01 | AX API: AXRole matches AXTextField/AXTextArea/AXComboBox/AXSearchField | kAXTextFieldRole, kAXTextAreaRole, kAXComboBoxRole, 'AXSearchField' all verified in venv |
| DET-02 | AX failure/None defaults to clipboard path without crash | All AX errors return False; try/except wrapper confirmed; kAXErrorAPIDisabled handled |
</phase_requirements>

---

## Summary

Phase 2 connects the existing worker threads (pynput keyboard listener, transcription thread) to the overlay via a 4-state machine living entirely on the main thread. The state machine is a pure Python enum with a transition guard dict — no external state machine library needed. All state mutations run on the main thread via `dispatch_to_main()` (already wired in Phase 1), eliminating any need for a threading.Lock on the state itself.

The macOS Accessibility API (`AXUIElementCreateSystemWide` + `AXUIElementCopyAttributeValue`) is thread-safe and can be called from the transcription worker thread. It returns a `(errCode, value)` tuple in PyObjC. The `is_cursor_in_text_field()` function wraps this in a try/except returning False on any failure, satisfying DET-02's safe-degradation requirement. The role constants `kAXTextFieldRole`, `kAXTextAreaRole`, `kAXComboBoxRole` are importable from `ApplicationServices`; `'AXSearchField'` must be a string literal (no importable constant named `kAXSearchFieldRole` — the package exports `kAXSearchFieldSubrole` with the same value `'AXSearchField'`).

For auto-dismiss timers, `PyObjCTools.AppHelper.callLater()` (already used for the SIGINT polling loop) is the right tool: it fires a Python callable on the main thread once after a delay, is non-repeating, and handles `NSAutoreleasePool` internally. Since `callLater` returns no cancellation token, the dismissal guard uses a generation counter: incrementing it on any new state transition makes stale callbacks no-ops.

The overlay panel show/hide mechanism uses `orderFront_(None)` + `setAlphaValue_(1.0)` to show, and `orderOut_(None)` to hide. Phase 3 will replace direct alpha changes with `NSAnimationContext`-based transitions; Phase 2 uses immediate setAlphaValue_ for correctness, leaving animation hooks as clearly-marked TODOs.

**Primary recommendation:** Implement `OverlayStateMachine` as a pure Python class that lives on the main thread; call AX detection on the transcription worker thread immediately before dispatching the result to main; use `callLater` for all deferred hide operations; guard stale dismissals with a generation integer.

---

## Standard Stack

### Core (all already installed in .venv — no new packages)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ApplicationServices` | 12.1 (pyobjc-framework-ApplicationServices) | AXUIElement Accessibility API | Already in venv via pynput transitive dep; provides all AX query functions |
| `PyObjCTools.AppHelper.callLater` | pyobjc-core 12.1 | One-shot deferred main-thread call (auto-dismiss timer) | Already used for SIGINT polling; handles NSAutoreleasePool; non-blocking |
| `PyObjCTools.AppHelper.callAfter` | pyobjc-core 12.1 | Immediate main-thread dispatch (`dispatch_to_main`) | Already wired in Phase 1 overlay.py |
| `AppKit.NSTextField` | 12.1 | Non-editable label for result text display | Verified: editable=False, drawsBackground=False, transparent, unicode OK |
| `AppKit.NSVisualEffectView` | 12.1 | Frosted glass rounded pill content view | Verified: material=HUDWindow (13), blending=BehindWindow, wantsLayer+cornerRadius |
| `enum.Enum` (stdlib) | Python 3.12 | State machine states | No external dep; pure Python; picklable |
| `pyperclip` | already in pyproject.toml | Clipboard copy for clipboard branch | Already used by output.py; `.copy()` confirmed callable |

### pyproject.toml Change Required

`pyobjc-framework-ApplicationServices` is currently in `.venv` as a transitive dep of `pynput`. We will import it directly, so it must be declared explicitly:

```toml
dependencies = [
    ...
    "pyobjc-framework-Cocoa>=10.0",
    "pyobjc-framework-ApplicationServices>=10.0",  # ADD — AX API for DET-01/DET-02
]
```

No `pip install` needed (already present); the pyproject.toml change ensures fresh-env correctness.

### Verified Constants from venv (Python 3.12 + PyObjC 12.1)

| Constant | Value | Import From |
|----------|-------|-------------|
| `kAXFocusedUIElementAttribute` | `'AXFocusedUIElement'` | `ApplicationServices` |
| `kAXRoleAttribute` | `'AXRole'` | `ApplicationServices` |
| `kAXTextFieldRole` | `'AXTextField'` | `ApplicationServices` |
| `kAXTextAreaRole` | `'AXTextArea'` | `ApplicationServices` |
| `kAXComboBoxRole` | `'AXComboBox'` | `ApplicationServices` |
| `kAXSearchFieldSubrole` | `'AXSearchField'` | `ApplicationServices` (use this OR the string literal `'AXSearchField'`) |
| `kAXErrorSuccess` | `0` | `ApplicationServices` |
| `kAXErrorAPIDisabled` | `-25211` | `ApplicationServices` |
| `kAXErrorCannotComplete` | `-25204` | `ApplicationServices` (returned when no focused element in terminal) |
| `NSVisualEffectMaterialHUDWindow` | `13` | `AppKit` |
| `NSVisualEffectBlendingModeBehindWindow` | `0` | `AppKit` |
| `NSVisualEffectStateActive` | `1` | `AppKit` |
| `NSTextAlignmentCenter` | `1` | `AppKit` |
| `NSLineBreakByWordWrapping` | `0` | `AppKit` |
| `NSLineBreakByTruncatingTail` | `4` | `AppKit` |

---

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)

```
whisperkey_mac/
├── main.py         # MODIFY: wire on_record_start/stop to overlay state transitions
├── overlay.py      # MODIFY: add state machine + show_recording/show_transcribing/show_result/hide methods + NSTextField labels
├── ax_detect.py    # CREATE: is_cursor_in_text_field() — isolated AX query module
├── keyboard_listener.py  # NO CHANGE
├── audio.py              # NO CHANGE
├── transcriber.py        # NO CHANGE
├── output.py             # NO CHANGE
└── config.py             # NO CHANGE
pyproject.toml      # MODIFY: add pyobjc-framework-ApplicationServices>=10.0
tests/
├── test_overlay.py       # EXTEND: add state machine transition tests
└── test_ax_detect.py     # CREATE: mock-based AX detection tests
```

### Threading Model (Phase 2)

```
Main Thread (NSApp.run())
  ALL overlay state transitions must execute here
  All _state reads/writes are main-thread-only (no Lock needed)
  callLater callbacks fire here

pynput daemon thread
  _on_press -> dispatch_to_main(overlay.show_recording)
  _on_release -> dispatch_to_main(overlay.show_transcribing)

Transcription worker thread (threading.Thread, daemon=True)
  is_cursor_in_text_field()  [AX API is thread-safe — verified]
  if in_text_field:
      output.inject(text)    [osascript Cmd+V — runs fine off main thread]
      dispatch_to_main(overlay.hide_after_paste)
  else:
      pyperclip.copy(text)
      dispatch_to_main(overlay.show_result, text)
```

### Pattern 1: 4-State Machine with Transition Guards

**What:** Pure Python enum + dict of valid transitions; all methods called on main thread
**When to use:** Any call to `show_recording()`, `show_transcribing()`, `show_result()`, `hide()` from any thread must go through `dispatch_to_main()` first

```python
# Source: pure Python — no library dependency
import enum
import threading

class OverlayState(enum.Enum):
    HIDDEN = "hidden"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    RESULT = "result"

_VALID_TRANSITIONS: dict[OverlayState, set[OverlayState]] = {
    OverlayState.HIDDEN:       {OverlayState.RECORDING},
    OverlayState.RECORDING:    {OverlayState.TRANSCRIBING},
    OverlayState.TRANSCRIBING: {OverlayState.RESULT},
    OverlayState.RESULT:       {OverlayState.HIDDEN},
    # HIDDEN -> HIDDEN is needed for the timer-based auto-dismiss
    # when the panel already hid (e.g. rapid hotkey cancelled the result)
    # Add it explicitly:
}
# Note: also allow RESULT -> HIDDEN explicitly for auto-dismiss path
_VALID_TRANSITIONS[OverlayState.RESULT].add(OverlayState.HIDDEN)

class OverlayStateMachine:
    """All public methods MUST be called on the main thread."""

    def __init__(self) -> None:
        self._state = OverlayState.HIDDEN
        self._dismiss_gen = 0  # increment to cancel stale auto-dismiss callbacks

    def _transition(self, target: OverlayState) -> bool:
        """Attempt a state transition. Returns True if allowed, False if rejected."""
        if target in _VALID_TRANSITIONS.get(self._state, set()):
            self._state = target
            return True
        return False  # invalid transition silently rejected (guard active)

    def show_recording(self) -> None:
        """Called from main thread (dispatched from pynput thread)."""
        if not self._transition(OverlayState.RECORDING):
            return  # reject: mid-transcription press has no effect
        self._dismiss_gen += 1  # invalidate any pending dismiss
        # Phase 2: show panel immediately (Phase 3 adds animation)
        self._panel.setAlphaValue_(1.0)
        self._panel.orderFront_(None)
        # Update content to "recording" placeholder (Phase 3 adds waveform)
        self._label.setStringValue_("...")

    def show_transcribing(self) -> None:
        """Called from main thread (dispatched from pynput thread on key-release)."""
        if not self._transition(OverlayState.TRANSCRIBING):
            return
        self._label.setStringValue_("转录中...")

    def show_result(self, text: str) -> None:
        """Called from main thread (dispatched from transcription thread)."""
        if not self._transition(OverlayState.RESULT):
            return
        gen = self._dismiss_gen
        self._label.setStringValue_(text)
        self._sublabel.setStringValue_("已复制到剪贴板")
        # Auto-dismiss after 3 seconds (RST-04); generation guard prevents stale hide
        from PyObjCTools.AppHelper import callLater
        callLater(3.0, lambda: self._auto_dismiss(gen))

    def hide_after_paste(self) -> None:
        """Called from main thread after successful paste (RST-01)."""
        # Allow TRANSCRIBING->HIDDEN (paste path skips RESULT state)
        # Adjust valid transitions or handle explicitly:
        if self._state in (OverlayState.RECORDING, OverlayState.TRANSCRIBING, OverlayState.RESULT):
            self._state = OverlayState.HIDDEN
            self._dismiss_gen += 1
            self._panel.orderOut_(None)

    def _auto_dismiss(self, gen: int) -> None:
        """Fires on main thread via callLater. Only hides if generation matches."""
        if gen != self._dismiss_gen:
            return  # stale callback — a newer transition already happened
        if self._state == OverlayState.RESULT:
            self._state = OverlayState.HIDDEN
            self._panel.orderOut_(None)
```

**Key design decisions:**
- `_state` is only ever read/written on the main thread — no Lock required
- `_dismiss_gen` increments on every new recording start, making any pending 3s timer a no-op
- `hide_after_paste()` bypasses the TRANSCRIBING→RESULT→HIDDEN chain because paste succeeds without showing result text

### Pattern 2: AX Text Field Detection Module

**What:** Standalone module querying macOS Accessibility API; safe to call from any thread
**When to use:** Called on the transcription worker thread immediately after transcription completes, before dispatching to main thread

```python
# Source: ApplicationServices constants verified in .venv Python 3.12 + PyObjC 12.1
from ApplicationServices import (
    AXUIElementCreateSystemWide,
    AXUIElementCopyAttributeValue,
    kAXFocusedUIElementAttribute,
    kAXRoleAttribute,
    kAXTextFieldRole,   # 'AXTextField'
    kAXTextAreaRole,    # 'AXTextArea'
    kAXComboBoxRole,    # 'AXComboBox'
    kAXErrorSuccess,
)

# kAXSearchFieldRole is NOT importable by that name; use the subrole value directly
_TEXT_INPUT_ROLES: frozenset[str] = frozenset({
    kAXTextFieldRole,
    kAXTextAreaRole,
    kAXComboBoxRole,
    "AXSearchField",   # Same value as kAXSearchFieldSubrole
})

def is_cursor_in_text_field() -> bool:
    """Return True if the currently focused macOS UI element is a text input field.

    Thread-safe: AXUIElement APIs are safe to call from non-main threads.
    Failure safe: any exception or AX error returns False (DET-02 safe-degradation).
    """
    try:
        system_wide = AXUIElementCreateSystemWide()
        err, focused = AXUIElementCopyAttributeValue(
            system_wide, kAXFocusedUIElementAttribute, None
        )
        if err != kAXErrorSuccess or focused is None:
            return False  # no focused element or permission denied
        err2, role = AXUIElementCopyAttributeValue(focused, kAXRoleAttribute, None)
        if err2 != kAXErrorSuccess or role is None:
            return False
        return role in _TEXT_INPUT_ROLES
    except Exception:
        return False  # DET-02: any failure -> clipboard path
```

### Pattern 3: Overlay Content View Setup

**What:** NSVisualEffectView with NSTextField labels as content view of the NSPanel
**When to use:** Called once in `OverlayPanel._build()` — Phase 2 extends Phase 1's `_build()` to add content

```python
# Source: AppKit constants verified in .venv Python 3.12 + PyObjC 12.1
from AppKit import (
    NSVisualEffectView, NSVisualEffectMaterialHUDWindow,
    NSVisualEffectBlendingModeBehindWindow, NSVisualEffectStateActive,
    NSTextField, NSColor, NSFont, NSTextAlignmentCenter,
    NSLineBreakByTruncatingTail, NSMakeRect,
)

def _build_content(self) -> None:
    w, h = float(self.PANEL_W), float(self.PANEL_H)

    # Frosted glass background
    vfx = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
    vfx.setMaterial_(NSVisualEffectMaterialHUDWindow)        # 13 — dark frosted glass
    vfx.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)  # 0
    vfx.setState_(NSVisualEffectStateActive)                 # 1

    # Rounded corners via CALayer (wantsLayer must be True)
    vfx.setWantsLayer_(True)
    vfx.layer().setCornerRadius_(12.0)
    vfx.layer().setMasksToBounds_(True)

    # Primary label: recording state "...", transcribing state "转录中...",
    # result state = transcribed text
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
```

### Pattern 4: Wiring Keyboard Callbacks to Overlay (main.py changes)

**What:** Replace the bare `_start_recording` / `_stop_and_transcribe` callbacks with overlay-aware versions
**When to use:** In `App.run()` after `self._overlay = OverlayPanel.create()`

```python
# In App.run(), after overlay is created:
from whisperkey_mac.overlay import dispatch_to_main

# Wrap existing callbacks to also update overlay state
def _on_record_start_with_overlay() -> None:
    dispatch_to_main(self._overlay.show_recording)
    self._start_recording()

def _on_record_stop_with_overlay() -> None:
    dispatch_to_main(self._overlay.show_transcribing)
    self._stop_and_transcribe()

# Then rebuild HotkeyListener with these wrappers, OR add overlay dispatch
# directly inside the existing _start_recording/_stop_and_transcribe methods.
# SIMPLEST: just add dispatch_to_main calls at the top of those methods.
```

### Pattern 5: Paste vs Clipboard Branch in Transcription Thread

**What:** Call AX detection before dispatching to main, branch accordingly
**When to use:** In `App._transcribe_and_inject()` after successful transcription

```python
# In _transcribe_and_inject(), after text is obtained:
from whisperkey_mac.ax_detect import is_cursor_in_text_field
from whisperkey_mac.overlay import dispatch_to_main
import pyperclip

if is_cursor_in_text_field():
    # RST-01: paste silently, dismiss quickly
    self._output.inject(text)          # copies to clipboard AND pastes
    dispatch_to_main(self._overlay.hide_after_paste)
else:
    # RST-02/03/04: clipboard branch
    pyperclip.copy(text)               # text already in clipboard via inject below
    dispatch_to_main(self._overlay.show_result, text)
    # Note: inject() is NOT called — no paste attempt in clipboard branch
    # User can still Cmd+V manually; text is in clipboard via pyperclip.copy()
```

### Anti-Patterns to Avoid

- **Calling overlay state methods from pynput/transcription threads directly:** Silent crash. Must use `dispatch_to_main()`.
- **Using a threading.Lock on `_state`:** Unnecessary. All state mutations are on main thread via dispatch. A lock would be harmful (potential deadlock if called from within a Cocoa callback chain).
- **Calling `AXUIElement*` from the main thread while AppKit is blocked:** Not required. AX APIs are designed for non-main-thread use. Put `is_cursor_in_text_field()` in the transcription thread where it runs naturally.
- **Using NSTimer directly for auto-dismiss:** Requires an NSObject selector-based callback or a custom NSObject subclass to hold a block. `callLater` is simpler, already tested in this codebase, and sufficient for one-shot timers.
- **Allowing RESULT -> RECORDING transition (rapid hotkey during result):** State machine guard rejects this, preventing overlay corruption. The second hotkey press is silently dropped until RESULT auto-dismisses and returns to HIDDEN.
- **Not invalidating the auto-dismiss timer on rapid key-press:** The generation counter pattern is the reliable solution. Without it, rapid presses can leave the overlay in HIDDEN while a stale dismiss callback tries to act on RESULT state.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Focused element role query | Custom CGEventTap + window focus tracking | `AXUIElementCreateSystemWide` + `AXUIElementCopyAttributeValue` | AX API is the only reliable cross-app mechanism; event tap doesn't tell you which element is focused |
| One-shot deferred main-thread call | `threading.Timer` + custom queue + NSThread | `callLater(delay, fn)` from `PyObjCTools.AppHelper` | Already used; handles NSAutoreleasePool, runs on main thread, no extra overhead |
| Rounded frosted glass background | Custom NSView with `drawRect_` compositing | `NSVisualEffectView` + `wantsLayer` + `CALayer.cornerRadius` | macOS vibrancy handles blur and theme adaptation; `drawRect_` requires Quartz compositing knowledge |
| State machine library | Import `transitions` or `statemachine` package | Python `enum.Enum` + dict | 4 states + linear transitions; zero deps; complete in ~20 lines |

**Key insight:** Every needed capability is already in PyObjC 12.1 + stdlib. No new packages beyond the one `pyproject.toml` declaration.

---

## Common Pitfalls

### Pitfall 1: kAXSearchFieldRole Does Not Exist as an Importable Constant
**What goes wrong:** `from ApplicationServices import kAXSearchFieldRole` raises `ImportError`
**Why it happens:** The ApplicationServices PyObjC bindings export `kAXSearchFieldSubrole` (value `'AXSearchField'`), not a separate `kAXSearchFieldRole`
**How to avoid:** Use `kAXSearchFieldSubrole` imported by that name, or simply use the string literal `'AXSearchField'` directly in the frozenset
**Warning signs:** ImportError at module load time for `kAXSearchFieldRole`

### Pitfall 2: AX API Requires Accessibility Permission — Returns -25211 If Denied
**What goes wrong:** `is_cursor_in_text_field()` always returns False even when a text field is focused
**Why it happens:** macOS requires the app to have Accessibility permission (System Settings → Privacy & Security → Accessibility). Unsigned / non-bundle CLI apps must be granted manually. If denied, `AXUIElementCopyAttributeValue` returns `kAXErrorAPIDisabled` (-25211).
**How to avoid:** DET-02 already handles this (any non-success error -> False -> clipboard path). For first run, document that user must grant Accessibility permission. Add a first-run check or print a hint if `kAXErrorAPIDisabled` is returned.
**Warning signs:** All transcriptions go to clipboard branch regardless of where cursor is

### Pitfall 3: AXUIElementCopyAttributeValue Third Argument Must Be None
**What goes wrong:** `TypeError` or wrong result if the third argument is omitted or wrong
**Why it happens:** The C API's third argument is an out-parameter (`CFTypeRef *value`); PyObjC bridges this as a three-argument function where the third arg is `None` (it's replaced by the return tuple's second element)
**How to avoid:** Always call as `AXUIElementCopyAttributeValue(element, attribute, None)` and unpack as `err, value = ...`
**Warning signs:** `TypeError: AXUIElementCopyAttributeValue() takes exactly 3 arguments`

### Pitfall 4: Stale Auto-Dismiss Fires After Rapid Key-Press
**What goes wrong:** User presses hotkey again while the 3-second result timer is running; overlay hides after new recording starts, leaving the new recording invisible
**Why it happens:** `callLater(3.0, fn)` has no built-in cancellation. The callback fires regardless of current state.
**How to avoid:** Generation counter: capture `gen = self._dismiss_gen` before scheduling; increment `_dismiss_gen` on every `show_recording()`; the callback checks `gen != self._dismiss_gen` and returns early if stale
**Warning signs:** Overlay disappears unexpectedly 3 seconds into a new recording

### Pitfall 5: orderFront_ Called on Panel While Still Alpha=0
**What goes wrong:** Panel appears opaque on some macOS versions (compositor catches up at wrong time)
**Why it happens:** Race between `orderFront_()` and `setAlphaValue_(1.0)` in some compositor states
**How to avoid:** Always call `setAlphaValue_(1.0)` BEFORE `orderFront_(None)`. Phase 3 will use `NSAnimationContext` which handles this correctly.
**Warning signs:** Panel flashes as solid black rectangle for one frame on show

### Pitfall 6: State Machine Accessed from Non-Main Thread
**What goes wrong:** Silent crash or corrupted `_state` value
**Why it happens:** `OverlayPanel` methods call AppKit directly; AppKit is not thread-safe
**How to avoid:** Every pynput callback and transcription-thread action that touches the overlay must go through `dispatch_to_main()`. Never call `overlay.show_*()` or `overlay.hide()` directly from a non-main thread.
**Warning signs:** Sporadic crash logs in Console.app, `NSInternalInconsistencyException: NSWindow drag regions should only be invalidated on the Main Thread!`

### Pitfall 7: Paste Branch Calling inject() AND pyperclip.copy() Duplicates Clipboard Write
**What goes wrong:** No functional bug, but two clipboard writes of the same text in the paste branch is unnecessary noise
**Why it happens:** `output.inject()` already calls `pyperclip.copy(text)` internally
**How to avoid:** In the paste branch, call `self._output.inject(text)` only — do NOT call `pyperclip.copy(text)` additionally. In the clipboard branch, call `pyperclip.copy(text)` only — do NOT call `self._output.inject(text)` (no paste attempt).

---

## Code Examples

Verified patterns from direct venv inspection:

### Complete is_cursor_in_text_field() Implementation

```python
# Source: ApplicationServices constants verified in .venv (Python 3.12, PyObjC 12.1)
# Thread-safe: AX API is designed for non-main-thread use (verified with threading.Thread test)
from ApplicationServices import (
    AXUIElementCreateSystemWide,
    AXUIElementCopyAttributeValue,
    kAXFocusedUIElementAttribute,  # 'AXFocusedUIElement'
    kAXRoleAttribute,              # 'AXRole'
    kAXTextFieldRole,              # 'AXTextField'
    kAXTextAreaRole,               # 'AXTextArea'
    kAXComboBoxRole,               # 'AXComboBox'
    kAXErrorSuccess,               # 0
)

_TEXT_INPUT_ROLES: frozenset[str] = frozenset({
    kAXTextFieldRole,
    kAXTextAreaRole,
    kAXComboBoxRole,
    "AXSearchField",  # kAXSearchFieldRole doesn't exist; kAXSearchFieldSubrole == 'AXSearchField'
})

def is_cursor_in_text_field() -> bool:
    try:
        system_wide = AXUIElementCreateSystemWide()
        err, focused = AXUIElementCopyAttributeValue(
            system_wide, kAXFocusedUIElementAttribute, None
        )
        if err != kAXErrorSuccess or focused is None:
            return False
        err2, role = AXUIElementCopyAttributeValue(focused, kAXRoleAttribute, None)
        if err2 != kAXErrorSuccess or role is None:
            return False
        return role in _TEXT_INPUT_ROLES
    except Exception:
        return False
```

### Generation Counter for Stale Dismiss Guard

```python
# Source: pure Python — generation counter pattern
# self._dismiss_gen: int — incremented on every new recording start

def show_recording(self) -> None:
    if not self._transition(OverlayState.RECORDING):
        return
    self._dismiss_gen += 1   # all pending 3s timers from previous result become stale
    self._panel.setAlphaValue_(1.0)
    self._panel.orderFront_(None)
    self._label.setStringValue_("...")
    self._sublabel.setStringValue_("")

def show_result(self, text: str) -> None:
    if not self._transition(OverlayState.RESULT):
        return
    gen = self._dismiss_gen  # capture current generation
    self._label.setStringValue_(text)
    self._sublabel.setStringValue_("已复制到剪贴板")
    from PyObjCTools.AppHelper import callLater
    callLater(3.0, lambda: self._auto_dismiss(gen))

def _auto_dismiss(self, gen: int) -> None:
    if gen != self._dismiss_gen:
        return  # stale — a newer recording already started
    if self._state == OverlayState.RESULT:
        self._state = OverlayState.HIDDEN
        self._panel.orderOut_(None)
```

### NSPanel Show/Hide (Phase 2 — no animation yet)

```python
# Source: AppKit orderFront_/orderOut_ verified in .venv Python 3.12 + PyObjC 12.1
# Phase 3 replaces these with NSAnimationContext-based transitions

def _show(self) -> None:
    # CRITICAL: set alpha BEFORE orderFront_ to avoid compositor race
    self._panel.setAlphaValue_(1.0)
    self._panel.orderFront_(None)

def _hide(self) -> None:
    self._panel.orderOut_(None)
    self._panel.setAlphaValue_(0.0)  # reset for next show (Phase 3 will animate)
```

---

## State of the Art

| Old Approach | Current Approach (Phase 2) | Notes |
|--------------|---------------------------|-------|
| No overlay state machine | 4-state enum + transition guard dict | Pure Python; no library needed |
| Bare `_start_recording` / `_stop_and_transcribe` callbacks | Callbacks dispatch to overlay state transitions via `dispatch_to_main()` | Non-breaking addition |
| `output.inject()` always pastes | Branch: AX detection -> paste or clipboard based on focus | DET-01/02 requirement |
| No UI feedback for transcription result | Overlay shows result text + "已复制到剪贴板" in clipboard branch | RST-02/03 |
| No auto-dismiss | `callLater(3.0, fn)` with generation guard | RST-04 |

**Phase 3 will replace:**
- `setAlphaValue_(1.0)` / `orderFront_` → `NSAnimationContext` 150ms fade-in + 8pt slide
- `orderOut_` → `NSAnimationContext` 200ms/400ms fade-out
- Static `"..."` label → animated waveform bars (NSBezierPath + NSTimer 30fps)
- Static `"转录中..."` label → pulsing dots (300ms/dot)

Phase 2 uses immediate show/hide intentionally: correct behavior is more important than polish, and animation is layered on top in Phase 3 without requiring Phase 2 code changes.

---

## Open Questions

1. **Accessibility permission first-run UX**
   - What we know: If AX permission is not granted, `kAXErrorAPIDisabled` is returned; `is_cursor_in_text_field()` returns False; all transcriptions go to clipboard path. This is correct behavior per DET-02.
   - What's unclear: Whether to proactively request permission on first run (macOS shows a permission dialog if the app calls `AXIsProcessTrustedWithOptions` with `kAXTrustedCheckOptionPrompt=True`).
   - Recommendation: Phase 2 does NOT add permission prompting — silent degradation to clipboard is acceptable per spec. Phase 4 (hardening) can add a first-run hint if desired.

2. **hide_after_paste transition path**
   - What we know: The paste branch goes RECORDING → TRANSCRIBING → [paste happens] → HIDDEN, skipping RESULT entirely. This means TRANSCRIBING → HIDDEN is needed but not in the original 4-state linear chain.
   - What's unclear: Whether to add TRANSCRIBING → HIDDEN as a valid transition, or treat hide_after_paste as a "force-hide" that bypasses the guard.
   - Recommendation: `hide_after_paste()` should bypass the guard entirely (just check `_state != HIDDEN` and force to HIDDEN), because paste success is unambiguous and there is no invalid-state risk.

3. **Overlay content for RECORDING state (Phase 2 vs Phase 3)**
   - What we know: Phase 2 shows a static `"..."` label during recording. Phase 3 replaces this with animated waveform bars.
   - What's unclear: Whether showing ANY text in the recording state (even `"..."`) matches the spec's intent before Phase 3 animation lands.
   - Recommendation: Use `"..."` as a placeholder in Phase 2. The overlay being visible with any content is better than appearing blank. The label disappears when Phase 3 replaces content drawing.

---

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` — section included.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 (already installed) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements — Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RST-01 | State machine: TRANSCRIBING → HIDDEN via hide_after_paste() when in text field | Unit | `pytest tests/test_overlay.py::test_hide_after_paste -x` | Wave 0 |
| RST-02 | State machine: TRANSCRIBING → RESULT on show_result(); label shows transcribed text | Unit | `pytest tests/test_overlay.py::test_show_result_sets_label -x` | Wave 0 |
| RST-03 | State machine: show_result() sets sublabel to "已复制到剪贴板" | Unit | `pytest tests/test_overlay.py::test_show_result_clipboard_hint -x` | Wave 0 |
| RST-04 | State machine: RESULT → HIDDEN on _auto_dismiss() with matching generation | Unit | `pytest tests/test_overlay.py::test_auto_dismiss_fires -x` | Wave 0 |
| RST-04 | Generation guard: stale _auto_dismiss() does NOT hide from RESULT state | Unit | `pytest tests/test_overlay.py::test_auto_dismiss_stale_ignored -x` | Wave 0 |
| DET-01 | is_cursor_in_text_field() returns True for AXTextField/AXTextArea/AXComboBox/AXSearchField roles | Unit (mocked) | `pytest tests/test_ax_detect.py::test_text_input_roles -x` | Wave 0 |
| DET-01 | is_cursor_in_text_field() returns False for AXButton, AXWindow roles | Unit (mocked) | `pytest tests/test_ax_detect.py::test_non_text_roles -x` | Wave 0 |
| DET-02 | is_cursor_in_text_field() returns False when AX returns error code | Unit (mocked) | `pytest tests/test_ax_detect.py::test_ax_error_returns_false -x` | Wave 0 |
| DET-02 | is_cursor_in_text_field() returns False when AX raises exception | Unit (mocked) | `pytest tests/test_ax_detect.py::test_ax_exception_returns_false -x` | Wave 0 |
| State guard | RECORDING transition rejected when state is TRANSCRIBING (rapid press) | Unit | `pytest tests/test_overlay.py::test_transition_guard_rejects_invalid -x` | Wave 0 |

**Manual smoke tests (not automatable):**
- Press hotkey → overlay appears; release → "转录中..." visible; result → clipboard text + "已复制到剪贴板" shows; auto-dismisses after 3s
- Press hotkey with cursor in TextEdit → transcription completes → text pasted silently, overlay hides
- Press hotkey, release, press again before transcription completes → second press has no visible effect on overlay

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q` (runs existing 6 tests + new Phase 2 tests)
- **Per wave merge:** `pytest tests/ -v` + manual smoke test checklist
- **Phase gate:** All 6 original + all new Phase 2 unit tests green + manual smoke passes before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_overlay.py` — extend with state machine tests (RST-01 through RST-04, state guard)
- [ ] `tests/test_ax_detect.py` — CREATE: mock-based unit tests for `ax_detect.is_cursor_in_text_field()` (DET-01, DET-02)

All new tests use `unittest.mock.patch` to replace AX API calls — no real Accessibility permission needed in CI.

*(Existing infrastructure — conftest.py, NSApplication setup, pytest config — already covers Phase 2 needs; no new fixtures required.)*

---

## Sources

### Primary (HIGH confidence — verified in project .venv)

- `.venv/lib/python3.12/site-packages/ApplicationServices/__init__.py` — `AXUIElementCreateSystemWide`, `AXUIElementCopyAttributeValue`, all kAX constants verified by Python REPL
- Python REPL in `.venv` — `AXUIElementCopyAttributeValue` returns `(int, value_or_None)` tuple confirmed
- Python REPL in `.venv` — `kAXTextFieldRole='AXTextField'`, `kAXTextAreaRole='AXTextArea'`, `kAXComboBoxRole='AXComboBox'`, `kAXSearchFieldSubrole='AXSearchField'` verified
- Python REPL in `.venv` — `kAXErrorSuccess=0`, `kAXErrorAPIDisabled=-25211`, `kAXErrorCannotComplete=-25204` verified
- Python REPL in `.venv` — Thread-safety of AX API confirmed: called from `threading.Thread` worker, no crash
- Python REPL in `.venv` — `NSVisualEffectMaterialHUDWindow=13`, `NSVisualEffectBlendingModeBehindWindow=0`, `NSVisualEffectStateActive=1` verified
- Python REPL in `.venv` — `NSTextField` label creation verified: unicode text, editable=False, transparent background
- Python REPL in `.venv` — `CALayer.setCornerRadius_(12.0)` + `setMasksToBounds_(True)` on NSVisualEffectView confirmed
- Python REPL in `.venv` — `orderFront_(None)` + `orderOut_(None)` panel show/hide confirmed
- `.venv/lib/python3.12/site-packages/PyObjCTools/AppHelper.py` — `callLater` source read: `performSelector_withObject_afterDelay_` — one-shot, non-repeating, main-thread delivery
- `tests/` — existing 6 tests pass green (`pytest tests/ -v` confirmed 2026-03-09)

### Secondary (MEDIUM confidence)

- [PyObjC GitHub: pyobjc-framework-ApplicationServices](https://github.com/ronaldoussoren/pyobjc) — AX framework bindings confirmed available
- [Apple Accessibility API docs](https://developer.apple.com/documentation/applicationservices/axuielement_h) — `AXUIElementCreateSystemWide`, `AXUIElementCopyAttributeValue` function signatures

### Tertiary (LOW confidence — informational only)

- [macdevelopers.wordpress.com: AXUIElement text value access](https://macdevelopers.wordpress.com/2014/01/31/accessing-text-value-from-any-system-wide-application-via-accessibility-api/) — confirms general pattern; outdated but pattern is stable

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all constants and APIs verified by running Python REPL in .venv
- State machine architecture: HIGH — pure Python; no framework dependency; pattern is standard
- AX detection: HIGH — call pattern verified in venv; tuple return confirmed; thread-safety confirmed
- Auto-dismiss timer: HIGH — callLater source read directly from .venv; behavior understood completely
- Pitfalls: HIGH — kAXSearchFieldRole ImportError confirmed by attempted import in venv; AX permission error code verified

**Research date:** 2026-03-09
**Valid until:** 2026-09-09 (AppKit/AX APIs are stable; PyObjC 12.x built against macOS 26.1 SDK; no breaking changes expected in 6 months)
