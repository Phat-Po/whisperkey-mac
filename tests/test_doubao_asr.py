"""Tests for the doubao_asr streaming ASR module (v3 API)."""

import gzip
import json
import struct
import unittest.mock

import websocket as _websocket_mod

from whisperkey_mac import doubao_asr


# ── Protocol helpers ─────────────────────────────────────────────────────────

def test_build_header_has_correct_size():
    header = doubao_asr._build_header(doubao_asr.MSG_TYPE_FULL_CLIENT_REQUEST)
    assert len(header) == 4


def test_build_header_byte1_has_msg_type_and_flags():
    header = doubao_asr._build_header(
        doubao_asr.MSG_TYPE_AUDIO_ONLY,
        flags=doubao_asr.NEG_SEQUENCE,
    )
    byte1 = header[1]
    msg_type = (byte1 >> 4) & 0x0F
    flags = byte1 & 0x0F
    assert msg_type == doubao_asr.MSG_TYPE_AUDIO_ONLY
    assert flags == doubao_asr.NEG_SEQUENCE


def test_build_header_byte2_has_serialization_and_compression():
    header = doubao_asr._build_header(
        doubao_asr.MSG_TYPE_FULL_CLIENT_REQUEST,
        serialization=doubao_asr.SERIALIZATION_JSON,
        compression=doubao_asr.COMPRESSION_GZIP,
    )
    byte2 = header[2]
    serialization = (byte2 >> 4) & 0x0F
    compression = byte2 & 0x0F
    assert serialization == doubao_asr.SERIALIZATION_JSON
    assert compression == doubao_asr.COMPRESSION_GZIP


def test_build_message_produces_valid_binary():
    msg = doubao_asr._build_message(
        doubao_asr.MSG_TYPE_FULL_CLIENT_REQUEST,
        {"test": "value"},
    )
    assert len(msg) > doubao_asr.HEADER_SIZE
    assert (msg[0] >> 4) == doubao_asr.PROTOCOL_VERSION


def test_build_message_audio_only_has_no_serialization():
    """Audio-only messages should use NO_SERIALIZATION."""
    msg = doubao_asr._build_message(
        doubao_asr.MSG_TYPE_AUDIO_ONLY,
        b"\x00" * 100,
        flags=doubao_asr.NO_SEQUENCE,
        compress=False,
    )
    byte2 = msg[2]
    serialization = (byte2 >> 4) & 0x0F
    assert serialization == doubao_asr.SERIALIZATION_NONE


def test_build_audio_message_sends_raw_pcm_no_compression():
    """v3 audio messages: raw PCM, no JSON, no compression."""
    asr = doubao_asr.DoubaoStreamingASR(doubao_asr.DoubaoConfig())
    pcm = b"\x00\x01" * 160
    msg = asr._build_audio_message(pcm)

    # header(4) + payload_size(4) + raw PCM
    assert len(msg) == 4 + 4 + len(pcm)
    byte1 = msg[1]
    msg_type = (byte1 >> 4) & 0x0F
    assert msg_type == doubao_asr.MSG_TYPE_AUDIO_ONLY

    # No compression
    byte2 = msg[2]
    compression = byte2 & 0x0F
    assert compression == doubao_asr.COMPRESSION_NONE

    # Payload is raw PCM
    payload_size = struct.unpack(">I", msg[4:8])[0]
    assert payload_size == len(pcm)
    assert msg[8:] == pcm


def test_build_end_message_uses_neg_sequence():
    asr = doubao_asr.DoubaoStreamingASR(doubao_asr.DoubaoConfig())
    msg = asr._build_end_message()

    byte1 = msg[1]
    msg_type = (byte1 >> 4) & 0x0F
    flags = byte1 & 0x0F
    assert msg_type == doubao_asr.MSG_TYPE_AUDIO_ONLY
    assert flags == doubao_asr.NEG_SEQUENCE

    payload_size = struct.unpack(">I", msg[4:8])[0]
    assert payload_size == 0


