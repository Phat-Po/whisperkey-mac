from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
import sounddevice as sd
import soundfile as sf

from whisperkey_mac.config import AppConfig
from whisperkey_mac.diagnostics import diag


def _input_device_online(name: str) -> bool:
    """True if an input-capable device matching ``name`` is currently available."""
    if not name:
        return False
    try:
        devices = sd.query_devices()
    except Exception:
        return False
    for d in devices:
        if d.get("max_input_channels", 0) > 0 and d.get("name") == name:
            return True
    return False


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
        self._smoothed_level: float = 0.0
        # Monotonic timestamp of the most recent audio callback. Used by the
        # disconnect watchdog to detect a mid-recording device removal (PortAudio
        # stops firing the callback when a CoreAudio input device disappears).
        self._last_chunk_time: float = 0.0
        # Name of the device actually opened for the current/last recording.
        # "" means the system default device was used.
        self.active_device_name: str = ""
        # True when the configured device was unavailable and we fell back to default.
        self.fell_back_to_default: bool = False
        # Optional callback for streaming: called with raw PCM bytes (int16, mono)
        self.on_chunk: "Callable[[bytes], None] | None" = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    @property
    def audio_level(self) -> float:
        """Normalized [0.0, 1.0] RMS-derived audio level. Thread-safe."""
        with self._lock:
            return min(1.0, self._smoothed_level * 10.0)

    @property
    def seconds_since_last_chunk(self) -> float:
        """Seconds since the audio callback last fired; 0.0 when not recording.

        When a pinned input device is removed mid-stream, PortAudio stops
        invoking the callback, so this value grows without bound. The disconnect
        watchdog reads it to tell "device gone" from a normal, active stream.
        """
        with self._lock:
            if not self._recording or self._last_chunk_time == 0.0:
                return 0.0
            return time.monotonic() - self._last_chunk_time

    def start(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._config.temp_dir.mkdir(parents=True, exist_ok=True)
            self._frames = []
            self._smoothed_level = 0.0

            configured = getattr(self._config, "input_device", "") or ""

            # Auto-reconnect (B-3): when a specific device is pinned, refresh
            # PortAudio's device list so a phone / Continuity mic that reconnected
            # after app launch becomes visible again. No stream is open at this
            # point, so re-initializing PortAudio is safe. Only pinned-device
            # users pay the ~100-300ms re-init cost; default-mic users skip it to
            # keep start latency low.
            if configured:
                try:
                    sd._terminate()
                    sd._initialize()
                except Exception:
                    pass  # never block recording on a refresh failure

            # Resolve the device to open. An empty name means system default.
            # If a specific device is configured but currently offline (e.g. an
            # iPhone Continuity mic that disconnected), fall back to the default
            # device instead of letting sounddevice raise.
            device: str | None = configured or None
            self.fell_back_to_default = False
            if configured and not _input_device_online(configured):
                diag("input_device_unavailable_fallback", configured=configured)
                device = None
                self.fell_back_to_default = True

            self._stream = self._open_stream(device)
            # _open_stream may have fallen back to default on a PortAudio error.
            if self.fell_back_to_default:
                self.active_device_name = ""
            else:
                self.active_device_name = "" if device is None else configured
            self._stream.start()
            self._recording = True
            self._last_chunk_time = time.monotonic()

    def _open_stream(self, device: str | None) -> sd.InputStream:
        """Open an input stream, retrying once with the default device on failure."""
        try:
            return sd.InputStream(
                samplerate=self._config.sample_rate,
                channels=1,
                dtype="float32",
                device=device,
                callback=self._callback,
            )
        except (ValueError, sd.PortAudioError) as exc:
            if device is None:
                # Already on the default device; nothing left to fall back to.
                diag("recording_open_failed", device="default", error_type=type(exc).__name__)
                raise
            diag(
                "recording_open_retry_default",
                device=str(device),
                error_type=type(exc).__name__,
            )
            stream = sd.InputStream(
                samplerate=self._config.sample_rate,
                channels=1,
                dtype="float32",
                device=None,
                callback=self._callback,
            )
            self.fell_back_to_default = True
            return stream

    def stop_and_save(self) -> AudioRecording | None:
        with self._lock:
            if not self._recording:
                return None
            stream = self._stream
            self._stream = None
            self._recording = False
            self._smoothed_level = 0.0

        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                # A device removed mid-recording can make stop()/close() raise.
                diag("stream_close_error", where="stop_and_save", error_type=type(exc).__name__)

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
            self._smoothed_level = 0.0

        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                diag("stream_close_error", where="cancel", error_type=type(exc).__name__)

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        with self._lock:
            # Heartbeat for the disconnect watchdog — cheap, every callback.
            self._last_chunk_time = time.monotonic()
            if self._recording:
                self._frames.append(indata.copy())
                rms = float(np.sqrt(np.mean(indata ** 2)))
                self._smoothed_level = 0.3 * rms + 0.7 * self._smoothed_level

        # Stream PCM chunk to Doubao ASR if callback is set
        chunk_cb = self.on_chunk
        if chunk_cb is not None and self._recording:
            try:
                # Convert float32 [-1.0, 1.0] to int16 PCM
                flat = indata.flatten()
                pcm = (flat * 32767).astype(np.int16).tobytes()
                chunk_cb(pcm)
            except Exception:
                pass  # Never let streaming errors break recording
