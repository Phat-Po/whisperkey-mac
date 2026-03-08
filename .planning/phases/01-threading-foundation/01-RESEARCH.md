# Phase 1: Threading Foundation - Research

**Researched:** 2026-03-09
**Domain:** PyObjC / AppKit run loop, NSPanel overlay window, cross-thread dispatch, signal handling
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Add `pyobjc-framework-Cocoa>=10.0` to `[project.dependencies]` in pyproject.toml (minimal install, not the full meta-package)
- After Phase 1 lands, run `pip install -e .` once to pick up the new dep
- Overlay size: compact pill, ~280x56px
- Bottom margin: ~40px from the bottom of the screen; horizontal: centered on screen
- Phase 1 scope: position the NSPanel at final bottom-center coordinates but set alpha=0 (fully transparent, invisible). Phase 3 animates alpha.
- SIGINT (Ctrl+C) must still work — wire to NSApp.terminate() via signal handler
- SIGTERM must also quit cleanly (needed for LaunchAgent and pkill)
- Terminal shutdown message must remain: `[whisperkey] shutting down (SIGINT)` — keep existing format

### Claude's Discretion
- Exact mechanism for wiring SIGINT/SIGTERM to NSApp.terminate() (signal handler vs MachSignals vs NSRunLoop timer)
- Whether to use `NSApp.run()` directly or `AppHelper.runEventLoop()` — choose whichever avoids the pynput + NSRunLoop event tap conflict
- dispatch_to_main() implementation details (performSelectorOnMainThread vs NSRunLoop.mainRunLoop().performBlock_ vs AppHelper.callAfter)
- NSPanel subclass vs standalone instance inside overlay.py

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| OVL-01 | NSPanel window exists: borderless, transparent, always-on-top, click-through | NSPanel API verified in venv; all flags confirmed importable at correct values |
| OVL-02 | Overlay appears without stealing keyboard focus from active app | NSApplicationActivationPolicyAccessory + NSNonactivatingPanelMask combination confirmed; must be set before NSApp.run() |
| OVL-03 | Overlay visible on all Spaces (Mission Control switching does not hide it) | NSWindowCollectionBehaviorCanJoinAllSpaces confirmed; value=1; additional flags for fullscreen apps identified |
</phase_requirements>

---

## Summary

Phase 1 replaces the existing `stop_event.wait()` blocking loop in `main.py` with `NSApp.run()`, creating a Cocoa run loop that all future UI work depends on. Simultaneously it creates `overlay.py` with an invisible NSPanel correctly configured for overlay use. All existing daemon threads (pynput, audio, transcription) survive the architectural change without modification.

The critical technical risk — pynput conflicting with NSApp's run loop — was resolved by reading pynput's actual source code. pynput creates its own `CFRunLoop` per listener thread using `CFRunLoopGetCurrent()` and `CFRunLoopRunInMode()`. It does NOT share or conflict with the main NSRunLoop that `NSApp.run()` manages. The two run loops operate independently on different threads. The known conflict pattern (TIS/TSM "not on main thread" warning) only triggers when pynput's listener is started from a non-main thread AND something also tries to call TIS on the main thread at the same time — not a problem in this architecture where pynput starts before NSApp.run() and callbacks run on pynput's daemon thread.

For signal handling, `PyObjCTools.MachSignals` delivers SIGINT reliably inside a Cocoa run loop via Mach port messages, which is the correct mechanism when `NSApp.run()` is active (plain Python `signal.signal()` handlers are not guaranteed to fire while blocked in C code). The shutdown message format is preserved by wrapping `NSApp.terminate_()` in our own handler.

**Primary recommendation:** Replace `stop_event.wait()` with `NSApplication.sharedApplication().run()` (not `AppHelper.runEventLoop()`, which calls `NSApplicationMain()` — incorrect for bundle-less scripts). Handle SIGINT/SIGTERM via `MachSignals.signal()` to call `NSApp().terminate_(None)`. Create `overlay.py` with an NSPanel instance configured with all required flags set at construction time.

---

## Standard Stack