def test_build_connect_message_has_no_app_field():
    """v3 API: no 'app' field, has 'model_name' in request."""
    asr = doubao_asr.DoubaoStreamingASR(doubao_asr.DoubaoConfig(
        app_id="test", access_key="key", cluster="test-cluster",
    ))
    msg = asr._build_connect_message()

    # Extract JSON payload (raw JSON after header+size, no compression)
    raw = msg[8:]
    payload = json.loads(raw)

    assert "app" not in payload
    assert payload["request"]["model_name"] == "bigmodel"
    assert payload["request"]["language"] == "zh-CN"
    assert payload["request"]["vad"]["vad_enable"] is True
    assert "user" in payload
    assert "audio" in payload


def test_build_connect_message_matches_working_reference_params():
    """v3 bigmodel: result_type/show_utterances/force_to_speech_time must match
    the proven-working reference, otherwise the engine returns empty text."""
    asr = doubao_asr.DoubaoStreamingASR(doubao_asr.DoubaoConfig(
        app_id="test", access_key="key", cluster="test-cluster",
    ))
    payload = json.loads(asr._build_connect_message()[8:])
    req = payload["request"]

    assert req["result_type"] == "single"
    assert req["show_utterances"] is False
    assert req["vad"]["force_to_speech_time"] == 100


# ── Response parsing (v3 format) ────────────────────────────────────────────

def test_parse_v3_server_response():
    """v3 server responses: payload at offset 12, JSON with 'type' field."""
    resp_payload = {
        "type": "final",
        "result": [{"text": "hello world", "definite": True}],
        "header": {"status": 20000000},
    }
    payload_bytes = json.dumps(resp_payload).encode()

    # Build v3 response: header(4) + unknown(4) + payload_size(4) + payload
    header = doubao_asr._build_header(
        doubao_asr.MSG_TYPE_FULL_SERVER_RESPONSE,
        flags=doubao_asr.NO_SEQUENCE,
        compression=doubao_asr.COMPRESSION_NONE,
    )
    unknown_field = struct.pack(">I", 0x02AEA540)
    payload_size = struct.pack(">I", len(payload_bytes))
    data = header + unknown_field + payload_size + payload_bytes

    msg_type, flags, parsed = doubao_asr._parse_message(data)
    assert msg_type == doubao_asr.MSG_TYPE_FULL_SERVER_RESPONSE
    assert parsed is not None
    assert parsed["type"] == "final"
    assert parsed["result"][0]["text"] == "hello world"


def test_parse_v3_gzip_response():
    """v3 gzip-compressed server response."""
    resp_payload = {
        "type": "partial",
        "result": [{"text": "hi", "definite": False}],
        "header": {"status": 20000000},
    }
    payload_bytes = gzip.compress(json.dumps(resp_payload).encode())

    header = doubao_asr._build_header(
        doubao_asr.MSG_TYPE_FULL_SERVER_RESPONSE,
        flags=doubao_asr.NO_SEQUENCE,
    )
    unknown_field = struct.pack(">I", 0x02AEA540)
    payload_size = struct.pack(">I", len(payload_bytes))
    data = header + unknown_field + payload_size + payload_bytes

    msg_type, flags, parsed = doubao_asr._parse_message(data)
    assert msg_type == doubao_asr.MSG_TYPE_FULL_SERVER_RESPONSE
    assert parsed is not None
    assert parsed["type"] == "partial"
    assert parsed["result"][0]["text"] == "hi"


def test_parse_v3_error_response():
    """v3 error response with JSON payload."""
    error_payload = {
        "reqid": "test-123",
        "message": "auth failed",
        "code": 400,
        "backend_code": 45000000,
    }
    payload_bytes = gzip.compress(json.dumps(error_payload).encode())

    header = doubao_asr._build_header(
        doubao_asr.MSG_TYPE_SERVER_ERROR,
        flags=doubao_asr.NO_SEQUENCE,
    )
    unknown_field = struct.pack(">I", 0x02AEA540)
    payload_size = struct.pack(">I", len(payload_bytes))
    data = header + unknown_field + payload_size + payload_bytes

    msg_type, flags, parsed = doubao_asr._parse_message(data)
    assert msg_type == doubao_asr.MSG_TYPE_SERVER_ERROR
    assert parsed is not None
    assert parsed["code"] == 400
    assert parsed["message"] == "auth failed"


