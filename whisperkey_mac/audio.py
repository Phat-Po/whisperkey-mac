from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
import sounddevice as sd
import soundfile as sf

from whisperkey_mac.config import AppConfig


@dataclass
class AudioRecording:
    path: Path
    duration_s: float


class AudioRecorder:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._recording = False

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def start(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._config.temp_dir.mkdir(parents=True, exist_ok=True)
            self._frames = []
            device = getattr(self._config, "input_device", "") or None
            self._stream = sd.InputStream(
                samplerate=self._config.sample_rate,
                channels=1,
                dtype="float32",
                device=device,
                callback=self._callback,
            )
            self._stream.start()
            self._recording = True

    def stop_and_save(self) -> AudioRecording | None:
        with self._lock:
            if not self._recording:
                return None
            stream = self._stream
            self._stream = None
            self._recording = False

        if stream is not None:
            stream.stop()
            stream.close()

        with self._lock:
            if not self._frames:
                return None
            audio = np.concatenate(self._frames, axis=0)
            self._frames = []

        duration = len(audio) / self._config.sample_rate
        if duration < self._config.min_duration_s:
            return None

        out_path = self._config.temp_dir / f"rec_{uuid4().hex}.wav"
        sf.write(str(out_path), audio, self._config.sample_rate)
        return AudioRecording(path=out_path, duration_s=duration)

    def cancel(self) -> None:
        with self._lock:
            if not self._recording:
                self._frames = []
                return
            stream = self._stream
            self._stream = None
            self._recording = False
            self._frames = []

        if stream is not None:
            stream.stop()
            stream.close()

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        with self._lock:
            if self._recording:
                self._frames.append(indata.copy())
