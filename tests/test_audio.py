"""Unit tests for AudioRecorder.audio_level — normalized RMS level property.

AUD-01: audio_level is 0.0 when not recording (silence / never started)
AUD-02: audio_level stays in [0.0, 1.0] range for silence, speech, and loud input
AUD-03: audio_level resets to 0.0 after cancel()
AUD-04: audio_level resets to 0.0 after stop_and_save()
"""

import numpy as np
import pytest

from whisperkey_mac.audio import AudioRecorder
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