def test_parse_message_returns_none_for_short_data():
    msg_type, flags, parsed = doubao_asr._parse_message(b"\x00" * 3)
    assert parsed is None


# ── Config ───────────────────────────────────────────────────────────────────

def test_doubao_config_defaults():
    cfg = doubao_asr.DoubaoConfig()
    assert cfg.app_id == ""
    assert cfg.access_key == ""
    assert cfg.cluster == "volc.bigasr.sauc.duration"


def test_is_configured_false_when_empty():
    assert doubao_asr.is_configured(doubao_asr.DoubaoConfig()) is False
    assert doubao_asr.is_configured(None) is False


def test_is_configured_true_when_set():
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    assert doubao_asr.is_configured(cfg) is True


# ── Cost estimation ──────────────────────────────────────────────────────────

def test_is_utterance_continuation_empty_current():
    assert doubao_asr._is_utterance_continuation("", "hello") is True


def test_is_utterance_continuation_cumulative():
    assert doubao_asr._is_utterance_continuation("OK", "OK，测试") is True


def test_is_utterance_continuation_correction_shorter():
    assert doubao_asr._is_utterance_continuation("OK，测试一下", "OK，测试") is True


def test_is_utterance_continuation_new_sentence():
    assert doubao_asr._is_utterance_continuation("好的，功能上线了。", "鉴别我们的") is False


def test_estimate_cost():
    cost = doubao_asr.estimate_cost(60.0)
    assert abs(cost - 1.98) < 0.01


# ── ASR client ───────────────────────────────────────────────────────────────

def test_client_start_fails_without_credentials():
    asr = doubao_asr.DoubaoStreamingASR(doubao_asr.DoubaoConfig())
    errors = []
    asr.on_error = lambda e: errors.append(e)
    assert asr.start() is False
    assert len(errors) == 1


def test_client_start_returns_false_on_websocket_import_error():
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    errors = []
    asr.on_error = lambda e: errors.append(e)

    def fake_run_loop():
        asr._connect_failed.set()
        asr._finished.set()

    asr._run_loop = fake_run_loop
    result = asr.start()
    assert result is False
    assert len(errors) >= 1


def test_client_start_returns_false_on_connection_refused():
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    errors = []
    asr.on_error = lambda e: errors.append(e)

    mock_ws = unittest.mock.MagicMock()
    mock_ws.connect.side_effect = ConnectionRefusedError("refused")

    with unittest.mock.patch("websocket.WebSocket", return_value=mock_ws):
        result = asr.start()

    assert result is False
    assert len(errors) >= 1


def test_client_handles_v3_partial_and_final():
    """v3 partial and final responses are correctly parsed."""
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    partials = []
    finals = []
    asr.on_partial = lambda t: partials.append(t)
    asr.on_final = lambda t: finals.append(t)

    # Build v3 partial response
    partial_payload = {"type": "partial", "result": [{"text": "hel"}], "header": {"status": 20000000}}
    partial_bytes = json.dumps(partial_payload).encode()
    partial_header = doubao_asr._build_header(
        doubao_asr.MSG_TYPE_FULL_SERVER_RESPONSE,
        flags=doubao_asr.NO_SEQUENCE,
        compression=doubao_asr.COMPRESSION_NONE,
    )
    partial_msg = partial_header + struct.pack(">I", 0) + struct.pack(">I", len(partial_bytes)) + partial_bytes

    # Build v3 final response
    final_payload = {"type": "final", "result": [{"text": "hello"}], "header": {"status": 20000000}}
    final_bytes = json.dumps(final_payload).encode()
    final_header = doubao_asr._build_header(
        doubao_asr.MSG_TYPE_FULL_SERVER_RESPONSE,
        flags=doubao_asr.NO_SEQUENCE,
        compression=doubao_asr.COMPRESSION_NONE,
    )
    final_msg = final_header + struct.pack(">I", 0) + struct.pack(">I", len(final_bytes)) + final_bytes

    _timeout = _websocket_mod.WebSocketTimeoutException
    mock_ws = unittest.mock.MagicMock()
    mock_ws.recv.side_effect = [_timeout(), partial_msg, _timeout(), final_msg, Exception("closed")]

    with unittest.mock.patch("websocket.WebSocket", return_value=mock_ws):
        asr.start()

    asr.stop(timeout_s=2.0)
    assert partials == ["hel"]
    assert finals == ["hello"]
    assert asr._final_text == "hello"


