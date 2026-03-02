from __future__ import annotations

from collections.abc import Callable
from pynput.mouse import Button, Listener


def _resolve_button(spec: str) -> Button | int:
    """
    Resolve a button spec to a pynput Button or an integer (macOS extra button number).

    Named buttons: left, right, middle, x1, x2
    Numeric buttons: 3, 4, 5 ... (for macOS extra/side buttons)

    On macOS, pynput only defines left/middle/right. Side buttons come through
    as Button.unknown but carry an integer button number we can compare against.
    Use `whisperkey detect` to find your mouse's button numbers.
    """
    spec = spec.strip().lower()

    # Named aliases (safe: only reference x1/x2 if they exist)
    if spec in ("left", "right", "middle"):
        return getattr(Button, spec)

    # x1/x2 exist on Windows/Linux pynput but not macOS
    if spec in ("x1", "x2"):
        btn = getattr(Button, spec, None)
        if btn is not None:
            return btn
        # macOS fallback: x1=button4, x2=button3 (common convention)
        return 4 if spec == "x1" else 3

    # Numeric spec: "3", "4", "5" etc.
    try:
        return int(spec)
    except ValueError:
        pass

    raise ValueError(
        f"Unknown button spec {spec!r}. "
        "Use: left, right, middle, x1, x2, or a number (3, 4, 5...). "
        "Run `whisperkey detect` to find your mouse's button numbers."
    )


def _button_matches(button: Button, spec: Button | int) -> bool:
    """Compare a pynput Button event against a resolved spec."""
    if isinstance(spec, Button):
        return button == spec
    # Integer spec: macOS extra button comparison
    # pynput reports extra buttons as Button.unknown; get raw value via button.value
    if button == Button.unknown:
        try:
            return button.value == spec  # type: ignore[union-attr]
        except Exception:
            pass
    # Some pynput versions expose button number directly
    try:
        return int(button.value) == spec  # type: ignore[arg-type]
    except Exception:
        return False


class MouseListener:
    """
    Listens for mouse side button presses and calls callbacks.

    Default mapping (macOS):
      forward side button (x1 / button 4) → toggle recording
      back side button    (x2 / button 3) → send Enter
    """

    def __init__(
        self,
        record_button: str,
        enter_button: str,
        on_record_toggle: Callable[[], None],
        on_enter: Callable[[], None],
    ) -> None:
        self._record_spec = _resolve_button(record_button)
        self._enter_spec = _resolve_button(enter_button) if enter_button != "none" else None
        self._on_record_toggle = on_record_toggle
        self._on_enter = on_enter
        self._listener: Listener | None = None

    def start(self) -> None:
        self._listener = Listener(on_click=self._on_click)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_click(
        self,
        x: float,
        y: float,
        button: Button,
        pressed: bool,
    ) -> None:
        if not pressed:
            return

        if _button_matches(button, self._record_spec):
            self._on_record_toggle()
        elif self._enter_spec is not None and _button_matches(button, self._enter_spec):
            self._on_enter()