### Core (confirmed in .venv — already installed, no new install needed for Phase 1)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pyobjc-framework-Cocoa` | 12.1 | AppKit + Foundation bindings | Already in venv; provides NSPanel, NSApp, NSRunLoop, NSScreen |
| `pyobjc-core` | 12.1 | PyObjC bridge runtime | Required by all PyObjC framework packages |
| `pyobjc-framework-Quartz` | 12.1 | CGEventTap (used by pynput internally) | Already in venv |
| `pynput` | 1.8.1 | Keyboard hotkey listener | Existing dep; daemon thread; per-thread CFRunLoop |
| `PyObjCTools.AppHelper` | (part of pyobjc-core 12.1) | `callAfter()` dispatch-to-main | Built-in; avoids reinventing cross-thread dispatch |
| `PyObjCTools.MachSignals` | (part of pyobjc-core 12.1) | SIGINT/SIGTERM inside run loop | The correct way to handle signals in a Cocoa run loop |

### pyproject.toml Change Required

```toml
dependencies = [
    ...
    "pyobjc-framework-Cocoa>=10.0",   # ADD THIS — already installed but not declared
]
```

Note: `pyobjc-framework-Cocoa` is already present in `.venv` at version 12.1. The pyproject.toml update makes the dependency explicit so `pip install -e .` installs it correctly in fresh environments.

**Installation (after editing pyproject.toml):**
```bash
pip install -e .
```

### Verified Constants (from .venv Python 3.12 + PyObjC 12.1)

| Constant | Value | Import From |
|----------|-------|-------------|
| `NSWindowStyleMaskBorderless` | 0 | `AppKit` |
| `NSWindowStyleMaskNonactivatingPanel` | 128 | `AppKit` |
| `NSNonactivatingPanelMask` | 128 | `AppKit` (alias) |
| `NSBackingStoreBuffered` | 2 | `AppKit` |
| `NSFloatingWindowLevel` | 3 | `AppKit` |
| `NSStatusWindowLevel` | 25 | `AppKit` |
| `NSWindowCollectionBehaviorCanJoinAllSpaces` | 1 | `AppKit` |
| `NSWindowCollectionBehaviorStationary` | 16 | `AppKit` |
| `NSWindowCollectionBehaviorFullScreenAuxiliary` | 256 | `AppKit` |
| `NSApplicationActivationPolicyAccessory` | 1 | `AppKit` |

---

## Architecture Patterns

### Recommended Project Structure (Phase 1 additions)

```
whisperkey_mac/
├── main.py         # MODIFY: replace stop_event.wait() with NSApp.run(); add overlay init
├── overlay.py      # CREATE: NSPanel subclass + dispatch_to_main() utility
├── keyboard_listener.py  # NO CHANGE — already daemon thread
├── audio.py        # NO CHANGE
├── transcriber.py  # NO CHANGE
└── output.py       # NO CHANGE
pyproject.toml      # MODIFY: add pyobjc-framework-Cocoa>=10.0 to dependencies
```

### Threading Model

```
Main Thread (NSApp.run() — blocks here)
  └── All AppKit/NSPanel calls must land here via dispatch_to_main()

Worker Threads (launched before NSApp.run())
  ├── pynput daemon thread — CFRunLoopRunInMode() loop (INDEPENDENT, no conflict)
  ├── audio daemon thread — sounddevice callbacks
  └── transcription daemon thread — faster-whisper
```

### Pattern 1: NSApp Run Loop Replacement

**What:** Replace `stop_event.wait()` with `NSApplication.sharedApplication().run()`
**When to use:** Any PyObjC app that needs AppKit timers, windows, animations
**Critical ordering:** Set activation policy BEFORE `.run()` starts. Wire signals BEFORE calling `.run()`.