def _v3_resp(text, flags):
    """Build a v3 bigmodel server response (no 'type' field, dict result)."""
    payload = {
        "audio_info": {"duration": 3000},
        "result": {"additions": {"log_id": "x"}, "text": text},
    }
    pb = json.dumps(payload, ensure_ascii=False).encode()
    header = doubao_asr._build_header(
        doubao_asr.MSG_TYPE_FULL_SERVER_RESPONSE,
        flags=flags,
        compression=doubao_asr.COMPRESSION_NONE,
    )
    return header + struct.pack(">I", 0) + struct.pack(">I", len(pb)) + pb


def test_client_handles_v3_bigmodel_no_type_field():
    """Single utterance with cumulative partials returns one complete final."""
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    partials = []
    finals = []
    asr.on_partial = lambda t: partials.append(t)
    asr.on_final = lambda t: finals.append(t)

    p1 = _v3_resp("OK", doubao_asr.POS_SEQUENCE)
    p2 = _v3_resp("OK，我测试一下", doubao_asr.POS_SEQUENCE)
    fin = _v3_resp("OK，我测试一下有没有东西呀？",
                   doubao_asr.POS_SEQUENCE | doubao_asr.NEG_SEQUENCE)

    _timeout = _websocket_mod.WebSocketTimeoutException
    mock_ws = unittest.mock.MagicMock()
    mock_ws.recv.side_effect = [_timeout(), p1, _timeout(), p2, fin, Exception("closed")]

    with unittest.mock.patch("websocket.WebSocket", return_value=mock_ws):
        asr.start()

    final_text = asr.stop(timeout_s=2.0)
    assert partials == ["OK", "OK，我测试一下"]
    assert finals == ["OK，我测试一下有没有东西呀？"]
    assert final_text == "OK，我测试一下有没有东西呀？"


def test_multi_utterance_accumulates_all_sentences():
    """Multiple utterances (text resets at each boundary, all POS_SEQUENCE until
    stream end NEG_SEQUENCE) must be joined so stop() returns the full transcript."""
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    partials = []
    finals = []
    asr.on_partial = lambda t: partials.append(t)
    asr.on_final = lambda t: finals.append(t)

    # Utterance 1: cumulative partials
    u1_p1 = _v3_resp("好的", doubao_asr.POS_SEQUENCE)
    u1_p2 = _v3_resp("好的，我们这个新的功能已经上线了。", doubao_asr.POS_SEQUENCE)
    # Utterance 2: text resets (new sentence, still POS_SEQUENCE)
    u2_p1 = _v3_resp("鉴别我们的", doubao_asr.POS_SEQUENCE)
    u2_p2 = _v3_resp("鉴别我们的这个讲话的字。", doubao_asr.POS_SEQUENCE)
    # Utterance 3: text resets again, then stream ends with NEG_SEQUENCE
    u3_fin = _v3_resp("但他有一个免费的使用。",
                      doubao_asr.POS_SEQUENCE | doubao_asr.NEG_SEQUENCE)

    _timeout = _websocket_mod.WebSocketTimeoutException
    mock_ws = unittest.mock.MagicMock()
    mock_ws.recv.side_effect = [
        u1_p1, u1_p2,
        _timeout(),
        u2_p1, u2_p2,
        u3_fin,
        Exception("closed"),
    ]

    with unittest.mock.patch("websocket.WebSocket", return_value=mock_ws):
        asr.start()

    final_text = asr.stop(timeout_s=2.0)

    assert partials == ["好的", "好的，我们这个新的功能已经上线了。",
                        "鉴别我们的", "鉴别我们的这个讲话的字。"]
    expected = "好的，我们这个新的功能已经上线了。\n鉴别我们的这个讲话的字。\n但他有一个免费的使用。"
    assert final_text == expected
    assert finals[-1] == expected


