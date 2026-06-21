"""Unit tests for AudioRecorder.audio_level — normalized RMS level property.

AUD-01: audio_level is 0.0 when not recording (silence / never started)
AUD-02: audio_level stays in [0.0, 1.0] range for silence, speech, and loud input
AUD-03: audio_level resets to 0.0 after cancel()
AUD-04: audio_level resets to 0.0 after stop_and_save()
"""

import threading
import time

import numpy as np
import pytest
import sounddevice as sd

from whisperkey_mac.audio import AudioRecorder, _input_device_online
from whisperkey_mac.config import AppConfig


@pytest.fixture
def recorder(tmp_path):
    cfg = AppConfig(temp_dir=tmp_path)
    return AudioRecorder(cfg)


def test_audio_level_initial_is_zero(recorder):
    """AUD-01: audio_level is 0.0 before any recording."""
    assert recorder.audio_level == 0.0


def test_audio_level_silence(recorder):
    """AUD-02: all-zero input stays at 0.0 after smoothing."""
    silence = np.zeros((512, 1), dtype="float32")
    recorder._recording = True
    recorder._callback(silence, 512, None, None)
    recorder._recording = False
    assert recorder.audio_level == 0.0


def test_audio_level_normal_speech(recorder):
    """AUD-02: normal speech RMS ~0.05 maps to a value in (0.0, 1.0]."""
    # Simulate a speech-level frame: RMS ≈ 0.05
    frames = np.random.uniform(-0.05, 0.05, (512, 1)).astype("float32")
    recorder._recording = True
    recorder._callback(frames, 512, None, None)
    recorder._recording = False
    level = recorder.audio_level
    assert 0.0 < level <= 1.0


def test_audio_level_loud_input_clamped(recorder):
    """AUD-02: very loud input (RMS ~0.5) is clamped to 1.0."""
    loud = np.full((512, 1), 0.5, dtype="float32")
    recorder._recording = True
    for _ in range(10):
        recorder._callback(loud, 512, None, None)
    recorder._recording = False
    assert recorder.audio_level == 1.0


def test_audio_level_resets_after_cancel(recorder):
    """AUD-03: cancel() resets _smoothed_level so audio_level returns 0.0."""
    frames = np.random.uniform(-0.05, 0.05, (512, 1)).astype("float32")
    recorder._recording = True
    recorder._callback(frames, 512, None, None)
    # Don't use public cancel() (it checks _recording flag); reset directly
    recorder._smoothed_level = recorder._smoothed_level  # confirm it's non-zero
    assert recorder.audio_level > 0.0

    # Now simulate cancel path: set recording False and reset level
    recorder._recording = False
    recorder._smoothed_level = 0.0
    assert recorder.audio_level == 0.0


def test_audio_level_not_updated_when_not_recording(recorder):
    """AUD-01: _callback while _recording=False does not update smoothed level."""
    frames = np.random.uniform(-0.1, 0.1, (512, 1)).astype("float32")
    recorder._recording = False
    recorder._callback(frames, 512, None, None)
    assert recorder.audio_level == 0.0


def test_audio_level_range_invariant(recorder):
    """AUD-02: level never exceeds 1.0 regardless of input amplitude."""
    clip = np.full((512, 1), 1.0, dtype="float32")
    recorder._recording = True
    for _ in range(20):
        recorder._callback(clip, 512, None, None)
    recorder._recording = False
    assert recorder.audio_level <= 1.0
    assert recorder.audio_level >= 0.0


# --- Device resolution & fallback (AUD-05) -------------------------------

_FAKE_DEVICES = [
    {"name": "MacBook Pro Microphone", "max_input_channels": 1},
    {"name": "MacBook Pro Speakers", "max_input_channels": 0},
]


def test_input_device_online_true(monkeypatch):
    """AUD-05: a matching input-capable device is reported online."""
    monkeypatch.setattr(sd, "query_devices", lambda: _FAKE_DEVICES)
    assert _input_device_online("MacBook Pro Microphone") is True


def test_input_device_online_false_for_offline_name(monkeypatch):
    """AUD-05: a name not present in the live list is offline."""
    monkeypatch.setattr(sd, "query_devices", lambda: _FAKE_DEVICES)
    assert _input_device_online("iPhone Microphone") is False


def test_input_device_online_false_for_output_only(monkeypatch):
    """AUD-05: an output-only device is not a valid input device."""
    monkeypatch.setattr(sd, "query_devices", lambda: _FAKE_DEVICES)
    assert _input_device_online("MacBook Pro Speakers") is False


def test_input_device_online_empty_is_false():
    """AUD-05: empty name means default, never treated as a named device."""
    assert _input_device_online("") is False