```python
# Source: PyObjCTools/AppHelper.py (read from .venv) + Apple AppKit docs
import signal
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
)
from PyObjCTools import MachSignals

def run(self) -> None:
    # ... existing startup prints ...

    # Set up NSApp BEFORE run loop starts
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    # Wire SIGINT/SIGTERM/SIGHUP to clean shutdown via Mach port
    # (MachSignals delivers reliably inside NSApp.run(), unlike Python signal module)
    sig_name_holder: list[str] = []

    def _mach_quit(signum: int) -> None:
        import signal as _signal
        sig_name_holder.append(_signal.Signals(signum).name)
        from AppKit import NSApp as _NSApp
        _NSApp().terminate_(None)

    MachSignals.signal(signal.SIGINT, _mach_quit)
    MachSignals.signal(signal.SIGTERM, _mach_quit)
    MachSignals.signal(signal.SIGHUP, _mach_quit)

    # Start daemon threads (existing code, no change needed)
    self._hotkey.start()

    # Create overlay (Phase 1: invisible, alpha=0)
    from whisperkey_mac.overlay import OverlayPanel
    self._overlay = OverlayPanel.create()

    # Block on NSApp run loop
    app.run()

    # After app.run() returns — print shutdown message
    sig_name = sig_name_holder[0] if sig_name_holder else "?"
    print(f"\n[whisperkey] {_('shutting_down')} ({sig_name})")
    self._hotkey.stop()
    self._recorder.cancel()
```

### Pattern 2: NSPanel Creation

**What:** Create an always-on-top, borderless, transparent, click-through panel visible on all Spaces
**When to use:** Any overlay window that must not steal focus or interfere with other apps

```python
# Source: AppKit constants verified in .venv Python 3.12; NSPanel API from Apple docs
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

class OverlayPanel:
    PANEL_W = 280
    PANEL_H = 56
    BOTTOM_MARGIN = 40

    @classmethod
    def create(cls) -> "OverlayPanel":
        instance = cls()
        instance._build()
        return instance

    def _build(self) -> None:
        screen = NSScreen.mainScreen()
        screen_frame = screen.frame()
        x = (screen_frame.size.width - self.PANEL_W) / 2
        y = self.BOTTOM_MARGIN

        frame = ((x, y), (self.PANEL_W, self.PANEL_H))
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel

        self._panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            NSBackingStoreBuffered,
            False,  # defer=False: create immediately
        )

        # Transparency flags — ALL three required; missing any one causes solid background
        self._panel.setOpaque_(False)
        self._panel.setBackgroundColor_(NSColor.clearColor())
        self._panel.setHasShadow_(False)

        # Always-on-top, floating above normal app windows
        self._panel.setLevel_(NSFloatingWindowLevel)

        # Click-through: mouse events pass to app beneath
        self._panel.setIgnoresMouseEvents_(True)

        # Visible on all Spaces + remains visible in fullscreen apps
        behavior = (
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        self._panel.setCollectionBehavior_(behavior)

        # Phase 1: invisible (alpha=0). Phase 3 animates alpha to 1.0 on show.
        self._panel.setAlphaValue_(0.0)

        # CRITICAL: do NOT call orderFront_() or makeKeyWindow() here — that would
        # trigger focus-steal despite NSNonactivatingPanelMask.
        # The panel is just created and configured; it stays offscreen.
```

### Pattern 3: dispatch_to_main() Utility

**What:** Route any callable from a background thread safely to the main run loop
**When to use:** EVERY AppKit call originating from pynput callbacks, audio callbacks, or transcription thread

```python
# Source: PyObjCTools/AppHelper.py (read from .venv) — callAfter uses
# performSelectorOnMainThread_withObject_waitUntilDone_ internally
from PyObjCTools.AppHelper import callAfter

def dispatch_to_main(fn, *args) -> None:
    """Queue fn(*args) on the main run loop. Safe to call from any thread.
    Non-blocking: caller continues immediately.
    """
    callAfter(fn, *args)
```

`callAfter` is the right choice because:
1. It is already in the installed `pyobjc-core` 12.1 — no new imports
2. It handles `NSAutoreleasePool` creation/teardown correctly
3. It uses `performSelectorOnMainThread_withObject_waitUntilDone_(... waitUntilDone=False)` — async, no deadlock risk
4. PyObjC's version catches exceptions from the target function (unlike raw `performSelectorOnMainThread`)

### Anti-Patterns to Avoid

