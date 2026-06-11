"""Tests for the self-update module and stale-TCC auto-reset."""

import io
import json
import unittest.mock
from pathlib import Path

from whisperkey_mac import permissions, updater


# ── version comparison ────────────────────────────────────────────────────────

def test_is_newer_basic_semver():
    assert updater.is_newer("3.2.0", "3.1.0") is True
    assert updater.is_newer("3.1.0", "3.1.0") is False
    assert updater.is_newer("3.0.9", "3.1.0") is False


def test_is_newer_handles_v_prefix_and_partial_versions():
    assert updater.is_newer("v3.10.0", "3.9.1") is True
    assert updater.is_newer("4", "3.9.9") is True
    assert updater.is_newer("dev", "3.1.0") is False


# ── release fetching ──────────────────────────────────────────────────────────

def _fake_release_payload():
    return {
        "tag_name": "v3.2.0",
        "html_url": "https://github.com/Phat-Po/whisperkey-mac/releases/tag/v3.2.0",
        "body": "release notes",
        "assets": [
            {"name": "WhisperKey-macOS-arm64-v3.2.0.dmg", "browser_download_url": "https://x/d.dmg"},
            {"name": "WhisperKey-macOS-arm64-v3.2.0.zip", "browser_download_url": "https://x/d.zip"},
        ],
    }


def test_fetch_latest_release_parses_github_payload():
    payload = io.BytesIO(json.dumps(_fake_release_payload()).encode())
    cm = unittest.mock.MagicMock()
    cm.__enter__.return_value = payload
    with unittest.mock.patch("whisperkey_mac.updater.urllib.request.urlopen", return_value=cm):
        info = updater.fetch_latest_release()

    assert info is not None
    assert info.version == "3.2.0"
    assert info.zip_url == "https://x/d.zip"
    assert "3.2.0" in info.html_url


def test_fetch_latest_release_returns_none_on_network_error():
    with unittest.mock.patch(
        "whisperkey_mac.updater.urllib.request.urlopen", side_effect=OSError("offline")
    ):
        assert updater.fetch_latest_release() is None


def test_select_zip_asset_prefers_macos_arm64_zip():
    assets = _fake_release_payload()["assets"]
    assert updater.select_zip_asset(assets) == "https://x/d.zip"
    assert updater.select_zip_asset([{"name": "other.tar.gz", "browser_download_url": "u"}]) is None


# ── auto-check throttle ───────────────────────────────────────────────────────

def test_should_auto_check_true_without_record(tmp_path: Path):
    assert updater.should_auto_check(last_check_path=tmp_path / "missing.txt") is True


def test_should_auto_check_respects_interval(tmp_path: Path):
    record = tmp_path / "last.txt"
    updater.record_auto_check(now=1000.0, last_check_path=record)
    assert updater.should_auto_check(now=1000.0 + 3600, last_check_path=record) is False
    assert updater.should_auto_check(now=1000.0 + 25 * 3600, last_check_path=record) is True


# ── download guard ────────────────────────────────────────────────────────────

def test_download_and_install_refuses_without_zip_asset(tmp_path: Path):
    info = updater.UpdateInfo(version="9.9.9", zip_url=None, notes="", html_url="u")
    assert updater.download_and_install(info, str(tmp_path / "WhisperKey.app")) is False


# ── signature stamp / stale TCC auto-reset ───────────────────────────────────

def _codesign_result(stderr: str):
    return unittest.mock.Mock(returncode=0, stderr=stderr, stdout="")


def test_current_signature_stamp_detects_adhoc():
    with unittest.mock.patch(
        "whisperkey_mac.permissions.subprocess.run",
        return_value=_codesign_result("Signature=adhoc\n"),
    ):
        assert permissions.current_signature_stamp("/x.app") == "adhoc"


def test_current_signature_stamp_detects_team():
    stderr = "Authority=Apple Development: a@b.com (52Y4Y32YA8)\nTeamIdentifier=Z42TPKX875\n"
    with unittest.mock.patch(
        "whisperkey_mac.permissions.subprocess.run",
        return_value=_codesign_result(stderr),
    ):
        assert permissions.current_signature_stamp("/x.app") == "team:Z42TPKX875"


def test_auto_reset_runs_when_signature_changed_and_denied(tmp_path: Path):
    stamp = tmp_path / "stamp.txt"
    stamp.write_text("adhoc\n")
    with (
        unittest.mock.patch.object(permissions, "current_signature_stamp", return_value="team:X"),
        unittest.mock.patch.object(permissions, "required_granted", return_value=False),
        unittest.mock.patch.object(permissions, "reset_tcc_permissions", return_value=True) as mock_reset,
    ):
        assert permissions.auto_reset_stale_grants("/x.app", stamp_path=stamp) is True

    mock_reset.assert_called_once()
    assert stamp.read_text().strip() == "team:X"


def test_auto_reset_skips_when_signature_unchanged(tmp_path: Path):
    stamp = tmp_path / "stamp.txt"
    stamp.write_text("team:X\n")
    with (
        unittest.mock.patch.object(permissions, "current_signature_stamp", return_value="team:X"),
        unittest.mock.patch.object(permissions, "reset_tcc_permissions") as mock_reset,
    ):
        assert permissions.auto_reset_stale_grants("/x.app", stamp_path=stamp) is False

    mock_reset.assert_not_called()


def test_auto_reset_skips_reset_when_permissions_already_granted(tmp_path: Path):
    stamp = tmp_path / "stamp.txt"
    stamp.write_text("adhoc\n")
    with (
        unittest.mock.patch.object(permissions, "current_signature_stamp", return_value="team:X"),
        unittest.mock.patch.object(permissions, "required_granted", return_value=True),
        unittest.mock.patch.object(permissions, "reset_tcc_permissions") as mock_reset,
    ):
        assert permissions.auto_reset_stale_grants("/x.app", stamp_path=stamp) is False

    mock_reset.assert_not_called()
    assert stamp.read_text().strip() == "team:X"


def test_auto_reset_handles_first_run_without_stamp(tmp_path: Path):
    stamp = tmp_path / "stamp.txt"
    with (
        unittest.mock.patch.object(permissions, "current_signature_stamp", return_value="team:X"),
        unittest.mock.patch.object(permissions, "required_granted", return_value=False),
        unittest.mock.patch.object(permissions, "reset_tcc_permissions", return_value=True) as mock_reset,
    ):
        assert permissions.auto_reset_stale_grants("/x.app", stamp_path=stamp) is True

    mock_reset.assert_called_once()