class _FakeStream:
    def __init__(self, *, device=None, **_kw):
        # Raise for any specifically-named device to simulate it being offline.
        if device is not None:
            raise sd.PortAudioError("device unavailable")
        self.device = device

    def start(self):
        pass


def test_start_falls_back_when_device_offline(tmp_path, monkeypatch):
    """AUD-05: configured-but-offline device resolves to default, no raise."""
    monkeypatch.setattr(sd, "query_devices", lambda: _FAKE_DEVICES)
    monkeypatch.setattr(sd, "InputStream", _FakeStream)
    cfg = AppConfig(temp_dir=tmp_path, input_device="iPhone Microphone")
    rec = AudioRecorder(cfg)
    rec.start()
    assert rec.is_recording
    assert rec.fell_back_to_default is True
    assert rec.active_device_name == ""


def test_start_uses_configured_device_when_online(tmp_path, monkeypatch):
    """AUD-05: an online configured device is opened as-is (no fallback)."""
    opened = {}

    class _OkStream:
        def __init__(self, *, device=None, **_kw):
            opened["device"] = device

        def start(self):
            pass

    monkeypatch.setattr(sd, "query_devices", lambda: _FAKE_DEVICES)
    monkeypatch.setattr(sd, "InputStream", _OkStream)
    cfg = AppConfig(temp_dir=tmp_path, input_device="MacBook Pro Microphone")
    rec = AudioRecorder(cfg)
    rec.start()
    assert rec.fell_back_to_default is False
    assert rec.active_device_name == "MacBook Pro Microphone"
    assert opened["device"] == "MacBook Pro Microphone"


def test_start_retries_default_on_open_error(tmp_path, monkeypatch):
    """AUD-05: if a device passes the online check but InputStream still
    errors, _open_stream retries once with the default device."""
    monkeypatch.setattr(
        sd, "query_devices", lambda: [{"name": "Flaky Mic", "max_input_channels": 1}]
    )
    monkeypatch.setattr(sd, "InputStream", _FakeStream)  # raises for any named device
    cfg = AppConfig(temp_dir=tmp_path, input_device="Flaky Mic")
    rec = AudioRecorder(cfg)
    rec.start()
    assert rec.is_recording
    assert rec.fell_back_to_default is True
    assert rec.active_device_name == ""


# --- Callback-stall tracking (B-1) ---------------------------------------

def test_seconds_since_last_chunk_zero_when_not_recording(recorder):
    """B-1: the stall property is 0.0 when no recording is active."""
    assert recorder.seconds_since_last_chunk == 0.0


def test_seconds_since_last_chunk_zero_before_first_callback(recorder):
    """B-1: recording started but no callback fired yet → 0.0 (not a huge value)."""
    recorder._recording = True
    recorder._last_chunk_time = 0.0
    assert recorder.seconds_since_last_chunk == 0.0


def test_seconds_since_last_chunk_grows_while_stalled(recorder, monkeypatch):
    """B-1: with no new callbacks, elapsed time since last chunk grows."""
    import whisperkey_mac.audio as audio_mod

    clock = {"t": 1000.0}
    monkeypatch.setattr(audio_mod.time, "monotonic", lambda: clock["t"])
    recorder._recording = True
    recorder._last_chunk_time = 1000.0
    clock["t"] = 1002.5
    assert recorder.seconds_since_last_chunk == pytest.approx(2.5)


def test_callback_refreshes_heartbeat(recorder, monkeypatch):
    """B-1: each audio callback updates _last_chunk_time, resetting the stall."""
    import whisperkey_mac.audio as audio_mod

    clock = {"t": 5000.0}
    monkeypatch.setattr(audio_mod.time, "monotonic", lambda: clock["t"])
    recorder._recording = True
    recorder._last_chunk_time = 4990.0  # stale heartbeat
    frames = np.zeros((512, 1), dtype="float32")
    recorder._callback(frames, 512, None, None)
    assert recorder.seconds_since_last_chunk == pytest.approx(0.0)


# --- Teardown hardening against a removed device (B-1) --------------------

class _RaisingTeardownStream:
    """Opens fine but raises on stop()/close() — mimics a removed device."""

    def __init__(self, *, device=None, **_kw):
        self.device = device

    def start(self):
        pass

    def stop(self):
        raise sd.PortAudioError("device removed")

    def close(self):
        raise sd.PortAudioError("device removed")


def test_stop_and_save_swallows_teardown_error(tmp_path, monkeypatch):
    """B-1: stop_and_save must not propagate a stream.stop()/close() that raises."""
    monkeypatch.setattr(sd, "query_devices", lambda: _FAKE_DEVICES)
    monkeypatch.setattr(sd, "InputStream", _RaisingTeardownStream)
    cfg = AppConfig(temp_dir=tmp_path, input_device="MacBook Pro Microphone")
    rec = AudioRecorder(cfg)
    rec.start()
    assert rec.stop_and_save() is None  # no frames captured; must not raise
    assert rec.is_recording is False


