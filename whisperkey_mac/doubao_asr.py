"""Streaming ASR client for Doubao (豆包) / Volcengine real-time speech recognition.

Uses WebSocket protocol to stream audio chunks and receive partial/final
transcription results in real-time. This enables "speak-and-see" UX where
text appears on the overlay as the user speaks.

Protocol: Volcengine Streaming ASR v3 (bigmodel)
Endpoint: wss://openspeech.bytedance.com/api/v3/sauc/bigmodel
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

ASR_ENDPOINT = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
RESOURCE_ID = "volc.bigasr.sauc.duration"

# Binary protocol header: 4 bytes
HEADER_SIZE = 4
PROTOCOL_VERSION = 0b0001  # version 1
DEFAULT_HEADER_SIZE = 0b0001  # 1 unit = 4 bytes

# Message types (byte 1 high nibble)
MSG_TYPE_FULL_CLIENT_REQUEST = 0b0001
MSG_TYPE_AUDIO_ONLY = 0b0010
MSG_TYPE_FULL_SERVER_RESPONSE = 0b1001
MSG_TYPE_SERVER_ACK = 0b1011
MSG_TYPE_SERVER_ERROR = 0b1111

# Message type specific flags (byte 1 low nibble)
NO_SEQUENCE = 0b0000
POS_SEQUENCE = 0b0001
NEG_SEQUENCE = 0b0010  # end-of-stream / tail packet
MSG_WITH_EVENT = 0b0100

# Serialization (byte 2 high nibble)
SERIALIZATION_NONE = 0b0000
SERIALIZATION_JSON = 0b0001

# Compression (byte 2 low nibble)
COMPRESSION_NONE = 0b0000
COMPRESSION_GZIP = 0b0001

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
    flags: int = NO_SEQUENCE,
    serialization: int = SERIALIZATION_JSON,
    compression: int = COMPRESSION_GZIP,
) -> bytes:
    """Build the 4-byte protocol header.

    Byte 0: (version << 4) | header_size
    Byte 1: (msg_type << 4) | flags
    Byte 2: (serialization << 4) | compression
    Byte 3: reserved
    """
    byte0 = (PROTOCOL_VERSION << 4) | DEFAULT_HEADER_SIZE
    byte1 = (msg_type << 4) | flags
    byte2 = (serialization << 4) | compression
    byte3 = 0x00  # reserved
    return bytes([byte0, byte1, byte2, byte3])


def _build_message(
    msg_type: int,
    payload: dict | bytes,
    flags: int = NO_SEQUENCE,
    compress: bool = True,
) -> bytes:
    """Build a complete binary protocol message."""
    if isinstance(payload, dict):
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        serialization = SERIALIZATION_JSON
    else:
        payload_bytes = payload
        serialization = SERIALIZATION_NONE

    if compress:
        payload_bytes = gzip.compress(payload_bytes)
        compression = COMPRESSION_GZIP
    else:
        compression = COMPRESSION_NONE

    header = _build_header(msg_type, flags, serialization, compression)
    payload_size = struct.pack(">I", len(payload_bytes))
    return header + payload_size + payload_bytes


def _parse_message(data: bytes) -> tuple[int, int, dict | None]:
    """Parse a binary protocol message from the Volcengine v3 server.

    Returns (msg_type, flags, parsed_json_or_None).

    Server responses have a 12-byte header area:
      bytes 0-3: protocol header (version, msg_type, flags, serial, compression)
      bytes 4-7: unknown field (possibly message length or backend code)
      bytes 8-11: payload_size
      bytes 12+: payload (gzip-compressed JSON or raw JSON)
    """
    if len(data) < HEADER_SIZE:
        return 0, 0, None

    byte1 = data[1]
    msg_type = (byte1 >> 4) & 0x0F
    flags = byte1 & 0x0F

    byte2 = data[2]
    compression = byte2 & 0x0F

    # Server responses start payload at offset 12 (not offset 4)
    # Observed structure: header(4) + unknown(4) + payload_size(4) + payload
    payload = b""
    if len(data) >= 12:
        payload_size = struct.unpack(">I", data[8:12])[0]
        if payload_size > 0 and 12 + payload_size <= len(data):
            payload = data[12:12 + payload_size]
        else:
            # Fallback: try to find gzip magic or JSON start
            payload = _find_payload_fallback(data[12:], compression)
    elif len(data) > 4:
        # Short message, try standard offset
        payload = _find_payload_fallback(data[4:], compression)

    # Decompress if gzip
    if compression == COMPRESSION_GZIP and payload:
        try:
            payload = gzip.decompress(payload)
        except Exception:
            pass

    # Parse JSON
    if payload:
        try:
            return msg_type, flags, json.loads(payload.decode("utf-8"))
        except Exception:
            # Try to find JSON start (v3 may have non-JSON prefix)
            json_start = payload.find(b"{")
            if json_start > 0:
                try:
                    return msg_type, flags, json.loads(payload[json_start:].decode("utf-8"))
                except Exception:
                    pass
            return msg_type, flags, None

    return msg_type, flags, None


def _find_payload_fallback(data: bytes, compression: int) -> bytes:
    """Find payload by scanning for gzip magic or JSON start."""
    if not data:
        return b""

    # If gzip, scan for magic bytes
    if compression == COMPRESSION_GZIP:
        for i in range(len(data) - 1):
            if data[i] == 0x1F and data[i + 1] == 0x8B:
                # Read payload_size from 4 bytes before gzip data
                if i >= 4:
                    alt_size = struct.unpack(">I", data[i - 4:i])[0]
                    if alt_size > 0 and i + alt_size <= len(data):
                        return data[i:i + alt_size]
                return data[i:]

    # Scan for JSON start
    json_start = data.find(b"{")
    if json_start >= 0:
        return data[json_start:]

    return data


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
        self._connect_failed = threading.Event()
        self._finished = threading.Event()
        self._lock = threading.Lock()

        # Callbacks
        self.on_partial: PartialCallback | None = None
        self.on_final: FinalCallback | None = None
        self.on_error: ErrorCallback | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set() and not self._connect_failed.is_set()

    def start(self) -> bool:
        """Start the streaming connection. Returns True if connected."""
        if not self._config.app_id or not self._config.access_key:
            diag("doubao_no_credentials")
            if self.on_error:
                self.on_error("No Doubao API credentials configured")
            return False

        self._reqid = str(uuid.uuid4())
        self._sequence = 0
        self._final_text = ""
        self._running = True
        self._connected.clear()
        self._connect_failed.clear()
        self._finished.clear()

        self._thread = threading.Thread(
            target=self._run_loop,
            name="DoubaoASRStream",
            daemon=True,
        )
        self._thread.start()

        # Wait for connection success or failure (up to 5s)
        while not self._connected.is_set() and not self._connect_failed.is_set():
            if self._connected.wait(timeout=0.1) or self._connect_failed.wait(timeout=0.1):
                break

        if self._connect_failed.is_set() or not self._connected.is_set():
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
                msg = self._build_audio_message(pcm_chunk)
                self._ws.send_binary(msg)
                self._sequence += 1
            except Exception as exc:
                diag("doubao_feed_error", error_type=type(exc).__name__)

    def finish(self) -> None:
        """Signal end of audio stream."""
        if not self._running or self._ws is None:
            return

        with self._lock:
            try:
                msg = self._build_end_message()
                self._ws.send_binary(msg)
                diag("doubao_finish_sent")
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
        """Build the initial connection/request message (v3 format).

        v3 API payload structure (no 'app' field):
        {
            "user": {"uid": "..."},
            "audio": {"format": "pcm", "codec": "raw", "rate": 16000, ...},
            "request": {"model_name": "bigmodel", "result_type": "full", ...}
        }
        """
        payload = {
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
                "model_name": "bigmodel",
                "language": "zh-CN",
                # Match the proven-working Volcengine reference config exactly.
                # "single" (not "full") + show_utterances False is the response
                # mode that actually emits recognized text; force_to_speech_time
                # makes VAD commit a speech segment (without it the engine
                # receives audio but never recognizes — empty text, 0 quota).
                "result_type": "single",
                "show_utterances": False,
                "enable_itn": True,
                "enable_punc": True,
                "vad": {
                    "vad_enable": True,
                    "end_window_size": 2000,
                    "force_to_speech_time": 100,
                },
            },
        }
        return _build_message(
            MSG_TYPE_FULL_CLIENT_REQUEST,
            payload,
            flags=NO_SEQUENCE,
            compress=False,
        )

    def _build_audio_message(self, audio_chunk: bytes) -> bytes:
        """Build an audio-only message with raw PCM data.

        v3 protocol: audio-only messages carry raw PCM bytes
        with no JSON wrapping and no compression.
        """
        return _build_message(
            MSG_TYPE_AUDIO_ONLY,
            audio_chunk,
            flags=NO_SEQUENCE,
            compress=False,
        )

    def _build_end_message(self) -> bytes:
        """Build the end-of-stream message.

        Send an audio-only message with NEG_SEQUENCE flag and empty payload.
        """
        return _build_message(
            MSG_TYPE_AUDIO_ONLY,
            b"",
            flags=NEG_SEQUENCE,
            compress=False,
        )

    def _run_loop(self) -> None:
        """WebSocket receive loop (runs in background thread)."""
        try:
            import websocket

            connect_id = str(uuid.uuid4())
            headers = {
                "X-Api-App-Key": self._config.app_id,
                "X-Api-Access-Key": self._config.access_key,
                "X-Api-Resource-Id": RESOURCE_ID,
                "X-Api-Connect-Id": connect_id,
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

            # Connection successful
            self._connected.set()
            diag("doubao_connected", connect_id=connect_id)

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
            self._connect_failed.set()
        finally:
            if not self._connected.is_set() and not self._connect_failed.is_set():
                self._connect_failed.set()
            self._finished.set()
            if self._ws:
                try:
                    self._ws.close()
                except Exception:
                    pass

    def _handle_response(self, data: bytes) -> None:
        """Parse and handle a server response."""
        msg_type, flags, payload = _parse_message(data)

        if msg_type == MSG_TYPE_SERVER_ERROR:
            error_msg = str(payload) if payload else "Unknown server error"
            diag("doubao_server_error", error=error_msg, error_payload=payload)
            if self.on_error:
                self.on_error(error_msg)
            self._finished.set()
            return

        if msg_type not in (MSG_TYPE_FULL_SERVER_RESPONSE, MSG_TYPE_SERVER_ACK):
            diag("doubao_unknown_msg_type", msg_type=msg_type)
            return

        if not isinstance(payload, dict):
            return

        # v3 response format (observed):
        # {"audio_info": {"duration": N}, "result": {"text": "...", "additions": {...}}}
        # Some responses also have: {"type": "final"|"partial", "result": [...]}
        resp_type = payload.get("type", "")

        # Check for error in response
        header_info = payload.get("header", {})
        status = header_info.get("status", 0)
        if resp_type == "error" or (status != 0 and status != 20000000):
            error_msg = payload.get("message", str(payload))
            diag("doubao_server_error", error=error_msg, error_payload=payload)
            if self.on_error:
                self.on_error(error_msg)
            self._finished.set()
            return

        # Extract text from result — handles both dict and list formats
        result_data = payload.get("result", {})
        text = ""
        if isinstance(result_data, dict):
            # v3 format: result is a dict with "text" directly
            t = result_data.get("text", "")
            if t and t.strip():
                text = t.strip()
        elif isinstance(result_data, list):
            for item in result_data:
                if isinstance(item, dict):
                    t = item.get("text", "")
                    if t and t.strip():
                        text = t.strip()
                elif isinstance(item, str) and item.strip():
                    text = item.strip()
        elif isinstance(result_data, str) and result_data.strip():
            text = result_data.strip()

        # The v3 bigmodel (/sauc) endpoint does NOT send a "type" field. It
        # marks the final result by setting the NEG_SEQUENCE flag bit on the
        # last response (observed flags=3 = POS_SEQUENCE | NEG_SEQUENCE). Older
        # / other endpoints use a "type": "final" field, so honor both.
        is_final = resp_type == "final" or bool(flags & NEG_SEQUENCE)

        if text:
            # Recognized text is cumulative; always retain the latest so stop()
            # returns the most complete result even if the final marker is
            # missed (e.g. the socket closes right after the last partial).
            self._final_text = text
            if is_final:
                diag("doubao_final", text_len=len(text))
                if self.on_final:
                    self.on_final(text)
                self._finished.set()
            else:
                diag("doubao_partial", text_len=len(text))
                if self.on_partial:
                    self.on_partial(text)
        elif is_final:
            # Server marked final but no text (silence)
            self._finished.set()


# ── Convenience functions ───────────────────────────────────────────────────

def is_configured(config: DoubaoConfig | None) -> bool:
    """Return True if Doubao ASR credentials are configured."""
    return bool(config and config.app_id and config.access_key)


def estimate_cost(duration_s: float, price_per_second: float = 0.033) -> float:
    """Estimate cost in CNY for a given duration."""
    return duration_s * price_per_second
