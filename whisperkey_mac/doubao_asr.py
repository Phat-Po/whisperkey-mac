"""Streaming ASR client for Doubao (豆包) / Volcengine real-time speech recognition.

Uses WebSocket protocol to stream audio chunks and receive partial/final
transcription results in real-time. This enables "speak-and-see" UX where
text appears on the overlay as the user speaks.

Protocol: Volcengine Streaming ASR v2
Endpoint: wss://openspeech.bytedance.com/api/v2/asr
"""
from __future__ import annotations

import gzip
import json
import struct
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from whisperkey_mac.diagnostics import diag

# ── Protocol constants ──────────────────────────────────────────────────────

ASR_ENDPOINT = "wss://openspeech.bytedance.com/api/v2/asr"
RESOURCE_ID = "volc.bigasr.sauc.duration"

# Binary protocol header: version(1) + header_size_flags(1) + msg_type(1) + compression(1)
# + header_size(4) + payload_size(4) = 12 bytes
HEADER_SIZE = 12
PROTOCOL_VERSION = 0b0001  # version 1
HEADER_SIZE_FLAGS = 0b0001  # 4 bytes for header size
MSG_TYPE_FULL_CLIENT_REQUEST = 0b0001
MSG_TYPE_AUDIO_ONLY = 0b0010
MSG_TYPE_FULL_SERVER_RESPONSE = 0b1001
MSG_TYPE_SERVER_ACK = 0b1011
MSG_TYPE_SERVER_ERROR = 0b1111
COMPRESSION_GZIP = 0b0001
COMPRESSION_NONE = 0b0000
SERIALIZATION_JSON = 0b0001

# Audio parameters
SAMPLE_RATE = 16000
BITS_PER_SAMPLE = 16
CHANNELS = 1
BYTES_PER_SAMPLE = BITS_PER_SAMPLE // 8
CHUNK_DURATION_MS = 100  # 100ms chunks
CHUNK_BYTES = int(SAMPLE_RATE * BYTES_PER_SAMPLE * CHANNELS * CHUNK_DURATION_MS / 1000)


# ── Data types ──────────────────────────────────────────────────────────────

@dataclass
class DoubaoConfig:
    """Configuration for Doubao ASR streaming."""
    app_id: str = ""
    access_key: str = ""
    cluster: str = "volc.bigasr.sauc.duration"


@dataclass
class ASRResult:
    """A single ASR result (partial or final)."""
    text: str
    is_final: bool
    confidence: float = 0.0
    language: str = ""


# Callback types
PartialCallback = Callable[[str], None]      # called with partial text
FinalCallback = Callable[[str], None]        # called with final text
ErrorCallback = Callable[[str], None]        # called with error message


# ── Binary protocol helpers ─────────────────────────────────────────────────

def _build_header(
    msg_type: int,
    compression: int = COMPRESSION_GZIP,
    serialization: int = SERIALIZATION_JSON,
) -> bytes:
    """Build the 4-byte protocol header."""
    byte1 = (PROTOCOL_VERSION << 4) | HEADER_SIZE_FLAGS
    byte2 = (msg_type << 4) | serialization
    byte3 = (compression << 4) | 0x00
    byte4 = 0x00  # reserved
    return bytes([byte1, byte2, byte3, byte4])


def _build_message(msg_type: int, payload: dict | bytes, compress: bool = True) -> bytes:
    """Build a complete binary protocol message."""
    if isinstance(payload, dict):
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    else:
        payload_bytes = payload

    if compress:
        payload_bytes = gzip.compress(payload_bytes)
        compression = COMPRESSION_GZIP
    else:
        compression = COMPRESSION_NONE

    header = _build_header(msg_type, compression)
    header_size = struct.pack(">I", HEADER_SIZE)
    payload_size = struct.pack(">I", len(payload_bytes))
    return header + header_size + payload_size + payload_bytes


