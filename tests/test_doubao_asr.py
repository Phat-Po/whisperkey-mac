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
    """v3 bigmodel: result_type "single" + force_to_speech_time keep recognition
    working; show_utterances is True so the server returns result.utterances[]
    (definite + start/end times) used to dedup the engine's re-recognition
    passes. C-1 capture verified text still emits with show_utterances on."""
    asr = doubao_asr.DoubaoStreamingASR(doubao_asr.DoubaoConfig(
        app_id="test", access_key="key", cluster="test-cluster",
    ))
    payload = json.loads(asr._build_connect_message()[8:])
    req = payload["request"]

    assert req["result_type"] == "single"
    assert req["show_utterances"] is True
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


def _v3_resp_utt(text, utterances, flags):
    """Build a v3 bigmodel response carrying a result.utterances[] array.

    utterances: list of (text, definite, start_time, end_time) tuples.
    """
    payload = {
        "audio_info": {"duration": 3000},
        "result": {
            "additions": {"log_id": "x"},
            "text": text,
            "utterances": [
                {"text": ut, "definite": d, "start_time": s, "end_time": e}
                for (ut, d, s, e) in utterances
            ],
        },
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
    """Distinct sentences (non-overlapping time spans) are all kept and joined in
    time order — no sentence dropped (regression for the truncation bug)."""
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    finals = []
    asr.on_final = lambda t: finals.append(t)

    s1 = _v3_resp_utt("好的，我们这个新的功能已经上线了。",
                      [("好的，我们这个新的功能已经上线了。", True, 0, 3000)],
                      doubao_asr.POS_SEQUENCE)
    s2 = _v3_resp_utt("鉴别我们的这个讲话的字。",
                      [("鉴别我们的这个讲话的字。", True, 3000, 6000)],
                      doubao_asr.POS_SEQUENCE)
    s3 = _v3_resp_utt("但他有一个免费的使用。",
                      [("但他有一个免费的使用。", True, 6000, 9000)],
                      doubao_asr.POS_SEQUENCE | doubao_asr.NEG_SEQUENCE)

    _timeout = _websocket_mod.WebSocketTimeoutException
    mock_ws = unittest.mock.MagicMock()
    mock_ws.recv.side_effect = [s1, _timeout(), s2, s3, Exception("closed")]

    with unittest.mock.patch("websocket.WebSocket", return_value=mock_ws):
        asr.start()

    final_text = asr.stop(timeout_s=2.0)
    expected = "好的，我们这个新的功能已经上线了。鉴别我们的这个讲话的字。但他有一个免费的使用。"
    assert final_text == expected
    assert finals[-1] == expected
    assert "\n" not in final_text


def test_re_recognition_overlapping_spans_dedup():
    """The engine re-recognizes the stream (an early rough pass, then a refined
    pass with shifted-but-overlapping timestamps). Overlapping spans must REPLACE,
    not append — regression for the Doubao filler-removal duplicated-output bug.
    Sequence and expected text are from a real captured recording."""
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    finals = []
    asr.on_final = lambda t: finals.append(t)

    rough_s1 = _v3_resp_utt(
        "我就说是，肯定是因为这个原因，不然人家为什么要删掉？",
        [("我就说是，肯定是因为这个原因，不然人家为什么要删掉？", True, 2362, 9722)],
        doubao_asr.POS_SEQUENCE)
    rough_s2 = _v3_resp_utt(
        "但他这个样子行为也很奇怪，好像是受了很多的侮辱。",
        [("但他这个样子行为也很奇怪，好像是受了很多的侮辱。", True, 10762, 16902)],
        doubao_asr.POS_SEQUENCE)
    refined_s1 = _v3_resp_utt(
        "我就说是，肯定是因为这个原因，不然人家好端端干嘛要删掉？",
        [("我就说是，肯定是因为这个原因，不然人家好端端干嘛要删掉？", True, 862, 7422)],
        doubao_asr.POS_SEQUENCE)
    refined_s2 = _v3_resp_utt(
        "但他这个行为也很奇怪，感觉好像是受了什么侮辱一样。",
        [("但他这个行为也很奇怪，感觉好像是受了什么侮辱一样。", True, 8542, 13412)],
        doubao_asr.POS_SEQUENCE | doubao_asr.NEG_SEQUENCE)

    _timeout = _websocket_mod.WebSocketTimeoutException
    mock_ws = unittest.mock.MagicMock()
    mock_ws.recv.side_effect = [
        rough_s1, rough_s2, _timeout(),
        refined_s1, refined_s2, Exception("closed"),
    ]

    with unittest.mock.patch("websocket.WebSocket", return_value=mock_ws):
        asr.start()

    final_text = asr.stop(timeout_s=2.0)
    expected = ("我就说是，肯定是因为这个原因，不然人家好端端干嘛要删掉？"
                "但他这个行为也很奇怪，感觉好像是受了什么侮辱一样。")
    assert final_text == expected
    assert finals[-1] == expected
    assert "\n" not in final_text
    assert final_text.count("但他") == 1      # S2 not duplicated
    assert "为什么要删掉" not in final_text   # rough S1 superseded by refined
    assert "很多的侮辱" not in final_text     # rough S2 superseded by refined


def test_partial_callback_shows_live_sentence():
    """on_partial receives the engine's live result.text (current sentence)."""
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    partials = []
    asr.on_partial = lambda t: partials.append(t)
    asr.on_final = lambda _: None

    p1 = _v3_resp_utt("第一句话。", [("第一句话。", True, 0, 2000)],
                      doubao_asr.POS_SEQUENCE)
    p2 = _v3_resp_utt("第二句", [("第二句", False, 2000, 3000)],
                      doubao_asr.POS_SEQUENCE)
    fin = _v3_resp_utt("第二句话。", [("第二句话。", True, 2000, 4000)],
                       doubao_asr.POS_SEQUENCE | doubao_asr.NEG_SEQUENCE)

    mock_ws = unittest.mock.MagicMock()
    mock_ws.recv.side_effect = [p1, p2, fin, Exception("closed")]

    with unittest.mock.patch("websocket.WebSocket", return_value=mock_ws):
        asr.start()

    asr.stop(timeout_s=2.0)
    assert partials == ["第一句话。", "第二句"]


def test_stop_returns_final_text():
    """stop() returns the assembled _final_text once finished."""
    asr = doubao_asr.DoubaoStreamingASR(doubao_asr.DoubaoConfig())
    asr._final_text = "句子一。句子二。"
    asr._finished.set()
    assert asr.stop() == "句子一。句子二。"


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
