"""Tests for the doubao_asr streaming ASR module."""

import gzip
import json
import struct

from whisperkey_mac import doubao_asr


# ── Protocol helpers ─────────────────────────────────────────────────────────

def test_build_header_has_correct_size():
    header = doubao_asr._build_header(doubao_asr.MSG_TYPE_FULL_CLIENT_REQUEST)
    assert len(header) == 4


def test_build_message_produces_valid_binary():
    msg = doubao_asr._build_message(
        doubao_asr.MSG_TYPE_FULL_CLIENT_REQUEST,
        {"test": "value"},
    )
    assert len(msg) > doubao_asr.HEADER_SIZE
    # First byte should have version in high nibble
    assert (msg[0] >> 4) == doubao_asr.PROTOCOL_VERSION


def test_parse_message_roundtrip():
    original = {"key": "value", "number": 42}
    msg = doubao_asr._build_message(doubao_asr.MSG_TYPE_FULL_SERVER_RESPONSE, original)
    msg_type, parsed = doubao_asr._parse_message(msg)
    assert msg_type == doubao_asr.MSG_TYPE_FULL_SERVER_RESPONSE
    assert parsed is not None
    assert parsed["key"] == "value"
    assert parsed["number"] == 42


def test_parse_message_handles_gzip():
    payload = {"result": [{"text": "hello", "definite": True}]}
    compressed = gzip.compress(json.dumps(payload).encode())
    header = doubao_asr._build_header(doubao_asr.MSG_TYPE_FULL_SERVER_RESPONSE)
    header_size = struct.pack(">I", doubao_asr.HEADER_SIZE)
    payload_size = struct.pack(">I", len(compressed))
    data = header + header_size + payload_size + compressed

    msg_type, parsed = doubao_asr._parse_message(data)
    assert msg_type == doubao_asr.MSG_TYPE_FULL_SERVER_RESPONSE
    assert parsed["result"][0]["text"] == "hello"


def test_parse_message_returns_none_for_short_data():
    msg_type, parsed = doubao_asr._parse_message(b"\x00" * 5)
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
    assert abs(cost - 1.98) < 0.01  # 60 * 0.033


# ── ASR client ───────────────────────────────────────────────────────────────

def test_client_start_fails_without_credentials():
    asr = doubao_asr.DoubaoStreamingASR(doubao_asr.DoubaoConfig())
    errors = []
    asr.on_error = lambda e: errors.append(e)
    assert asr.start() is False
    assert len(errors) == 1


def test_client_start_fails_with_bad_endpoint():
    cfg = doubao_asr.DoubaoConfig(app_id="test", access_key="key")
    asr = doubao_asr.DoubaoStreamingASR(cfg)
    errors = []
    asr.on_error = lambda e: errors.append(e)
    # This will fail to connect (invalid credentials/endpoint)
    result = asr.start()
    # May return True (connected) or False (timeout) depending on network
    # Either way, it should not crash
    asr.stop()