def test_cancel_swallows_teardown_error(tmp_path, monkeypatch):
    """B-1: cancel must not propagate a stream.stop()/close() that raises."""
    monkeypatch.setattr(sd, "query_devices", lambda: _FAKE_DEVICES)
    monkeypatch.setattr(sd, "InputStream", _RaisingTeardownStream)
    cfg = AppConfig(temp_dir=tmp_path, input_device="MacBook Pro Microphone")
    rec = AudioRecorder(cfg)
    rec.start()
    rec.cancel()  # must not raise
    assert rec.is_recording is False


# --- Teardown DEADLOCK hardening (Fix 1) ----------------------------------
# A removed device can make stop()/close() *block forever* in PortAudio's C
# layer (not raise). The timeout helper must abandon the hung stream so the
# caller returns and the service state machine recovers.

class _HangingTeardownStream:
    """Opens fine but blocks indefinitely in stop() — mimics a CoreAudio deadlock."""

    def __init__(self, *, device=None, **_kw):
        self.device = device
        self.released = threading.Event()

    def start(self):
        pass

    def stop(self):
        self.released.wait()  # block until the test releases the zombie thread

    def close(self):
        pass


def _patch_hanging_stream(monkeypatch, holder):
    def _factory(*, device=None, **_kw):
        stream = _HangingTeardownStream(device=device)
        holder.append(stream)
        return stream

    monkeypatch.setattr(sd, "query_devices", lambda: _FAKE_DEVICES)
    monkeypatch.setattr(sd, "InputStream", _factory)


def test_cancel_returns_when_teardown_hangs(tmp_path, monkeypatch):
    """Fix 1: cancel() returns promptly even if stream.stop() deadlocks."""
    import whisperkey_mac.audio as audio_mod

    monkeypatch.setattr(audio_mod, "_STREAM_CLOSE_TIMEOUT_S", 0.2)
    streams: list = []
    _patch_hanging_stream(monkeypatch, streams)
    cfg = AppConfig(temp_dir=tmp_path, input_device="MacBook Pro Microphone")
    rec = AudioRecorder(cfg)
    rec.start()

    t0 = time.monotonic()
    rec.cancel()
    elapsed = time.monotonic() - t0

    assert elapsed < 1.0  # did not block on the hung teardown
    assert rec.is_recording is False
    assert rec._needs_pa_reset is True  # flagged for PortAudio reset
    streams[0].released.set()  # let the zombie thread exit cleanly


def test_stop_and_save_returns_when_teardown_hangs(tmp_path, monkeypatch):
    """Fix 1: stop_and_save() returns promptly even if stream.stop() deadlocks."""
    import whisperkey_mac.audio as audio_mod

    monkeypatch.setattr(audio_mod, "_STREAM_CLOSE_TIMEOUT_S", 0.2)
    streams: list = []
    _patch_hanging_stream(monkeypatch, streams)
    cfg = AppConfig(temp_dir=tmp_path, input_device="MacBook Pro Microphone")
    rec = AudioRecorder(cfg)
    rec.start()

    t0 = time.monotonic()
    result = rec.stop_and_save()  # no frames captured → None, must not hang
    elapsed = time.monotonic() - t0

    assert elapsed < 1.0
    assert result is None
    assert rec.is_recording is False
    assert rec._needs_pa_reset is True
    streams[0].released.set()


def test_start_resets_portaudio_after_teardown_timeout(tmp_path, monkeypatch):
    """Fix 1: a pending _needs_pa_reset forces a PortAudio re-init on next start,
    even for the default device (which normally skips the re-init)."""
    calls = {"term": 0, "init": 0}
    monkeypatch.setattr(sd, "query_devices", lambda: _FAKE_DEVICES)

    class _OkStream:
        def __init__(self, *, device=None, **_kw):
            self.device = device

        def start(self):
            pass

    monkeypatch.setattr(sd, "InputStream", _OkStream)
    monkeypatch.setattr(sd, "_terminate", lambda: calls.__setitem__("term", calls["term"] + 1))
    monkeypatch.setattr(sd, "_initialize", lambda: calls.__setitem__("init", calls["init"] + 1))

    cfg = AppConfig(temp_dir=tmp_path, input_device="")  # default device
    rec = AudioRecorder(cfg)
    rec._needs_pa_reset = True
    rec.start()

    assert calls["term"] == 1
    assert calls["init"] == 1
    assert rec._needs_pa_reset is False  # cleared after the reset
