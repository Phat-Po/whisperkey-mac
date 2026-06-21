"""Tests for stuck-state recovery and mic-switch recorder rebuild.

Covers two fixes for the "recording can't be stopped → service_busy forever"
incident (a deadlocked CoreAudio teardown left _processing_busy pinned True):

  Fix 2 — _recover_if_busy_stuck force-clears a wedged _processing_busy.
  Fix 3 — apply_config rebuilds the recorder when the mic device changes, so the
          old (possibly dead) stream is torn down instead of swapped underneath.
"""

import threading
import time

import whisperkey_mac.service_controller as sc
from whisperkey_mac.audio import AudioRecorder
from whisperkey_mac.config import AppConfig
from whisperkey_mac.service_controller import ServiceController


# --- Fix 2: busy-state backstop -------------------------------------------

class _BackstopStub:
    """Minimal stand-in exposing only what _recover_if_busy_stuck touches."""

    def __init__(self, busy, since):
        self._activity_lock = threading.Lock()
        self._processing_busy = busy
        self._processing_busy_since = since
        self._ui_quiet_until = 999_999.0
        self.hide_calls = 0

    def _hide_overlay_after_cancel(self):
        self.hide_calls += 1


def test_backstop_resets_when_busy_too_long():
    """A _processing_busy older than BUSY_BACKSTOP_S is force-cleared."""
    stuck_since = time.monotonic() - (sc.BUSY_BACKSTOP_S + 5.0)
    stub = _BackstopStub(busy=True, since=stuck_since)

    ServiceController._recover_if_busy_stuck(stub)

    assert stub._processing_busy is False
    assert stub._processing_busy_since == 0.0
    assert stub._ui_quiet_until == 0.0
    assert stub.hide_calls == 1


def test_backstop_noop_when_busy_recent():
    """A freshly-set _processing_busy is left alone (legit processing in flight)."""
    stub = _BackstopStub(busy=True, since=time.monotonic())

    ServiceController._recover_if_busy_stuck(stub)

    assert stub._processing_busy is True
    assert stub.hide_calls == 0


def test_backstop_noop_when_not_busy():
    """No reset, no overlay churn when the service isn't busy at all."""
    stub = _BackstopStub(busy=False, since=0.0)

    ServiceController._recover_if_busy_stuck(stub)

    assert stub._processing_busy is False
    assert stub.hide_calls == 0


# --- Fix 3: mic switch rebuilds the recorder ------------------------------

def _controller(tmp_path, **cfg_kw):
    cfg = AppConfig(temp_dir=tmp_path, **cfg_kw)
    return ServiceController(cfg)


def test_mic_change_rebuilds_recorder(tmp_path):
    """Switching input_device must replace the AudioRecorder instance so the
    old (possibly disconnected) stream is torn down, not swapped underneath."""
    ctrl = _controller(tmp_path, input_device="iPhone Microphone")
    original = ctrl._recorder
    assert isinstance(original, AudioRecorder)

    new_cfg = AppConfig(temp_dir=tmp_path, input_device="MacBook Pro Microphone")
    ctrl.apply_config(new_cfg)

    assert ctrl._recorder is not original
    assert ctrl._config.input_device == "MacBook Pro Microphone"


def test_unchanged_mic_keeps_recorder(tmp_path):
    """A config change that does not touch the mic keeps the same recorder."""
    ctrl = _controller(tmp_path, input_device="MacBook Pro Microphone")
    original = ctrl._recorder

    new_cfg = AppConfig(temp_dir=tmp_path, input_device="MacBook Pro Microphone")
    ctrl.apply_config(new_cfg)

    assert ctrl._recorder is original
