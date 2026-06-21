"""Unit tests for the disconnect watchdog loop (Workstream B-2).

The loop is exercised in isolation by calling the unbound method with a
duck-typed stand-in for ``self``, so we don't construct a full
``ServiceController`` (which would pull in the transcriber, hotkey listener,
overlay, etc.). Only the handful of attributes the loop touches are stubbed.
"""

import threading
import time

import pytest

import whisperkey_mac.service_controller as sc
from whisperkey_mac.service_controller import ServiceController


class _FakeRecorder:
    def __init__(self, stall_values, is_recording=True):
        # stall_values: a constant float, or a list consumed one-per-read.
        self._stall_values = stall_values
        self.is_recording = is_recording
        self.active_device_name = "iPhone Microphone"

    @property
    def seconds_since_last_chunk(self):
        if isinstance(self._stall_values, (int, float)):
            return float(self._stall_values)
        if self._stall_values:
            return float(self._stall_values.pop(0))
        return 0.0  # list exhausted → healthy from here on


class _FakeHotkey:
    def __init__(self):
        self.reset_calls = 0

    def reset_state(self):
        self.reset_calls += 1


class _StubController:
    """Minimal stand-in exposing only what _disconnect_watchdog_loop touches."""

    def __init__(self, recorder):
        self._recorder = recorder
        self._hotkey = _FakeHotkey()
        self.stop_calls = 0
        self.notify_calls = 0

    def _notify_device_disconnected(self):
        self.notify_calls += 1

    def _stop_and_transcribe(self):
        self.stop_calls += 1


@pytest.fixture(autouse=True)
def _fast_ticks(monkeypatch):
    # Keep the loop fast; threshold semantics (1.5s, 2 consecutive) unchanged.
    monkeypatch.setattr(sc, "WATCHDOG_TICK_S", 0.001)


def _spawn(stub):
    stop_event = threading.Event()
    thread = threading.Thread(
        target=ServiceController._disconnect_watchdog_loop,
        args=(stub, stop_event),
        daemon=True,
    )
    thread.start()
    return thread, stop_event


def test_watchdog_autostops_on_sustained_stall():
    """A device that stops delivering callbacks triggers exactly one auto-stop."""
    stub = _StubController(_FakeRecorder(stall_values=sc.STALL_THRESHOLD_S + 1.0))
    thread, stop_event = _spawn(stub)
    thread.join(timeout=2.0)
    stop_event.set()
    assert not thread.is_alive()  # loop returned on its own
    assert stub.stop_calls == 1
    assert stub.notify_calls == 1
    assert stub._hotkey.reset_calls == 1


def test_watchdog_no_autostop_when_healthy():
    """A steady stream (stall ~0) never triggers an auto-stop."""
    stub = _StubController(_FakeRecorder(stall_values=0.0))
    thread, stop_event = _spawn(stub)
    time.sleep(0.05)  # many ticks
    stop_event.set()
    thread.join(timeout=1.0)
    assert stub.stop_calls == 0


def test_watchdog_requires_two_consecutive_stalls():
    """A single stalled tick followed by recovery must NOT auto-stop."""
    over = sc.STALL_THRESHOLD_S + 1.0
    alternating = [over, 0.0, over, 0.0, over, 0.0, over, 0.0]
    stub = _StubController(_FakeRecorder(stall_values=alternating))
    thread, stop_event = _spawn(stub)
    time.sleep(0.05)
    stop_event.set()
    thread.join(timeout=1.0)
    assert stub.stop_calls == 0


def test_watchdog_exits_when_not_recording():
    """If recording already ended, the loop exits without auto-stopping."""
    stub = _StubController(_FakeRecorder(stall_values=0.0, is_recording=False))
    thread, stop_event = _spawn(stub)
    thread.join(timeout=2.0)
    stop_event.set()
    assert not thread.is_alive()
    assert stub.stop_calls == 0


def test_watchdog_stops_immediately_on_stop_event():
    """Setting the stop event before any stall ends the loop with no auto-stop."""
    stub = _StubController(_FakeRecorder(stall_values=sc.STALL_THRESHOLD_S + 1.0))
    stop_event = threading.Event()
    stop_event.set()  # pre-set: first wait() returns True immediately
    ServiceController._disconnect_watchdog_loop(stub, stop_event)
    assert stub.stop_calls == 0