def test_multi_utterance_partial_callback_shows_current_sentence_only():
    """on_partial receives only the current sentence, not the joined full transcript."""
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    partials = []
    asr.on_partial = lambda t: partials.append(t)
    asr.on_final = lambda _: None

    u1_p1 = _v3_resp("第一句话。", doubao_asr.POS_SEQUENCE)
    # Text resets → new utterance
    u2_partial = _v3_resp("第二句", doubao_asr.POS_SEQUENCE)
    u2_fin = _v3_resp("第二句话。",
                      doubao_asr.POS_SEQUENCE | doubao_asr.NEG_SEQUENCE)

    mock_ws = unittest.mock.MagicMock()
    mock_ws.recv.side_effect = [u1_p1, u2_partial, u2_fin, Exception("closed")]

    with unittest.mock.patch("websocket.WebSocket", return_value=mock_ws):
        asr.start()

    asr.stop(timeout_s=2.0)
    assert partials == ["第一句话。", "第二句"]


def test_stop_returns_all_finalized_utterances():
    """stop() must return concatenated text from all utterance finals."""
    asr = doubao_asr.DoubaoStreamingASR(doubao_asr.DoubaoConfig())
    asr._utterances = ["句子一。", "句子二。"]
    asr._final_text = "句子一。\n句子二。"
    asr._finished.set()
    assert asr.stop() == "句子一。\n句子二。"


def test_client_handles_server_error():
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    errors = []
    asr.on_error = lambda e: errors.append(e)

    error_payload = {"reqid": "x", "message": "bad creds", "code": 400}
    error_bytes = gzip.compress(json.dumps(error_payload).encode())
    error_header = doubao_asr._build_header(
        doubao_asr.MSG_TYPE_SERVER_ERROR,
        flags=doubao_asr.NO_SEQUENCE,
    )
    error_msg = error_header + struct.pack(">I", 0) + struct.pack(">I", len(error_bytes)) + error_bytes

    mock_ws = unittest.mock.MagicMock()
    mock_ws.recv.side_effect = [error_msg, Exception("closed")]

    with unittest.mock.patch("websocket.WebSocket", return_value=mock_ws):
        asr.start()

    asr.stop(timeout_s=2.0)
    assert len(errors) >= 1
    assert asr._final_text == ""


def test_feed_audio_coalesces_before_enqueue_without_socket_access():
    """feed_audio must coalesce tiny callback fragments and never touch the socket."""
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    asr._running = True
    fragment = b"\x00" * 28

    for _ in range(doubao_asr.CHUNK_BYTES // len(fragment)):
        asr.feed_audio(fragment)
    assert asr._audio_queue.qsize() == 0

    asr.feed_audio(fragment)
    assert asr._audio_queue.qsize() == 1
    assert len(asr._audio_queue.get_nowait()) == doubao_asr.CHUNK_BYTES


def test_finish_flushes_partial_audio_before_sentinel():
    """finish() must send buffered tail audio before the end sentinel."""
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    asr._running = True
    pcm = b"\x00" * 320

    asr.feed_audio(pcm)
    assert asr._audio_queue.qsize() == 0
    asr.finish()

    assert asr._audio_queue.get_nowait() == pcm
    assert asr._audio_queue.get_nowait() is None


def test_finish_enqueues_sentinel():
    """finish() must enqueue None sentinel, not send on the socket."""
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    asr._running = True
    asr.finish()
    assert asr._audio_queue.get_nowait() is None
