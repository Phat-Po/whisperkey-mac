from __future__ import annotations

import gc
import threading
from pathlib import Path

import opencc
from faster_whisper import WhisperModel

from whisperkey_mac.config import AppConfig
from whisperkey_mac.diagnostics import diag
from whisperkey_mac import model_manager

# Traditional Chinese → Simplified Chinese converter
_t2s = opencc.OpenCC("t2s")


class Transcriber:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._model: WhisperModel | None = None
        self._lock = threading.Lock()

    def preload(self) -> None:
        """Eagerly load the model so the first transcription does not trigger a
        GIL-holding native-library dlopen on the record->transcribe hot path.

        Safe to call from a background thread and safe to call repeatedly:
        _ensure_loaded() is lock-guarded and a no-op once the model is loaded.
        """
        self._ensure_loaded()

    def transcribe(self, audio_path: Path) -> str:
        diag("transcriber_transcribe_start")
        self._ensure_loaded()
        assert self._model is not None

        segments, _info = self._model.transcribe(
            str(audio_path),
            language=self._config.language,  # None = auto-detect
            task="transcribe",
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )

        text = " ".join(seg.text.strip() for seg in segments)
        text = text.strip()

        # Convert any Traditional Chinese characters to Simplified
        text = _t2s.convert(text)
        diag("transcriber_transcribe_end", has_text=bool(text))
        return text

    def _resolve_local_model_path(self, model_size: str) -> str | None:
        """Check local cache for a downloaded model. Returns path or None."""
        return model_manager.model_local_path(model_size)

    def is_model_cached(self) -> bool:
        """Return True if the current model is cached locally (no download needed)."""
        return model_manager.is_model_cached(self._config.model_size)

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            diag("transcriber_model_already_loaded")
            return
        with self._lock:
            if self._model is not None:
                diag("transcriber_model_already_loaded")
                return
            model_size = self._config.model_size
            local_path = self._resolve_local_model_path(model_size)
            model_arg = local_path or model_size
            diag(
                "transcriber_model_load_start",
                model_size=model_size,
                local_path=local_path,
                device=self._config.device,
                compute_type=self._config.compute_type,
            )
            print(
                f"[whisperkey] Loading Whisper model '{model_size}' "
                f"({'local' if local_path else 'download'}) "
                f"on {self._config.device} ({self._config.compute_type}) ..."
            )
            self._model = WhisperModel(
                model_arg,
                device=self._config.device,
                compute_type=self._config.compute_type,
            )
            print("[whisperkey] Model ready.")
            diag("transcriber_model_load_end")

    def unload(self) -> None:
        diag("transcriber_unload_start", had_model=self._model is not None)
        with self._lock:
            self._model = None
        gc.collect()
        diag("transcriber_unload_end")