- **Calling NSPanel/NSView methods from pynput callbacks directly:** Silent crash. Always use `dispatch_to_main()`.
- **Using `AppHelper.runEventLoop()` for bundle-less scripts:** Calls `NSApplicationMain()` which requires an app bundle and Info.plist. Use `NSApplication.sharedApplication().run()` instead.
- **Setting `NSApplicationActivationPolicyAccessory` AFTER `NSApp.run()`:** The Dock icon and focus-steal behavior is already committed by the time the run loop starts. Set it first.
- **Using `NSWindowStyleMaskNonactivatingPanel` on an NSWindow instead of NSPanel:** NSWindow ignores this flag (confirmed in Electron bug tracker issue #35815). Only NSPanel subclasses respect it.
- **Calling `setCollectionBehavior_()` without `NSWindowCollectionBehaviorFullScreenAuxiliary`:** Panel disappears when user enters fullscreen mode.
- **Using Python `signal.signal()` inside `NSApp.run()`:** Python signal handlers are not reliably called while blocked inside C code. Use `MachSignals.signal()` instead.
- **Calling `orderFront_()` on an alpha=0 panel at startup:** Unnecessary and may trigger focus evaluation.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dispatch to main thread | Custom queue + threading.Event + polling | `PyObjCTools.AppHelper.callAfter()` | Already handles NSAutoreleasePool, exception safety, and NSObject messaging protocol |
| Signal handling in run loop | threading.Event + sleep polling | `PyObjCTools.MachSignals.signal()` | Mach port delivery is the only reliable mechanism inside NSApp.run() |
| Transparent window background | Custom compositing, alpha blending | Three-flag combination: `setOpaque_(False)` + `clearColor()` + `setHasShadow_(False)` | All three flags interact; missing any one breaks transparency |

**Key insight:** PyObjC 12.1 in `.venv` already provides all threading and dispatch infrastructure needed. No new packages needed for Phase 1.

---

## Common Pitfalls

### Pitfall 1: Activation Policy Set Too Late
**What goes wrong:** NSApp appears in the Dock and steals focus when `NSApp.run()` starts
**Why it happens:** macOS commits the activation policy during app initialization; changing it after run loop starts has no effect on focus behavior
**How to avoid:** Call `NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)` as the very first NSApp call, before any thread starts or imports trigger AppKit side-effects
**Warning signs:** A Dock icon appears when starting whisperkey; typing in another app is interrupted on startup

### Pitfall 2: AppKit Import Side Effects
**What goes wrong:** `from AppKit import *` at the top of `main.py` can trigger `NSApplication.sharedApplication()` internally before `setActivationPolicy_` is called, locking in the wrong policy
**Why it happens:** Some PyObjC imports initialize NSApp as a side effect
**How to avoid:** Keep AppKit imports inside `overlay.py` only. Import `overlay.py` inside `App.run()` (not at module load time). Call `setActivationPolicy_` immediately after `NSApplication.sharedApplication()`.
**Warning signs:** Policy set correctly in code but Dock icon still appears

### Pitfall 3: NSNonactivatingPanelMask Must Be Set at Init Time
**What goes wrong:** Panel activates the app when it first appears, stealing keyboard focus
**Why it happens:** AppKit stores the nonactivating flag (via `kCGSPreventsActivationTagBit` WindowServer tag) at initialization. Changing `styleMask` after init does NOT update the WindowServer tag — documented bug (philz.blog/nspanel-nonactivating-style-mask-flag/)
**How to avoid:** Include `NSWindowStyleMaskNonactivatingPanel` in the `styleMask` parameter of `initWithContentRect_styleMask_backing_defer_()`. Never modify the style mask after creation for this flag.
**Warning signs:** Focus-steal check fails: typing in TextEdit is interrupted when NSApp.run() starts or overlay's panel is ordered front

### Pitfall 4: Python signal.signal() Unreliable Inside NSApp.run()
**What goes wrong:** Ctrl+C appears to do nothing; app cannot be quit
**Why it happens:** Python's signal handler mechanism relies on the Python interpreter checking for pending signals between bytecode instructions. While blocked inside `NSApp.run()` (C code), this check does not happen
**How to avoid:** Use `MachSignals.signal(signal.SIGINT, handler)` which registers a Mach port listener delivered inside the Cocoa run loop. The handler runs as part of the run loop, not as a Python signal
**Warning signs:** Ctrl+C in terminal produces no output; process only killable with SIGKILL

### Pitfall 5: Missing Transparency Flags (Solid Black Background)
**What goes wrong:** NSPanel shows with a solid black or dark gray background
**Why it happens:** Three separate flags all need to be False/clear: `isOpaque`, `backgroundColor`, `hasShadow`. AppKit defaults are all "visible"
**How to avoid:** Set all three: `setOpaque_(False)`, `setBackgroundColor_(NSColor.clearColor())`, `setHasShadow_(False)`
**Warning signs:** When Phase 3 sets alpha to 1.0, a solid dark rectangle appears instead of a transparent pill

### Pitfall 6: pynput TIS Warning on First Run
**What goes wrong:** Console prints warning: `"This is NOT allowed. Please call TIS/TSM in main thread!!!"`
**Why it happens:** pynput's `keycode_context()` calls TIS functions from the pynput daemon thread. macOS High Sierra+ prints this warning but does NOT crash or stop the listener.
**How to avoid:** This warning is cosmetic only. pynput uses `CFRunLoopGetCurrent()` (its OWN per-thread run loop, not the main NSRunLoop) so no actual conflict with NSApp.run() occurs. The warning can be suppressed by starting pynput's listener before NSApp.run(), which is already the architecture.
**Warning signs:** Console shows TIS warning but hotkeys still function — this is expected, not an error.

### Pitfall 7: NSWindowCollectionBehaviorFullScreenAuxiliary Missing
**What goes wrong:** Overlay panel vanishes when any app enters fullscreen mode
**Why it happens:** Without `NSWindowCollectionBehaviorFullScreenAuxiliary`, AppKit hides windows that aren't part of the fullscreen app
**How to avoid:** Include `NSWindowCollectionBehaviorFullScreenAuxiliary` in the `setCollectionBehavior_()` call alongside `NSWindowCollectionBehaviorCanJoinAllSpaces`
**Warning signs:** Overlay works on desktop but disappears on YouTube in fullscreen or macOS fullscreen apps

---

## Code Examples

Verified patterns from direct inspection of installed packages:

### Correct NSApp Startup Sequence

```python
# Source: PyObjCTools/AppHelper.py read from .venv/lib/python3.12/site-packages/
# Ordering is critical — do NOT rearrange

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
from PyObjCTools import MachSignals
import signal

# 1. Get shared app instance (creates NSApp singleton)
app = NSApplication.sharedApplication()

# 2. Set activation policy IMMEDIATELY — before any other NSApp call
app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

# 3. Register Mach port signal handlers (work inside NSApp.run())
MachSignals.signal(signal.SIGINT, lambda signum: app.terminate_(None))
MachSignals.signal(signal.SIGTERM, lambda signum: app.terminate_(None))
MachSignals.signal(signal.SIGHUP, lambda signum: app.terminate_(None))

# 4. Start all daemon threads (pynput, audio, etc.)
self._hotkey.start()

# 5. Create overlay (invisible at alpha=0)
overlay = OverlayPanel.create()

# 6. Enter run loop — blocks until terminate_() called
app.run()
```

### Verified MachSignals Signal Handler with Message Preservation

```python
# Source: PyObjCTools/MachSignals.py — verified from .venv
# MachSignals.signal(signum, handler) where handler takes one arg: signum

sig_name_holder: list[str] = []

def _quit(signum: int) -> None:
    import signal as _signal
    try:
        sig_name_holder.append(_signal.Signals(signum).name)
    except Exception:
        sig_name_holder.append(str(signum))
    from AppKit import NSApp as _NSApp
    _NSApp().terminate_(None)

MachSignals.signal(signal.SIGINT, _quit)
MachSignals.signal(signal.SIGTERM, _quit)
MachSignals.signal(signal.SIGHUP, _quit)

# After app.run() returns:
sig_name = sig_name_holder[0] if sig_name_holder else "SIGTERM"
print(f"\n[whisperkey] shutting down ({sig_name})")
```

### dispatch_to_main Pattern

```python
# Source: PyObjCTools/AppHelper.py — callAfter implementation read from .venv
from PyObjCTools.AppHelper import callAfter

def dispatch_to_main(fn, *args) -> None:
    """Call fn(*args) on the main thread. Non-blocking. Safe from any thread."""
    callAfter(fn, *args)

# Usage from pynput callback (background thread):
def _on_key_press(self, key):
    dispatch_to_main(self._overlay.show_recording)  # Phase 2+

# Usage from transcription thread:
def _transcribe_and_inject(self, recording):
    dispatch_to_main(self._overlay.show_transcribing)  # Phase 2+
```

### NSScreen Bottom-Center Position Calculation

```python
# Source: verified with Python REPL in .venv — NSScreen.mainScreen().frame() returns
# CoreFoundation.CGRect with .size.width/.size.height
from AppKit import NSScreen

def _compute_panel_frame(w: int = 280, h: int = 56, margin: int = 40):
    screen = NSScreen.mainScreen()
    sf = screen.frame()
    x = (sf.size.width - w) / 2
    y = float(margin)
    return ((x, y), (float(w), float(h)))
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `stop_event.wait()` blocking loop | `NSApplication.sharedApplication().run()` | Phase 1 | Enables AppKit timers, windows, animations |
| Python `signal.signal()` | `MachSignals.signal()` | Phase 1 | Signals reliably delivered inside NSApp run loop |
| No overlay window | NSPanel at alpha=0 | Phase 1 | Foundation in place for Phase 3 animation |
| Threads without main-thread dispatch | `callAfter()` via dispatch_to_main() | Phase 1 | Safe path for all future UI calls from worker threads |

**Current as of PyObjC 12.1 (built against macOS 26.1 SDK), verified 2026-03-09.**

---

## Open Questions

1. **NSApplicationMain vs NSApp.run() edge cases in bundle-less environment**
   - What we know: `AppHelper.runEventLoop()` calls `NSApplicationMain()` on first run which requires a bundle. `NSApplication.sharedApplication().run()` is the correct approach for a script-based app.
   - What's unclear: Whether any macOS 15 / macOS 26 security changes require a bundle for NSPanel at floating level.
   - Recommendation: Use `NSApp.run()` directly. If panel creation fails, the error will be an explicit exception rather than a silent no-op.

2. **pynput TIS warning — whether it can be fully silenced**
   - What we know: The warning is cosmetic; pynput's per-thread CFRunLoop does not conflict with NSApp.run().
   - What's unclear: Whether the warning affects App Store / notarization (not relevant for local tool).
   - Recommendation: Accept the warning; document it in Phase 1 verification notes.

3. **SIGTERM message format**
   - What we know: The current code prints `SIGINT` name from `signal.Signals(signum).name`. MachSignals handler receives signum as an int.
   - What's unclear: Whether `signal.Signals(signum).name` works correctly inside a MachSignals handler (different calling context).
   - Recommendation: Wrap in try/except; fall back to string `"SIGTERM"` if Signals lookup fails.

---

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` — section included.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest — NOT YET INSTALLED |
| Config file | None — Wave 0 must create |
| Quick run command | `pytest tests/ -x -q` (after Wave 0 setup) |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements — Test Map

Phase 1 requirements are architectural/behavioral. They cannot be fully automated because they require visual inspection, window focus verification, and real keyboard input. The correct test strategy is a structured manual smoke test checklist run after each plan. However, structural unit tests CAN verify the helper code.

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OVL-01 | NSPanel instance exists with correct flags (borderless, opaque=False, clearColor, ignoresMouseEvents, floatingLevel) | Unit | `pytest tests/test_overlay.py::test_panel_flags -x` | Wave 0 |
| OVL-01 | NSPanel positioned at correct bottom-center coordinates | Unit | `pytest tests/test_overlay.py::test_panel_position -x` | Wave 0 |
| OVL-01 | NSPanel alpha is 0.0 after creation | Unit | `pytest tests/test_overlay.py::test_panel_invisible -x` | Wave 0 |
| OVL-02 | NSApplicationActivationPolicyAccessory is set before run | Unit | `pytest tests/test_overlay.py::test_activation_policy -x` | Wave 0 |
| OVL-02 | Focus-steal: TextEdit keeps focus when WhisperKey starts | Manual smoke | Manual — start WhisperKey, type in TextEdit, confirm no interruption | N/A |
| OVL-03 | collectionBehavior includes CanJoinAllSpaces | Unit | `pytest tests/test_overlay.py::test_collection_behavior -x` | Wave 0 |
| OVL-03 | collectionBehavior includes FullScreenAuxiliary | Unit | `pytest tests/test_overlay.py::test_collection_behavior -x` | Wave 0 |
| Thread survival | Hotkey press — speak — release — text appears (all threads alive after NSApp.run()) | Manual smoke | Manual — press hotkey, speak, release, confirm transcription | N/A |
| SIGINT | Ctrl+C prints `[whisperkey] shutting down (SIGINT)` | Manual smoke | Manual — run, Ctrl+C, confirm message | N/A |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q` (structural checks only; manual smokes separate)
- **Per wave merge:** `pytest tests/ -v` + full manual smoke test checklist
- **Phase gate:** All unit tests green + manual smoke test checklist complete before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/__init__.py` — empty file to make tests a package
- [ ] `tests/test_overlay.py` — unit tests for NSPanel flag verification (OVL-01, OVL-02, OVL-03 structural checks)
- [ ] `tests/conftest.py` — shared fixtures (e.g., NSApplication.sharedApplication() setup)
- [ ] Framework install: `pip install pytest` — pytest not in pyproject.toml dependencies

Note: Unit tests for NSPanel flags work WITHOUT a running NSApp run loop — NSPanel.alloc().initWithContentRect_... can be called and introspected in a test process since creating an NSPanel does not require NSApp.run() to be active.

---

## Sources

### Primary (HIGH confidence)

- `.venv/lib/python3.12/site-packages/PyObjCTools/AppHelper.py` — `callAfter`, `runEventLoop`, `machInterrupt`, `installMachInterrupt` source read directly
- `.venv/lib/python3.12/site-packages/PyObjCTools/MachSignals.py` — signal handler mechanism verified
- `.venv/lib/python3.12/site-packages/pynput/_util/darwin.py` — `ListenerMixin._run()` confirms per-thread `CFRunLoopGetCurrent()`, NOT main NSRunLoop
- Python REPL in `.venv` — all AppKit constants verified with exact integer values
- Python REPL in `.venv` — `NSScreen.mainScreen().frame()` verified; position calculation confirmed

### Secondary (MEDIUM confidence)

- [PyObjC GitHub repo](https://github.com/ronaldoussoren/pyobjc) — official source for pyobjc-framework-Cocoa 12.1
- [PyObjCTools AppKit helpers docs](https://pyobjc.readthedocs.io/en/latest/api/threading-helpers.html) — `pyobjc_performSelectorOnMainThread_withObject_waitUntilDone_` safe variant confirmed
- [pynput issue #99: TIS/TSM non-main thread warning](https://github.com/moses-palmer/pynput/issues/99) — warning is cosmetic, listener continues working
- [pynput issue #511: crash with Qt6](https://github.com/moses-palmer/pynput/issues/511) — start pynput BEFORE NSApp.run() to avoid ordering issues
- [NSWindowLevel constants](https://cocoadev.github.io/NSWindowLevel/) — NSFloatingWindowLevel purpose confirmed
- [NSPanel nonactivating style mask pitfall](https://philz.blog/nspanel-nonactivating-style-mask-flag/) — must set at init time, not after; WindowServer tag not updated on post-init mask change

### Tertiary (LOW confidence — informational only)

- [Apple docs: NSWindowCollectionBehavior](https://developer.apple.com/forums/thread/26677) — canJoinAllSpaces flag confirmed
- [PyObjC RoundTransparentWindow example](https://pyobjc.readthedocs.io/en/latest/examples/Cocoa/AppKit/RoundTransparentWindow/index.html) — transparency three-flag combination confirmed

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all constants verified in running Python REPL from .venv
- Architecture: HIGH — pynput source read directly; CFRunLoop isolation confirmed
- Pitfalls: HIGH — sources verified via installed package source + official bug trackers
- Signal handling: HIGH — MachSignals source verified from .venv
- NSPanel flags: HIGH — constants verified numerically; pitfall (init-time only) sourced from documented bug

**Research date:** 2026-03-09
**Valid until:** 2026-09-09 (AppKit APIs are stable; PyObjC 12.x is built against macOS 26.1 SDK)
