"""Regression tests for whisperkey_mac.transcriber."""

from pathlib import Path
from types import SimpleNamespace
import unittest.mock

from whisperkey_mac.config import AppConfig
from whisperkey_mac.transcriber import Transcriber


def test_transcribe_uses_low_latency_options_and_simplifies_text():
    cfg = AppConfig(language="zh", model_size="small", compute_type="int8", device="cpu")
    transcriber = Transcriber(cfg)
    transcriber._model = unittest.mock.MagicMock()
    transcriber._model.transcribe.return_value = (
        [
            SimpleNamespace(text="學習 "),
            SimpleNamespace(text=" English "),
        ],
        SimpleNamespace(language="zh"),
    )

    with unittest.mock.patch.object(transcriber, "_ensure_loaded") as mock_ensure_loaded:
        result = transcriber.transcribe(Path("/tmp/audio.wav"))

    assert result == "学习 English"
    mock_ensure_loaded.assert_called_once_with()
    transcriber._model.transcribe.assert_called_once_with(
        "/tmp/audio.wav",
        language="zh",
        task="transcribe",
        beam_size=1,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
    )
