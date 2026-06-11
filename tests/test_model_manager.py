"""Tests for the model_manager module."""

import time
import unittest.mock
from pathlib import Path

from whisperkey_mac import model_manager


# ── Network check ───────────────────────────────────────────────────────────

def test_check_network_true_on_success():
    with unittest.mock.patch("whisperkey_mac.model_manager.urllib.request.urlopen") as mock:
        mock.return_value.__enter__ = lambda s: s
        mock.return_value.__exit__ = lambda *a: None
        assert model_manager.check_network() is True


def test_check_network_false_on_failure():
    with unittest.mock.patch(
        "whisperkey_mac.model_manager.urllib.request.urlopen",
        side_effect=OSError("offline"),
    ):
        assert model_manager.check_network() is False


# ── Local cache queries ─────────────────────────────────────────────────────

def test_model_local_path_returns_none_when_not_cached(tmp_path: Path):
    with unittest.mock.patch.object(model_manager, "HUB_CACHE", tmp_path):
        assert model_manager.model_local_path("small") is None


def test_model_local_path_returns_path_when_cached(tmp_path: Path):
    repo_dir = tmp_path / "models--Systran--faster-whisper-small" / "snapshots"
    snapshot = repo_dir / "abc123"
    snapshot.mkdir(parents=True)
    with unittest.mock.patch.object(model_manager, "HUB_CACHE", tmp_path):
        result = model_manager.model_local_path("small")
    assert result == str(snapshot)


def test_is_model_cached_false(tmp_path: Path):
    with unittest.mock.patch.object(model_manager, "HUB_CACHE", tmp_path):
        assert model_manager.is_model_cached("small") is False


def test_is_model_cached_true(tmp_path: Path):
    repo_dir = tmp_path / "models--Systran--faster-whisper-base" / "snapshots"
    (repo_dir / "snap1").mkdir(parents=True)
    with unittest.mock.patch.object(model_manager, "HUB_CACHE", tmp_path):
        assert model_manager.is_model_cached("base") is True


def test_cached_model_sizes(tmp_path: Path):
    # Cache only "small"
    repo_dir = tmp_path / "models--Systran--faster-whisper-small" / "snapshots"
    (repo_dir / "snap1").mkdir(parents=True)
    with unittest.mock.patch.object(model_manager, "HUB_CACHE", tmp_path):
        result = model_manager.cached_model_sizes()
    assert result == ["small"]


# ── Download state ───────────────────────────────────────────────────────────

def test_get_current_download_none_by_default():
    with unittest.mock.patch.object(model_manager, "_current_download", None):
        assert model_manager.get_current_download() is None


def test_download_model_returns_cached_path_if_already_cached(tmp_path: Path):
    repo_dir = tmp_path / "models--Systran--faster-whisper-small" / "snapshots"
    snap = repo_dir / "abc123"
    snap.mkdir(parents=True)
    with unittest.mock.patch.object(model_manager, "HUB_CACHE", tmp_path):
        result = model_manager.download_model("small")
    assert result == str(snap)


def test_download_model_returns_none_for_unknown_model():
    assert model_manager.download_model("nonexistent") is None


# ── ETA estimation ───────────────────────────────────────────────────────────

def test_estimate_eta_returns_none_on_insufficient_data():
    assert model_manager.estimate_eta(0, 100, 5.0) is None
    assert model_manager.estimate_eta(50, 100, 0.5) is None


def test_estimate_eta_returns_seconds():
    result = model_manager.estimate_eta(50, 100, 2.0)
    assert result is not None
    assert "s" in result


def test_estimate_eta_returns_minutes():
    # 100 bytes done in 2s = 50 B/s, 900 remaining = 18s
    result = model_manager.estimate_eta(100, 1000, 2.0)
    assert result is not None
    assert "s" in result


# ── Format bytes ─────────────────────────────────────────────────────────────

def test_format_bytes():
    assert model_manager.format_bytes(500) == "500 B"
    assert model_manager.format_bytes(1024) == "1 KB"
    assert model_manager.format_bytes(1024 * 1024) == "1 MB"
    assert "GB" in model_manager.format_bytes(1024 * 1024 * 1024)


# ── Model catalog ────────────────────────────────────────────────────────────

def test_model_catalog_has_expected_models():
    assert "tiny" in model_manager.MODEL_CATALOG
    assert "base" in model_manager.MODEL_CATALOG
    assert "small" in model_manager.MODEL_CATALOG
    assert "large-v3-turbo" in model_manager.MODEL_CATALOG


def test_model_order_matches_catalog():
    assert set(model_manager.MODEL_ORDER) == set(model_manager.MODEL_CATALOG.keys())