def _parse_message(data: bytes) -> tuple[int, dict | None]:
    """Parse a binary protocol message. Returns (msg_type, parsed_json_or_None)."""
    if len(data) < HEADER_SIZE:
        return 0, None

    byte1 = data[0]
    version = (byte1 >> 4) & 0x0F

    byte2 = data[1]
    msg_type = (byte2 >> 4) & 0x0F
    serialization = byte2 & 0x0F

    byte3 = data[2]
    compression = (byte3 >> 4) & 0x0F

    header_size = struct.unpack(">I", data[4:8])[0]
    payload_size = struct.unpack(">I", data[8:12])[0]

    payload = data[header_size:header_size + payload_size]

    if compression == COMPRESSION_GZIP:
        try:
            payload = gzip.decompress(payload)
        except Exception:
            pass

    if serialization == SERIALIZATION_JSON:
        try:
            return msg_type, json.loads(payload.decode("utf-8"))
        except Exception:
            return msg_type, None

    return msg_type, None


# ── Streaming ASR client ────────────────────────────────────────────────────

class DoubaoStreamingASR:
    """Streaming ASR client for Doubao/Volcengine.

    Usage:
        asr = DoubaoStreamingASR(config)
        asr.on_partial = lambda text: print("partial:", text)
        asr.on_final = lambda text: print("final:", text)
        asr.start()
        asr.feed_audio(chunk)  # call repeatedly with PCM chunks
        asr.finish()           # signal end of audio
        final_text = asr.stop()  # wait for final result
    """

    def __init__(self, config: DoubaoConfig) -> None:
        self._config = config
        self._ws = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._reqid = ""
        self._sequence = 0
        self._final_text = ""
        self._connected = threading.Event()
        self._finished = threading.Event()
        self._lock = threading.Lock()

        # Callbacks
        self.on_partial: PartialCallback | None = None
        self.on_final: FinalCallback | None = None
        self.on_error: ErrorCallback | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> bool:
        """Start the streaming connection. Returns True if connected."""
        if not self._config.app_id or not self._config.access_key:
            diag("doubao_no_credentials")
            if self.on_error:
                self.on_error("No Doubao API credentials configured")
            return False

        self._reqid = str(uuid.uuid4())
        self._sequence = -1
        self._final_text = ""
        self._running = True
        self._connected.clear()
        self._finished.clear()

        self._thread = threading.Thread(
            target=self._run_loop,
            name="DoubaoASRStream",
            daemon=True,
        )
        self._thread.start()

        # Wait for connection (up to 5s)
        if not self._connected.wait(timeout=5.0):
            diag("doubao_connect_timeout")
            self._running = False
            if self.on_error:
                self.on_error("Connection timeout")
            return False

        return True

    def feed_audio(self, pcm_chunk: bytes) -> None:
        """Send a PCM audio chunk to the streaming ASR."""
        if not self._running or self._ws is None:
            return

        with self._lock:
            try:
                self._sequence = 0
                msg = self._build_audio_message(pcm_chunk)
                self._ws.send_binary(msg)
            except Exception as exc:
                diag("doubao_feed_error", error_type=type(exc).__name__)

    def finish(self) -> None:
        """Signal end of audio stream and wait for final result."""
        if not self._running or self._ws is None:
            return

        with self._lock:
            try:
                self._sequence = 1  # end of stream
                msg = self._build_end_message()
                self._ws.send_binary(msg)
            except Exception as exc:
                diag("doubao_finish_error", error_type=type(exc).__name__)

    def stop(self, timeout_s: float = 5.0) -> str:
        """Stop the client and return the final transcription text."""
        self._finished.wait(timeout=timeout_s)
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)
        return self._final_text

    def _build_connect_message(self) -> bytes:
        """Build the initial connection/request message."""
        payload = {
            "app": {
                "appid": self._config.app_id,
                "token": self._config.access_key,
                "cluster": self._config.cluster,
            },
            "user": {
                "uid": f"whisperkey-{uuid.uuid4().hex[:8]}",
            },
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": SAMPLE_RATE,
                "bits": BITS_PER_SAMPLE,
                "channel": CHANNELS,
            },
            "request": {
                "reqid": self._reqid,
                "sequence": -1,
                "nbest": 1,
                "workflow": "audio_in,resample,partition,vad,fe,decode,itn,nlu_punctuate",
                "show_language": True,
                "result_type": "full",
                "text": "",
            },
        }
        return _build_message(MSG_TYPE_FULL_CLIENT_REQUEST, payload)

    def _build_audio_message(self, audio_chunk: bytes) -> bytes:
        """Build an audio-only message."""
        payload = {
            "app": {
                "appid": self._config.app_id,
                "token": self._config.access_key,
                "cluster": self._config.cluster,
            },
            "user": {
                "uid": f"whisperkey-{uuid.uuid4().hex[:8]}",
            },
            "audio": {
                "format": "pcm",
            },
            "request": {
                "reqid": self._reqid,
                "sequence": 0,
            },
        }
        # Audio-only messages: JSON header + raw audio concatenated
        json_bytes = gzip.compress(json.dumps(payload).encode("utf-8"))
        audio_bytes = gzip.compress(audio_chunk)
        combined = json_bytes + audio_bytes
        return _build_message(MSG_TYPE_AUDIO_ONLY, combined)

    def _build_end_message(self) -> bytes:
        """Build the end-of-stream message."""
        payload = {
            "app": {
                "appid": self._config.app_id,
                "token": self._config.access_key,
                "cluster": self._config.cluster,
            },
            "user": {
                "uid": f"whisperkey-{uuid.uuid4().hex[:8]}",
            },
            "audio": {
                "format": "pcm",
            },
            "request": {
                "reqid": self._reqid,
                "sequence": 1,
            },
        }
        return _build_message(MSG_TYPE_FULL_CLIENT_REQUEST, payload)

    def _run_loop(self) -> None:
        """WebSocket receive loop (runs in background thread)."""
        try:
            import websocket

            headers = {
                "X-Api-App-Key": self._config.app_id,
                "X-Api-Access-Key": self._config.access_key,
                "X-Api-Resource-Id": RESOURCE_ID,
            }

            self._ws = websocket.WebSocket()
            self._ws.connect(
                ASR_ENDPOINT,
                header=[f"{k}: {v}" for k, v in headers.items()],
                timeout=10.0,
            )

            # Send initial request
            init_msg = self._build_connect_message()
            self._ws.send_binary(init_msg)

            self._connected.set()
            diag("doubao_connected")

            # Receive loop
            while self._running:
                try:
                    data = self._ws.recv()
                    if isinstance(data, str):
                        data = data.encode("utf-8")
                    self._handle_response(data)
                except Exception as exc:
                    if self._running:
                        diag("doubao_recv_error", error_type=type(exc).__name__)
                    break

        except Exception as exc:
            diag("doubao_connect_error", error_type=type(exc).__name__)
            if self.on_error:
                self.on_error(f"Connection failed: {exc}")
        finally:
            self._connected.set()  # unblock start() if it's waiting
            self._finished.set()
            if self._ws:
                try:
                    self._ws.close()
                except Exception:
                    pass

    def _handle_response(self, data: bytes) -> None:
        """Parse and handle a server response."""
        msg_type, payload = _parse_message(data)

        if msg_type == MSG_TYPE_SERVER_ERROR:
            error_msg = str(payload) if payload else "Unknown server error"
            diag("doubao_server_error", error=error_msg)
            if self.on_error:
                self.on_error(error_msg)
            self._finished.set()
            return

        if msg_type not in (MSG_TYPE_FULL_SERVER_RESPONSE, MSG_TYPE_SERVER_ACK):
            return

        if not isinstance(payload, dict):
            return

        # Parse result
        result_list = payload.get("result", [])
        if not result_list:
            # Check for sequence end
            req = payload.get("request", {})
            if req.get("sequence", 0) > 0:
                self._finished.set()
            return

        result = result_list[0] if isinstance(result_list, list) else result_list
        text = result.get("text", "")
        is_final = result.get("definite", False)
        language = result.get("language", "")

        if text:
            if is_final:
                self._final_text = text
                diag("doubao_final", text_len=len(text), language=language)
                if self.on_final:
                    self.on_final(text)
                self._finished.set()
            else:
                diag("doubao_partial", text_len=len(text))
                if self.on_partial:
                    self.on_partial(text)


# ── Convenience functions ───────────────────────────────────────────────────

def is_configured(config: DoubaoConfig | None) -> bool:
    """Return True if Doubao ASR credentials are configured."""
    return bool(config and config.app_id and config.access_key)


def estimate_cost(duration_s: float, price_per_second: float = 0.033) -> float:
    """Estimate cost in CNY for a given duration."""
    return duration_s * price_per_second
